import assert from "node:assert/strict";
import { once } from "node:events";
import test from "node:test";

import { buildServer, getListenHost } from "../src/server.js";

async function withServer(options, run) {
  const server = buildServer(options);
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  const { port } = server.address();
  try {
    await run(`http://127.0.0.1:${port}`);
  } finally {
    server.closeAllConnections?.();
    server.close();
    await once(server, "close");
  }
}

test("serves the browser app from the root route", async () => {
  await withServer({ env: { OPENAI_API_KEY: "sk-test" } }, async (baseUrl) => {
    const response = await fetch(`${baseUrl}/`);
    const body = await response.text();

    assert.equal(response.status, 200);
    assert.match(response.headers.get("content-type") ?? "", /text\/html/);
    assert.match(body, /In-browser Realtime Translation/);
    assert.match(body, /Choose tab to start translating/);
    assert.doesNotMatch(body, /Start translating</);
    assert.doesNotMatch(body, /OpenAI Developers/);
    assert.doesNotMatch(body, /class="topbar"/);
    assert.doesNotMatch(body, /Open a tab that is already playing audio/);
  });
});

test("uses localhost by default and allows the listen host to be configured", () => {
  assert.equal(getListenHost({}), "127.0.0.1");
  assert.equal(getListenHost({ HOST: "0.0.0.0" }), "0.0.0.0");
});

test("serves the source speech WAV as audio", async () => {
  await withServer({ env: { OPENAI_API_KEY: "sk-test" } }, async (baseUrl) => {
    const response = await fetch(`${baseUrl}/source-speech.wav`, { method: "HEAD" });

    assert.equal(response.status, 200);
    assert.match(response.headers.get("content-type") ?? "", /audio\/wav/);
  });
});

test("serves browser app code that connects to translation over WebRTC", async () => {
  await withServer({ env: { OPENAI_API_KEY: "sk-test" } }, async (baseUrl) => {
    const response = await fetch(`${baseUrl}/app.js`);
    const body = await response.text();

    assert.equal(response.status, 200);
    assert.match(body, /RTCPeerConnection/);
    assert.match(body, /realtime\/translations\/calls/);
    assert.doesNotMatch(body, /new WebSocket/);
  });
});

test("POST /session validates target language before calling OpenAI", async () => {
  let calls = 0;
  await withServer(
    {
      env: { OPENAI_API_KEY: "sk-test" },
      fetchImpl: async () => {
        calls += 1;
        throw new Error("fetch should not be called");
      },
    },
    async (baseUrl) => {
      const response = await fetch(`${baseUrl}/session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ targetLanguage: "english" }),
      });
      const body = await response.json();

      assert.equal(response.status, 400);
      assert.match(body.error, /language code/i);
      assert.equal(calls, 0);
    },
  );
});

test("POST /session returns a browser-safe client secret response", async () => {
  const requests = [];
  await withServer(
    {
      env: { OPENAI_API_KEY: "sk-test" },
      fetchImpl: async (url, init) => {
        requests.push({ url, init });
        return Response.json({
          value: "ek_test",
          expires_at: 123,
          session: { id: "sess_test" },
        });
      },
    },
    async (baseUrl) => {
      const response = await fetch(`${baseUrl}/session`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ targetLanguage: "es" }),
      });
      const body = await response.json();

      assert.equal(response.status, 200);
      assert.deepEqual(body, {
        client_secret: "ek_test",
        expires_at: 123,
        model: "gpt-realtime-translate",
        session: { id: "sess_test" },
        session_update: {
          type: "session.update",
          session: {
            audio: {
              input: {
                transcription: { model: "gpt-realtime-whisper" },
                noise_reduction: null,
              },
              output: { language: "es" },
            },
          },
        },
        targetLanguage: "es",
      });
      assert.equal(requests.length, 1);
      const requestBody = JSON.parse(requests[0].init.body);
      assert.equal(requestBody.session.model, "gpt-realtime-translate");
      assert.equal(requestBody.session.audio.output.language, "es");
      assert.deepEqual(requestBody.session.audio.input, {
        transcription: { model: "gpt-realtime-whisper" },
        noise_reduction: null,
      });
    },
  );
});
