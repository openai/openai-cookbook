import assert from "node:assert/strict";
import test from "node:test";
import {
  deliveryChecks,
  estimateCost,
  structuralChecks,
  summarize,
  taskMetrics,
  type Annotation,
  type LogEvent,
  type Rates,
  type TaskAnnotation,
  type Trial,
} from "../scripts/evaluation.ts";
import type { VoiceSnapshot } from "../src/types.ts";

const rates: Rates = {
  checked_at: "2026-09-18",
  source_urls: ["https://example.com/test-rates"],
  responses: { test: { input_per_million: 2, cached_input_per_million: 0.5, output_per_million: 8 } },
  parallel_search_per_call_usd: 0.005,
};
// An accepted final update for every finished task, as the runner records it.
function proof(events: LogEvent[]): VoiceSnapshot {
  const latest = new Map<string, Record<string, any>>();
  for (const e of events) if (e.type === "ui.task") latest.set(String(e.data.task_id), e.data);
  return {
    version: 1,
    updates: [...latest.values()]
      .filter(t => t.state !== "researching")
      .map((t, i) => ({
        id: `update-${i}`,
        task_id: t.task_id,
        revision: t.revision,
        conclusion: t.conclusion_version ?? 0,
        purpose: t.state === "cancelled" ? "cancellation" : "finding",
        kind: "final",
        type: "session.commentary.append",
        state: "accepted",
        chunks: [{ event_id: `event-${i}`, state: "accepted" }],
        updated_at: 1,
      })),
  };
}
function trial(events: LogEvent[] = [], expectations: Trial["expectations"] = {}): Trial {
  return {
    scenario: "normal",
    status: "completed",
    recording_file: "run.webm",
    recording_check: { pass: true },
    errors: [],
    client: { recordingStart: 10, events: [] },
    server: { closed: true, events: [{ type: "session.created", data: { today: "2026-10-01" } }, ...events], voice: proof(events) },
    expectations,
  };
}
const taskGrade = (grades: Partial<TaskAnnotation> = {}): TaskAnnotation => ({
  task_id: "A",
  revision: 1,
  request_end_ms: 2000,
  first_useful_speech_ms: 6500,
  final_speech_ms: 9000,
  task_completion_pass: true,
  quality_pass: true,
  correction_pass: null,
  cancellation_pass: null,
  cancelled: false,
  notes: "Reviewed recording and source evidence.",
  ...grades,
});
const graded = (grades: Partial<TaskAnnotation> = {}): Annotation => ({
  tasks: [taskGrade(grades)],
  task_completion_pass: null,
  quality_pass: null,
  correction_pass: null,
  notes: "",
});
const snapshot = (
  id: string,
  revision: number,
  version: number,
  task: object = {},
  state = "researching",
): LogEvent => ({ type: "ui.task", data: { task_id: id, revision, version, task, state } });
const call = (id: string, task = "A"): LogEvent => ({
  type: "parallel.dispatched",
  data: { task_id: task, revision: 1, call_id: id },
});
const events = { request: "Find two events", location: "San Francisco", date: "2026-10-03", constraints: [] };
const general = { request: "Compare tools", location: null, date: null, constraints: [] };

test("snapshots accept independent revisions and parallel tools, and reject stale snapshots and repeated call IDs", () => {
  const log = [
    snapshot("A", 1, 1),
    snapshot("B", 1, 1),
    call("one"),
    call("two"),
    snapshot("B", 1, 2, {}, "completed"),
    snapshot("A", 2, 2),
    snapshot("A", 2, 3, {}, "completed"),
  ];
  const run = trial(log, { task_count: 2 });
  assert.equal(structuralChecks(run).pass, true);
  assert(
    structuralChecks(trial([...log, snapshot("A", 1, 4)], { task_count: 2 })).issues.includes(
      "An obsolete task snapshot was published.",
    ),
  );
  assert(
    structuralChecks(trial([...log, call("one")], { task_count: 2 })).issues.includes(
      "Duplicate or missing tool call ID.",
    ),
  );
});

test("an event correction keeps the location, changes the date, adds indoors, and leaves other tasks alone", () => {
  const make = (revised: object, other = snapshot("B", 1, 2, general, "completed")) => ({
    ...trial(
      [snapshot("A", 1, 1, events), snapshot("B", 1, 1, general), snapshot("A", 2, 2, revised, "completed"), other],
      { task_count: 2, correction: true },
    ),
    scenario: "multi-task-correction",
  });
  assert.equal(structuralChecks(make({ ...events, date: "2026-10-04", constraints: ["indoors"] })).pass, true);
  assert.equal(structuralChecks(make({ ...events, date: "2026-10-04", constraints: [] })).pass, false);
  assert.equal(
    structuralChecks(make({ ...events, location: "Oakland", date: "2026-10-04", constraints: ["indoors"] })).pass,
    false,
  );
  for (const date of [null, "2026-10-05", "2026-10-11"]) {
    assert.equal(structuralChecks(make({ ...events, date, constraints: ["indoors"] })).pass, false);
  }
  const changed = make(
    { ...events, date: "2026-10-04", constraints: ["indoors"] },
    snapshot("B", 2, 2, general, "completed"),
  );
  assert(structuralChecks(changed).issues.includes("Correction changed an unrelated task."));
});

test("correction trials report whether the correction steered, went with the next request, or restarted research", () => {
  const sunday = { ...events, date: "2026-10-04", constraints: ["indoors"] };
  const applied = (via: string): LogEvent => ({
    type: "research.revision_applied",
    data: { task_id: "A", revision: 2, via, response_id: "r2" },
  });
  const run = (log: LogEvent[], during = true) => ({
    ...trial(log, { task_count: 1, correction: true, correct_during_research: during }),
    scenario: "correction",
  });
  const running = [snapshot("A", 1, 1, events), snapshot("A", 2, 2, sunday)];
  const done = snapshot("A", 2, 3, sunday, "completed");
  for (const via of ["steer", "next_request"]) {
    const checks = structuralChecks(run([...running, applied(via), done]));
    assert.equal(checks.pass, true, via);
    assert.equal(checks.correction_path, via);
  }
  // Revision 1 finished first, so the correction started a new run instead of reaching running research.
  const late = [
    snapshot("A", 1, 1, events),
    snapshot("A", 1, 2, events, "completed"),
    snapshot("A", 2, 3, sunday),
    snapshot("A", 2, 4, sunday, "completed"),
  ];
  const missed = structuralChecks(run(late));
  assert.equal(missed.correction_path, "restarted");
  assert(missed.issues.includes("The correction reached the event task after its research finished."));
  assert.equal(
    structuralChecks(run(late, false)).pass,
    true,
    "allowed when the scenario does not require a correction during research",
  );
  const report = summarize(
    [
      { trial: run([...running, applied("steer"), done]) },
      { trial: run([...running, applied("next_request"), done]) },
      { trial: run(late) },
    ],
    rates,
  );
  assert.deepEqual(report.by_scenario.correction!.correction_paths, { steer: 1, next_request: 1, restarted: 1 });
});

test("cancellation must isolate the event task, and expected counts are enforced", () => {
  const log = [
    snapshot("A", 1, 1, events),
    snapshot("B", 1, 1, general),
    snapshot("A", 1, 2, events, "cancelled"),
    snapshot("B", 1, 2, general, "completed"),
  ];
  assert.equal(structuralChecks(trial(log, { task_count: 2, cancelled_count: 1 })).pass, true);
  assert.equal(structuralChecks(trial(log, { task_count: 2, cancelled_count: 0 })).pass, false);
  assert.equal(structuralChecks(trial([], { task_count: 0 })).pass, true, "missing-city creates no task");
  assert.equal(structuralChecks(trial([snapshot("A", 1, 1, events)], { task_count: 0 })).pass, false);
  const restarted = {
    ...trial([snapshot("A", 1, 1), snapshot("A", 2, 2, {}, "completed")], { task_count: 1 }),
    scenario: "acknowledgment",
  };
  assert(structuralChecks(restarted).issues.includes("Acknowledgment restarted research."));
});

test("task speech timing keeps separate first/final latency and never assigns cancelled final latency", () => {
  const values = taskMetrics(trial(), {
    ...graded(),
    tasks: [taskGrade({ cancelled: true }), taskGrade({ task_id: "B" })],
  });
  assert.equal(values[0]!.first_useful_latency_ms, 4500);
  assert.equal(values[0]!.final_latency_ms, null);
  assert.equal(values[1]!.final_latency_ms, 7000);
  assert.equal(taskMetrics({ ...trial(), recording_file: null }, graded())[0]!.first_useful_latency_ms, null);
  assert.equal(
    taskMetrics({ ...trial(), recording_check: { pass: false } }, graded())[0]!.first_useful_latency_ms,
    null,
  );
});

test("unreviewed runs stay unknown; per-task and run-level grades are both counted", () => {
  const missingCity: Annotation = {
    task_completion_pass: true,
    quality_pass: true,
    correction_pass: null,
    notes: "Asked for the city.",
  };
  const report = summarize(
    [
      { trial: trial() },
      { trial: trial(), annotation: graded({ task_completion_pass: false, quality_pass: true }) },
      {
        trial: { ...trial(), scenario: "correction", expectations: { correction: true } },
        annotation: graded({ correction_pass: true }),
      },
      { trial: { ...trial(), scenario: "missing-city" }, annotation: missingCity },
    ],
    rates,
  );
  const normal = report.by_scenario.normal!;
  assert.equal(normal.trials, 2);
  assert.equal(normal.task_completion_reviewed, 1);
  assert.equal(normal.task_completion_pass_rate, 0);
  assert.equal(
    normal.quality_pass_rate,
    1,
    "an honest insufficient-evidence answer can pass quality without fulfilling the task",
  );
  assert.equal(normal.task_first_useful_p50_ms, 4500);
  assert.equal(report.by_scenario.correction!.correction_pass_rate, 1);
  assert.equal(report.by_scenario["missing-city"]!.task_completion_pass_rate, 1);
  assert.equal(report.runs[0]!.task_completion, "unreviewed");
  assert.equal(report.runs[1]!.task_completion, undefined, "runs with tasks are graded under tasks");
  assert.equal(report.runs[3]!.notes, "Asked for the city.");
});

test("all completed Responses usage is charged once, with cached input separated", () => {
  const completed: LogEvent = {
    type: "responses.completed",
    data: {
      response_id: "old",
      model: "test",
      service_tier: "default",
      usage: { input_tokens: 1000, output_tokens: 100, input_tokens_details: { cached_tokens: 400 } },
    },
  };
  const cost = estimateCost([{ type: "responses.dispatched", data: {} }, completed, completed], rates);
  assert.ok(Math.abs(cost.known_responses_usd - 0.0022) < 1e-10);
  assert.equal(cost.responses_completed, 1);
  assert.equal(cost.total_usd, null);
  assert.ok(cost.unknown_reasons.some(reason => reason.includes("closure is unconfirmed")));
});

test("aborted work, automatic successors, unreported Parallel usage and absent rates stay unknown", () => {
  const cost = estimateCost(
    [
      { type: "responses.failed", data: { aborted: true } },
      { type: "research.event", data: { type: "response.created", response: { id: "successor" } } },
      call("one"),
      { type: "parallel.failed", data: { task_id: "A", call_id: "one" } },
      {
        type: "parallel.dispatched",
        data: {
          task_id: "A",
          call_id: "two",
          operation: "extract",
          arguments: { urls: ["https://a.test", "https://b.test"] },
        },
      },
      { type: "live.event", data: { type: "session.closed", usage: { arbitrary_provider_unit: 3 } } },
    ],
    { ...rates, parallel_search_per_call_usd: null, parallel_extract_per_url_usd: 0.001 },
  );
  assert.equal(cost.parallel_estimated_usd, null);
  assert.equal(cost.extraction_urls, 2);
  assert.equal(cost.extraction_estimated_usd, null);
  assert.equal(cost.gpt_live_usd, null);
  for (const reason of ["aborted work", "automatic successors", "provider-reported usage", "rate for sku_search"]) {
    assert.ok(
      cost.unknown_reasons.some(r => r.includes(reason)),
      reason,
    );
  }
});

test("final cumulative Live seconds are priced once and a fully reported run is complete", () => {
  const cost = estimateCost(
    [
      { type: "live.event", data: { type: "session.usage.updated", usage: { seconds: 20 } } },
      { type: "live.event", data: { type: "session.closed", usage: { seconds: 90 } } },
      call("one"),
      { type: "parallel.completed", data: { task_id: "A", call_id: "one", usage: [{ name: "sku_search", count: 1 }] } },
    ],
    { ...rates, gpt_live_per_minute_usd: 0.05 },
  );
  assert.ok(Math.abs(cost.gpt_live_usd! - 0.075) < 1e-10);
  assert.equal(cost.complete, true);
  assert.ok(Math.abs(cost.total_usd! - 0.08) < 1e-10);
});

test("Parallel estimates price reported units and keep missing receipts out of the subtotal", () => {
  const dispatch = { type: "parallel.dispatched", data: { task_id: "A", call_id: "extract", operation: "extract",
    arguments: { urls: ["https://a.test", "https://b.test"] } } };
  const receipt = { type: "parallel.completed", data: { task_id: "A", call_id: "extract",
    usage: [{ name: "sku_extract_excerpts", count: 1 }] } };
  const cost = estimateCost([dispatch, receipt, call("unreported")], { ...rates, parallel_extract_per_url_usd: 0.001 });
  assert.equal(cost.extraction_urls, 2);
  assert.equal(cost.extraction_estimated_usd, 0.001);
  assert.equal(cost.estimated_subtotal_usd, 0.001);
  assert.equal(cost.total_usd, null);
  for (const usage of [[], [{ name: "unknown", count: 1 }]]) {
    const result = estimateCost([dispatch, { ...receipt, data: { ...receipt.data, usage } }],
      { ...rates, parallel_extract_per_url_usd: 0.001 });
    assert.equal(result.extraction_estimated_usd, null);
  }
});

test("Responses pricing follows the returned Fast or Standard tier and leaves unknown tiers unpriced", () => {
  const pricing = {
    ...rates,
    responses_fast: {
      test: { input_per_million: 4, cached_input_per_million: 1, cache_write_per_million: 5, output_per_million: 16 },
    },
  };
  const cost = (tier: string | null, table: Rates = pricing) =>
    estimateCost(
      [
        {
          type: "responses.completed",
          data: {
            response_id: "response",
            model: "test",
            service_tier: tier,
            usage: {
              input_tokens: 1000,
              output_tokens: 100,
              input_tokens_details: { cached_tokens: 400, cache_write_tokens: 100 },
            },
          },
        },
      ],
      table,
    );
  for (const tier of ["priority", "fast"]) assert.ok(Math.abs(cost(tier).known_responses_usd - 0.0045) < 1e-10);
  // A server downgrade must use Standard prices even when Fast was requested.
  const standard = { ...pricing, responses: { test: { ...rates.responses.test!, cache_write_per_million: 2.5 } } };
  assert.ok(Math.abs(cost("default", standard).known_responses_usd - 0.00225) < 1e-10);
  for (const tier of [null, "flex"]) {
    assert.equal(cost(tier).known_responses_usd, 0);
    assert(cost(tier).unknown_reasons.some(reason => reason.includes("rates")));
  }
  assert.equal(cost("priority", { ...pricing, responses_fast: {} }).known_responses_usd, 0);
});

test("prepared speech after completion must match the current conclusion and revision", () => {
  const done = snapshot("A", 2, 2, {}, "completed");
  Object.assign(done.data, { current_summary: "Not enough evidence.", outcome: "insufficient_evidence" });
  const answer = {
    type: "answer.appended",
    data: { task_id: "A", revision: 2, summary: "Not enough evidence.", outcome: "insufficient_evidence" },
  };
  assert(structuralChecks(trial([done, answer])).pass);
  for (const change of [{ revision: 1 }, { summary: "Old advice" }, { outcome: "supported" }]) {
    assert(
      structuralChecks(trial([done, { ...answer, data: { ...answer.data, ...change } }])).issues.includes(
        "An obsolete answer was appended.",
      ),
    );
  }
  for (const type of ["voice.preparation.failed", "append.rejected"]) {
    assert(structuralChecks(trial([done, { type, data: {} }])).issues.includes("A voice update was not delivered."));
  }
  assert(structuralChecks(trial([done, { type: "append.rejected", data: { during_close: true } }])).pass);
});

test("a run cannot pass without delivery proof or verified audio, or with duplicate commentary", () => {
  const completed = snapshot("A", 1, 1, {}, "completed");
  Object.assign(completed.data, { current_summary: "A", outcome: "supported" });
  const run = trial([completed], { task_count: 1 });
  assert.equal(structuralChecks(run).pass, true);
  assert(
    structuralChecks({ ...run, server: { closed: true, events: [completed] } }).issues.includes(
      "Voice delivery proof is missing.",
    ),
  );
  assert(
    structuralChecks({ ...run, recording_check: { pass: false } }).issues.includes("Audio capture was not verified."),
  );
  const answer = { type: "answer.appended", data: { task_id: "A", revision: 1, summary: "A", outcome: "supported" } };
  assert(
    structuralChecks(trial([completed, answer, answer], { task_count: 1 })).issues.includes(
      "Duplicate commentary finding.",
    ),
  );
});

test("delivery proof belongs to the current conclusion, including quiet finals", () => {
  const completed = snapshot("A", 1, 2, {}, "completed");
  completed.data.conclusion_version = 2;
  const accepted = {
    id: "old",
    task_id: "A",
    revision: 1,
    conclusion: 1,
    purpose: "finding" as const,
    kind: "final" as const,
    type: "session.thinking.append",
    state: "accepted" as const,
    chunks: [{ event_id: "one", state: "accepted" as const }],
    updated_at: 1,
  };
  const server = { closed: true, events: [completed], voice: { version: 1 as const, updates: [accepted] } };
  assert.equal(deliveryChecks({ server }).ready, false);
  server.voice.updates[0]!.conclusion = 2;
  assert.equal(deliveryChecks({ server }).ready, true);
});
