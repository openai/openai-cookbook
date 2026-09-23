import { spawnSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import {
  DEFAULT_TRANSLATION_MODEL,
  createClientSecret,
} from "../src/session.js";
import { loadEnvFiles } from "../src/server.js";
import { PCM16_200MS_CHUNK_BYTES } from "../src/public/audio-chunks.js";

const TRANSLATION_WS_URL = "wss://api.openai.com/v1/realtime/translations";
const TARGET_LANGUAGE = process.env.SMOKE_TARGET_LANGUAGE ?? "es";
const PHRASE =
  process.env.SMOKE_PHRASE ??
  "Hello, this is a browser tab audio translation test.";

loadEnvFiles(process.env, process.cwd());

if (!process.env.OPENAI_API_KEY) {
  throw new Error("OPENAI_API_KEY is not configured.");
}

const session = await createClientSecret({
  apiKey: process.env.OPENAI_API_KEY,
  targetLanguage: TARGET_LANGUAGE,
  model: process.env.OPENAI_TRANSLATION_MODEL ?? DEFAULT_TRANSLATION_MODEL,
});

const audio = createSpeechPcm16(PHRASE) ?? Buffer.alloc(24_000 * 2);
const usedSpeech = audio.some((byte) => byte !== 0);
const result = await runWebSocketSmoke({ session, audio, requireOutput: usedSpeech });

console.log(
  JSON.stringify(
    {
      ok: true,
      mode: usedSpeech ? "speech" : "silence",
      targetLanguage: session.targetLanguage,
      sessionCreated: result.sessionCreated,
      outputAudioDeltas: result.outputAudioDeltas,
      outputTranscriptPreview: result.outputTranscript.slice(0, 160),
    },
    null,
    2,
  ),
);

async function runWebSocketSmoke({ session, audio, requireOutput }) {
  return new Promise((resolve, reject) => {
    const url = new URL(TRANSLATION_WS_URL);
    url.searchParams.set("model", session.model);

    const ws = new WebSocket(url, [
      `openai-insecure-api-key.${session.client_secret}`,
      "realtime",
    ]);

    const state = {
      sessionCreated: false,
      sessionUpdateSent: false,
      sessionUpdated: false,
      outputAudioDeltas: 0,
      outputTranscript: "",
      sending: false,
      sent: false,
    };
    let settled = false;

    const finish = (error) => {
      if (settled) {
        return;
      }
      settled = true;
      clearTimeout(timeout);
      ws.close();
      if (error) {
        reject(error);
        return;
      }
      resolve(state);
    };

    const timeout = setTimeout(() => {
      if (!state.sessionCreated) {
        finish(new Error("Realtime session was not created before timeout."));
        return;
      }
      if (requireOutput && state.outputAudioDeltas === 0 && !state.outputTranscript) {
        finish(new Error("Realtime session produced no translated output before timeout."));
        return;
      }
      finish();
    }, requireOutput ? 25_000 : 5_000);

    ws.addEventListener("error", () => {
      finish(new Error("Realtime WebSocket error."));
    });

    ws.addEventListener("open", () => {
      if (session.session_update) {
        ws.send(JSON.stringify(session.session_update));
        state.sessionUpdateSent = true;
      }
    });

    ws.addEventListener("message", async (message) => {
      let event;
      try {
        event = JSON.parse(await messageToText(message.data));
      } catch (error) {
        finish(error);
        return;
      }

      if (event.type === "error") {
        finish(new Error(JSON.stringify(event.error ?? event)));
        return;
      }

      if (event.type === "session.created") {
        state.sessionCreated = true;
        if (!session.session_update) {
          void sendAudioAndMaybeFinish(ws, audio, state, requireOutput, finish);
        }
      }

      if (event.type === "session.updated") {
        state.sessionUpdated = true;
        void sendAudioAndMaybeFinish(ws, audio, state, requireOutput, finish);
      }

      if (
        (event.type === "session.output_audio.delta" ||
          event.type === "response.output_audio.delta") &&
        typeof event.delta === "string"
      ) {
        state.outputAudioDeltas += 1;
      }

      if (
        (event.type === "session.output_transcript.delta" ||
          event.type === "response.output_audio_transcript.delta") &&
        typeof event.delta === "string"
      ) {
        state.outputTranscript += event.delta;
      }

      if (
        state.sessionCreated &&
        state.sent &&
        (!requireOutput || state.outputAudioDeltas > 0 || state.outputTranscript)
      ) {
        finish();
      }
    });
  });
}

async function sendAudioAndMaybeFinish(ws, audio, state, requireOutput, finish) {
  if (state.sending || state.sent) {
    return;
  }
  state.sending = true;
  try {
    await sendAudio(ws, audio);
    state.sent = true;
    if (!requireOutput || state.outputAudioDeltas > 0 || state.outputTranscript) {
      finish();
    }
  } catch (error) {
    finish(error);
  }
}

async function sendAudio(ws, audio) {
  const chunkBytes = PCM16_200MS_CHUNK_BYTES;
  for (let offset = 0; offset < audio.length; offset += chunkBytes) {
    const chunk = audio.subarray(offset, offset + chunkBytes);
    ws.send(
      JSON.stringify({
        type: "session.input_audio_buffer.append",
        audio: chunk.toString("base64"),
      }),
    );
    await delay(100);
  }

  const silence = Buffer.alloc(chunkBytes);
  for (let i = 0; i < 12; i += 1) {
    ws.send(
      JSON.stringify({
        type: "session.input_audio_buffer.append",
        audio: silence.toString("base64"),
      }),
    );
    await delay(100);
  }
}

function createSpeechPcm16(phrase) {
  if (!existsSync("/usr/bin/say") || !existsSync("/usr/bin/afconvert")) {
    return null;
  }

  const dir = mkdtempSync(path.join(tmpdir(), "browser-translation-smoke-"));
  const aiffPath = path.join(dir, "speech.aiff");
  const wavPath = path.join(dir, "speech.wav");

  try {
    const say = spawnSync("/usr/bin/say", ["-v", "Samantha", "-o", aiffPath, phrase], {
      stdio: "ignore",
    });
    if (say.status !== 0) {
      return null;
    }

    const convert = spawnSync(
      "/usr/bin/afconvert",
      ["-f", "WAVE", "-d", "LEI16@24000", aiffPath, wavPath],
      { stdio: "ignore" },
    );
    if (convert.status !== 0) {
      return null;
    }

    return extractWavData(readFileSync(wavPath));
  } finally {
    rmSync(dir, { force: true, recursive: true });
  }
}

function extractWavData(wav) {
  let offset = 12;
  while (offset + 8 <= wav.length) {
    const chunkId = wav.toString("ascii", offset, offset + 4);
    const chunkSize = wav.readUInt32LE(offset + 4);
    const dataStart = offset + 8;
    const dataEnd = dataStart + chunkSize;
    if (chunkId === "data") {
      return wav.subarray(dataStart, dataEnd);
    }
    offset = dataEnd + (chunkSize % 2);
  }
  throw new Error("Generated WAV did not contain a data chunk.");
}

async function messageToText(data) {
  if (typeof data === "string") {
    return data;
  }
  if (data instanceof ArrayBuffer) {
    return Buffer.from(data).toString("utf8");
  }
  if (ArrayBuffer.isView(data)) {
    return Buffer.from(data.buffer, data.byteOffset, data.byteLength).toString("utf8");
  }
  if (typeof data?.text === "function") {
    return data.text();
  }
  return String(data);
}

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
