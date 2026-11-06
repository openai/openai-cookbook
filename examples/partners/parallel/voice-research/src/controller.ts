import { isDeepStrictEqual } from "node:util";
import type { PrepareUpdate } from "./live-updates.ts";
import type { Backend, Finding, FindingOutcome, Fragment, RecordEvent, ResearchRun, Task, Utterance, VoiceDelivery, VoiceSnapshot } from "./types.ts";

type TaskState = "researching" | "completed" | "cancelled" | "failed";
type State = {
  task_id: string; task: Task; revision: number; state: TaskState; run?: ResearchRun;
  // The latest Live delegation for this request; appends about it go back on this handoff.
  delegation_id: string; intentVersion: number;
  // The last spoken update submitted for this revision.
  conclusionVersion: number; findings: Finding[]; lastCommentarySummary?: string; lastCommentaryOutcome?: FindingOutcome; version: number;
};
type Update = { task_id: string; revision: number; finding?: Finding; error?: string };
type Delivery = {
  task_id?: string; receipt: VoiceDelivery; abort: AbortController; current: () => boolean; ready: () => boolean;
  send: (chunks: string[]) => void; chunks?: string[];
};
type Options = {
  backend: Backend; prepareUpdate: PrepareUpdate; send: (event: object) => void; publish: RecordEvent; record: RecordEvent; debounceMs?: number;
  // How long a delegation without new words waits for its transcript before it is interpreted anyway.
  transcriptWaitMs?: number;
};

// Owns user intent, task lifecycle and voice publication. Research protocol
// details stay inside each task's ResearchRun.
export class TaskController {
  options: Options; transcript: Fragment[] = []; tasks = new Map<string, State>(); closed = false;
  // Publication waits until the latest user speech has been interpreted.
  inputVersion = 0; interpretedVersion = -1; failures = 0;
  handledFragments = 0;
  seen = new Set<string>(); waiting = new Map<string, { offset: number; received: number }>();
  // A delegation answered with a clarifying question stays open for the next interpreted turn, so the
  // user's reply can start research on it without waiting for GPT-Live to delegate again. So does a
  // delegation interpreted before its words arrived.
  open: string[] = [];
  queue = new Map<string, Update>(); appends = new Map<string, { receipt: VoiceDelivery; expected: string }>();
  voiceUpdates = new Map<string, VoiceDelivery>();
  deliveries = new Set<Delivery>();
  timer: ReturnType<typeof setTimeout> | undefined; interpretation: AbortController | undefined;
  constructor(options: Options) { this.options = options; }

  // Returns true when the event acknowledged or rejected one of this controller's appends.
  receive(event: Record<string, any>) {
    const owned = this.acknowledge(event);
    if (this.closed) return owned;
    if (event.type === "session.input_transcript.delta" || event.type === "session.output_transcript.delta") {
      const user = event.type === "session.input_transcript.delta";
      const { delta, start_ms, end_ms } = event;
      this.transcript.push({ role: user ? "user" : "assistant", delta, start_ms, end_ms });
      if (user) {
        this.inputVersion++;
        // Corrections to finished tasks arrive as delegations, so idle speech costs no interpretation.
        if (this.waiting.size || this.open.length || this.researching() || this.deliveries.size) this.schedule(this.options.debounceMs ?? 700);
      }
    }
    if (event.type === "session.delegation.created" && event.delegation.target === "client") {
      const id = event.delegation.id;
      if (this.seen.has(id)) return owned;
      this.seen.add(id);
      this.waiting.set(id, { offset: event.offset_ms, received: Date.now() });
      this.options.record("delegation.received", { id, offset_ms: event.offset_ms });
      this.schedule();
    }
    return owned;
  }

  acknowledge(event: Record<string, any>) {
    const id = event.type === "error" ? event.error?.client_event_id ?? event.client_event_id : event.client_event_id;
    if (!id || !this.appends.has(id)) return false;
    const { receipt, expected } = this.appends.get(id)!;
    if (event.type !== "error" && event.type !== expected) return false;
    const type = event.type === "error" ? "append.rejected" : "append.acknowledged";
    const chunk = receipt.chunks.find(chunk => chunk.event_id === id)!;
    chunk.state = event.type === 'error' ? 'failed' : 'accepted';
    receipt.state = receipt.chunks.some(c => c.state === 'failed') ? 'failed' :
      receipt.chunks.every(c => c.state === 'accepted') ? 'accepted' : 'submitted';
    this.stamp(receipt);
    this.options.record(type, { task_id: receipt.task_id, revision: receipt.revision, event_id: id, during_close: this.closed });
    this.appends.delete(id);
    // Closing returns errors for appends still pending; record them, but do not show them as failures.
    if (event.type === "error" && !this.closed) {
      const message = "A voice update was rejected. See the research card; the update will not be replayed.";
      this.options.publish("error", { message });
    }
    return true;
  }

  voiceSnapshot(): VoiceSnapshot {
    return { version: 1, updates: structuredClone([...this.voiceUpdates.values()]) };
  }

  stamp(receipt: VoiceDelivery) {
    receipt.updated_at = Date.now();
  }

  // Joins fragments in the order they arrived. Timestamps are approximate, so they don't decide word order.
  utterances(fragments = this.transcript): Utterance[] {
    const turns: Utterance[] = [];
    for (const f of fragments) {
      const last = turns.at(-1);
      if (last?.role === f.role && f.start_ms - last.end_ms < 2000) { last.text += f.delta; last.end_ms = f.end_ms; }
      else turns.push({ role: f.role, text: f.delta, start_ms: f.start_ms, end_ms: f.end_ms });
    }
    return turns.map(turn => ({ ...turn, text: turn.text.trim() }));
  }

  researching() { return [...this.tasks.values()].some(t => t.state === "researching"); }

  schedule(delay = this.options.debounceMs ?? 250) {
    clearTimeout(this.timer);
    this.timer = setTimeout(() => void this.interpret(), delay);
  }

  async interpret() {
    if (this.closed) return;
    // Delegation offsets are approximate, so new words are used as soon as the debounce fires.
    // A delegation with no new words waits briefly for them.
    const userEnd = Math.max(0, ...this.transcript.filter(f => f.role === "user").map(f => f.end_ms));
    const hasFreshWords = this.transcript.slice(this.handledFragments).some(f => f.role === "user" && f.delta.trim());
    const missingTranscript = !hasFreshWords && this.waiting.size > 0 &&
      (!this.transcript.some(f => f.role === "user" && f.delta.trim()) ||
        [...this.waiting.values()].some(w => userEnd < w.offset - 600));
    // GPT-Live can delegate again for speech that was already interpreted, such as a correction applied
    // while research was running. Its words never arrive, and a pending delegation holds publication for
    // every task, so stop waiting after a bound and keep the delegation open in case its words are late.
    const transcriptWait = this.options.transcriptWaitMs ?? 2000;
    const waited = Math.min(...[...this.waiting.values()].map(w => Date.now() - w.received));
    if (missingTranscript && waited < transcriptWait) { this.schedule(transcriptWait - waited); return; }
    // `fresh` are new handoffs about this turn; `ids` adds an open clarification, which only a new
    // request or another question can use.
    const version = this.inputVersion, fresh = [...this.waiting.keys()], ids = [...this.open, ...fresh];
    this.interpretation?.abort();
    const abort = new AbortController(); this.interpretation = abort;
    const fragmentEnd = this.transcript.length;
    const tasks = [...this.tasks.values()]
      .map(({ task_id, task, revision, state }) => ({ task_id, task, revision, state }));
    try {
      const result = await this.options.backend.interpret({ transcript: this.utterances().slice(-40), unhandled: this.utterances(this.transcript.slice(this.handledFragments)), tasks }, abort.signal);
      // Aborted means a newer interpretation or close() superseded this one.
      if (this.closed || abort.signal.aborted || version !== this.inputVersion) return;
      this.failures = 0; this.interpretedVersion = version;
      // Speech may precede its delegation. A new request is not consumed until it can start.
      if (ids.length || !result.actions.some(a => a.relation === "new")) this.handledFragments = fragmentEnd;
      fresh.forEach(id => this.waiting.delete(id));
      this.open = result.actions.some(a => a.relation === "unclear") && ids.length ? [ids.at(-1)!] :
        missingTranscript ? fresh.slice(-1) : [];
      this.options.record("task.interpreted", { ...result, version, delegation_ids: ids });
      for (const a of result.actions) {
        if (this.closed) return;
        const targets = a.target_ids.map(id => this.tasks.get(id)!);
        if (a.relation === "unclear") {
          const id = ids.at(-1) ?? (targets.length === 1 ? targets[0]!.delegation_id : null);
          this.append("session.commentary.append", id, a.clarification!);
        } else if (a.relation === "unchanged" || a.relation === "cancel") {
          for (const t of targets) {
            if (fresh.length) t.delegation_id = fresh.at(-1)!;
            if (a.relation === "cancel" && (t.state === "researching" ||
                t.state === "completed" && [...this.deliveries].some(d => d.task_id === t.task_id))) this.cancel(t);
            // A delegation about a known task gets its grounded status in return.
            else if (fresh.length) this.append("session.thinking.append", t.delegation_id, notice(t), t);
          }
        } else if (a.relation === "new") {
          this.create(a.task!, version, ids);
        } else {
          this.revise(targets[0]!, a.task!, fresh);
        }
      }
      this.flush();
    } catch (error) {
      if (this.closed || abort.signal.aborted || version !== this.inputVersion) return;
      this.options.record("interpretation.failed", { message: String(error), attempt: this.failures + 1 });
      if (this.failures++ < 1) { this.schedule(); return; }
      // A failed interpretation leaves the speech unhandled and keeps results held.
      // The next speech or delegation tries again.
      this.failures = 0;
      this.options.publish("error", { message: "Could not interpret the latest request. Please clarify it." });
      // Even speech without a delegation may have corrected or cancelled current work.
      const retry = "I didn't catch that request. Could you say it again?";
      this.append("session.commentary.append", ids.at(-1) ?? null, retry);
    }
  }

  create(task: Task, version: number, ids: string[]) {
    // A late duplicate delegation joins the existing task instead of starting another.
    const identity = taskIdentity(task);
    const same = [...this.tasks.values()].find(t => t.intentVersion === version && taskIdentity(t.task) === identity);
    if (same) { same.delegation_id = ids.at(-1) ?? same.delegation_id; return; }
    if (!ids.length) return;
    const t: State = {
      task_id: crypto.randomUUID(), task, revision: 1, state: "researching", delegation_id: ids.at(-1)!,
      intentVersion: version, conclusionVersion: 0, findings: [], version: 0,
    };
    this.tasks.set(t.task_id, t); this.snapshot(t); this.start(t);
  }

  revise(t: State, task: Task, ids: string[]) {
    if (ids.length) t.delegation_id = ids.at(-1)!;
    if (taskIdentity(t.task) === taskIdentity(task)) return;
    const hadSpoken = t.lastCommentarySummary !== undefined;
    const oldRequest = t.task.request;
    Object.assign(t, { task, revision: t.revision + 1, state: "researching", findings: [], lastCommentarySummary: undefined, lastCommentaryOutcome: undefined });
    this.discardObsoleteDeliveries();
    if (hadSpoken) this.append("session.thinking.append", t.delegation_id,
      `The user corrected this request: ${fit(oldRequest, 240)}. Its earlier findings are superseded; wait for revised evidence.`, t);
    if (this.closed) return;
    this.snapshot(t);
    const running = t.run;
    if (!running) { this.start(t); return; }
    try { running.update(t.task, t.revision); } catch { running.cancel(); this.start(t); }
  }

  // run.cancel() is synchronous and flush() drops the task's late results, so the outcome is
  // confirmed before the voice is told.
  cancel(t: State) {
    if (t.state === "completed") {
      // Research can finish before its voice update is ready. Honor cancellation of that
      // unsent update without changing the completed evidence on the card.
      t.conclusionVersion++; this.discardObsoleteDeliveries();
      this.append("session.commentary.append", t.delegation_id,
        `Research on "${fit(t.task.request, 160)}" has already finished. Any unsent voice update has been stopped.`, t, undefined, undefined, { purpose: "cancellation" });
      return;
    }
    t.run?.cancel(); t.run = undefined; t.state = "cancelled"; this.discardObsoleteDeliveries(); this.snapshot(t);
    this.append("session.commentary.append", t.delegation_id,
      `Cancelled the research on "${fit(t.task.request, 160)}". No results from it will follow.`, t, undefined, undefined, { purpose: "cancellation" });
  }

  start(t: State) {
    this.options.record("task.started", { task_id: t.task_id, revision: t.revision, task: t.task });
    t.run = this.options.backend.research(t.task_id, t.task, t.revision,
      finding => {
        if (this.closed || t.state !== "researching" || finding.revision !== t.revision) return;
        const previous = this.queue.get(t.task_id);
        // An identical partial is still the same candidate. Keep its preparation alive.
        if (isDeepStrictEqual(previous?.revision === t.revision ? previous.finding : t.findings.at(-1), finding)) return;
        t.conclusionVersion++; this.discardObsoleteDeliveries();
        this.queue.set(t.task_id, { task_id: t.task_id, revision: finding.revision, finding }); this.flush();
      },
      (revision, error) => {
        if (this.closed || t.revision !== revision || t.state !== "researching") return;
        t.conclusionVersion++; this.discardObsoleteDeliveries();
        t.run = undefined; this.queue.set(t.task_id, { task_id: t.task_id, revision, error: error.message }); this.flush();
      });
  }

  flush() {
    if (this.closed || this.inputVersion !== this.interpretedVersion || this.waiting.size) return;
    // Each finding replaces the previous conclusion for its task while publication is held.
    const ready = [...this.queue.values()];
    this.queue.clear();
    for (const update of ready) {
      const t = this.tasks.get(update.task_id);
      // A revision or cancel makes earlier queued updates stale; they are dropped here.
      if (!t || t.revision !== update.revision || t.state !== "researching") continue;
      const f = update.finding;
      if (!f) {
        t.state = "failed"; t.run = undefined;
        this.options.record("research.failed", { task_id: t.task_id, revision: t.revision, message: update.error });
        this.append("session.commentary.append", t.delegation_id,
          "I could not verify a final answer. Any earlier findings are provisional, not a confirmed recommendation. " +
          "Please retry or narrow the request.", t);
        this.snapshot(t); continue;
      }
      const prior = t.findings.at(-1);
      const repeat = prior?.spoken_summary === f.spoken_summary && prior.outcome === f.outcome;
      if (repeat) {
        // The current conclusion owns its exact citations and display fields. Never merge
        // evidence from a superseded answer just because the spoken wording matches.
        if (JSON.stringify(prior.sources) !== JSON.stringify(f.sources)) t.findings.push(f);
        else t.findings[t.findings.length - 1] = f;
        if (f.kind === "partial" && t.lastCommentarySummary === f.spoken_summary && t.lastCommentaryOutcome === f.outcome) {
          this.snapshot(t); continue;
        }
      } else t.findings.push(f);
      // Speak the first partial and a final that adds something; everything else is quiet context.
      // Either way GPT-Live learns whether research is still running.
      const outcomeChanged = t.lastCommentarySummary !== undefined && f.outcome !== t.lastCommentaryOutcome;
      const speak = outcomeChanged || (f.kind === "final" ? f.spoken_summary !== t.lastCommentarySummary : t.lastCommentarySummary === undefined);
      const withdrawal = outcomeChanged && f.outcome === "insufficient_evidence"
        ? "The earlier recommendation is withdrawn. " : "";
      const label = f.kind === "final" ? "Final result" : "Early result; research is still running";
      const type = speak ? "session.commentary.append" : "session.thinking.append";
      const content = `${label}: ${withdrawal}${f.spoken_summary}`;
      const parts = f.display_items?.map(item => `${label}: ${withdrawal}${[item.heading, item.detail].filter(Boolean).join(": ")}`);
      if (!this.append(type, t.delegation_id, content, t, () => {
        if (!speak) return;
        t.lastCommentarySummary = f.spoken_summary;
        t.lastCommentaryOutcome = f.outcome;
        this.options.record("answer.appended", { task_id: t.task_id, revision: t.revision, kind: f.kind,
          summary: f.spoken_summary, outcome: f.outcome });
      }, parts, { purpose: "finding", kind: f.kind })) return;
      if (f.kind === "final") { t.state = "completed"; t.run = undefined; }
      this.snapshot(t);
    }
    this.flushDeliveries();
  }

  snapshot(t: State) {
    const sources = new Map(t.findings.flatMap(f => f.sources.map(s => [s.url, s] as const)));
    const current = t.state === "failed" ? undefined : t.findings.at(-1);
    this.options.publish("task", {
      task_id: t.task_id, task: t.task, revision: t.revision, version: ++t.version, state: t.state, conclusion_version: t.conclusionVersion,
      summary: [...new Set(t.findings.map(f => f.spoken_summary))].join("\n\n"), sources: [...sources.values()],
      outcome: current?.outcome, display_title: current?.display_title, display_items: current?.display_items ?? [],
      current_summary: current?.spoken_summary ?? "", current_sources: current?.sources ?? [],
    });
  }

  // Returns whether the update was queued for preparation. A newer conclusion cancels it.
  append(type: string, delegation_id: string | null, content: string, t?: State, onSent?: () => void, parts?: string[], proof: { purpose: VoiceDelivery["purpose"]; kind?: "partial" | "final" } = { purpose: "context" }) {
    if (this.closed) return false;
    const revision = t?.revision, conclusion = t?.conclusionVersion, state = t?.state, input = this.inputVersion;
    const abort = new AbortController();
    const context = t ? { task_id: t.task_id, revision } : {};
    // Only findings may finish preparing after their completed snapshot. A running-status
    // notice must expire when the task completes, even if its conclusion version is unchanged.
    const receipt: VoiceDelivery = { id: crypto.randomUUID(), ...context, conclusion,
      ...proof, type, state: 'preparing', chunks: [], updated_at: Date.now() };
    this.voiceUpdates.set(receipt.id, receipt); this.stamp(receipt);
    const delivery: Delivery = {
      task_id: t?.task_id, receipt, abort,
      current: () => !this.closed && (t ? t.revision === revision && t.conclusionVersion === conclusion &&
        (t.state === state || onSent !== undefined && state === "researching" && t.state === "completed") : this.inputVersion === input),
      ready: () => !t || this.inputVersion === this.interpretedVersion && !this.waiting.size,
      send: chunks => {
        for (const chunk of chunks) {
          if (!delivery.current() || !delivery.ready()) {
            receipt.state = receipt.chunks.length ? 'failed' : 'superseded'; this.stamp(receipt); return;
          }
          const event = { type, event_id: crypto.randomUUID(), delegation_id, content: chunk };
          try { this.options.send(event); } catch {
            receipt.state = 'failed'; this.stamp(receipt);
            this.close(); this.options.record("transport.failed", { type }); return;
          }
          receipt.state = 'submitted';
          receipt.chunks.push({ event_id: event.event_id, state: 'submitted' });
          this.appends.set(event.event_id, { receipt, expected: type + 'ed' });
          this.stamp(receipt);
          this.options.record("live.command", event);
        }
        onSent?.();
      },
    };
    this.deliveries.add(delivery);
    const prepared = (chunks: string[]) => {
      if (abort.signal.aborted) return;
      if (!chunks.length || chunks.some(chunk => !chunk.trim())) throw new Error("Empty prepared voice update.");
      delivery.chunks = chunks; this.flushDeliveries();
    };
    const failed = (error: unknown) => {
      this.deliveries.delete(delivery);
      if (!delivery.current() || abort.signal.aborted) {
        // Settle an obsolete update here, since it has left `deliveries` and nothing else will.
        if (receipt.state === "preparing") { receipt.state = "superseded"; this.stamp(receipt); }
        return;
      }
      receipt.state = "failed"; this.stamp(receipt);
      this.options.record("voice.preparation.failed", { ...context, message: String(error) });
      this.options.publish("error", { message: "The voice update could not be prepared. The current research result is still on its card." });
    };
    try {
      const result = this.options.prepareUpdate(content, abort.signal, context, parts);
      if (Array.isArray(result)) prepared(result);
      else void result.then(prepared).catch(failed);
    } catch (error) { failed(error); }
    return !this.closed;
  }

  discardObsoleteDeliveries() {
    for (const delivery of this.deliveries) if (!delivery.current()) {
      delivery.abort.abort(); this.deliveries.delete(delivery);
      delivery.receipt.state = "superseded"; this.stamp(delivery.receipt);
    }
  }

  flushDeliveries() {
    this.discardObsoleteDeliveries();
    for (const delivery of this.deliveries) if (delivery.chunks && delivery.ready()) {
      this.deliveries.delete(delivery); delivery.send(delivery.chunks);
    }
  }

  close() {
    if (this.closed) return;
    this.closed = true;
    for (const delivery of this.deliveries) {
      delivery.abort.abort(); delivery.receipt.state = "superseded"; this.stamp(delivery.receipt);
    }
    this.deliveries.clear();
    clearTimeout(this.timer); this.interpretation?.abort(); this.options.backend.close?.();
    for (const t of this.tasks.values()) {
      t.run?.cancel();
      if (t.state === "researching") { t.state = "cancelled"; this.snapshot(t); }
    }
  }
}

export function taskIdentity(task: Task) {
  return JSON.stringify([task.request.trim().toLowerCase(), task.location?.trim().toLowerCase() ?? null, task.date,
    [...task.constraints].map(c => c.trim().toLowerCase()).sort()]);
}

// Grounded state for a delegation about a known task. Only completed tasks return their result.
function notice(t: State) {
  const request = `Research on "${fit(t.task.request, 120)}"`;
  if (t.state === "researching") return `${request} is still running; its result will follow.`;
  if (t.state === "cancelled") return `${request} was cancelled. Do not mention its results.`;
  if (t.state === "failed") return `${request} could not be finished. Earlier findings are provisional, not a confirmed recommendation.`;
  // Keep the replay instruction alongside the complete result.
  const head = `${request} is complete. Repeat its result only if asked.`;
  const result = t.findings.at(-1)?.spoken_summary;
  if (!result) return head;
  const prefix = `${head} Current result: `;
  return prefix + result;
}

// Shortens text to a UTF-8 byte budget, ending at a sentence when one ends in the second half.
function fit(value: string, bytes: number) {
  if (Buffer.byteLength(value) <= bytes) return value;
  let result = "";
  for (const char of value) { if (Buffer.byteLength(result + char) > bytes) break; result += char; }
  const sentence = result.lastIndexOf(". ");
  return sentence > result.length / 2 ? result.slice(0, sentence + 1) : result;
}
