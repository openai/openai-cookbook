import { test } from "node:test";
import assert from "node:assert/strict";
import { once } from "node:events";
import WebSocket, { WebSocketServer } from "ws";
import { startResearch, parseFinding, researchBudget } from "../src/research.ts";
import type { Finding, Task } from "../src/types.ts";

const task: Task = { request: "Compare alpha beta", location: null, date: null, constraints: [] };
const src = (key: string) => ({ url: `https://example.org/${key}`, title: key, publish_date: null, excerpts: [key] });
const msg = (summary = "", urls: string[] = []) => ({
  type: "message",
  status: "completed",
  content: [
    {
      type: "output_text",
      text: JSON.stringify({
        outcome: "supported",
        display_title: "Research",
        display_items: summary ? [{ heading: "", detail: summary }] : [],
        cited_urls: urls,
      }),
    },
  ],
});
const wait = () => new Promise(r => setTimeout(r, 20));

// An in-process peer stands in for the Responses WebSocket and scripts server events.
async function setup(
  deadlineMs = 1000,
  beforeOpen?: (run: ReturnType<typeof startResearch>) => void,
  initialTask = task,
) {
  const server = new WebSocketServer({ port: 0, host: "127.0.0.1" });
  await once(server, "listening");
  const connected = once(server, "connection");
  const socket = new WebSocket(`ws://127.0.0.1:${(server.address() as { port: number }).port}`);
  const findings: Finding[] = [],
    errors: Error[] = [],
    requests: any[] = [],
    logs: any[] = [],
    jobs: any[] = [];
  const run = startResearch({
    today: "2026-09-30",
    task_id: "A",
    task: initialTask,
    revision: 1,
    model: "configured",
    effort: "none",
    socket,
    deadlineMs,
    record: (type, data) => logs.push({ type, data }),
    onFinding: f => findings.push(f),
    onError: (_, e) => errors.push(e),
    retrieve: (name, args, c) => new Promise((resolve, reject) => jobs.push({ name, args, c, resolve, reject })),
  });
  beforeOpen?.(run);
  const peer = (await connected)[0] as WebSocket;
  peer.on("message", raw => requests.push(JSON.parse(raw.toString())));
  // Wait for the opening response.create rather than a fixed delay; the suite runs files in parallel.
  for (let i = 0; i < 100 && !requests.length; i++) await new Promise(r => setTimeout(r, 5));
  const send = (e: object) => peer.send(JSON.stringify(e));
  const created = (id: string) => send({ type: "response.created", response: { id } });
  const completed = (id: string, output: any[] = []) =>
    send({
      type: "response.completed",
      response: { id, status: "completed", output, usage: { input_tokens: 1, output_tokens: 1 } },
    });
  const call = (id: string, extra: Record<string, unknown> = {}, name = "parallel_search") =>
    send({
      type: "response.output_item.done",
      item: {
        type: "function_call",
        status: "completed",
        async: true,
        name,
        call_id: id,
        arguments: JSON.stringify({ objective: id, search_queries: [id], ...extra }),
      },
    });
  const waitCall = (id: string) =>
    send({
      type: "response.output_item.done",
      item: {
        type: "function_call",
        status: "completed",
        name: "wait_for_results",
        call_id: id,
        arguments: "{}",
      },
    });
  const accepted = (parent: string) =>
    send({ type: "response.steer.accepted", steer: { id: "st", previous_response_id: parent } });
  const resolve = (i: number) => jobs[i].resolve({ sources: [src(jobs[i].args.objective)], errors: [] });
  const creates = () => requests.filter(e => e.type === "response.create");
  const close = async () => {
    run.cancel();
    peer.terminate();
    await new Promise(r => server.close(r));
  };
  return {
    run,
    socket,
    findings,
    errors,
    requests,
    logs,
    jobs,
    send,
    created,
    completed,
    call,
    waitCall,
    accepted,
    resolve,
    creates,
    close,
  };
}
const outputIds = (request: any) =>
  request.input.filter((i: any) => i.type === "function_call_output").map((i: any) => i.call_id);

test("ordinary research enforces one initial lookup and one explained follow-up, then disables retrieval", async () => {
  const s = await setup(1000, undefined, { ...task, request: "Find outdoor music in San Francisco" });
  try {
    assert.deepEqual(
      s.creates()[0].tools.map((t: any) => t.name),
      ["parallel_search", "wait_for_results"],
    );
    assert.equal(s.creates()[0].text.format.schema.properties.display_items.maxItems, undefined,
      "a retrieval limit must not cap the number of findings from a lookup");
    s.created("r1");
    s.call("first");
    s.call("too-early", { missing_evidence: "date" });
    s.waitCall("w1");
    s.completed("r1");
    await wait();
    assert.equal(s.jobs.length, 1, "a second lookup cannot run before the first result is read");
    s.resolve(0);
    await wait();
    // The rejected call may have resumed the response first; finish it to deliver the initial evidence.
    if (
      !s
        .creates()
        .at(-1)
        .input.some((i: any) => i.call_id === "first")
    ) {
      s.created("yield");
      s.waitCall("wy");
      s.completed("yield");
      await wait();
    }
    const followup = s
      .creates()
      .at(-1)
      .tools.find((t: any) => t.name === "parallel_extract");
    assert(followup.parameters.required.includes("missing_evidence"));
    s.created("r2");
    s.call("unexplained");
    s.call(
      "followup",
      { missing_evidence: "The listing does not state whether the performance is outdoors.", urls: [src("first").url] },
      "parallel_extract",
    );
    s.call("third", { missing_evidence: "More variety" });
    s.waitCall("w2");
    s.completed("r2");
    await wait();
    assert.equal(s.jobs.length, 2, "only the explained follow-up is dispatched");
    s.resolve(1);
    await wait();
    if (s.creates().at(-1).tool_choice !== "none") {
      s.created("yield2");
      s.waitCall("wy2");
      s.completed("yield2");
      await wait();
    }
    assert.equal(s.creates().at(-1).tool_choice, "none");
    s.created("r3");
    s.completed("r3", [msg("Supported options", [src("first").url])]);
    await wait();
    assert.equal(s.findings.at(-1)?.kind, "final");
    assert(
      s.creates().every((r: any) => r.service_tier === "priority"),
      "initial and continuation requests use Fast mode",
    );
    assert.equal(s.errors.length, 0);
  } finally {
    await s.close();
  }
});

test("ordinary corrections reset the short budget without allowing obsolete evidence through", async () => {
  const s = await setup(1000, undefined, { ...task, request: "Find music events" });
  try {
    s.created("r1");
    s.call("old");
    s.waitCall("w1");
    s.completed("r1");
    await wait();
    s.run.update({ ...task, request: "Find indoor music on Sunday" }, 2);
    await wait();
    assert.equal(s.creates().at(-1).text.format.schema.properties.cited_urls.maxItems, 0);
    s.created("r2");
    s.call("new");
    s.waitCall("w2");
    s.completed("r2");
    await wait();
    s.resolve(0);
    s.resolve(1);
    await wait();
    s.created("r3");
    s.completed("r3", [msg("Sunday indoor event", [src("new").url])]);
    await wait();
    assert.deepEqual(
      s.findings.map(f => [f.revision, f.sources.map(v => v.title)]),
      [[2, ["new"]]],
    );
    assert(
      s.creates().every((r: any) => r.service_tier === "priority"),
      "correction continuations retain Fast mode",
    );
    assert.equal(s.jobs.length, 2);
    assert.equal(s.errors.length, 0);
  } finally {
    await s.close();
  }
});

test("broader requests keep the larger allowance and speech comes from the card findings", () => {
  for (const request of ["Compare Node.js and Deno", "Find five events", "Find 6 options", "A comprehensive review"]) {
    assert.equal(researchBudget({ ...task, request }), 4);
  }
  assert.equal(researchBudget({ ...task, request: "Any outdoor music this weekend?" }), 2);
  assert.equal(researchBudget({ ...task, request: "When is Three Sisters playing?" }), 2);
  const output = { ...msg() };
  output.content[0].text = JSON.stringify({
    outcome: "supported",
    display_title: "Music",
    display_items: [
      { heading: "First concert", detail: "Free, with RSVP." },
      { heading: "Second concert", detail: "Tickets required." },
      { heading: "Third concert", detail: "Additional card detail." },
    ],
    cited_urls: [src("a").url],
  });
  assert.equal(
    parseFinding([output], new Map([[src("a").url, src("a")]]))?.spoken_summary,
    "First concert: Free, with RSVP. Second concert: Tickets required. Third concert: Additional card detail.",
  );
});

test("a requested list longer than two keeps the larger allowance for any subject", () => {
  for (const request of ["Find three restaurants in Oakland", "List 5 Python libraries for PDFs",
    "Top 10 coffee shops in SF", "Three good bookstores near me"]) {
    assert.equal(researchBudget({ ...task, request }), 4, request);
  }
  for (const request of ["Find two restaurants", "Events after 5 pm on Sunday", "Concerts in the next 3 days",
    "What changed in Node 2 releases ago?"]) {
    assert.equal(researchBudget({ ...task, request }), 2, request);
  }
});

async function connectionSetup(failures: number, status = 503) {
  let attempts = 0;
  const server = new WebSocketServer({
    port: 0,
    host: "127.0.0.1",
    verifyClient: (_info, done) => done(++attempts > failures, status, "Test handshake failure"),
  });
  await once(server, "listening");
  const peers: WebSocket[] = [],
    requests: any[] = [],
    logs: any[] = [],
    errors: Error[] = [];
  server.on("connection", peer => {
    peers.push(peer);
    peer.on("message", raw => requests.push(JSON.parse(raw.toString())));
  });
  const run = startResearch({
    today: "2026-10-15",
    task_id: "connection",
    task,
    revision: 1,
    model: "configured",
    effort: "none",
    socketFactory: () => new WebSocket(`ws://127.0.0.1:${(server.address() as { port: number }).port}`),
    record: (type, data) => logs.push({ type, data }),
    onFinding: () => {},
    onError: (_, e) => errors.push(e),
    retrieve: async () => ({ sources: [], errors: [] }),
  });
  const until = async (done: () => boolean) => {
    for (let i = 0; i < 150 && !done(); i++) await wait();
    assert(done(), "connection condition should settle within three seconds");
  };
  const close = async () => {
    run.cancel();
    peers.forEach(p => p.terminate());
    await new Promise(r => server.close(r));
  };
  return { run, peers, requests, logs, errors, until, close, attempts: () => attempts };
}

test("a failed initial handshake retries without replaying any model request", async () => {
  const s = await connectionSetup(1);
  try {
    await s.until(() => s.requests.length === 1);
    assert.equal(s.attempts(), 2);
    assert.equal(s.errors.length, 0);
    assert.equal(s.logs.filter(e => e.type === "responses.dispatched").length, 1);
    assert.equal(s.logs.filter(e => e.type === "research.connection_retry").length, 1);
    // A dropped connection after dispatch must fail rather than reconnect and duplicate work.
    s.peers[0].terminate();
    await s.until(() => s.errors.length === 1);
    await new Promise(r => setTimeout(r, 300));
    assert.equal(s.attempts(), 2);
    assert.equal(s.requests.length, 1);
  } finally {
    await s.close();
  }
});

test("connection retries stop after three attempts and do not retry authentication failures", async () => {
  for (const status of [503, 401]) {
    const s = await connectionSetup(10, status);
    try {
      await s.until(() => s.errors.length === 1);
      assert.equal(s.attempts(), status === 503 ? 3 : 1);
      assert.match(s.errors[0].message, /Could not connect to research/);
      assert(s.errors[0].message.includes(String(status)));
      assert.equal(s.requests.length, 0);
    } finally {
      await s.close();
    }
  }
});

test("cancelling during connection backoff prevents another attempt", async () => {
  const s = await connectionSetup(10);
  try {
    await s.until(() => s.logs.some(e => e.type === "research.connection_retry"));
    s.run.cancel();
    await new Promise(r => setTimeout(r, 350));
    assert.equal(s.attempts(), 1);
    assert.equal(s.requests.length, 0);
    assert.equal(s.errors.length, 0);
  } finally {
    await s.close();
  }
});

test("an empty aggregate network error retains the underlying connection codes", async () => {
  const s = await setup();
  try {
    const nested = Object.assign(new Error(""), { code: "ETIMEDOUT" });
    s.socket.emit("error", new AggregateError([nested], ""));
    assert.match(s.errors[0].message, /ETIMEDOUT/);
    assert.match(s.logs.find(e => e.type === "responses.failed").data.message, /ETIMEDOUT/);
  } finally {
    await s.close();
  }
});

test("waiting resumes on the first result, without an intermediate answer or waiting for slower searches", async () => {
  const s = await setup();
  try {
    const tool = s.creates()[0].tools.find((t: any) => t.name === "wait_for_results");
    assert(tool && !tool.async, "waiting is synchronous so generation yields");
    s.created("r1");
    s.call("slow");
    s.call("fast");
    s.waitCall("wait1");
    s.completed("r1");
    await wait();
    assert.equal(s.creates().length, 1, "no empty continuation while all searches are pending");
    assert.equal(s.jobs.length, 2, "waiting is not a retrieval");
    s.resolve(1);
    await wait();
    assert.deepEqual(outputIds(s.creates().at(-1)), ["fast", "wait1"], "evidence precedes wait status");
    assert.equal(s.jobs[0].c.signal.aborted, false, "the slower search keeps running");
    s.created("r2");
    s.waitCall("wait2");
    s.completed("r2");
    await wait();
    assert.equal(s.creates().length, 2);
    s.resolve(0);
    await wait();
    assert.deepEqual(outputIds(s.creates().at(-1)), ["slow", "wait2"]);
    s.created("r3");
    s.completed("r3", [msg("Both results", [src("slow").url, src("fast").url])]);
    await wait();
    assert.deepEqual(
      s.findings.map(f => [f.kind, f.spoken_summary]),
      [["final", "Both results"]],
    );
    assert.equal(s.errors.length, 0);
  } finally {
    await s.close();
  }
});

test("results arriving before the wait are batched once when the response yields", async () => {
  const s = await setup();
  try {
    s.created("r1");
    s.call("a");
    s.call("b");
    await wait();
    s.resolve(0);
    s.resolve(1);
    await wait();
    s.waitCall("wait1");
    s.completed("r1");
    await wait();
    assert.deepEqual(outputIds(s.creates().at(-1)), ["a", "b", "wait1"]);
    assert.equal(s.creates().length, 2, "only one continuation is sent");
    s.created("r2");
    s.completed("r2", [msg("Both results", [src("a").url, src("b").url])]);
    await wait();
    assert.equal(s.findings.at(-1)?.kind, "final");
    assert.equal(s.errors.length, 0);
  } finally {
    await s.close();
  }
});

test("correction supersedes a pending wait and cannot return its old evidence", async () => {
  const s = await setup();
  try {
    s.created("r1");
    s.call("old");
    s.waitCall("wait1");
    s.completed("r1");
    await wait();
    s.run.update({ ...task, request: "Corrected" }, 2);
    await wait();
    const next = s.creates().at(-1);
    assert.deepEqual(outputIds(next), ["old", "wait1"]);
    assert(
      next.input
        .filter((i: any) => i.type === "function_call_output")
        .every((i: any) => JSON.parse(i.output).status === "superseded"),
    );
    s.created("r2");
    s.call("new");
    s.waitCall("wait2");
    s.completed("r2");
    await wait();
    s.resolve(0);
    await wait();
    assert.equal(s.creates().length, 2, "late obsolete results never resume the model");
    s.resolve(1);
    await wait();
    assert.deepEqual(outputIds(s.creates().at(-1)), ["new", "wait2"]);
    s.created("r3");
    s.completed("r3", [msg("New evidence", [src("new").url])]);
    await wait();
    assert.equal(s.findings.at(-1)?.revision, 2);
    assert.deepEqual(
      s.findings.at(-1)?.sources.map(v => v.title),
      ["new"],
    );
    assert.equal(s.errors.length, 0);
  } finally {
    await s.close();
  }
});

test("exhausting the retrieval budget still permits waiting for outstanding results", async () => {
  const s = await setup();
  try {
    s.created("r1");
    for (const id of ["a", "b", "c", "d"]) s.call(id);
    s.waitCall("wait1");
    s.completed("r1");
    await wait();
    s.resolve(0);
    await wait();
    const next = s.creates().at(-1);
    assert.deepEqual(
      next.tools.map((t: any) => t.name),
      ["wait_for_results"],
    );
    assert.equal(next.tool_choice, "auto");
    s.created("r2");
    s.waitCall("wait2");
    s.completed("r2");
    await wait();
    for (let i = 1; i < 4; i++) s.resolve(i);
    await wait();
    assert.deepEqual(outputIds(s.creates().at(-1)), ["b", "c", "d", "wait2"]);
    assert.equal(s.creates().at(-1).tool_choice, "none", "all evidence is delivered; only the final answer remains");
    s.created("r3");
    s.completed("r3", [msg("All results", [src("a").url])]);
    await wait();
    assert.equal(s.jobs.length, 4);
    assert.equal(s.findings.at(-1)?.kind, "final");
    assert.equal(s.errors.length, 0);
  } finally {
    await s.close();
  }
});

test("failed retrievals release the wait; cancellation suppresses late results", async () => {
  const s = await setup();
  try {
    s.created("r1");
    s.call("failed");
    s.call("good");
    s.waitCall("wait1");
    s.completed("r1");
    await wait();
    s.jobs[0].reject(new Error("Search unavailable"));
    await wait();
    assert.deepEqual(outputIds(s.creates().at(-1)), ["failed", "wait1"]);
    assert.match(s.creates().at(-1).input[0].output, /Search unavailable/);
    s.created("r2");
    s.waitCall("wait2");
    s.completed("r2");
    await wait();
    s.resolve(1);
    await wait();
    s.created("r3");
    s.completed("r3", [msg("Available evidence", [src("good").url])]);
    await wait();
    assert.equal(s.findings.at(-1)?.kind, "final");
    assert.equal(s.errors.length, 0);
  } finally {
    await s.close();
  }
  const t = await setup();
  try {
    t.created("r1");
    t.call("late");
    t.waitCall("wait1");
    t.completed("r1");
    await wait();
    t.run.cancel();
    assert(t.jobs[0].c.signal.aborted);
    t.resolve(0);
    await wait();
    assert.equal(t.creates().length, 1);
    assert.equal(t.findings.length, 0);
    assert.equal(t.errors.length, 0);
  } finally {
    await t.close();
  }
});

test("research wire flow: tools launch before completion; results return independently on original IDs", async () => {
  const s = await setup();
  try {
    assert.match(s.requests[0].instructions, /Today is Wednesday 2026-09-30\./);
    assert.equal(s.requests[0].reasoning.effort, "none");
    // Successors inherit instructions, so the objective and progress live in input messages.
    assert.doesNotMatch(s.requests[0].instructions, /Compare alpha beta|Revision \d|Remaining retrievals/);
    assert.match(s.requests[0].input[0].content, /Compare alpha beta/);
    assert(s.requests[0].input.every((item: any) => item.role !== "developer"));
    s.created("r1");
    s.call("a");
    s.call("b");
    s.call("a");
    await wait();
    assert.equal(s.jobs.length, 2, "a duplicate call ID does not relaunch");
    s.completed("r1", [msg()]);
    await wait();
    s.resolve(1);
    await wait();
    assert.equal(s.requests.at(-1).previous_response_id, "r1");
    assert.deepEqual(outputIds(s.requests.at(-1)), ["b"]);
    s.created("r2");
    s.resolve(0);
    await wait();
    assert.equal(s.creates().length, 2, "no second continuation while one is generating");
    s.completed("r2", [msg()]);
    await wait();
    assert.equal(s.requests.at(-1).previous_response_id, "r2");
    assert.deepEqual(outputIds(s.requests.at(-1)), ["a"]);
    assert.equal(s.errors.length, 0);
  } finally {
    await s.close();
  }
});

test("partial then final: the app decides finality from pending jobs", async () => {
  const s = await setup();
  try {
    s.created("r1");
    s.call("a");
    s.call("b");
    s.completed("r1", [msg()]);
    await wait();
    s.resolve(0);
    await wait();
    s.created("r2");
    s.completed("r2", [msg("Uncited guess")]);
    await wait();
    assert.equal(s.findings.length, 0, "an uncited summary while jobs are pending is not published");
  } finally {
    await s.close();
  }
  const t = await setup();
  try {
    t.created("r1");
    t.call("a");
    t.call("b");
    t.completed("r1", [msg()]);
    await wait();
    t.resolve(0);
    await wait();
    t.created("r2");
    t.completed("r2", [msg("Alpha so far", [src("a").url])]);
    await wait();
    assert.equal(t.findings.at(-1)?.kind, "partial", "b is still running");
    t.resolve(1);
    await wait();
    t.created("r3");
    t.completed("r3", [msg("Alpha and beta", [src("a").url, src("b").url])]);
    await wait();
    assert.equal(t.findings.at(-1)?.kind, "final");
    assert.deepEqual(
      t.findings.at(-1)?.sources.map(v => v.title),
      ["a", "b"],
    );
    assert.equal(t.errors.length, 0);
  } finally {
    await t.close();
  }
});

test("a ready but unsent result holds the answer instead of speaking a near-duplicate partial", async () => {
  // A partial and an almost identical final must not both be spoken.
  const s = await setup();
  try {
    s.created("r1");
    s.call("a");
    s.call("b");
    s.completed("r1", [msg()]);
    await wait();
    s.resolve(0);
    await wait();
    s.created("r2");
    s.resolve(1);
    await wait();
    s.completed("r2", [msg("Alpha so far", [src("a").url])]);
    await wait();
    assert.equal(s.findings.length, 0, "b is ready, so the next generation will refine this answer");
    assert.deepEqual(outputIds(s.requests.at(-1)), ["b"]);
    s.created("r3");
    s.completed("r3", [msg("Alpha and beta", [src("a").url, src("b").url])]);
    await wait();
    assert.deepEqual(
      s.findings.map(f => [f.kind, f.spoken_summary]),
      [["final", "Alpha and beta"]],
    );
  } finally {
    await s.close();
  }
  const t = await setup();
  try {
    t.created("r1");
    t.call("a");
    t.call("b");
    t.completed("r1", [msg()]);
    await wait();
    t.resolve(0);
    await wait();
    t.created("r2");
    t.resolve(1);
    await wait();
    t.completed("r2", [msg("Alpha so far", [src("a").url])]);
    await wait();
    t.created("r3");
    t.completed("r3", [msg()]);
    await wait();
    assert.deepEqual(t.findings, [], "new evidence requires a fresh final conclusion");
    assert.equal(t.errors.length, 1);
  } finally {
    await t.close();
  }
});

test("steer successor: corrections steer the active response and old evidence never publishes", async () => {
  const s = await setup();
  try {
    s.created("r1");
    s.call("old");
    await wait();
    s.run.update({ ...task, request: "Corrected" }, 2);
    await wait();
    const steer = s.requests.at(-1);
    assert.deepEqual(Object.keys(steer).sort(), ["input", "previous_response_id", "type"]);
    assert.equal(steer.type, "response.steer");
    assert.equal(steer.previous_response_id, "r1");
    assert(s.jobs[0].c.signal.aborted, "obsolete retrieval is aborted");
    s.accepted("r1");
    const steered = { id: "r1", status: "incomplete", incomplete_details: { reason: "steered" } };
    s.send({ type: "response.incomplete", response: steered });
    s.created("r2");
    s.call("new");
    await wait();
    assert.equal(s.jobs[1].c.revision, 2);
    s.jobs[0].resolve({ sources: [src("old")], errors: [] });
    s.completed("r2", [msg()]);
    await wait();
    // The old call's superseded marker and nothing else goes back.
    assert.deepEqual(outputIds(s.requests.at(-1)), ["old"]);
    assert.match(s.requests.at(-1).input[0].output, /superseded/);
    s.created("r3");
    s.completed("r3", [msg("Stale", [src("old").url])]);
    await wait();
    assert.equal(s.findings.length, 0);
    assert.match(s.errors[0]?.message ?? "", /citation/, "citing old evidence fails the run");
  } finally {
    await s.close();
  }
});

test("steer pending once: repeated pending notices produce one continuation with superseded markers", async () => {
  const s = await setup();
  try {
    s.created("r1");
    s.call("a");
    await wait();
    s.run.update({ ...task, request: "Corrected" }, 2);
    s.accepted("r1");
    s.completed("r1", [msg()]);
    const pending = {
      type: "response.steer.pending",
      steer: { id: "st", previous_response_id: "r1" },
      reason: "waiting_for_required_input",
      required_input: [{ type: "function_call_output", call_id: "a" }],
    };
    s.send(pending);
    s.send(pending);
    await wait();
    assert.equal(s.creates().length, 2);
    const continuation = s.creates().at(-1);
    assert.equal(continuation.previous_response_id, "r1");
    assert.deepEqual(outputIds(continuation), ["a"]);
    assert.match(continuation.input[0].output, /superseded/);
    assert(!continuation.input.some((i: any) => i.role === "user"), "the accepted steer is not repeated");
    s.created("r2");
    s.call("fresh");
    s.completed("r2", [msg()]);
    await wait();
    s.resolve(1);
    await wait();
    s.created("r3");
    s.completed("r3", [msg("Current evidence", [src("fresh").url])]);
    await wait();
    assert.equal(s.findings.at(-1)?.revision, 2);
    assert.equal(s.errors.length, 0);
  } finally {
    await s.close();
  }
});

test("steer failure codes: uncommitted steers continue with the latest objective; other codes fail", async () => {
  for (const code of ["response_already_completed", "successor_creation_failed", "invalid_input"]) {
    const s = await setup();
    try {
      s.created("r1");
      await wait();
      s.run.update({ ...task, request: "Corrected" }, 2);
      await wait();
      const steer = s.requests.at(-1);
      s.accepted("r1");
      s.completed("r1", [msg()]);
      s.send({
        type: "response.steer.failed",
        steer: { id: "st", previous_response_id: "r1", input: steer.input },
        error: { code, message: code },
      });
      await wait();
      if (code === "invalid_input") {
        assert.equal(s.errors.length, 1, code);
        continue;
      }
      const retry = s.requests.at(-1);
      assert.equal(retry.type, "response.create", code);
      assert.equal(retry.previous_response_id, "r1");
      assert.deepEqual(
        retry.input.filter((i: any) => i.role === "user"),
        [{ role: "user", content: steer.input }],
      );
      assert.equal(retry.tool_choice, "auto");
      assert.equal(s.errors.length, 0);
    } finally {
      await s.close();
    }
  }
});

test("superseded bundled: a correction between responses sends one continuation with every marker", async () => {
  const s = await setup();
  try {
    s.created("r1");
    s.call("a");
    s.call("b");
    s.completed("r1", [msg()]);
    await wait();
    const before = s.creates().length;
    s.run.update({ ...task, request: "Corrected" }, 2);
    await wait();
    const sent = s.creates().slice(before);
    assert.equal(sent.length, 1);
    assert.deepEqual(outputIds(sent[0]).sort(), ["a", "b"]);
    assert(sent[0].input.some((i: any) => i.role === "user" && /Corrected/.test(i.content)));
    s.resolve(0);
    await wait();
    assert.equal(s.creates().length, before + 1, "late old results are not sent again");
  } finally {
    await s.close();
  }
});

test("each correction records whether it steered the active response or went with the next request", async () => {
  const applied = (s: Awaited<ReturnType<typeof setup>>) =>
    s.logs
      .filter(e => e.type === "research.revision_applied")
      .map(e => [e.data.revision, e.data.via, e.data.response_id]);
  const steered = await setup();
  try {
    steered.created("r1");
    steered.call("old");
    await wait();
    steered.run.update({ ...task, request: "Corrected" }, 2);
    await wait();
    steered.accepted("r1");
    steered.created("r2");
    await wait();
    assert.deepEqual(applied(steered), [[2, "steer", "r2"]]);
  } finally {
    await steered.close();
  }
  const between = await setup();
  try {
    between.created("r1");
    between.call("a");
    between.completed("r1", [msg()]);
    await wait();
    between.run.update({ ...task, request: "Corrected" }, 2);
    await wait();
    between.created("r2");
    await wait();
    assert.deepEqual(applied(between), [[2, "next_request", "r2"]]);
  } finally {
    await between.close();
  }
});

test("budget: excess calls get an error result and later continuations disable tools", async () => {
  const s = await setup();
  try {
    s.created("r1");
    for (const id of ["a", "b", "c", "d", "e"]) s.call(id);
    await wait();
    assert.equal(s.jobs.length, 4);
    s.completed("r1", [msg()]);
    await wait();
    const rejected = s.requests.at(-1);
    assert.deepEqual(outputIds(rejected), ["e"]);
    assert.match(rejected.input[0].output, /budget exhausted/);
    assert.equal(rejected.tool_choice, "auto");
    assert.deepEqual(
      rejected.tools.map((t: any) => t.name),
      ["wait_for_results"],
    );
    s.created("r2");
    for (let i = 0; i < 4; i++) s.resolve(i);
    await wait();
    s.completed("r2", [msg()]);
    await wait();
    s.created("r3");
    s.completed("r3", [msg("Available evidence", [src("a").url])]);
    await wait();
    assert.equal(s.findings.at(-1)?.kind, "final");
    assert.equal(s.errors.length, 0);
  } finally {
    await s.close();
  }
});

test("a correction during a tools-off response waits for it, then restores tools", async () => {
  const s = await setup();
  try {
    s.created("r1");
    for (const id of ["a", "b", "c", "d"]) s.call(id);
    s.completed("r1", [msg()]);
    await wait();
    for (let i = 0; i < 4; i++) s.resolve(i);
    await wait();
    s.created("r2");
    await wait();
    assert.equal(s.creates().at(-1).tool_choice, "none");
    s.run.update({ ...task, request: "New objective" }, 2);
    await wait();
    assert(!s.requests.some(e => e.type === "response.steer"), "a tools-off response is not steered");
    s.completed("r2", [msg("Old answer", [src("a").url])]);
    await wait();
    assert.equal(s.findings.length, 0);
    assert.equal(s.creates().at(-1).tool_choice, "auto");
    assert.equal(s.creates().at(-1).previous_response_id, "r2");
    s.created("r3");
    s.call("new");
    await wait();
    assert.equal(s.jobs.length, 5);
    assert.equal(s.jobs[4].c.revision, 2);
  } finally {
    await s.close();
  }
});

test("citation gate: guessed citations and uncited terminal answers fail; commentary is skipped", async () => {
  const evidence = new Map([[src("a").url, src("a")]]);
  assert.deepEqual(parseFinding([msg("A", [src("a").url])], evidence)?.cited_urls, [src("a").url]);
  assert.throws(() => parseFinding([msg("Bad", ["https://fake.test"])], evidence), /citation/);
  const commentary = { ...msg(), phase: "commentary" };
  commentary.content[0].text = "Waiting ⏳";
  assert.equal(parseFinding([commentary, msg("A", [src("a").url])], evidence)?.spoken_summary, "A");
  for (const retrieved of [false, true]) {
    const s = await setup();
    try {
      s.created("r1");
      if (retrieved) {
        s.call("a");
        s.completed("r1", [msg()]);
        await wait();
        s.jobs[0].resolve({ sources: [], errors: [] });
        await wait();
        s.created("r2");
      }
      s.completed(retrieved ? "r2" : "r1", [msg("I could not find supporting evidence.")]);
      await wait();
      assert.equal(s.findings.length, 0);
      assert.match(s.errors[0]?.message ?? "", /supported answer/);
    } finally {
      await s.close();
    }
  }
});

for (const mode of ["failed", "idle", "timeout", "cancel"] as const) {
  test(`research lifecycle ${mode}`, async () => {
    const s = await setup(70);
    try {
      if (mode === "timeout") {
        await new Promise(r => setTimeout(r, 100));
        assert.match(s.errors[0]?.message ?? "", /timed out/);
        return;
      }
      s.created("r1");
      await wait();
      if (mode === "failed") s.send({ type: "response.failed", response: { id: "r1", status: "failed" } });
      if (mode === "idle") s.completed("r1", [msg()]);
      if (mode === "cancel") s.run.cancel();
      await wait();
      assert.equal(s.findings.length, 0);
      assert.equal(s.errors.length, mode === "cancel" ? 0 : 1);
      assert(s.logs.every(e => e.type !== "responses.completed" || e.data.response_id === "r1"));
    } finally {
      await s.close();
    }
  });
}

test("a correction during the WebSocket handshake folds into the opening request", async () => {
  const s = await setup(1000, run => run.update({ ...task, request: "Corrected" }, 2));
  try {
    assert.equal(s.errors.length, 0);
    assert.equal(s.creates().length, 1);
    assert.match(s.creates()[0].input[0].content, /Corrected/);
    s.created("r1");
    await wait();
    assert.equal(s.creates().length, 1, "no second request follows");
    assert(!s.requests.some(e => e.type === "response.steer"));
  } finally {
    await s.close();
  }
});

test("a held answer cannot finalize after tool-only continuations and an empty terminal response", async () => {
  const s = await setup();
  try {
    s.created("r1");
    s.call("a");
    s.call("b");
    s.completed("r1", [msg()]);
    await wait();
    s.resolve(0);
    await wait();
    s.created("r2");
    s.resolve(1);
    await wait();
    s.completed("r2", [msg("Alpha so far", [src("a").url])]);
    await wait();
    s.created("r3");
    s.call("c");
    s.completed("r3", [msg()]);
    await wait();
    assert.equal(s.findings.length, 0, "nothing pending was ready, so the answer is still held");
    s.resolve(2);
    await wait();
    s.created("r4");
    s.completed("r4", [msg()]);
    await wait();
    assert.deepEqual(s.findings, [], "newer tool evidence cannot implicitly endorse the old held answer");
    assert.equal(s.errors.length, 1);
  } finally {
    await s.close();
  }
});

test("cancelling before the socket opens records nothing, since no request was sent", async () => {
  const server = new WebSocketServer({ port: 0, host: "127.0.0.1" });
  await once(server, "listening");
  const socket = new WebSocket(`ws://127.0.0.1:${(server.address() as { port: number }).port}`);
  const logs: any[] = [];
  const run = startResearch({
    today: "2026-09-30",
    task_id: "A",
    task,
    revision: 1,
    model: "configured",
    effort: "none",
    socket,
    record: (type, data) => logs.push({ type, data }),
    onFinding: () => {},
    onError: () => {},
    retrieve: () => new Promise(() => {}),
  });
  run.cancel();
  await wait();
  assert(!logs.some(e => e.type === "responses.failed" || e.type === "responses.dispatched"));
  await new Promise(r => server.close(r));
});

test("cancelling while a request or steer is in flight records unknown usage", async () => {
  for (const steering of [false, true]) {
    const s = await setup();
    try {
      if (steering) {
        s.created("r1");
        await wait();
        s.run.update({ ...task, request: "Corrected" }, 2);
        s.accepted("r1");
        await wait();
      }
      s.run.cancel();
      const label = steering ? "steer successor" : "opening request";
      assert(
        s.logs.some(e => e.type === "responses.failed" && e.data.aborted),
        label,
      );
    } finally {
      await s.close();
    }
  }
});

test("supplied URL parsing drops prose delimiters but preserves balanced URL punctuation", async () => {
  const { suppliedUrls } = await import("../src/research.ts");
  assert.deepEqual(suppliedUrls("Read https://example.com. Then (https://example.org/a_(b))."), [
    "https://example.com/",
    "https://example.org/a_(b)",
  ]);
  assert.deepEqual(suppliedUrls("Read <https://example.com/file.>"), ["https://example.com/file."]);
});

test("a token-limited response returns completed tool results once and finishes without new tools", async () => {
  const s = await setup();
  try {
    s.created("r1");
    s.call("a");
    await wait();
    s.send({
      type: "response.incomplete",
      response: { id: "r1", status: "incomplete", incomplete_details: { reason: "max_output_tokens" }, output: [] },
    });
    await wait();
    assert.equal(s.errors.length, 0);
    assert.equal(s.findings.length, 0);
    s.resolve(0);
    await wait();
    assert.deepEqual(outputIds(s.requests.at(-1)), ["a"]);
    assert.equal(s.requests.at(-1).tool_choice, "none");
    s.created("r2");
    s.completed("r2", [msg("Supported A", [src("a").url])]);
    await wait();
    assert.equal(s.findings.at(-1)?.kind, "final");
    assert.equal(s.jobs.length, 1);
  } finally {
    await s.close();
  }
});

test("citations are constrained to retrieved URLs without a repair generation", async () => {
  const s = await setup();
  try {
    assert.equal(s.creates()[0].text.format.schema.properties.cited_urls.maxItems, 0);
    s.created("r1");
    s.call("calendar");
    s.completed("r1");
    await wait();
    s.resolve(0);
    await wait();
    assert.deepEqual(s.creates().at(-1).text.format.schema.properties.cited_urls.items.enum, [src("calendar").url]);
    s.created("r2");
    s.completed("r2", [msg("Event details", ["https://example.org/event-linked-in-excerpt"])]);
    await wait();
    assert.equal(s.findings.length, 0, "a malformed provider output still cannot publish");
    assert.match(s.errors[0]?.message ?? "", /citation/);
    assert.equal(s.creates().length, 2, "never generates a second answer to repair a citation");
  } finally {
    await s.close();
  }
});

test("citation choices grow with evidence and reset on correction", async () => {
  const s = await setup();
  try {
    s.created("r1");
    s.call("old");
    s.completed("r1");
    await wait();
    s.resolve(0);
    await wait();
    assert.deepEqual(s.creates().at(-1).text.format.schema.properties.cited_urls.items.enum, [src("old").url]);
    s.created("r2");
    s.call("second");
    s.completed("r2");
    await wait();
    s.resolve(1);
    await wait();
    assert.deepEqual(s.creates().at(-1).text.format.schema.properties.cited_urls.items.enum, [
      src("old").url,
      src("second").url,
    ]);
    s.created("r3");
    await wait();
    s.run.update({ ...task, request: "Find Sunday events" }, 2);
    await wait();
    s.completed("r3");
    await wait();
    s.created("r4");
    s.call("new");
    s.completed("r4");
    await wait();
    s.resolve(2);
    await wait();
    assert.deepEqual(s.creates().at(-1).text.format.schema.properties.cited_urls.items.enum, [src("new").url]);
    s.created("r5");
    s.completed("r5", [msg("Sunday", [src("new").url])]);
    await wait();
    assert.equal(s.findings.at(-1)?.revision, 2);
    assert.equal(s.errors.length, 0);
  } finally {
    await s.close();
  }
});

test("a later abstention replaces a supported partial, including when citations are empty", async () => {
  for (const cited of [false, true]) {
    const s = await setup();
    try {
      s.created("r1");
      s.call("a");
      s.call("b");
      s.completed("r1");
      await wait();
      s.resolve(0);
      await wait();
      s.created("r2");
      s.completed("r2", [msg("I recommend the Sunday event.", [src("a").url])]);
      await wait();
      s.jobs[1].resolve({ sources: [{ ...src("b"), excerpts: ["The event is cancelled."] }], errors: [] });
      await wait();
      s.created("r3");
      const conclusion = msg("The listings conflict. I cannot recommend this event.", cited ? [src("b").url] : []);
      conclusion.content[0].text = JSON.stringify({
        ...JSON.parse(conclusion.content[0].text),
        outcome: "insufficient_evidence",
      });
      s.completed("r3", [conclusion]);
      await wait();
      assert.equal(s.findings.at(-1)?.spoken_summary, "The listings conflict. I cannot recommend this event.");
      assert.equal(s.findings.at(-1)?.kind, "final");
      assert.deepEqual(
        s.findings.at(-1)?.sources.map(v => v.url),
        cited ? [src("b").url] : [],
      );
      assert.equal(s.errors.length, 0);
    } finally {
      await s.close();
    }
  }
});

test("an empty terminal response cannot finalize a recommendation made before new evidence", async () => {
  const s = await setup();
  try {
    s.created("r1");
    s.call("a");
    s.call("b");
    s.completed("r1");
    await wait();
    s.resolve(0);
    await wait();
    s.created("r2");
    s.completed("r2", [msg("Early recommendation", [src("a").url])]);
    await wait();
    s.resolve(1);
    await wait();
    s.created("r3");
    s.completed("r3");
    await wait();
    assert.equal(s.findings.filter(f => f.kind === "final").length, 0);
    assert.equal(s.errors.length, 1);
  } finally {
    await s.close();
  }
});

test("explicit insufficient evidence completes without inventing sources", async () => {
  const s = await setup();
  try {
    s.created("r1");
    s.call("a");
    s.completed("r1");
    await wait();
    s.jobs[0].resolve({ sources: [], errors: [] });
    await wait();
    s.created("r2");
    const conclusion = msg("No listing confirms the requested date.");
    conclusion.content[0].text = JSON.stringify({
      ...JSON.parse(conclusion.content[0].text),
      outcome: "insufficient_evidence",
    });
    s.completed("r2", [conclusion]);
    await wait();
    assert.equal(s.findings.at(-1)?.kind, "final");
    assert.deepEqual(s.findings.at(-1)?.sources, []);
    assert.equal(s.errors.length, 0);
  } finally {
    await s.close();
  }
});

test("a socket that is already open starts the request without waiting for another open event", async () => {
  const server = new WebSocketServer({ port: 0, host: "127.0.0.1" });
  await once(server, "listening");
  const requests: any[] = [];
  server.on("connection", peer => peer.on("message", raw => requests.push(JSON.parse(raw.toString()))));
  const socket = new WebSocket(`ws://127.0.0.1:${(server.address() as { port: number }).port}`);
  await once(socket, "open");
  const run = startResearch({
    today: "2026-10-15", task_id: "warm", task, revision: 1, model: "configured", effort: "none",
    socketFactory: () => socket, record: () => {}, onFinding: () => {}, onError: () => {},
    retrieve: async () => ({ sources: [], errors: [] }),
  });
  try {
    for (let i = 0; i < 50 && !requests.length; i++) await wait();
    assert.equal(requests.length, 1);
    assert.equal(requests[0].type, "response.create");
  } finally {
    run.cancel();
    await new Promise(r => server.close(r));
  }
});
