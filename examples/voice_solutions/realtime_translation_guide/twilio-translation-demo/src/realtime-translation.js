import WebSocket from "ws";
import {
  realtimeAudioToTwilioMedia,
  twilioMediaToRealtimeAudio,
} from "./audio.js";

export const DEFAULT_TRANSLATION_MODEL = "gpt-realtime-translate";
export const DEFAULT_INPUT_TRANSCRIPTION_MODEL = "gpt-realtime-whisper";
export const TRANSLATION_ENDPOINT =
  "wss://api.openai.com/v1/realtime/translations";

const INPUT_TRANSCRIPT_EVENTS = new Set([
  "conversation.item.input_audio_transcription.delta",
  "conversation.item.input_audio_transcription.completed",
  "session.input_transcript.delta",
  "session.input_transcript.completed",
  "session.input_transcript.done",
]);

const OUTPUT_TRANSCRIPT_EVENTS = new Set([
  "session.output_transcript.delta",
  "session.output_transcript.completed",
  "session.output_transcript.done",
  "response.output_audio_transcript.delta",
  "response.output_audio_transcript.done",
]);

export function buildTranslationUrl(model = DEFAULT_TRANSLATION_MODEL) {
  const url = new URL(TRANSLATION_ENDPOINT);
  url.searchParams.set("model", model);
  return url.toString();
}

export function buildSessionUpdate(targetLanguage) {
  return {
    type: "session.update",
    session: {
      audio: {
        input: {
          transcription: { model: DEFAULT_INPUT_TRANSCRIPTION_MODEL },
          noise_reduction: { type: "near_field" },
        },
        output: { language: targetLanguage },
      },
    },
  };
}

export function createRealtimeTranslationBridge({
  apiKey,
  model = DEFAULT_TRANSLATION_MODEL,
  sourceLabel,
  target,
  targetLanguage,
  WebSocketImpl = WebSocket,
  logger = console,
}) {
  if (!apiKey) {
    throw new Error("OPENAI_API_KEY is required.");
  }
  if (!targetLanguage) {
    throw new Error("targetLanguage is required.");
  }

  const socket = new WebSocketImpl(buildTranslationUrl(model), {
    headers: {
      Authorization: `Bearer ${apiKey}`,
    },
  });
  const pendingEvents = [];

  const sendEvent = (event) => {
    const payload = JSON.stringify(event);
    if (socket.readyState === 1) {
      socket.send(payload);
      return;
    }
    pendingEvents.push(payload);
  };

  socket.on("open", () => {
    socket.send(JSON.stringify(buildSessionUpdate(targetLanguage)));
    while (pendingEvents.length > 0) {
      socket.send(pendingEvents.shift());
    }
    logger.info?.(`[translation:${sourceLabel}] connected -> ${targetLanguage}`);
  });

  socket.on("message", (data) => {
    const text = Buffer.isBuffer(data) ? data.toString("utf8") : String(data);
    let event;
    try {
      event = JSON.parse(text);
    } catch {
      logger.warn?.(`[translation:${sourceLabel}] non-JSON message`, text);
      return;
    }

    if (event.type === "session.output_audio.delta" && typeof event.delta === "string") {
      target.sendTwilioMedia(realtimeAudioToTwilioMedia(event.delta));
      return;
    }

    if (
      logTranscriptEvent({
        direction: transcriptDirection(event.type),
        event,
        logger,
        sourceLabel,
        targetLanguage,
      })
    ) {
      return;
    }

    if (event.type === "error") {
      logger.error?.(`[translation:${sourceLabel}]`, event.error ?? event);
    }
  });

  socket.on("close", () => {
    logger.info?.(`[translation:${sourceLabel}] closed`);
  });

  socket.on("error", (error) => {
    logger.error?.(`[translation:${sourceLabel}] websocket error`, error);
  });

  return {
    sendTwilioMedia(payload) {
      if (!payload) {
        return;
      }
      sendEvent({
        type: "session.input_audio_buffer.append",
        audio: twilioMediaToRealtimeAudio(payload),
      });
    },
    close() {
      socket.close();
    },
  };
}

function transcriptDirection(eventType) {
  if (INPUT_TRANSCRIPT_EVENTS.has(eventType)) {
    return "input";
  }
  if (OUTPUT_TRANSCRIPT_EVENTS.has(eventType)) {
    return "output";
  }
  return null;
}

function logTranscriptEvent({
  direction,
  event,
  logger,
  sourceLabel,
  targetLanguage,
}) {
  if (!direction) {
    return false;
  }

  const text = transcriptText(event);
  if (!text) {
    return false;
  }

  logger.info?.(
    "[translation-transcript] " +
      JSON.stringify({
        callSid: sourceLabel,
        direction,
        phase: transcriptPhase(event.type),
        targetLanguage,
        eventType: event.type,
        itemId: event.item_id,
        responseId: event.response_id,
        text,
      }),
  );
  return true;
}

function transcriptText(event) {
  if (typeof event.delta === "string") {
    return event.delta;
  }
  if (typeof event.transcript === "string") {
    return event.transcript;
  }
  if (typeof event.text === "string") {
    return event.text;
  }
  return "";
}

function transcriptPhase(eventType) {
  if (eventType.endsWith(".delta")) {
    return "delta";
  }
  if (eventType.endsWith(".completed")) {
    return "completed";
  }
  if (eventType.endsWith(".done")) {
    return "done";
  }
  return "unknown";
}
