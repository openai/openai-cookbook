import type { VoiceSnapshot } from "../src/types.ts";
export type LogEvent = { type: string; data: Record<string, unknown>; at?: number; client_ms?: number };
export type TaskAnnotation = {
  task_id: string;
  revision: number;
  request_end_ms: number | null;
  first_useful_speech_ms: number | null;
  final_speech_ms: number | null;
  task_completion_pass: boolean | null;
  quality_pass: boolean | null;
  correction_pass: boolean | null;
  cancellation_pass: boolean | null;
  cancelled: boolean;
  notes: string;
};
// Per-task entries carry timing and grades. Run-level grades apply only to runs with no task, such as missing-city.
export type Annotation = {
  tasks?: TaskAnnotation[];
  task_completion_pass: boolean | null;
  quality_pass: boolean | null;
  correction_pass: boolean | null;
  notes: string;
};
export function taskLocation(task: Record<string, any> | undefined) {
  return task?.location ?? null;
}
export function taskIndoor(task: Record<string, any> | undefined) {
  return Array.isArray(task?.constraints) && task.constraints.some((c: unknown) => /indoor/i.test(String(c)));
}

type ResponseRate = {
  input_per_million: number;
  cached_input_per_million: number;
  cache_write_per_million?: number;
  output_per_million: number;
};
export type Rates = {
  checked_at: string | null;
  source_urls: string[];
  responses: Record<string, ResponseRate>;
  responses_fast?: Record<string, ResponseRate>;
  parallel_extract_per_url_usd?: number | null;
  parallel_search_per_call_usd: number | null;
  gpt_live_per_minute_usd?: number | null;
};
export type Trial = {
  expectations?: {
    correction?: boolean;
    correct_during_research?: boolean;
    task_count?: number;
    cancelled_count?: number;
    [key: string]: unknown;
  };
  scenario: string;
  status: "completed" | "failed";
  recording_file: string | null;
  recording_check?: { pass: boolean };
  errors: string[];
  client: { recordingStart: number | null; events: LogEvent[] };
  server: { closed: boolean; events: LogEvent[]; voice?: VoiceSnapshot } | null;
};

function object(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}
function nonnegative(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}
export function percentile(values: number[], fraction: number): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.max(0, Math.ceil(sorted.length * fraction) - 1)]!;
}

export function estimateCost(events: LogEvent[], rates: Rates) {
  const unknown = new Set<string>();
  const completed = new Map<string, LogEvent>();
  for (const event of events.filter(event => event.type === "responses.completed")) {
    if (typeof event.data.response_id === "string") completed.set(event.data.response_id, event);
    else unknown.add("A Responses completion has no response ID.");
  }
  let knownResponses = 0;
  for (const event of completed.values()) {
    const usage = object(event.data.usage);
    // Price the tier OpenAI actually reports, including downgrades. An unreported or unsupported
    // tier must not silently use Standard pricing.
    const tier = event.data.service_tier;
    const table =
      tier === "default"
        ? rates.responses
        : ["priority", "fast"].includes(String(tier))
          ? rates.responses_fast
          : undefined;
    const rate = table?.[String(event.data.model)];
    const cached = object(usage.input_tokens_details).cached_tokens;
    if (
      !rate ||
      !nonnegative(usage.input_tokens) ||
      !nonnegative(usage.output_tokens) ||
      !nonnegative(cached) ||
      cached > usage.input_tokens ||
      !Object.values(rate).every(nonnegative)
    ) {
      unknown.add("Some Responses usage or model rates are missing.");
      continue;
    }
    const writes = object(usage.input_tokens_details).cache_write_tokens ?? 0;
    if (
      !nonnegative(writes) ||
      cached + writes > usage.input_tokens ||
      (writes > 0 && !nonnegative(rate.cache_write_per_million))
    ) {
      unknown.add("Cache-write usage or rate is missing.");
      continue;
    }
    knownResponses +=
      ((usage.input_tokens - cached - writes) * rate.input_per_million +
        cached * rate.cached_input_per_million +
        writes * (rate.cache_write_per_million ?? 0) +
        usage.output_tokens * rate.output_per_million) /
      1_000_000;
  }
  // Every dispatch ends as a completion, a recorded failure (including cancellation in flight), or a
  // created response without terminal usage.
  const dispatches = events.filter(event => event.type === "responses.dispatched").length;
  if (events.some(event => event.type === "responses.failed") || dispatches > completed.size)
    unknown.add("Some dispatched Responses requests have unknown usage, including aborted work.");
  const created = new Set(
    events
      .filter(e => e.type === "research.event" && e.data.type === "response.created")
      .map(e => String(object(e.data.response).id)),
  );
  if ([...created].some(id => !completed.has(id)))
    unknown.add("Some created Responses, including automatic successors, lack terminal usage.");
  const searches = events.filter(event => event.type === "parallel.dispatched" && event.data.operation !== "extract");
  const extracts = events.filter(event => event.type === "parallel.dispatched" && event.data.operation === "extract");
  const callKey = (e: LogEvent) => `${e.data.task_id}:${e.data.call_id}`;
  const reported = new Map(events.filter(e => e.type === "parallel.completed").map(e => [callKey(e), e.data.usage]));
  function priceUnits(calls: LogEvent[], sku: string, rate: number | null | undefined) {
    if (!calls.length) return 0;
    if (!nonnegative(rate)) unknown.add(`Missing Parallel rate for ${sku}.`);
    let units: number | null = null;
    for (const call of calls) {
      const usage = reported.get(callKey(call));
      if (!Array.isArray(usage) || !usage.length || !usage.every(item =>
        item?.name === sku && Number.isInteger(item.count) && item.count >= 0)) {
        unknown.add("Some Parallel calls lack recognized provider-reported usage.");
        continue;
      }
      units = (units ?? 0) + usage.reduce((sum, item) => sum + item.count, 0);
    }
    return units !== null && nonnegative(rate) ? units * rate : null;
  }
  const extractEstimate = priceUnits(extracts, "sku_extract_excerpts", rates.parallel_extract_per_url_usd);
  const parallelEstimate = priceUnits(searches, "sku_search", rates.parallel_search_per_call_usd);
  const extractedUrls = extracts.reduce(
    (n, e) =>
      n + (Array.isArray(object(e.data.arguments).urls) ? (object(e.data.arguments).urls as unknown[]).length : 0),
    0,
  );
  const closed = events.filter(event => event.type === "live.event" && event.data.type === "session.closed").at(-1);
  const liveUsage = closed?.data.usage ?? null;
  if (!closed) unknown.add("GPT-Live session closure is unconfirmed, so final usage is unavailable.");
  else if (!liveUsage) unknown.add("GPT-Live session closure did not include final usage.");
  const seconds = object(liveUsage).seconds;
  const liveEstimate =
    closed && nonnegative(seconds) && nonnegative(rates.gpt_live_per_minute_usd)
      ? (seconds / 60) * rates.gpt_live_per_minute_usd
      : null;
  if (liveEstimate === null) unknown.add("GPT-Live seconds or applicable rate is unavailable.");
  const estimatedSubtotal = knownResponses + (extractEstimate ?? 0) + (parallelEstimate ?? 0) + (liveEstimate ?? 0);
  return {
    known_responses_usd: knownResponses,
    responses_completed: completed.size,
    responses_dispatched: dispatches,
    parallel_dispatched: searches.length + extracts.length,
    extraction_urls: extractedUrls,
    extraction_estimated_usd: extractEstimate,
    parallel_estimated_usd: parallelEstimate,
    gpt_live_usage: liveUsage,
    gpt_live_usd: liveEstimate,
    estimated_subtotal_usd: estimatedSubtotal,
    total_usd: unknown.size ? null : estimatedSubtotal,
    complete: unknown.size === 0,
    unknown_reasons: [...unknown],
  };
}

export function summarize(trials: { trial: Trial; annotation?: Annotation }[], rates: Rates) {
  const rate = (values: boolean[]) => (values.length ? values.filter(Boolean).length / values.length : null);
  const graded = (a?: Annotation) => (a?.tasks?.length ? a.tasks : a ? [a] : []);
  const booleans = (values: unknown[]) => values.filter((value): value is boolean => typeof value === "boolean");
  const byScenario = Object.fromEntries(
    [...new Set(trials.map(({ trial }) => trial.scenario))].map(scenario => {
      const group = trials.filter(({ trial }) => trial.scenario === scenario);
      const completion = booleans(
        group.flatMap(({ annotation }) => graded(annotation).map(a => a.task_completion_pass)),
      );
      const quality = booleans(group.flatMap(({ annotation }) => graded(annotation).map(a => a.quality_pass)));
      const corrections = booleans(
        group
          .filter(({ trial }) => trial.expectations?.correction ?? trial.scenario === "correction")
          .flatMap(({ annotation }) => graded(annotation).map(a => a.correction_pass)),
      );
      const taskTimes = group.flatMap(({ trial, annotation }) => taskMetrics(trial, annotation));
      const first = taskTimes.map(t => t.first_useful_latency_ms).filter((n): n is number => n !== null);
      const final = taskTimes.map(t => t.final_latency_ms).filter((n): n is number => n !== null);
      const cancellations = booleans(taskTimes.map(t => t.cancellation_pass));
      const paths = group.map(({ trial }) => structuralChecks(trial).correction_path);
      return [
        scenario,
        {
          task_first_useful_reviewed: first.length,
          task_first_useful_p50_ms: percentile(first, 0.5),
          task_first_useful_p90_ms: percentile(first, 0.9),
          task_final_reviewed: final.length,
          task_final_p50_ms: percentile(final, 0.5),
          task_final_p90_ms: percentile(final, 0.9),
          cancellations_reviewed: cancellations.length,
          cancellation_pass_rate: rate(cancellations),
          trials: group.length,
          completed: group.filter(({ trial }) => trial.status === "completed").length,
          task_completion_reviewed: completion.length,
          task_completion_pass_rate: rate(completion),
          quality_reviewed: quality.length,
          quality_pass_rate: rate(quality),
          corrections_reviewed: corrections.length,
          correction_pass_rate: rate(corrections),
          correction_paths: Object.fromEntries(
            correctionPaths.map(path => [path, paths.filter(p => p === path).length]),
          ),
        },
      ];
    }),
  );
  return {
    trials: trials.length,
    completed: trials.filter(({ trial }) => trial.status === "completed").length,
    by_scenario: byScenario,
    runs: trials.map(({ trial, annotation }) => ({
      scenario: trial.scenario,
      status: trial.status,
      // Runs with tasks are graded per task under `tasks`.
      ...(annotation?.tasks?.length
        ? {}
        : {
            task_completion: annotation?.task_completion_pass ?? "unreviewed",
            quality: annotation?.quality_pass ?? "unreviewed",
            correction: annotation?.correction_pass ?? "unreviewed",
          }),
      notes: annotation?.notes ?? "",
      tasks: taskMetrics(trial, annotation),
      structure: structuralChecks(trial),
      cost: estimateCost(trial.server?.events ?? [], rates),
    })),
  };
}

const correctionPaths = ["steer", "next_request", "restarted"] as const;
// How a correction reached a task's research. It either steered the response that was generating, went
// out with the next request because none was, or found the research already finished and started a new
// run. Only a correction inside a running research run logs `research.revision_applied`.
export function correctionPath(
  events: LogEvent[],
  task_id: string,
  revision: number,
): (typeof correctionPaths)[number] {
  const applied = events.find(
    e => e.type === "research.revision_applied" && e.data.task_id === task_id && e.data.revision === revision,
  );
  return applied ? (applied.data.via === "steer" ? "steer" : "next_request") : "restarted";
}

// Behavioral checks on the server log. Invariants the controller guarantees by construction are
// covered by the unit tests instead.
export function structuralChecks(trial: Trial) {
  const issues: string[] = [],
    tasks = new Map<string, Record<string, any>>(),
    calls = new Set<string>();
  const revisions = new Set<string>(),
    initial = new Map<string, Record<string, any>>();
  for (const e of trial.server?.events ?? []) {
    const d = e.data as Record<string, any>;
    if (
      ["ui.task", "parallel.dispatched", "answer.appended"].includes(e.type) &&
      (typeof d.task_id !== "string" || !Number.isInteger(d.revision))
    ) {
      issues.push("Missing task identity.");
      continue;
    }
    if (e.type === "ui.task") {
      const previous = tasks.get(d.task_id);
      if (previous && (d.revision < previous.revision || d.version <= previous.version))
        issues.push("An obsolete task snapshot was published.");
      if (previous && previous.revision === d.revision && ["cancelled", "completed", "failed"].includes(previous.state))
        issues.push("An update followed a terminal task state.");
      if (!initial.has(d.task_id)) initial.set(d.task_id, d);
      revisions.add(`${d.task_id}:${d.revision}`);
      tasks.set(d.task_id, d);
      if (d.state === "failed") issues.push("Research failed.");
    }
    if (e.type === "parallel.dispatched") {
      const key = `${d.task_id}:${d.call_id}`;
      if (!d.call_id || calls.has(key)) issues.push("Duplicate or missing tool call ID.");
      calls.add(key);
    }
    if (e.type === "voice.preparation.failed" || (e.type === "append.rejected" && !d.during_close))
      issues.push("A voice update was not delivered.");
    if (e.type === "answer.appended") {
      const t = tasks.get(d.task_id);
      const currentCompleted =
        t?.state === "completed" &&
        typeof d.summary === "string" &&
        d.summary === t.current_summary &&
        d.outcome === t.outcome;
      if (!t || t.revision !== d.revision || (t.state !== "researching" && !currentCompleted))
        issues.push("An obsolete answer was appended.");
    }
  }
  if (!trial.server?.closed) issues.push("Session closure was not confirmed.");
  if (!trial.recording_file) issues.push("Client audio recording is missing.");
  if (trial.expectations?.task_count !== undefined && tasks.size !== trial.expectations.task_count)
    issues.push("Expected task count was not reached.");
  if (
    trial.expectations?.cancelled_count !== undefined &&
    [...tasks.values()].filter(t => t.state === "cancelled").length !== trial.expectations.cancelled_count
  )
    issues.push("Expected cancellation count was not reached.");
  if ([...tasks.values()].some(t => !["completed", "cancelled"].includes(t.state)))
    issues.push("A required task did not finish.");
  const delivery = deliveryChecks(trial);
  issues.push(...delivery.issues);
  if (!delivery.ready && !delivery.issues.length) issues.push("Required voice delivery is still pending.");
  if (trial.recording_check?.pass !== true) issues.push("Audio capture was not verified.");
  const prior = new Map<string, string>();
  for (const e of trial.server?.events ?? [])
    if (e.type === "answer.appended") {
      const key = `${e.data.task_id}:${e.data.revision}`;
      const value = JSON.stringify([e.data.summary, e.data.outcome]);
      if (prior.get(key) === value) issues.push("Duplicate commentary finding.");
      prior.set(key, value);
    }
  if (trial.scenario === "missing-city" && calls.size) issues.push("Missing-city request dispatched research.");
  const eventTask = [...initial.values()].find(t => taskLocation(t.task));
  let correction_path: (typeof correctionPaths)[number] | null = null;
  if (trial.expectations?.correction ?? trial.scenario === "correction") {
    const latest = eventTask && tasks.get(eventTask.task_id);
    // The interpreter resolves a named weekday to its next occurrence, including today.
    const today = trial.server?.events.find(e => e.type === "session.created")?.data.today;
    const sunday = new Date(String(today) + "T00:00:00Z");
    sunday.setUTCDate(sunday.getUTCDate() + (7 - sunday.getUTCDay()) % 7);
    const expectedDate = Number.isFinite(sunday.getTime()) ? sunday.toISOString().slice(0, 10) : undefined;
    if (
      !latest ||
      latest.revision <= eventTask!.revision ||
      taskLocation(latest.task) !== taskLocation(eventTask!.task) ||
      !taskIndoor(latest.task) ||
      !expectedDate || latest.task.date !== expectedDate
    )
      issues.push("Event correction did not keep the location and apply the requested Sunday and indoor constraint.");
    if (
      eventTask &&
      [...tasks.values()].some(t => t.task_id !== eventTask.task_id && t.revision !== initial.get(t.task_id)!.revision)
    )
      issues.push("Correction changed an unrelated task.");
    if (latest && latest.revision > eventTask!.revision)
      correction_path = correctionPath(trial.server?.events ?? [], latest.task_id, latest.revision);
    if (trial.expectations?.correct_during_research && correction_path === "restarted")
      issues.push("The correction reached the event task after its research finished.");
  }
  if (
    (trial.expectations?.cancelled_count ?? 0) > 0 &&
    (!eventTask ||
      tasks.get(eventTask.task_id)?.state !== "cancelled" ||
      [...tasks.values()].some(t => t.task_id !== eventTask.task_id && t.state !== "completed"))
  )
    issues.push("Cancellation did not isolate the requested event task.");
  if (trial.scenario === "acknowledgment" && revisions.size !== 1) issues.push("Acknowledgment restarted research.");
  return {
    pass: !issues.length,
    issues,
    delivery_verified: delivery.ready,
    correction_path,
    researching_revisions: [...revisions],
  };
}
// Annotation timestamps are measured from the start of the saved recording.
export function taskMetrics(trial: Trial, annotation?: Annotation) {
  const elapsed = (a: TaskAnnotation, end: number | null) =>
    trial.recording_file &&
    trial.recording_check?.pass === true &&
    nonnegative(a.request_end_ms) &&
    nonnegative(end) &&
    end >= a.request_end_ms
      ? end - a.request_end_ms
      : null;
  return (annotation?.tasks ?? []).map(a => ({
    ...a,
    first_useful_latency_ms: elapsed(a, a.first_useful_speech_ms),
    final_latency_ms: a.cancelled ? null : elapsed(a, a.final_speech_ms),
  }));
}

// This gate verifies context delivery. The recording still needs a listening review.
export function deliveryChecks(trial: Pick<Trial, "server">) {
  const voice = trial.server?.voice;
  const issues: string[] = [];
  if (!voice || voice.version !== 1)
    return { ready: false, issues: ["Voice delivery proof is missing."], accepted_at: 0 };
  const latest = new Map<string, Record<string, any>>();
  for (const e of trial.server?.events ?? []) if (e.type === "ui.task") latest.set(String(e.data.task_id), e.data);
  let pending = false,
    accepted_at = 0;
  const ids = new Set<string>(),
    chunks = new Set<string>();
  for (const update of voice.updates) {
    if (ids.has(update.id)) issues.push("Duplicate logical voice delivery.");
    ids.add(update.id);
    if (update.state === "failed") issues.push("A required voice update failed.");
    if (["preparing", "submitted"].includes(update.state)) pending = true;
    if (update.state === "accepted") {
      if (!update.chunks.length || update.chunks.some(c => c.state !== "accepted"))
        issues.push("Voice acceptance is incomplete.");
      accepted_at = Math.max(accepted_at, update.updated_at);
    }
    for (const chunk of update.chunks) {
      if (chunks.has(chunk.event_id)) issues.push("Duplicate voice chunk ID.");
      chunks.add(chunk.event_id);
      if (chunk.state === "failed") issues.push("A required voice chunk was rejected.");
    }
  }
  for (const task of latest.values()) {
    if (task.state === "failed") issues.push("Research failed.");
    if (task.state === "researching") {
      pending = true;
      continue;
    }
    const matching = voice.updates.filter(u => u.task_id === task.task_id && u.revision === task.revision);
    const conclusion = Math.max(task.conclusion_version ?? 0, ...matching.map(u => u.conclusion ?? 0));
    const current = matching.filter(u => u.conclusion === conclusion);
    const required =
      task.state === "cancelled"
        ? current.filter(u => u.purpose === "cancellation")
        : current.filter(u => (u.purpose === "finding" && u.kind === "final") || u.purpose === "cancellation");
    if (!required.some(u => u.state === "accepted")) {
      if (required.some(u => ["preparing", "submitted"].includes(u.state))) pending = true;
      else issues.push("A terminal task has no accepted final update.");
    }
  }
  return { ready: !pending && !issues.length, issues, accepted_at };
}
