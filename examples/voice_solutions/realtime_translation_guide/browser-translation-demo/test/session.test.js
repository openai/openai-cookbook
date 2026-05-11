import assert from "node:assert/strict";
import test from "node:test";

import {
  DEFAULT_INPUT_TRANSCRIPTION_MODEL,
  DEFAULT_TRANSLATION_MODEL,
  TRANSLATION_CLIENT_SECRET_URL,
  buildClientSecretRequest,
  buildSessionUpdate,
  normalizeTargetLanguage,
} from "../src/session.js";

test("normalizeTargetLanguage accepts compact BCP-47 style tags", () => {
  assert.equal(normalizeTargetLanguage(" ES "), "es");
  assert.equal(normalizeTargetLanguage("PT"), "pt");
  assert.equal(normalizeTargetLanguage("zh"), "zh");
});

test("normalizeTargetLanguage rejects missing or unsafe values", () => {
  assert.throws(() => normalizeTargetLanguage(""), /target language/i);
  assert.throws(() => normalizeTargetLanguage("english"), /language code/i);
  assert.throws(() => normalizeTargetLanguage("pt-br"), /supported target language/i);
  assert.throws(() => normalizeTargetLanguage("zh-hans"), /supported target language/i);
  assert.throws(() => normalizeTargetLanguage("../es"), /language code/i);
});

test("buildClientSecretRequest builds the current translation payload", () => {
  const request = buildClientSecretRequest({
    apiKey: "sk-test",
    targetLanguage: " ES ",
  });

  assert.equal(request.url, TRANSLATION_CLIENT_SECRET_URL);
  assert.equal(request.init.method, "POST");
  assert.equal(request.init.headers.Authorization, "Bearer sk-test");
  assert.equal(request.init.headers["Content-Type"], "application/json");

  const body = JSON.parse(request.init.body);
  assert.equal(body.session.model, DEFAULT_TRANSLATION_MODEL);
  assert.equal(body.session.audio.input.transcription.model, DEFAULT_INPUT_TRANSCRIPTION_MODEL);
  assert.equal(body.session.audio.input.noise_reduction, null);
  assert.equal(body.session.audio.output.language, "es");
  assert.equal(Object.hasOwn(body, "model"), false);
  assert.equal(Object.hasOwn(body, "max_output_tokens"), false);
  assert.equal(Object.hasOwn(body.session, "max_output_tokens"), false);
});

test("buildSessionUpdate applies input transcription after session.created", () => {
  assert.deepEqual(buildSessionUpdate({ targetLanguage: " ES " }), {
    type: "session.update",
    session: {
      audio: {
        input: {
          transcription: { model: DEFAULT_INPUT_TRANSCRIPTION_MODEL },
          noise_reduction: null,
        },
        output: { language: "es" },
      },
    },
  });
});
