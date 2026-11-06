import test from "node:test";
import assert from "node:assert/strict";
import { createUpdatePreparer } from "../src/live-updates.ts";

const overlong = "界".repeat(510);
const shortened = "Concise finding, with reservations required.";

function setup(counts: Record<string, number>, summary = shortened) {
  const requests: { path: string; body: any }[] = [],
    events: { type: string; data: any }[] = [];
  const prepare = createUpdatePreparer({
    voiceModel: "voice-configured",
    researchModel: "research-configured",
    effort: "none",
    record: (type, data) => events.push({ type, data }),
    fetch: async (url, options) => {
      const body = JSON.parse(String(options!.body)),
        path = String(url);
      requests.push({ path, body });
      if (path.endsWith("/input_tokens")) {
        assert.equal(body.model, "voice-configured");
        assert.equal(typeof body.input, "string");
        return Response.json({ input_tokens: counts[body.input] });
      }
      assert.equal(body.model, "research-configured");
      assert.equal(body.store, false);
      assert.equal(body.tools, undefined);
      return Response.json({
        id: "shortening",
        status: "completed",
        service_tier: "priority",
        usage: { input_tokens: 800, output_tokens: 50 },
        output: [{ type: "message", content: [{ type: "output_text", text: summary }] }],
      });
    },
  });
  return { prepare, requests, events, summary };
}

test("a short UTF-8 update needs no counting request", async () => {
  const s = setup({});
  const content = "é".repeat(250);
  assert.deepEqual(await s.prepare(content, new AbortController().signal, {}), [content]);
  assert.equal(s.requests.length, 0);
});

test("a summary over 500 bytes is preserved when its provider count fits, including the label", async () => {
  const content = "Final result: " + "A qualified finding. ".repeat(40);
  assert(Buffer.byteLength(content) > 500);
  const s = setup({ [content]: 300 });
  assert.deepEqual(await s.prepare(content, new AbortController().signal, {}), [content]);
  assert.equal(s.requests.length, 1, "no answer-writing call for a fitting update");
});

test("all complete finding chunks are checked before returning, with qualifications intact", async () => {
  const parts = [
    "Final result: " + "First event requires registration. ".repeat(8),
    "Final result: " + "Second event is not yet confirmed. ".repeat(8),
  ];
  const combined = parts.join(" ");
  const s = setup({ [combined]: 501, [parts[0]]: 500, [parts[1]]: 499 });
  assert.deepEqual(await s.prepare(combined, new AbortController().signal, {}, parts), parts);
  assert.equal(s.requests.length, 1);
});

test("a single oversized finding gets one tools-free shortening", async () => {
  const s = setup({ [overlong]: 510 });
  assert.deepEqual(await s.prepare(overlong, new AbortController().signal, { task_id: "A", revision: 3 }), [
    s.summary,
  ]);
  assert.equal(s.requests.filter(r => r.path.endsWith("/responses")).length, 1);
  assert(
    s.events.some(
      e =>
        e.type === "responses.completed" &&
        e.data.task_id === "A" &&
        e.data.revision === 3 &&
        e.data.usage.output_tokens === 50,
    ),
  );
});

test("an oversized or empty shortened result fails without returning truncated or partial content", async () => {
  for (const summary of [overlong, ""]) {
    const s = setup({ [overlong]: 510 }, summary);
    await assert.rejects(
      () => Promise.resolve(s.prepare(overlong, new AbortController().signal, {})),
      /complete voice update/,
    );
    assert.equal(s.requests.filter(r => r.path.endsWith("/responses")).length, 1);
  }
});

test("unavailable or malformed counting fails closed and forwards cancellation", async () => {
  for (const response of [new Response("", { status: 503 }), Response.json({}), Response.json({ input_tokens: -1 })]) {
    const prepare = createUpdatePreparer({
      voiceModel: "voice-configured",
      researchModel: "research-configured",
      effort: "none",
      record() {},
      fetch: async () => response,
    });
    await assert.rejects(() => Promise.resolve(prepare(overlong, new AbortController().signal, {})));
  }
  const abort = new AbortController();
  const prepare = createUpdatePreparer({
    voiceModel: "voice-configured",
    researchModel: "research-configured",
    effort: "none",
    record() {},
    fetch: async (_url, options) => {
      assert(options?.signal);
      abort.abort();
      assert(options.signal.aborted);
      throw options.signal.reason;
    },
  });
  await assert.rejects(() => Promise.resolve(prepare(overlong, abort.signal, {})));
});
