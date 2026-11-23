import assert from "node:assert/strict";
import test from "node:test";
import type { AgentSessionEvent } from "openai/resources/beta/agents/agents";
import { parseCommand } from "../src/cli.js";
import { redact, reduceEvent, TextOutput } from "../src/events.js";
import { cleanupResources, readCredentials, retryTransient, SandboxSession, TurnState } from "../src/session.js";

test("reduces SDK events to terminal updates and ignores subagent completion", () => {
  const event = (payload: unknown) => reduceEvent(payload as AgentSessionEvent);
  assert.deepEqual(event({ type: "agent.session.environment.connected", obfuscation: "padding" }),
    { kind: "connected" });
  assert.deepEqual(event({
    type: "agent.session.turn.output_text.delta", item_id: "msg", content_index: 1, delta: "hello",
  }), { kind: "text", phase: "delta", part: "msg:1", text: "hello" });
  const command = { type: "command_execution", command: "pwd", exit_code: 0, output: "raw details" };
  assert.deepEqual(event({ type: "agent.session.turn.item.done", item: command }),
    { kind: "command", phase: "finished", command: "pwd", exitCode: 0 });
  assert.equal(event({ type: "agent.session.turn.completed", turn: { subagent_id: "sub" } }), undefined);
  assert.deepEqual(event({ type: "agent.session.turn.cancelled", turn: { subagent_id: null } }),
    { kind: "turn", outcome: "cancelled" });
  assert.deepEqual(event({ type: "agent.session.failed", session: { private: "details" } }),
    { kind: "fatal", message: "The Agents API marked the session failed." });
});

test("turn waits for root outcome and idle, in either order", () => {
  const completed = { kind: "turn", outcome: "completed" } as const;
  const idle = { kind: "idle" } as const;
  const state = new TurnState();
  assert.equal(state.update(idle), undefined); // An idle update can arrive before turn creation.
  assert.equal(state.update({ kind: "turn-started" }), undefined);
  assert.equal(state.update(completed), undefined);
  assert.equal(state.update(idle), "completed");

  const cancelled = new TurnState();
  assert.equal(cancelled.update({ kind: "turn-started" }), undefined);
  assert.equal(cancelled.update(idle), undefined);
  assert.equal(cancelled.update({ kind: "turn", outcome: "cancelled" }), "cancelled");
});

test("parses operator commands and rejects paths that leave the workspace", () => {
  assert.deepEqual(parseCommand(""), { kind: "empty" });
  assert.deepEqual(parseCommand(" write outputs/table.csv "), { kind: "prompt", text: "write outputs/table.csv" });
  for (const kind of ["status", "logs", "quit"]) assert.deepEqual(parseCommand("/" + kind), { kind });
  for (const path of ["outputs/My file.txt", "/workspace/outputs/My file.txt"]) {
    assert.deepEqual(parseCommand("/download " + path), {
      kind: "download", path: "/workspace/outputs/My file.txt",
    });
  }
  for (const command of ["/download", "/status extra", "/shell", "/download /workspace",
    "/download ../secret", "/download /workspace/../etc/passwd", "/download /workspace2/file",
    "/download outputs/evil\x00.txt"]) {
    assert.throws(() => parseCommand(command));
  }
});

test("requires two different keys and redacts secrets split across text chunks", () => {
  const applicationKey = "sk-example-application-only";
  const executorKey = "sk-example-executor-only";
  assert.throws(() => readCredentials({ OPENAI_API_KEY: applicationKey }));
  assert.throws(() => readCredentials({ OPENAI_API_KEY: applicationKey, OPENAI_EXECUTOR_API_KEY: applicationKey }),
    /distinct/);
  assert.deepEqual(readCredentials({ OPENAI_API_KEY: applicationKey, OPENAI_EXECUTOR_API_KEY: executorKey }),
    { applicationKey, executorKey });

  const remoteUrl = "https://api.openai.com/example-secret-path";
  const safe = (text: string) => redact(text, [applicationKey, executorKey, remoteUrl]);
  const chunks: string[] = [];
  const output = new TextOutput(safe, (chunk) => { chunks.push(chunk); });
  output.delta("1", "key=sk-example-");
  output.delta("1", "executor-only link=https://api.openai.");
  output.delta("1", "com/example-secret-path");
  output.done("1", "duplicate");
  output.done("2", " plain\x1b");
  assert.equal(chunks.join(""), "key=[redacted] link=[redacted] plain");
});

test("retries bounded transient failures and skips retries for permanent failures", async () => {
  let attempts = 0;
  const waits: number[] = [];
  const transient = new Error("transient");
  const delay = async (ms: number) => { waits.push(ms); };
  await assert.rejects(retryTransient(async () => {
    attempts++;
    throw transient;
  }, (error) => error === transient, delay), transient);
  assert.equal(attempts, 3);
  assert.deepEqual(waits, [250, 1_000]);

  attempts = 0;
  await assert.rejects(retryTransient(async () => {
    attempts++;
    throw new Error("permanent");
  }, () => false, delay), /permanent/);
  assert.equal(attempts, 1);
});

test("attempts session deletion after sandbox deletion fails", async () => {
  const order: string[] = [];
  const result = await cleanupResources(async () => {
    order.push("sandbox");
    throw new Error("gateway unreachable");
  }, async () => {
    order.push("session");
  });
  assert.deepEqual(order, ["sandbox", "session"]);
  assert.deepEqual(result, { sandbox: false, session: true });
});

test("shutdown is idempotent even before session creation", async () => {
  const session = new SandboxSession({
    applicationKey: "sk-example-application-only",
    executorKey: "sk-example-executor-only",
  });
  const stopped = session.stop();
  assert.equal(session.stop(), stopped);
  assert.equal(await stopped, true);
  assert.throws(() => session.start(), /closing/);
});

test("opens the SDK event stream before provisioning and cleans up on EOF", { timeout: 5_000 }, async (t) => {
  const calls: string[] = [];
  const sessionId = "session-test";
  const environmentId = "environment-test";
  const remoteUrl = "https://api.openai.com/v1";
  const applicationKey = "sk-example-application-only";
  const executorKey = "sk-example-executor-only";
  const turn = { subagent_id: null };
  const encoder = new TextEncoder();
  let submissions = 0;
  let stream!: ReadableStreamDefaultController<Uint8Array>;
  const emit = (type: string, data = {}) => {
    stream.enqueue(encoder.encode(`event: ${type}\ndata: ${JSON.stringify({ type, ...data })}\n\n`));
  };
  const session = new SandboxSession({ applicationKey, executorKey }, async (input, options) => {
    const path = new URL(String(input)).pathname;
    const method = options?.method;
    assert.equal(new Headers(options?.headers).get("authorization"), "Bearer " + applicationKey);
    if (method === "POST" && path === "/v1/agents/sessions") {
      calls.push("create session");
      return Response.json({
        id: sessionId, status: "idle", environment: {
          type: "self_hosted", id: environmentId, remote_url: remoteUrl,
        },
      });
    }
    if (path === `/v1/agents/sessions/${sessionId}/events`) {
      if (method === "GET") {
        calls.push("subscribe");
        return new Response(new ReadableStream({ start: (controller) => { stream = controller; } }), {
          headers: { "Content-Type": "text/event-stream" },
        });
      }
      assert.equal(method, "POST");
      const { events } = JSON.parse(String(options?.body));
      if (events[0].type === "agent.session.input.cancel") {
        calls.push("cancel");
        emit("agent.session.turn.cancelled", { turn });
        emit("agent.session.idle");
      } else {
        assert.equal(events[0].type, "agent.session.input.message");
        assert.ok(new Headers(options?.headers).get("idempotency-key"));
        calls.push("submit");
        emit("agent.session.turn.created", { turn });
        if (++submissions === 1) {
          emit("agent.session.turn.completed", { turn });
          emit("agent.session.idle");
        }
      }
      return new Response(null, { status: 202 });
    }
    assert.equal(method, "DELETE");
    assert.equal(path, `/v1/agents/sessions/${sessionId}`);
    calls.push("delete session");
    return Response.json({ id: sessionId, deleted: true });
  });
  t.after(async () => { await session.stop(); });
  t.mock.method(session.sandbox, "create", async (id: string, url: string, key: string) => {
    assert.deepEqual([id, url, key], [environmentId, remoteUrl, executorKey]);
    calls.push("create sandbox");
    emit("agent.session.environment.connected");
  });
  t.mock.method(session.sandbox, "delete", async () => { calls.push("delete sandbox"); });

  await session.start();
  assert.equal(await session.runTurn("test turn"), "completed");
  const running = session.runTurn("test interruption");
  await assert.rejects(session.runTurn("test overlapping input"), /already active/);
  await session.cancelTurn();
  assert.equal(await running, "cancelled");
  stream.close();
  assert.equal(await session.closing, "The Agents API event stream disconnected.");
  assert.equal(await session.stop(), true);
  assert.deepEqual(calls, [
    "create session", "subscribe", "create sandbox", "submit", "submit", "cancel",
    "delete sandbox", "delete session",
  ]);
});
