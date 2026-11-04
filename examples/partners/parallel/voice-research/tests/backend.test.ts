import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import { once } from "node:events";
import WebSocket, { WebSocketServer } from "ws";
import { calendar, createBackend, parseTask, retrieve, tools } from "../src/backend.ts";

const original = globalThis.fetch;
afterEach(() => {
  globalThis.fetch = original;
});
const source = { url: "https://example.org", title: "Source", excerpts: ["Evidence"], publish_date: null };
const models = { interpretation_model: "configured", research_model: "configured", research_effort: "none" };
function context() {
  const logs: any[] = [];
  return {
    task_id: "A",
    revision: 1,
    call_id: "call1",
    model: "configured",
    session_id: "session",
    allowedUrls: new Set([source.url]),
    signal: new AbortController().signal,
    record: (type: string, data: object) => logs.push({ type, data }),
    logs,
  };
}
function mock(body: unknown, check?: (body: any) => void) {
  globalThis.fetch = async (_, init) => {
    check?.(JSON.parse(String(init?.body)));
    return new Response(JSON.stringify(body), { status: 200 });
  };
}
const reply = (actions: unknown) => ({
  id: "r",
  status: "completed",
  output: [{ type: "message", content: [{ type: "output_text", text: JSON.stringify({ actions }) }] }],
});

test("Search uses V1 Turbo with task context; Extract uses V1 URLs and keeps partial errors", async () => {
  const c = context();
  mock({ results: [source], usage: [] }, b => {
    assert.equal(b.mode, "turbo");
    assert.equal(b.max_chars_total, 12000);
    assert.equal(b.session_id, "session");
  });
  assert.equal(
    (await retrieve("parallel_search", { objective: "Find evidence", search_queries: ["evidence"] }, c)).sources.length,
    1,
  );
  mock({ results: [source], errors: [{ url: "https://bad.test", error: "failed" }] }, b =>
    assert.deepEqual(b.urls, [new URL(source.url).href]),
  );
  assert.equal(
    (await retrieve("parallel_extract", { objective: "Read evidence", urls: [source.url] }, c)).errors.length,
    1,
  );
});

test("colon query: queries may contain colons; site: operators move into the objective", async () => {
  const items = (tools[0] as any).parameters.properties.search_queries.items;
  assert.equal(items.pattern, undefined);
  const c = context();
  mock({ results: [source] }, b => assert.deepEqual(b.search_queries, ["Node.js 24: release notes"]));
  await retrieve("parallel_search", { objective: "Release notes", search_queries: ["Node.js 24: release notes"] }, c);
  // A site: query must not fail or spend a retrieval from the budget.
  mock({ results: [source] }, b => {
    assert.deepEqual(b.search_queries, ['"Saturday, October 3" events', "SF events"]);
    assert.equal(b.objective, "Find events Prefer sources from sf.funcheap.com.");
  });
  const queries = ['site:sf.funcheap.com "Saturday, October 3" events', "SF events"];
  await retrieve("parallel_search", { objective: "Find events", search_queries: queries }, c);
  await assert.rejects(
    retrieve("parallel_search", { objective: "Find", search_queries: ["site:nodejs.org"] }, c),
    /keyword/,
  );
});

test("invalid arguments and unsupplied extraction URLs cannot dispatch", async () => {
  const c = context();
  globalThis.fetch = async () => {
    throw Error("must not dispatch");
  };
  await assert.rejects(
    retrieve("parallel_search", { objective: "Find", search_queries: ["x".repeat(201)] }, c),
    /keyword/,
  );
  const result = await retrieve("parallel_extract", { objective: "Read", urls: ["https://guessed.test"] }, c);
  assert.deepEqual(result.sources, []);
  assert.match(String((result.errors[0] as any).error), /not supplied/);
  assert(!c.logs.some(e => e.type === "parallel.dispatched"));
});

test("extraction variants resolve to the retrieved URL and are deduplicated", async () => {
  const c = context();
  const url = "https://www.sfstation.com/sports-fitness/calendar";
  c.allowedUrls = new Set([url]);
  mock({ results: [{ ...source, url }] }, body => assert.deepEqual(body.urls, [url]));
  const result = await retrieve(
    "parallel_extract",
    {
      objective: "Read event details",
      urls: [
        "https://sfstation.com/sports-fitness/calendar",
        "https://www.sfstation.com/sports-fitness/calendar/#saturday",
        url,
      ],
    },
    c,
  );
  assert.equal(result.sources[0].url, url);
  assert.deepEqual(result.errors, []);
});

test("a bad extraction URL cannot discard valid URLs or provider partial results", async () => {
  const c = context();
  const other = "https://example.org/other";
  c.allowedUrls.add(other);
  mock({ results: [source], errors: [{ url: other, error: "Timed out" }] }, body => {
    assert.deepEqual(body.urls, [new URL(source.url).href, other]);
  });
  const result = await retrieve(
    "parallel_extract",
    { objective: "Read", urls: [source.url, "https://unknown.test", other] },
    c,
  );
  assert.equal(result.sources.length, 1);
  assert.equal(result.errors.length, 2);
  assert.match((result.errors[0] as any).error, /not supplied/);
  assert.equal((result.errors[1] as any).error, "Timed out");
  assert.equal(c.logs.find(e => e.type === "parallel.completed").data.errors.length, 2);
});

test("URL variants preserve scheme, port, credentials, path case, and query identity", async () => {
  const c = context();
  c.allowedUrls = new Set(["https://www.example.org/Events?day=17"]);
  globalThis.fetch = async () => {
    throw Error("must not dispatch");
  };
  for (const url of [
    "http://example.org/Events?day=17",
    "https://example.org:8443/Events?day=17",
    "https://user:pass@example.org/Events?day=17",
    "https://example.org/events?day=17",
    "https://example.org/Events?day=18",
    "https://example.org.evil.test/Events?day=17",
    "not a URL",
    "javascript:alert(1)",
  ]) {
    const result = await retrieve("parallel_extract", { objective: "Read", urls: [url] }, c);
    assert.equal(result.sources.length, 0, url);
    assert.equal(result.errors.length, 1, url);
  }
  assert(!c.logs.some(e => e.type === "parallel.dispatched"));
});

test("exact retrieved URLs win; ambiguous aliases are rejected individually", async () => {
  const c = context();
  const plain = "https://example.org/page",
    www = "https://www.example.org/page/";
  c.allowedUrls = new Set([plain, www]);
  mock({ results: [{ ...source, url: www }] }, body => assert.deepEqual(body.urls, [www]));
  const result = await retrieve(
    "parallel_extract",
    { objective: "Read", urls: [www, "https://example.org/page/#section"] },
    c,
  );
  assert.equal(result.sources.length, 1);
  assert.equal(result.errors.length, 1);
  assert.match((result.errors[0] as any).error, /ambiguous/);
});

test("aborted retrieval records usage but cannot accept evidence", async () => {
  const c = context(),
    abort = new AbortController();
  c.signal = abort.signal;
  mock({ results: [source], usage: [] }, () => abort.abort());
  await assert.rejects(retrieve("parallel_search", { objective: "Find", search_queries: ["evidence"] }, c), {
    name: "AbortError",
  });
  assert(c.logs.some(e => e.type === "parallel.completed"));
});

test("empty evidence stays empty and malformed sources fail", async () => {
  const c = context();
  mock({ results: [] });
  assert.deepEqual(
    (await retrieve("parallel_search", { objective: "Find", search_queries: ["evidence"] }, c)).sources,
    [],
  );
  mock({ results: [{ url: "javascript:bad", excerpts: [] }] });
  await assert.rejects(retrieve("parallel_search", { objective: "Find", search_queries: ["evidence"] }, c));
});

test("general task shape: no location or date is needed, and constraints must be text", () => {
  const general = {
    request: "What changed in the latest Deno release?",
    location: null,
    date: null,
    constraints: ["official docs only"],
  };
  assert.deepEqual(parseTask(general), general);
  assert.throws(() => parseTask({ ...general, constraints: [true] }), /nonempty text/);
  assert.throws(() => parseTask({ ...general, date: "2026-02-30" }), /date/);
});

// Interpretation opens a spare research socket, so tests point it at an in-process peer.
async function sockets() {
  const server = new WebSocketServer({ port: 0, host: "127.0.0.1" });
  await once(server, "listening");
  const peers: WebSocket[] = [], requests: any[] = [];
  server.on("connection", peer => {
    peers.push(peer);
    peer.on("message", raw => requests.push(JSON.parse(raw.toString())));
  });
  const factory = () => new WebSocket(`ws://127.0.0.1:${(server.address() as { port: number }).port}`);
  const close = async () => {
    peers.forEach(p => p.terminate());
    await new Promise(r => server.close(r));
  };
  return { peers, requests, factory, close };
}
const until = async (done: () => boolean) => {
  for (let i = 0; i < 100 && !done(); i++) await new Promise(r => setTimeout(r, 20));
  assert(done(), "condition should settle within two seconds");
};

test("interpretation opens the next task's research socket while it runs", async () => {
  const s = await sockets();
  const b = createBackend({ today: "2026-09-30", models, record: () => {}, socketFactory: s.factory });
  const task = { request: "Compare tools", location: null, date: null, constraints: [] };
  try {
    mock(reply([{ relation: "new", target_ids: [], task, clarification: null }]));
    await b.interpret({ transcript: [], tasks: [] }, new AbortController().signal);
    await until(() => s.peers.length === 1);
    // A second interpretation keeps the same spare instead of opening another.
    await b.interpret({ transcript: [], tasks: [] }, new AbortController().signal);
    const run = b.research("A", task, 1, () => {}, () => {});
    await until(() => s.requests.length === 1);
    assert.equal(s.requests[0].type, "response.create");
    assert.equal(s.peers.length, 1, "the task uses the spare socket");
    run.cancel();
    // With the spare used, the next task opens its own socket.
    const next = b.research("B", task, 1, () => {}, () => {});
    await until(() => s.requests.length === 2);
    assert.equal(s.peers.length, 2);
    next.cancel();
  } finally {
    b.close?.();
    await s.close();
  }
});

test("closing the backend closes an unused spare socket", async () => {
  const s = await sockets();
  const b = createBackend({ today: "2026-09-30", models, record: () => {}, socketFactory: s.factory });
  try {
    mock(reply([{ relation: "unchanged", target_ids: [], task: null, clarification: null }]));
    await b.interpret({ transcript: [], tasks: [] }, new AbortController().signal);
    await until(() => s.peers.length === 1);
    const closed = once(s.peers[0], "close");
    b.close?.();
    await closed;
  } finally {
    await s.close();
  }
});

test("interpretation round-trips a general request and validates targets", async () => {
  const s = await sockets();
  const b = createBackend({ today: "2026-09-30", models, record: () => {}, socketFactory: s.factory });
  try {
    const input = { transcript: [], tasks: [] };
    const actions = [
      {
        relation: "new",
        target_ids: [],
        task: { request: "Compare tools", location: null, date: null, constraints: [] },
        clarification: null,
      },
    ];
    mock(reply(actions), body => {
      assert.deepEqual(JSON.parse(body.input[0].content), { ...input, calendar: calendar("2026-09-30") });
      assert.equal(body.store, false);
      assert.equal(body.service_tier, "priority");
    });
    assert.deepEqual((await b.interpret(input, new AbortController().signal)).actions, actions);
    mock(reply([{ ...actions[0], relation: "revision" }]));
    await assert.rejects(b.interpret(input, new AbortController().signal), /targets/);
  } finally {
    b.close?.();
    await s.close();
  }
});

test("unknown targets are rejected", async () => {
  const s = await sockets();
  const b = createBackend({ today: "2026-09-30", models, record: () => {}, socketFactory: s.factory });
  const task = { request: "Read documentation", location: null, date: null, constraints: [] };
  const input = { transcript: [], tasks: [{ task_id: "A", revision: 1, state: "researching", task }] };
  try {
    mock(reply([{ relation: "cancel", target_ids: ["unknown"], task: null, clarification: null }]));
    await assert.rejects(b.interpret(input, new AbortController().signal), /target/i);
  } finally {
    b.close?.();
    await s.close();
  }
});

test("calendar: relative dates resolve by lookup", () => {
  const days = calendar("2026-10-01");
  assert.equal(days.length, 14);
  assert.equal(days[0], "Thursday 2026-10-01");
  assert.equal(days[2], "Saturday 2026-10-03");
  assert.equal(calendar("2026-10-30")[3], "Monday 2026-11-02", "month boundaries and DST do not shift dates");
});
