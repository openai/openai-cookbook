import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import { retrieve } from "../src/backend.ts";
import { startResearch } from "../src/research.ts";
import type { Finding, Task } from "../src/types.ts";

// A paid compatibility check for a research model. It runs the app's own research code against
// the real Responses API with synthetic results for its Parallel tools, steers it once, then makes one
// real Parallel Search and one Extract request through the app's retrieve().
const settings = JSON.parse(await readFile(new URL("../settings.json", import.meta.url), "utf8"));
const model = process.env.RESEARCH_MODEL_OVERRIDE ?? settings.research_model;
const effort = process.env.RESEARCH_EFFORT_OVERRIDE ?? settings.research_effort;
if (!process.env.OPENAI_API_KEY || !process.env.PARALLEL_API_KEY) {
  throw new Error("OpenAI and Parallel keys are required.");
}
const directory = new URL(`../evals/results/probe-${Date.now()}/`, import.meta.url);
await mkdir(directory, { recursive: true });
const trace: { at: string; type: string; data: any }[] = [];
const record = (type: string, data: Record<string, unknown>) => {
  trace.push({ at: new Date().toISOString(), type, data });
};

const task: Task = {
  request: "Find the synthetic marker in the sources.",
  location: null,
  date: null,
  constraints: [],
};
const corrected: Task = { ...task, request: "Find the corrected synthetic marker in the sources." };
// Lookups resolve after a delay, so the model has to keep going while they are pending.
let lookups = 0;
let correctPending: (() => void) | undefined;
const synthetic: typeof retrieve = async (_name, _args, context) => {
  const n = ++lookups;
  if (context.revision === 1) correctPending?.();
  await new Promise(resolve => setTimeout(resolve, 1500));
  context.signal.throwIfAborted();
  const marker = context.revision === 1 ? "alpha-7" : "corrected beta-9";
  const source = {
    url: `https://example.org/source-${n}`,
    title: `Synthetic source ${n}`,
    publish_date: null,
    excerpts: [`The synthetic marker is ${marker}.`],
  };
  return { sources: [source], errors: [] };
};

try {
  const finding = await new Promise<Finding>((resolve, reject) => {
    let steered = false;
    const run = startResearch({
      today: new Date().toISOString().slice(0, 10),
      task_id: "probe",
      task,
      revision: 1,
      model,
      effort,
      retrieve: synthetic,
      record,
      onFinding: f => {
        record("probe.finding", f);
        if (f.kind === "final") resolve(f);
      },
      onError: (_revision, error) => reject(error),
    });
    correctPending = () => {
      if (!steered) {
        steered = true;
        run.update(corrected, 2);
      }
    };
  });
  const events = trace.filter(e => e.type === "research.event").map(e => e.data);
  const commands = trace.filter(e => e.type === "research.command").map(e => e.data);
  const calls = events
    .filter(e => e.type === "response.output_item.done" && e.item.type === "function_call")
    .map(e => e.item);
  const creates = commands.filter(c => c.type === "response.create");
  const accepted = events.findIndex(e => e.type === "response.steer.accepted");
  assert(
    commands.some(c => c.type === "response.steer"),
    "The correction was sent as response.steer.",
  );
  assert(accepted >= 0, "Steering was accepted.");
  assert(!events.some(e => e.type === "response.steer.failed"), "Steering did not fail.");
  assert(
    events.slice(accepted).some(e => e.type === "response.created"),
    "A successor response was created.",
  );
  const retrievalCalls = calls.filter(c => c.name !== "wait_for_results");
  assert(retrievalCalls.length && retrievalCalls.every(c => c.async === true), "Retrieval calls are async.");
  assert(
    calls.filter(c => c.name === "wait_for_results").every(c => !c.async),
    "Wait calls are synchronous.",
  );
  const ids = new Set(calls.map(c => c.call_id));
  const returned = creates.flatMap(c => c.input).filter((i: any) => i.type === "function_call_output");
  assert(
    returned.every((i: any) => ids.has(i.call_id)),
    "Results return under their original call IDs.",
  );
  assert(
    creates.every(c => c.store === false),
    "Every request uses store: false.",
  );
  assert.equal(finding.revision, 2, "The final answer belongs to the corrected request.");
  const onlyCorrected = finding.outcome === "supported" && finding.sources.length > 0 && finding.sources.every(s => s.excerpts.join(" ").includes("beta-9"));
  assert(onlyCorrected, "The final cites only corrected evidence.");
  assert.match(finding.spoken_summary, /beta-9/, "The final summary states the corrected marker.");
  assert.doesNotMatch(finding.spoken_summary, /alpha-7/, "The old marker is not published.");
  assert(
    returned.some((i: any) => i.output.includes("superseded")),
    "An old in-flight tool was superseded.",
  );
  console.log("async tools and steering: passed");

  const context = (allowedUrls: string[]) => ({
    task_id: "probe",
    revision: 1,
    call_id: randomUUID(),
    model,
    session_id: randomUUID(),
    allowedUrls: new Set(allowedUrls),
    signal: AbortSignal.timeout(15_000),
    record,
  });
  // The two checks are independent, so run them together.
  const [search, extract] = await Promise.all([
    retrieve(
      "parallel_search",
      { objective: "Find the official Node.js documentation.", search_queries: ["Node.js official documentation"] },
      context([]),
    ),
    retrieve(
      "parallel_extract",
      { objective: "What does this page say?", urls: ["https://example.com"] },
      context(["https://example.com"]),
    ),
  ]);
  for (const result of [search, extract]) {
    const excerpts = result.sources.length > 0 && result.sources.every(s => s.excerpts.some(x => x.trim()));
    assert(excerpts, "Parallel returned excerpts.");
  }
  console.log("Parallel search and extract: passed");
  record("outcome", { passed: true });
} catch (error) {
  record("outcome", { failed: String(error) });
  console.error(String(error));
  process.exitCode = 1;
} finally {
  // Wall time from each research request to its terminal event, for comparing reasoning effort settings.
  const durations: number[] = [];
  const started = new Map<string, number>();
  for (const entry of trace) {
    if (entry.type === "research.event" && entry.data.type === "response.created") {
      started.set(entry.data.response.id, Date.parse(entry.at));
    }
    if (entry.type === "responses.completed" && started.has(entry.data.response_id)) {
      durations.push(Date.parse(entry.at) - started.get(entry.data.response_id)!);
      started.delete(entry.data.response_id);
    }
  }
  const sorted = [...durations].sort((x, y) => x - y);
  record("timing", { model, effort, response_ms: durations, median_ms: sorted[Math.floor(sorted.length / 2)] ?? null });
  await writeFile(new URL("trace.json", directory), JSON.stringify(trace, null, 2) + "\n");
  console.log(`Trace: ${directory.pathname}trace.json`);
  process.exit();
}
