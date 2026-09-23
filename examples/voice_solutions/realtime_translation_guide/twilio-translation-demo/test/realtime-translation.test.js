import { describe, expect, it, vi } from "vitest";
import {
  buildSessionUpdate,
  buildTranslationUrl,
  createRealtimeTranslationBridge,
} from "../src/realtime-translation.js";

describe("Realtime Translation bridge", () => {
  it("selects the translation model in the direct server-side WebSocket URL", () => {
    expect(buildTranslationUrl("gpt-realtime-translate")).toBe(
      "wss://api.openai.com/v1/realtime/translations?model=gpt-realtime-translate",
    );
  });

  it("builds the translation session payload", () => {
    expect(buildSessionUpdate("es")).toEqual({
      type: "session.update",
      session: {
        audio: {
          input: {
            transcription: { model: "gpt-realtime-whisper" },
            noise_reduction: { type: "near_field" },
          },
          output: { language: "es" },
        },
      },
    });
  });

  it("opens Realtime and forwards translated audio to Twilio", () => {
    const sentToRealtime = [];
    const sentToTwilio = [];
    class FakeWebSocket {
      static instances = [];

      constructor(url, options) {
        this.url = url;
        this.options = options;
        this.readyState = FakeWebSocket.OPEN;
        this.listeners = new Map();
        FakeWebSocket.instances.push(this);
      }

      static OPEN = 1;

      on(event, handler) {
        this.listeners.set(event, handler);
      }

      send(payload) {
        sentToRealtime.push(JSON.parse(payload));
      }

      emit(event, payload) {
        this.listeners.get(event)?.(payload);
      }

      close() {}
    }

    const target = {
      streamSid: "MZ123",
      sendTwilioMedia: vi.fn((payload) => sentToTwilio.push(payload)),
    };
    const bridge = createRealtimeTranslationBridge({
      apiKey: "sk-test",
      sourceLabel: "caller-a",
      target,
      targetLanguage: "es",
      WebSocketImpl: FakeWebSocket,
    });

    const socket = FakeWebSocket.instances[0];
    expect(socket.url).toBe(
      "wss://api.openai.com/v1/realtime/translations?model=gpt-realtime-translate",
    );
    expect(socket.options.headers).toMatchObject({
      Authorization: "Bearer sk-test",
    });
    expect(Object.keys(socket.options.headers)).toEqual(["Authorization"]);

    socket.emit("open");
    expect(sentToRealtime[0]).toEqual(buildSessionUpdate("es"));

    socket.emit(
      "message",
      JSON.stringify({
        type: "session.output_audio.delta",
        delta: "AAAA",
      }),
    );
    expect(sentToTwilio).toHaveLength(1);
  });

  it("logs input and output transcript events with eval-friendly metadata", () => {
    const sentToRealtime = [];
    class FakeWebSocket {
      static instances = [];

      constructor() {
        this.readyState = FakeWebSocket.OPEN;
        this.listeners = new Map();
        FakeWebSocket.instances.push(this);
      }

      static OPEN = 1;

      on(event, handler) {
        this.listeners.set(event, handler);
      }

      send(payload) {
        sentToRealtime.push(JSON.parse(payload));
      }

      emit(event, payload) {
        this.listeners.get(event)?.(payload);
      }

      close() {}
    }

    const logger = {
      info: vi.fn(),
      warn: vi.fn(),
      error: vi.fn(),
    };
    createRealtimeTranslationBridge({
      apiKey: "sk-test",
      sourceLabel: "caller-a",
      target: { sendTwilioMedia: vi.fn() },
      targetLanguage: "de",
      WebSocketImpl: FakeWebSocket,
      logger,
    });

    const socket = FakeWebSocket.instances[0];
    socket.emit("open");
    socket.emit(
      "message",
      JSON.stringify({
        type: "conversation.item.input_audio_transcription.completed",
        item_id: "item-1",
        transcript: "hello there",
      }),
    );
    socket.emit(
      "message",
      JSON.stringify({
        type: "session.output_transcript.delta",
        response_id: "response-1",
        delta: "hallo",
      }),
    );

    expect(logger.info).toHaveBeenCalledWith(
      "[translation-transcript] " +
        JSON.stringify({
          callSid: "caller-a",
          direction: "input",
          phase: "completed",
          targetLanguage: "de",
          eventType: "conversation.item.input_audio_transcription.completed",
          itemId: "item-1",
          responseId: undefined,
          text: "hello there",
        }),
    );
    expect(logger.info).toHaveBeenCalledWith(
      "[translation-transcript] " +
        JSON.stringify({
          callSid: "caller-a",
          direction: "output",
          phase: "delta",
          targetLanguage: "de",
          eventType: "session.output_transcript.delta",
          itemId: undefined,
          responseId: "response-1",
          text: "hallo",
        }),
    );
  });
});
