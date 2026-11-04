import { test } from "node:test";
import assert from "node:assert/strict";
import type { PrepareUpdate } from "../src/live-updates.ts";
import { TaskController } from "../src/controller.ts";
import type { Action, Backend, Finding, Interpretation, Task } from "../src/types.ts";

const task: Task = { request: "Find two events", location: "San Francisco", date: "2026-10-03", constraints: [] };
const other: Task = { request: "Compare tools", location: null, date: null, constraints: [] };
const pause = () => new Promise(r => setTimeout(r, 15));
const act = (
  relation: Action["relation"],
  target_ids: string[] = [],
  task: Task | null = null,
  clarification: string | null = null,
): Action => ({ relation, target_ids, task, clarification });
const sunday: Task = { ...task, date: "2026-10-04", constraints: ["indoors"] };
const label = /^(Final result|Early result; research is still running): /;

function setup(prepareUpdate: PrepareUpdate = content => [content], transcriptWaitMs?: number) {
  const resolve: ((v: Interpretation) => void)[] = [],
    jobs: any[] = [],
    sent: any[] = [],
    visible: any[] = [];
  const logs: any[] = [],
    interpretations: Parameters<Backend["interpret"]>[0][] = [];
  const backend: Backend = {
    interpret: input => {
      interpretations.push(input);
      return new Promise(r => resolve.push(r));
    },
    research: (id, task, rev, finding, error) => {
      const job = {
        id,
        task,
        rev,
        finding: (f: any) => finding({ outcome: "supported", ...f }),
        error,
        cancelled: false,
        corrections: [] as any[],
      };
      jobs.push(job);
      return {
        update: (task, rev) => {
          job.corrections.push({ task, rev });
          job.rev = rev;
        },
        cancel: () => {
          job.cancelled = true;
        },
      };
    },
  };
  const c = new TaskController({
    backend,
    prepareUpdate,
    debounceMs: 0,
    send: e => sent.push(e),
    publish: (type, data) => visible.push({ type, data }),
    record: (type, data) => logs.push({ type, data }),
    transcriptWaitMs,
  });
  const input = (delta: string) =>
    c.receive({ type: "session.input_transcript.delta", delta, start_ms: 0, end_ms: 1000 });
  const delegate = (id: string = crypto.randomUUID()) =>
    c.receive({ type: "session.delegation.created", offset_ms: 0, delegation: { id, target: "client" } });
  // Speaks, optionally delegates, then resolves the resulting interpretation.
  const action = async (actions: Action[], delegated = false) => {
    input("next");
    if (delegated) delegate();
    await pause();
    resolve.at(-1)!({ actions });
    await pause();
  };
  const start = (t = task) => action([act("new", [], t)], true);
  const answer = (index: number, text: string, kind: "partial" | "final" = "final", revision = jobs[index].rev) => {
    const url = `https://example.org/${text}`;
    const sources = [{ url, title: text, publish_date: null, excerpts: [text] }];
    jobs[index].finding({ revision, kind, spoken_summary: text, outcome: "supported", sources } satisfies Finding);
  };
  // Spoken text without the interim/final label.
  const spoken = () => sent.filter(e => e.type === "session.commentary.append").map(e => e.content.replace(label, ""));
  const quiet = () => sent.filter(e => e.type === "session.thinking.append").map(e => e.content);
  const card = (id: string) => visible.filter(e => e.type === "task" && e.data.task_id === id).at(-1)?.data;
  return {
    c,
    backend,
    resolve,
    jobs,
    sent,
    visible,
    logs,
    interpretations,
    input,
    delegate,
    action,
    start,
    answer,
    spoken,
    quiet,
    card,
  };
}

test("independent tasks finish separately; a revision changes only its target", async () => {
  const s = setup();
  try {
    await s.start();
    await s.start(other);
    assert.equal(s.jobs.length, 2);
    s.answer(1, "B");
    await s.action([act("revision", [s.jobs[0].id], sunday)]);
    assert.equal(s.jobs.length, 2, "a running task is steered, not restarted");
    assert.equal(s.jobs[0].corrections.length, 1);
    assert.equal(s.jobs[1].corrections.length, 0);
    s.answer(0, "old", "final", 1);
    s.answer(0, "A");
    assert.deepEqual(s.spoken(), ["B", "A"], "the stale revision-1 answer is never spoken");
    assert.equal(s.card(s.jobs[0].id).revision, 2);
    assert.equal(s.card(s.jobs[1].id).state, "completed");
  } finally {
    s.c.close();
  }
});

test("results carry an interim or final label so GPT-Live knows whether research is still running", async () => {
  const s = setup();
  try {
    await s.start();
    s.answer(0, "A", "partial");
    s.answer(0, "B", "partial");
    s.answer(0, "B", "partial");
    s.answer(0, "B");
    const appended = s.sent.map(e => [e.type.split(".")[1], e.content]);
    assert.deepEqual(
      appended,
      [
        ["commentary", "Early result; research is still running: A"],
        ["thinking", "Early result; research is still running: B"],
        ["commentary", "Final result: B"],
      ],
      "one spoken partial, later partials as quiet context, a repeated partial dropped, then the final",
    );
    assert.deepEqual(
      s.card(s.jobs[0].id).sources.map((v: any) => v.title),
      ["A", "B"],
    );
    const t = setup();
    await t.start();
    t.answer(0, "A", "partial");
    t.answer(0, "A");
    assert.deepEqual(t.spoken(), ["A"]);
    assert.deepEqual(t.quiet(), ["Final result: A"], "a final repeating the spoken partial completes quietly");
    assert.equal(t.card(t.jobs[0].id).state, "completed");
    t.c.close();
  } finally {
    s.c.close();
  }
});

test("targeted cancel: the other task continues and the outcome is confirmed aloud", async () => {
  const s = setup();
  try {
    await s.start();
    await s.start(other);
    await s.action([act("cancel", [s.jobs[0].id])]);
    assert(s.jobs[0].cancelled);
    assert(!s.jobs[1].cancelled);
    s.answer(0, "late");
    s.answer(1, "B");
    assert.deepEqual(s.spoken(), ['Cancelled the research on "Find two events". No results from it will follow.', "B"]);
    assert(!s.sent.some(e => e.type === "session.instructions.append"), "cancellation never interrupts speech");
    assert.equal(s.card(s.jobs[0].id).state, "cancelled");
  } finally {
    s.c.close();
  }
});

test("cancelling a finished task changes nothing and replies with its status", async () => {
  const s = setup();
  try {
    await s.start();
    s.answer(0, "A");
    const version = s.card(s.jobs[0].id).version,
      sent = s.sent.length;
    await s.action([act("cancel", [s.jobs[0].id])], true);
    assert.equal(s.card(s.jobs[0].id).state, "completed");
    assert.equal(s.card(s.jobs[0].id).version, version);
    assert.equal(s.sent.length, sent + 1);
    assert.match(s.quiet().at(-1)!, /is complete\. Repeat its result only if asked\. Current result: A/);
  } finally {
    s.c.close();
  }
});

test("a delegation about a known task gets its grounded status", async () => {
  const s = setup();
  try {
    await s.start();
    await s.start(other);
    s.answer(0, "Partial A", "partial");
    await s.action([act("cancel", [s.jobs[0].id])]);
    await s.action([act("unchanged", [s.jobs[0].id, s.jobs[1].id])], true);
    const [cancelled, running] = s.quiet().slice(-2);
    assert.match(cancelled!, /was cancelled/);
    assert.doesNotMatch(cancelled!, /Partial A/);
    assert.match(running!, /is still running/);
    s.input("Mm-hmm");
    await pause();
    s.resolve.at(-1)!({ actions: [act("unchanged", [s.jobs[1].id])] });
    await pause();
    assert.equal(s.quiet().length, 2, "speech alone gets no notice");
  } finally {
    s.c.close();
  }
});

test("card always updates: an unclear target still publishes its result", async () => {
  const s = setup();
  try {
    await s.start();
    await s.start(other);
    await s.action([act("unclear", [s.jobs[0].id, s.jobs[1].id], null, "Which request?")]);
    assert.equal(s.sent.at(-1).delegation_id, null, "a question across tasks is session-wide");
    s.answer(0, "A");
    s.answer(1, "B");
    assert.equal(s.card(s.jobs[0].id).state, "completed");
    assert.equal(s.card(s.jobs[0].id).summary, "A");
    assert.deepEqual(s.spoken(), ["Which request?", "A", "B"]);
  } finally {
    s.c.close();
  }
});

test("a clarified delegation stays open, so the reply starts research without another delegation", async () => {
  const s = setup();
  try {
    s.delegate("d1");
    s.input("Find events this Saturday");
    await pause();
    s.resolve.at(-1)!({ actions: [act("unclear", [], null, "Which city?")] });
    await pause();
    s.input("San Francisco");
    await pause();
    s.resolve.at(-1)!({ actions: [act("new", [], task)] });
    await pause();
    assert.equal(s.jobs.length, 1);
    s.answer(0, "A");
    assert.equal(s.sent.at(-1).delegation_id, "d1", "the result answers the original handoff");
    s.input("Thanks");
    await pause();
    assert.equal(s.interpretations.length, 2, "once resolved, idle speech is not interpreted");
  } finally {
    s.c.close();
  }
});

test("an open clarification lasts one turn and never reroutes other tasks", async () => {
  const s = setup();
  try {
    await s.start(other);
    const comparison = s.sent.length;
    s.delegate("d1");
    s.input("Find events this Saturday");
    await pause();
    s.resolve.at(-1)!({ actions: [act("unclear", [], null, "Which city?")] });
    await pause();
    s.input("How is the comparison going?");
    await pause();
    s.resolve.at(-1)!({ actions: [act("unchanged", [s.jobs[0].id])] });
    await pause();
    assert.equal(s.sent.length, comparison + 1, "speech alone sends no status notice");
    assert.deepEqual(s.c.open, [], "the clarification closes after one turn");
    s.answer(0, "B");
    assert.notEqual(s.sent.at(-1).delegation_id, "d1", "the comparison keeps its own handoff");
    s.input("Never mind");
    await pause();
    assert.equal(s.interpretations.length, 3, "nothing is researching, so idle speech is not interpreted");
  } finally {
    s.c.close();
  }
});

test("a completed task notice keeps its instruction when the request and result are long", async () => {
  const s = setup();
  try {
    await s.start({ ...other, request: "Compare ".repeat(20).trim() });
    s.answer(0, "Long result sentence. ".repeat(20).trim());
    await s.action([act("unchanged", [s.jobs[0].id])], true);
    const notice = s.quiet().at(-1)!;
    assert(notice.endsWith("Long result sentence. ".repeat(20).trim()));
    assert.match(notice, /Repeat its result only if asked\. Current result: Long/);
  } finally {
    s.c.close();
  }
});

test("failed interpretation retains correction intent and blocks stale results until recovery", async () => {
  const s = setup();
  try {
    await s.start();
    const original = s.backend.interpret;
    let calls = 0;
    s.backend.interpret = async () => {
      calls++;
      throw Error("offline");
    };
    s.input("Actually Sunday indoors");
    await pause();
    s.answer(0, "obsolete Saturday");
    await pause();
    assert.equal(calls, 2);
    assert(!s.spoken().includes("obsolete Saturday"));
    assert(s.spoken().some(t => /say it again/.test(t)));
    s.backend.interpret = original;
    await s.action([act("revision", [s.jobs[0].id], sunday)]);
    s.answer(0, "Sunday indoors");
    assert(s.spoken().includes("Sunday indoors"));
    assert(!s.spoken().includes("obsolete Saturday"));
  } finally {
    s.c.close();
  }
});

test("idle acknowledgment: speech after every task finishes costs no interpretation call", async () => {
  const s = setup();
  try {
    await s.start();
    const before = s.interpretations.length;
    s.input("Mm-hmm");
    await pause();
    assert.equal(s.interpretations.length, before + 1, "speech while researching is interpreted");
    s.resolve.at(-1)!({ actions: [act("unchanged", [s.jobs[0].id])] });
    await pause();
    s.answer(0, "A");
    s.input("Thanks");
    await pause();
    assert.equal(s.interpretations.length, before + 1);
    assert.deepEqual(s.spoken(), ["A"]);
  } finally {
    s.c.close();
  }
});

test("late interpretation ignored: speech holds publication; an older result cannot undo newer intent", async () => {
  const s = setup();
  try {
    await s.start();
    s.input("Actually");
    await pause();
    const stale = s.resolve.at(-1)!;
    s.answer(0, "old");
    assert.equal(s.sent.length, 0, "publication waits for the latest speech");
    s.input("Sunday indoors");
    await pause();
    s.resolve.at(-1)!({ actions: [act("revision", [s.jobs[0].id], sunday)] });
    await pause();
    stale({ actions: [act("unchanged", [s.jobs[0].id])] });
    await pause();
    s.answer(0, "new");
    assert.deepEqual(s.spoken(), ["new"]);
  } finally {
    s.c.close();
  }
});

test("duplicate delegation joins known intent without another run; new tasks require a delegation", async () => {
  const s = setup();
  try {
    await s.start();
    // Live delegates again with no new speech; the interpreter calls it new, yet it joins the running task.
    s.delegate();
    await pause();
    s.resolve.at(-1)!({ actions: [act("new", [], task)] });
    await pause();
    await s.action([act("new", [], other)]);
    assert.equal(s.jobs.length, 1);
    await s.action(
      [other, { ...other, request: "Read a URL" }].map(t => act("new", [], t)),
      true,
    );
    assert.equal(s.jobs.length, 3, "one delegated turn can carry two new tasks");
  } finally {
    s.c.close();
  }
});

test("completed task correction starts a new run with the same ID and redirects only that topic", async () => {
  const s = setup();
  try {
    await s.start();
    s.answer(0, "A");
    // With nothing researching, a correction arrives through a Live delegation.
    await s.action([act("revision", [s.jobs[0].id], { ...task, constraints: ["indoors"] })], true);
    assert.equal(s.jobs.length, 2);
    assert.equal(s.jobs[1].id, s.jobs[0].id);
    assert.equal(s.jobs[1].rev, 2);
    // Docs: corrections are quiet context, and user-derived text never goes into instructions.
    assert.equal(s.sent.at(-1).type, "session.thinking.append");
    assert.match(s.sent.at(-1).content, /Find two events/);
  } finally {
    s.c.close();
  }
});

test("research failure keeps earlier evidence and gives an honest fallback", async () => {
  const s = setup();
  try {
    await s.start();
    await s.start(other);
    s.answer(0, "A", "partial");
    s.jobs[0].error(1, Error("Research ended without a citation-backed result."));
    s.answer(1, "Comparison");
    const failed = s.card(s.jobs[0].id);
    assert.equal(failed.state, "failed");
    assert.equal(failed.sources.length, 1);
    assert(s.spoken().some(t => t.includes("I could not verify a final answer.")));
    assert.equal(s.card(s.jobs[1].id).state, "completed");
  } finally {
    s.c.close();
  }
});

test("close blocks late results; transport failure closes all work", async () => {
  const s = setup();
  await s.start();
  s.answer(0, "A", "partial");
  s.c.close();
  s.answer(0, "late");
  assert(!s.spoken().includes("late"));
  assert(s.jobs[0].cancelled);
  const t = setup();
  await t.start();
  t.c.options.send = () => {
    throw Error("lost");
  };
  t.answer(0, "A");
  assert(t.c.closed);
  assert(t.jobs[0].cancelled);
});

test("Live errors reject the matching append once; errors after close are recorded, not shown", async () => {
  const s = setup();
  try {
    await s.start();
    s.answer(0, "Evidence", "partial");
    const rejected = s.sent.at(-1);
    assert(s.c.receive({ type: "error", error: { client_event_id: rejected.event_id, message: "Command rejected" } }));
    const record = s.logs.find(e => e.type === "append.rejected")?.data;
    assert.deepEqual(record, { task_id: s.jobs[0].id, revision: 1, event_id: rejected.event_id, during_close: false });
    assert(s.visible.some(e => e.type === "error" && e.data.message.includes("will not be replayed")));
    s.c.receive({ type: "error", error: { client_event_id: rejected.event_id } });
    assert.equal(s.logs.filter(e => e.type === "append.rejected").length, 1);
    s.answer(0, "Final");
    const pending = s.sent.at(-1);
    const errors = s.visible.filter(e => e.type === "error").length;
    s.c.close();
    assert(s.c.receive({ type: "error", error: { client_event_id: pending.event_id } }));
    assert.equal(s.logs.filter(e => e.type === "append.rejected").length, 2);
    assert.equal(s.visible.filter(e => e.type === "error").length, errors);
  } finally {
    s.c.close();
  }
});

test("sideband failure during an interpretation cannot start or revise research", async () => {
  for (const relation of ["revision", "unclear"] as const) {
    const s = setup();
    try {
      await s.start();
      s.answer(0, "Supported partial", "partial");
      s.c.options.send = () => {
        throw Error("sideband lost");
      };
      await s.action(
        [
          relation === "revision"
            ? act("revision", [s.jobs[0].id], sunday)
            : act("unclear", [s.jobs[0].id], null, "Which request?"),
          act("new", [], other),
        ],
        true,
      );
      assert(s.c.closed);
      assert(s.jobs[0].cancelled);
      assert.equal(s.jobs.length, 1, `${relation} must not dispatch after transport failure`);
      assert.equal(s.jobs[0].corrections.length, 0);
      assert.equal(s.card(s.jobs[0].id).state, "cancelled");
    } finally {
      s.c.close();
    }
  }
});

test("interpretation preserves delivered fragment order despite approximate timestamps", async () => {
  const s = setup();
  try {
    const say = (type: string, delta: string, start_ms: number) =>
      s.c.receive({ type: `session.${type}_transcript.delta`, delta, start_ms, end_ms: start_ms + 200 });
    // Delivery can be uneven: an assistant fragment arrives after later user speech.
    say("input", "Find events", 0);
    say("input", " this Saturday", 200);
    say("input", " in Oakland", 4000);
    say("output", "Sure.", 1000);
    s.delegate();
    await pause();
    assert.deepEqual(
      s.interpretations.at(-1)!.transcript.map(t => [t.role, t.text]),
      [
        ["user", "Find events this Saturday"],
        ["user", "in Oakland"],
        ["assistant", "Sure."],
      ],
    );
  } finally {
    s.c.close();
  }
});

test("long spoken findings reach GPT-Live intact instead of being replaced by a card referral", async () => {
  const s = setup();
  try {
    await s.start();
    const long = "First finding sentence. ".repeat(30).trim();
    const url = "https://example.org/long";
    const sources = [{ url, title: "Long", publish_date: null, excerpts: [] }];
    s.jobs[0].finding({ revision: 1, kind: "final", spoken_summary: long, sources });
    const spoken = s.sent.at(-1).content;
    assert.equal(spoken, `Final result: ${long}`);
    assert.equal(s.card(s.jobs[0].id).summary, long, "the card keeps the full summary");
  } finally {
    s.c.close();
  }
});

test("a delegation waits briefly for its transcript", async () => {
  const s = setup();
  try {
    await s.start();
    s.answer(0, "first complete");
    const before = s.interpretations.length;
    s.c.receive({ type: "session.delegation.created", offset_ms: 5000, delegation: { id: "late", target: "client" } });
    await pause();
    assert.equal(s.interpretations.length, before);
    assert(s.c.waiting.has("late"));
    s.c.receive({ type: "session.input_transcript.delta", delta: "Compare tools", start_ms: 4000, end_ms: 5000 });
    await pause();
    s.resolve.at(-1)!({ actions: [act("new", [], other)] });
    await pause();
    assert.equal(s.jobs.length, 2);
    assert(!s.c.waiting.has("late"));
  } finally {
    s.c.close();
  }
});

test("overlapping requests stay unhandled until one successful interpretation covers both", async () => {
  const s = setup();
  try {
    s.input("Request A");
    s.delegate("a");
    await pause();
    const old = s.resolve.at(-1)!;
    s.c.receive({ type: "session.output_transcript.delta", delta: "Okay", start_ms: 1000, end_ms: 1100 });
    s.input("Request B");
    s.delegate("b");
    await pause();
    assert.deepEqual(
      s.interpretations
        .at(-1)!
        .unhandled!.filter(t => t.role === "user")
        .map(t => t.text),
      ["Request A", "Request B"],
    );
    old({ actions: [act("new", [], task)] });
    await pause();
    assert.equal(s.jobs.length, 0);
    s.resolve.at(-1)!({ actions: [act("new", [], task), act("new", [], other)] });
    await pause();
    assert.equal(s.jobs.length, 2);
    assert.equal(s.c.waiting.size, 0);
    s.input("thanks");
    await pause();
    assert.deepEqual(
      s.interpretations.at(-1)!.unhandled!.map(t => t.text),
      ["thanks"],
    );
  } finally {
    s.c.close();
  }
});

test("equal summary retains new final citations without repeating commentary", async () => {
  const s = setup();
  try {
    await s.start();
    s.answer(0, "Same", "partial");
    s.jobs[0].finding({
      revision: 1,
      kind: "final",
      spoken_summary: "Same",
      sources: [{ url: "https://new.example/", title: "New", publish_date: null, excerpts: ["New"] }],
    });
    assert.equal(s.card(s.jobs[0].id).sources.length, 2);
    assert.deepEqual(s.spoken(), ["Same"]);
  } finally {
    s.c.close();
  }
});

test("nonmonotonic timestamps never reverse words within delivered speech", () => {
  const s = setup();
  try {
    s.c.receive({ type: "session.input_transcript.delta", delta: "Do not ", start_ms: 1000, end_ms: 1200 });
    s.c.receive({ type: "session.input_transcript.delta", delta: "cancel research.", start_ms: 500, end_ms: 1300 });
    assert.equal(s.c.utterances()[0]!.text, "Do not cancel research.");
  } finally {
    s.c.close();
  }
});

test("new speech without its delegation stays unhandled until the handoff arrives", async () => {
  const s = setup();
  try {
    await s.start();
    await s.action([act("new", [], other)]);
    assert.equal(s.jobs.length, 1);
    s.delegate("late-new");
    await pause();
    assert.equal(s.interpretations.at(-1)!.unhandled!.filter(t => t.role === "user").length, 1);
    s.resolve.at(-1)!({ actions: [act("new", [], other)] });
    await pause();
    assert.equal(s.jobs.length, 2);
  } finally {
    s.c.close();
  }
});

test("later question proceeds when delegation offset follows the complete transcript", async () => {
  const s = setup();
  try {
    await s.start();
    s.answer(0, "events");
    await s.start(other);
    s.answer(1, "software");
    const before = s.interpretations.length;
    const request = "Tell me about the latest releases from Ruby";
    s.c.receive({ type: "session.input_transcript.delta", delta: request, start_ms: 177200, end_ms: 182400 });
    s.c.receive({
      type: "session.delegation.created",
      offset_ms: 183400,
      delegation: { id: "ruby", target: "client" },
    });
    await pause();
    assert.equal(s.interpretations.length, before + 1, "fresh words bypass approximate offset lag");
    assert.equal(s.interpretations.at(-1)!.unhandled!.find(t => t.role === "user")?.text, request);
    s.resolve.at(-1)!({ actions: [act("new", [], { ...other, request })] });
    await pause();
    assert.equal(s.jobs.length, 3);
    assert.equal(s.c.waiting.size, 0);
    assert(!s.visible.some(e => e.type === "error"));
    s.answer(2, "Ruby result");
    assert.equal(s.card(s.jobs[2].id).state, "completed");
  } finally {
    s.c.close();
  }
});

test("a first delegation without words waits even at offset zero", async () => {
  const s = setup();
  try {
    s.delegate("first");
    await pause();
    assert.equal(s.interpretations.length, 0);
    assert(s.c.waiting.has("first"));
    s.input("Find events");
    await pause();
    assert.equal(s.interpretations.length, 1);
    s.resolve[0]({ actions: [act("new", [], task)] });
    await pause();
    assert.equal(s.jobs.length, 1);
    assert.equal(s.c.waiting.size, 0);
  } finally {
    s.c.close();
  }
});

test("queued conclusions supersede unsent recommendations without affecting another task", async () => {
  for (const final of ["withdrawal", "supported", "failure"]) {
    const s = setup();
    try {
      await s.start();
      await s.start(other);
      s.input("Thanks");
      await pause();
      s.answer(0, "Obsolete recommendation", "partial");
      s.answer(1, "Independent answer");
      if (final === "failure") s.jobs[0].error(1, new Error("No usable final conclusion"));
      else
        s.jobs[0].finding({
          revision: 1,
          kind: "final",
          spoken_summary: "Current conclusion",
          outcome: final === "withdrawal" ? "insufficient_evidence" : "supported",
          sources: [],
        });
      s.resolve.at(-1)!({ actions: [act("unchanged", [s.jobs[0].id])] });
      await pause();
      assert(!s.sent.some(e => e.content.includes("Obsolete recommendation")));
      assert(s.spoken().includes("Independent answer"));
      assert.equal(s.card(s.jobs[0].id).state, final === "failure" ? "failed" : "completed");
    } finally {
      s.c.close();
    }
  }
});

test("a partial withdrawal is spoken immediately and its identical final is quiet", async () => {
  const s = setup();
  try {
    await s.start();
    s.answer(0, "Recommendation", "partial");
    const f = {
      revision: 1,
      kind: "partial",
      outcome: "insufficient_evidence",
      spoken_summary: "The sources conflict.",
      display_title: "Not confirmed",
      display_items: [{ heading: "Unconfirmed", detail: "The sources conflict." }],
      sources: [],
    };
    s.jobs[0].finding(f);
    assert.equal(s.spoken().length, 2);
    assert.match(s.spoken()[1], /withdrawn/i);
    s.jobs[0].finding({ ...f, kind: "final" });
    assert.equal(s.spoken().length, 2);
    const card = s.card(s.jobs[0].id);
    assert.equal(card.outcome, "insufficient_evidence");
    assert.deepEqual(card.current_sources, []);
    assert.equal(card.current_summary, "The sources conflict.");
    await s.action([act("unchanged", [s.jobs[0].id])], true);
    assert(!s.quiet().at(-1)!.includes("Recommendation"));
  } finally {
    s.c.close();
  }
});

test("identical summary text replaces current citations and outcome instead of merging them", async () => {
  const s = setup();
  try {
    await s.start();
    s.answer(0, "Uncertain", "partial");
    s.jobs[0].finding({
      revision: 1,
      kind: "final",
      outcome: "insufficient_evidence",
      spoken_summary: "Uncertain",
      sources: [],
    });
    assert.deepEqual(s.card(s.jobs[0].id).current_sources, []);
    assert.equal(s.card(s.jobs[0].id).outcome, "insufficient_evidence");
    assert.equal(s.spoken().length, 2, "a changed outcome is not a duplicate");
  } finally {
    s.c.close();
  }
});

test("failed final research clears the current recommendation while retaining historical evidence", async () => {
  const s = setup();
  try {
    await s.start();
    s.answer(0, "Provisional", "partial");
    s.jobs[0].error(1, new Error("Invalid final answer"));
    const card = s.card(s.jobs[0].id);
    assert.equal(card.state, "failed");
    assert.equal(card.current_summary, "");
    assert.deepEqual(card.current_sources, []);
    assert.match(card.summary, /Provisional/);
    assert(!s.sent.at(-1).content.includes("already supported"));
  } finally {
    s.c.close();
  }
});

test("delayed preparation cannot publish an older conclusion in the same revision", async () => {
  const pending: { content: string; resolve: (chunks: string[]) => void; signal: AbortSignal }[] = [];
  const s = setup((content, signal) => new Promise(resolve => pending.push({ content, signal, resolve })));
  try {
    await s.start();
    s.answer(0, "Old answer", "partial");
    s.jobs[0].finding({
      revision: 1,
      kind: "final",
      outcome: "insufficient_evidence",
      spoken_summary: "Not confirmed",
      sources: [],
    });
    assert(pending[0].signal.aborted);
    pending[1].resolve([pending[1].content]);
    await pause();
    pending[0].resolve([pending[0].content]);
    await pause();
    assert.deepEqual(s.spoken(), ["Not confirmed"]);
    assert.equal(s.logs.filter(e => e.type === "answer.appended").length, 1);
  } finally {
    s.c.close();
  }
});

test("preparing final speech does not strand new input or block independent tasks", async () => {
  let finish!: (chunks: string[]) => void;
  const s = setup(content =>
    content.includes("Delayed")
      ? new Promise(resolve => {
          finish = resolve;
        })
      : [content],
  );
  try {
    await s.start();
    await s.start(other);
    s.answer(0, "Delayed");
    s.answer(1, "Independent");
    assert.deepEqual(s.spoken(), ["Independent"]);
    const before = s.interpretations.length;
    s.input("Thanks");
    await pause();
    assert.equal(
      s.interpretations.length,
      before + 1,
      "completed research with pending speech still interprets fresh input",
    );
    finish(["Final result: Delayed"]);
    await pause();
    assert.deepEqual(s.spoken(), ["Independent"], "publication waits for input interpretation");
    s.resolve.at(-1)!({ actions: [act("unchanged", [s.jobs[0].id])] });
    await pause();
    assert.deepEqual(s.spoken(), ["Independent", "Delayed"]);
    assert.equal(s.c.appends.size, 2, "unacknowledged commands do not block one another");
  } finally {
    s.c.close();
  }
});

test("cancel and close invalidate preparation, while preparation failure preserves the current card", async () => {
  for (const mode of ["cancel", "close", "failure"]) {
    let finish!: (chunks: string[]) => void, fail!: (error: Error) => void;
    let signal!: AbortSignal;
    const s = setup((content, pendingSignal) =>
      content.includes("Delayed")
        ? new Promise((resolve, reject) => {
            finish = resolve;
            fail = reject;
            signal = pendingSignal;
          })
        : [content],
    );
    try {
      await s.start();
      s.answer(0, "Delayed", mode === "cancel" ? "partial" : "final");
      if (mode === "cancel") await s.action([act("cancel", [s.jobs[0].id])]);
      if (mode === "close") s.c.close();
      if (mode === "failure") {
        fail(Error("Counting unavailable"));
        await pause();
        assert.equal(s.card(s.jobs[0].id).current_summary, "Delayed");
        assert(s.visible.some(e => e.type === "error"));
        assert(!s.logs.some(e => e.type === "answer.appended"));
      } else {
        assert(signal.aborted);
        finish(["Final result: Delayed"]);
        await pause();
        assert(!s.spoken().includes("Delayed"));
      }
    } finally {
      s.c.close();
    }
  }
});

test("a failed second chunk closes delivery without replaying the accepted first chunk", async () => {
  const s = setup(() => ["First complete finding", "Second complete finding"]);
  try {
    await s.start();
    s.c.options.send = event => {
      if (s.sent.length) throw Error("Transport lost");
      s.sent.push(event);
    };
    s.answer(0, "Both findings");
    assert.equal(s.sent.length, 1);
    assert(s.c.closed);
    assert(!s.logs.some(e => e.type === "answer.appended"));
  } finally {
    s.c.close();
  }
});

test("an 800 ms delegation lag starts research once from complete speech", async () => {
  const s = setup();
  try {
    s.c.receive({ type: "session.input_transcript.delta", delta: "Find events", start_ms: 0, end_ms: 1000 });
    s.c.receive({
      type: "session.delegation.created",
      offset_ms: 1800,
      delegation: { id: "handoff", target: "client" },
    });
    await pause();
    assert.equal(s.interpretations.length, 1);
    s.resolve[0]({ actions: [act("new", [], task)] });
    await pause();
    assert.equal(s.jobs.length, 1);
    assert.equal(s.c.waiting.size, 0);
  } finally {
    s.c.close();
  }
});

test("a late delegation for an already applied correction cannot hold results", async () => {
  const s = setup(undefined, 40);
  try {
    s.c.receive({
      type: "session.input_transcript.delta",
      delta: "Find events. Separately, compare tools.",
      start_ms: 0,
      end_ms: 4000,
    });
    s.c.receive({ type: "session.delegation.created", offset_ms: 4800, delegation: { id: "first", target: "client" } });
    await pause();
    s.resolve.at(-1)!({ actions: [act("new", [], task), act("new", [], other)] });
    await pause();
    const [events, tools] = s.jobs;
    // The correction is interpreted from speech while research runs, before GPT-Live delegates it.
    s.c.receive({
      type: "session.input_transcript.delta",
      delta: "For the events, make that Sunday and indoors.",
      start_ms: 9000,
      end_ms: 11000,
    });
    await pause();
    s.resolve.at(-1)!({ actions: [act("revision", [events.id], sunday)] });
    await pause();
    assert.equal(events.rev, 2);
    // The delegation for the same correction arrives later and has no new words.
    const before = s.interpretations.length;
    s.c.receive({
      type: "session.delegation.created",
      offset_ms: 11800,
      delegation: { id: "again", target: "client" },
    });
    await pause();
    assert.equal(s.interpretations.length, before, "waits for a transcript first");
    s.answer(1, "tools result");
    assert.equal(s.card(tools.id).state, "researching", "held while the delegation waits");
    await new Promise(r => setTimeout(r, 60));
    assert.equal(s.interpretations.length, before + 1, "interprets the delegation after the wait");
    assert.deepEqual(s.interpretations.at(-1)!.unhandled, []);
    s.resolve.at(-1)!({ actions: [act("unchanged", [events.id])] });
    await pause();
    assert.equal(s.c.waiting.size, 0);
    assert.equal(s.card(tools.id).state, "completed");
    assert(s.spoken().includes("tools result"));
    assert.equal(s.c.tasks.get(events.id)!.delegation_id, "again");
    s.answer(0, "Sunday indoor events");
    assert.equal(s.card(events.id).state, "completed");
    assert(s.spoken().includes("Sunday indoor events"));
  } finally {
    s.c.close();
  }
});

test("a delegation interpreted before its words arrive can still start their request", async () => {
  const s = setup(undefined, 30);
  try {
    s.c.receive({ type: "session.delegation.created", offset_ms: 2000, delegation: { id: "early", target: "client" } });
    await new Promise(r => setTimeout(r, 50));
    assert.equal(s.interpretations.length, 1);
    s.resolve[0]({ actions: [act("unchanged")] });
    await pause();
    assert.equal(s.jobs.length, 0);
    assert.equal(s.c.waiting.size, 0);
    s.c.receive({ type: "session.input_transcript.delta", delta: "Find events", start_ms: 0, end_ms: 1500 });
    await pause();
    s.resolve.at(-1)!({ actions: [act("new", [], task)] });
    await pause();
    assert.equal(s.jobs.length, 1);
    assert.equal(s.c.tasks.get(s.jobs[0].id)!.delegation_id, "early");
    s.input("thanks");
    await pause();
    s.resolve.at(-1)!({ actions: [act("unchanged")] });
    await pause();
    assert.deepEqual(s.c.open, [], "stays open for one turn only");
  } finally {
    s.c.close();
  }
});

test("a repeated partial does not cancel its pending voice preparation", async () => {
  let finish!: (chunks: string[]) => void;
  let signal!: AbortSignal;
  const s = setup(
    (content, pendingSignal) =>
      new Promise(resolve => {
        signal = pendingSignal;
        finish = resolve;
      }),
  );
  try {
    await s.start();
    s.answer(0, "Same finding", "partial");
    s.answer(0, "Same finding", "partial");
    assert(!signal.aborted);
    finish(["Early result; research is still running: Same finding"]);
    await pause();
    assert.deepEqual(s.spoken(), ["Same finding"]);
  } finally {
    s.c.close();
  }
});

test("a held final answer invalidates a status notice prepared before its completed snapshot", async () => {
  const pending: { content: string; resolve: (chunks: string[]) => void }[] = [];
  const s = setup(content => new Promise(resolve => pending.push({ content, resolve })));
  try {
    await s.start();
    s.input("How is it going?");
    s.delegate();
    await pause();
    s.answer(0, "Finished finding");
    s.resolve.at(-1)!({ actions: [act("unchanged", [s.jobs[0].id])] });
    await pause();
    assert.equal(pending.length, 2);
    pending[1].resolve([pending[1].content]);
    await pause();
    pending[0].resolve([pending[0].content]);
    await pause();
    assert.deepEqual(s.spoken(), ["Finished finding"]);
    assert(!s.quiet().some(text => text.includes("still running")));
  } finally {
    s.c.close();
  }
});

test("cancelling completed research stops its still-unsent final voice update", async () => {
  let finish!: (chunks: string[]) => void, pendingSignal!: AbortSignal;
  const s = setup((content, signal) =>
    content.includes("Delayed final")
      ? new Promise(resolve => {
          finish = resolve;
          pendingSignal = signal;
        })
      : [content],
  );
  try {
    await s.start();
    s.answer(0, "Delayed final");
    assert.equal(s.card(s.jobs[0].id).state, "completed");
    await s.action([act("cancel", [s.jobs[0].id])], true);
    assert(pendingSignal.aborted);
    finish(["Final result: Delayed final"]);
    await pause();
    assert(!s.spoken().includes("Delayed final"));
    assert.equal(s.card(s.jobs[0].id).state, "completed", "completed evidence stays available on the card");
  } finally {
    s.c.close();
  }
});

test("updated citations with identical words replace pending preparation without losing speech", async () => {
  const pending: { content: string; resolve: (chunks: string[]) => void; signal: AbortSignal }[] = [];
  const s = setup((content, signal) => new Promise(resolve => pending.push({ content, resolve, signal })));
  try {
    await s.start();
    s.answer(0, "Same words", "partial");
    const source = {
      url: "https://example.org/new",
      title: "Replacement evidence",
      publish_date: null,
      excerpts: ["Same words"],
    };
    s.jobs[0].finding({ revision: 1, kind: "partial", spoken_summary: "Same words", sources: [source] });
    assert(pending[0].signal.aborted);
    assert.equal(pending.length, 2);
    pending[1].resolve([pending[1].content]);
    await pause();
    assert.deepEqual(s.spoken(), ["Same words"]);
    assert.deepEqual(s.card(s.jobs[0].id).current_sources, [source]);
  } finally {
    s.c.close();
  }
});

test("only the matching append acknowledgment settles a submitted update", async () => {
  const s = setup();
  try {
    await s.start();
    s.answer(0, "Finding");
    const event = s.sent.at(-1);
    for (const type of ["info", "session.thinking.appended"]) {
      assert.equal(s.c.receive({ type, client_event_id: event.event_id }), false);
      assert.equal(s.c.appends.size, 1);
    }
    assert.equal(s.c.receive({ type: "session.commentary.appended", client_event_id: event.event_id }), true);
    assert.equal(s.c.appends.size, 0);
    assert.equal(s.c.receive({ type: "session.commentary.appended", client_event_id: event.event_id }), false);
  } finally {
    s.c.close();
  }
});

test("delivery evidence tracks delayed preparation, chunks, quiet finals, and supersession", async () => {
  const pending: ((chunks: string[]) => void)[] = [];
  const s = setup(() => new Promise(resolve => pending.push(resolve)));
  const ack = () => {
    for (const e of s.sent) s.c.receive({ type: e.type + "ed", client_event_id: e.event_id });
  };
  try {
    await s.start();
    s.answer(0, "First", "partial");
    assert.equal(s.c.voiceSnapshot().updates.at(-1)?.state, "preparing");
    pending.shift()!(["First chunk", "Second chunk"]);
    await pause();
    assert.equal(s.c.voiceSnapshot().updates.at(-1)?.state, "submitted");
    ack();
    assert.equal(s.c.voiceSnapshot().updates.at(-1)?.state, "accepted");
    s.answer(0, "First");
    const final = s.c.voiceSnapshot().updates.at(-1)!;
    assert.equal(final.kind, "final");
    assert.equal(final.type, "session.thinking.append");
    assert.equal(s.card(s.jobs[0].id).state, "completed");
    assert.equal(final.state, "preparing", "card completion cannot settle the delayed final");
    pending.shift()!(["Final result: First"]);
    await pause();
    ack();
    assert.equal(s.c.voiceSnapshot().updates.at(-1)?.state, "accepted");
    await s.start(other);
    s.answer(1, "Obsolete");
    await s.action([act("cancel", [s.jobs[1].id])]);
    assert(s.c.voiceSnapshot().updates.some(u => u.state === "superseded"));
    pending.shift()!(["Must not be sent"]);
    pending.shift()!(["Cancellation"]);
    await pause();
    ack();
    assert(!s.sent.some(e => e.content === "Must not be sent"));
    assert.equal(s.c.voiceSnapshot().updates.at(-1)?.purpose, "cancellation");
    assert.equal(s.c.voiceSnapshot().updates.at(-1)?.state, "accepted");
  } finally {
    s.c.close();
  }
});

test("an obsolete update whose preparation fails is settled instead of staying pending", async () => {
  let reject!: (error: Error) => void;
  const s = setup(() => new Promise((_, r) => { reject = r; }));
  await s.action([act("unclear", [], null, "Which city?")], true);
  assert.equal(s.c.voiceSnapshot().updates.at(-1)?.state, "preparing");
  // The user answers before the clarification is ready, then its preparation fails.
  s.input("San Francisco");
  reject(new Error("Voice update preparation failed (500)."));
  await pause();
  assert.equal(s.c.voiceSnapshot().updates.at(-1)?.state, "superseded");
  assert(!s.visible.some(v => v.type === "error"), "an obsolete failure is not shown");
});
