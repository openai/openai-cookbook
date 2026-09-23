import assert from "node:assert/strict"
import { describe, it } from "node:test"

import {
  DEFAULT_INPUT_TRANSCRIPTION_MODEL,
  DEFAULT_TRANSLATION_MODEL,
  REALTIME_TRANSLATION_CLIENT_SECRET_URL,
  REALTIME_TRANSLATION_CALL_URL,
  buildSessionUpdate,
  buildTranslationClientSecretRequest,
  normalizeTranslationLanguage,
} from "../lib/realtime-translation-config.js"

describe("Realtime Translation config", () => {
  it("builds the client secret request shape", () => {
    const request = buildTranslationClientSecretRequest({
      apiKey: "sk-test",
      language: " ES ",
      inputTranscriptionEnabled: true,
      noiseReductionEnabled: true,
    })

    assert.equal(
      request.url,
      "https://api.openai.com/v1/realtime/translations/client_secrets"
    )
    assert.equal(request.init.method, "POST")
    assert.deepEqual(request.init.headers, {
      Authorization: "Bearer sk-test",
      "Content-Type": "application/json",
    })

    const body = JSON.parse(request.init.body)
    assert.deepEqual(body, {
      session: {
        model: DEFAULT_TRANSLATION_MODEL,
        audio: {
          input: {
            transcription: {
              model: DEFAULT_INPUT_TRANSCRIPTION_MODEL,
            },
            noise_reduction: { type: "near_field" },
          },
          output: {
            language: "es",
          },
        },
      },
    })
    assert.equal("type" in body.session, false)
    assert.equal("format" in body.session.audio.input, false)
    assert.equal("max_output_tokens" in body.session, false)
  })

  it("uses null noise reduction and omits transcription when disabled", () => {
    const request = buildTranslationClientSecretRequest({
      apiKey: "sk-test",
      language: "fr",
      inputTranscriptionEnabled: false,
      noiseReductionEnabled: false,
    })

    const body = JSON.parse(request.init.body)
    assert.deepEqual(body.session.audio.input, {
      noise_reduction: null,
    })
  })

  it("builds session.update without session.type", () => {
    const update = buildSessionUpdate({
      language: "vi",
      inputTranscriptionEnabled: true,
      noiseReductionEnabled: false,
    })

    assert.deepEqual(update, {
      type: "session.update",
      session: {
        audio: {
          input: {
            transcription: {
              model: DEFAULT_INPUT_TRANSCRIPTION_MODEL,
            },
            noise_reduction: null,
          },
          output: {
            language: "vi",
          },
        },
      },
    })
  })

  it("normalizes supported language codes", () => {
    assert.equal(normalizeTranslationLanguage("JA"), "ja")
    assert.throws(() => normalizeTranslationLanguage("pt-br"), /Unsupported/)
    assert.throws(() => normalizeTranslationLanguage("<script>"), /Invalid/)
  })

  it("exposes the translation WebRTC calls endpoint", () => {
    assert.equal(
      REALTIME_TRANSLATION_CALL_URL,
      "https://api.openai.com/v1/realtime/translations/calls"
    )
    assert.equal(
      REALTIME_TRANSLATION_CLIENT_SECRET_URL,
      "https://api.openai.com/v1/realtime/translations/client_secrets"
    )
  })
})
