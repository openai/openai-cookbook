export const DEFAULT_TRANSLATION_MODEL = "gpt-realtime-translate";
export const DEFAULT_INPUT_TRANSCRIPTION_MODEL = "gpt-realtime-whisper";
export const TRANSLATION_CLIENT_SECRET_URL =
  "https://api.openai.com/v1/realtime/translations/client_secrets";

const LANGUAGE_TAG_PATTERN = /^[a-z]{2,3}(?:-[a-z0-9]{2,8}){0,2}$/;
const SUPPORTED_TRANSLATION_LANGUAGES = new Set([
  "es",
  "pt",
  "fr",
  "ja",
  "ru",
  "zh",
  "de",
  "ko",
  "hi",
  "id",
  "vi",
  "it",
  "en",
]);

export function normalizeTargetLanguage(targetLanguage) {
  if (typeof targetLanguage !== "string" || !targetLanguage.trim()) {
    throw new Error("A target language code is required.");
  }

  const normalized = targetLanguage.trim().toLowerCase();
  if (!LANGUAGE_TAG_PATTERN.test(normalized)) {
    throw new Error("Use a compact supported target language code such as es, fr, pt, or zh.");
  }
  if (!SUPPORTED_TRANSLATION_LANGUAGES.has(normalized)) {
    throw new Error(
      "Use a supported target language code: es, pt, fr, ja, ru, zh, de, ko, hi, id, vi, it, or en.",
    );
  }

  return normalized;
}

export function buildClientSecretRequest({
  apiKey,
  targetLanguage,
  model = DEFAULT_TRANSLATION_MODEL,
  inputTranscriptionModel = DEFAULT_INPUT_TRANSCRIPTION_MODEL,
  noiseReduction = null,
}) {
  if (!apiKey) {
    throw new Error("OPENAI_API_KEY is required.");
  }

  const language = normalizeTargetLanguage(targetLanguage);
  const body = {
    session: {
      model,
      audio: {
        input: {
          transcription: { model: inputTranscriptionModel },
          noise_reduction: noiseReduction,
        },
        output: { language },
      },
    },
  };

  return {
    url: TRANSLATION_CLIENT_SECRET_URL,
    init: {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(body),
    },
    language,
    model,
  };
}

export function buildSessionUpdate({
  targetLanguage,
  inputTranscriptionModel = DEFAULT_INPUT_TRANSCRIPTION_MODEL,
  noiseReduction = null,
}) {
  return {
    type: "session.update",
    session: {
      audio: {
        input: {
          transcription: { model: inputTranscriptionModel },
          noise_reduction: noiseReduction,
        },
        output: { language: normalizeTargetLanguage(targetLanguage) },
      },
    },
  };
}

export async function createClientSecret({
  apiKey,
  targetLanguage,
  model,
  inputTranscriptionModel,
  noiseReduction,
  fetchImpl = fetch,
}) {
  const request = buildClientSecretRequest({
    apiKey,
    targetLanguage,
    model,
    inputTranscriptionModel,
    noiseReduction,
  });

  const response = await fetchImpl(request.url, request.init);
  if (!response.ok) {
    throw new OpenAIRequestError(
      response.status,
      await readResponseBodySafely(response),
    );
  }

  const data = await response.json();
  if (!data || typeof data.value !== "string") {
    throw new Error("OpenAI did not return a client secret value.");
  }

  return {
    client_secret: data.value,
    expires_at: data.expires_at ?? null,
    model: request.model,
    session: data.session ?? null,
    session_update: buildSessionUpdate({
      targetLanguage: request.language,
      inputTranscriptionModel,
      noiseReduction,
    }),
    targetLanguage: request.language,
  };
}

export class OpenAIRequestError extends Error {
  constructor(status, body) {
    super(`OpenAI request failed with status ${status}.`);
    this.name = "OpenAIRequestError";
    this.status = status;
    this.body = body;
  }
}

async function readResponseBodySafely(response) {
  try {
    return await response.text();
  } catch {
    return "";
  }
}
