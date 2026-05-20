import Fastify from "fastify";
import formBody from "@fastify/formbody";
import websocket from "@fastify/websocket";
import dotenv from "dotenv";
import { fileURLToPath } from "node:url";
import { languageLabelForCode } from "./languages.js";
import {
  DEFAULT_TRANSLATION_MODEL,
  createRealtimeTranslationBridge,
} from "./realtime-translation.js";
import { TranslationRoom } from "./room.js";
import {
  busyTwiml,
  chooseLanguageTwiml,
  incomingCallTwiml,
  rejectedCallerTwiml,
} from "./twiml.js";
import {
  isAllowedCaller,
  maxActiveCallers,
  validateTwilioRequest,
} from "./security.js";

dotenv.config();

export function buildApp(env = process.env, logger = console) {
  const app = Fastify({ logger: false });
  const room = new TranslationRoom({
    logger,
    createBridge: (options) =>
      createRealtimeTranslationBridge({
        ...options,
        apiKey: env.OPENAI_API_KEY,
        model: env.OPENAI_TRANSLATION_MODEL ?? DEFAULT_TRANSLATION_MODEL,
        logger,
      }),
  });

  app.register(formBody);
  app.register(websocket);

  app.get("/", async () => ({
    ok: true,
    service: "twilio-realtime-translation-demo",
    status: room.status(),
  }));

  app.get("/status", async () => room.status());

  app.all("/incoming-call", async (request, reply) => {
    if (!validateTwilioRequest(request, env)) {
      reply.code(403).send("Invalid Twilio signature");
      return;
    }

    if (!isAllowedCaller(request.body?.From, env.ALLOWED_CALLER_NUMBERS)) {
      reply.type("text/xml").send(rejectedCallerTwiml());
      return;
    }

    reply.type("text/xml").send(incomingCallTwiml());
  });

  app.all("/choose-language", async (request, reply) => {
    if (!validateTwilioRequest(request, env)) {
      reply.code(403).send("Invalid Twilio signature");
      return;
    }

    if (room.status().activeCallers >= maxActiveCallers(env)) {
      reply.type("text/xml").send(busyTwiml());
      return;
    }

    const body = request.body ?? {};
    const speechResult =
      typeof body.SpeechResult === "string" ? body.SpeechResult : undefined;
    const callSid = typeof body.CallSid === "string" ? body.CallSid : "unknown";

    reply.type("text/xml").send(
      chooseLanguageTwiml({
        speechResult,
        host: publicHost(request, env),
        callSid,
        attempt: request.query?.attempt,
      }),
    );
  });

  app.register(async (scopedApp) => {
    scopedApp.get("/media-stream", { websocket: true }, (connection, request) => {
      const socket = connection.socket ?? connection;
      let callSid = null;

      if (!validateTwilioRequest(request, env, { protocol: "wss" })) {
        logger.warn?.("[twilio] rejected media stream with invalid signature");
        socket.close(1008, "Invalid Twilio signature");
        return;
      }

      socket.on("message", (raw) => {
        const message = parseTwilioMessage(raw, logger);
        if (!message) {
          return;
        }

        if (message.event === "start") {
          const custom = message.start?.customParameters ?? {};
          callSid = custom.callSid ?? message.start?.callSid;
          const language = custom.language ?? "es";
          const languageLabel =
            custom.languageLabel ?? languageLabelForCode(language);
          const streamSid = message.start?.streamSid;

          if (!callSid || !streamSid) {
            logger.warn?.("[twilio] start event missing callSid or streamSid");
            return;
          }

          room.addCaller(
            createCaller({
              callSid,
              language,
              languageLabel,
              logger,
              socket,
              streamSid,
            }),
          );
          return;
        }

        if (message.event === "media" && callSid && message.media?.payload) {
          room.handleMedia(callSid, message.media.payload);
          return;
        }

        if (message.event === "stop" && callSid) {
          room.removeCaller(callSid);
        }
      });

      socket.on("close", () => {
        if (callSid) {
          room.removeCaller(callSid);
        }
      });
    });
  });

  return app;
}

function createCaller({
  callSid,
  language,
  languageLabel,
  logger,
  socket,
  streamSid,
}) {
  return {
    callSid,
    language,
    languageLabel,
    streamSid,
    close() {
      try {
        socket.close();
      } catch (error) {
        logger.warn?.(`[twilio:${callSid}] failed to close socket`, error);
      }
    },
    sendTwilioMedia(payload) {
      if (!payload || socket.readyState !== 1) {
        return;
      }
      socket.send(
        JSON.stringify({
          event: "media",
          streamSid,
          media: { payload },
        }),
      );
    },
  };
}

function parseTwilioMessage(raw, logger) {
  try {
    const text = Buffer.isBuffer(raw) ? raw.toString("utf8") : String(raw);
    return JSON.parse(text);
  } catch (error) {
    logger.warn?.("[twilio] failed to parse message", error);
    return null;
  }
}

function publicHost(request, env) {
  if (env.PUBLIC_URL) {
    return new URL(env.PUBLIC_URL).host;
  }

  const forwardedHost = request.headers["x-forwarded-host"];
  if (typeof forwardedHost === "string" && forwardedHost.trim()) {
    return forwardedHost.split(",")[0].trim();
  }

  if (request.headers.host) {
    return request.headers.host;
  }

  throw new Error("Set PUBLIC_URL or provide a Host header.");
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const port = Number.parseInt(process.env.PORT ?? "5050", 10);
  const app = buildApp();

  app.listen({ host: "0.0.0.0", port }, (error, address) => {
    if (error) {
      console.error(error);
      process.exit(1);
    }
    console.log(`Twilio Realtime Translation demo listening at ${address}`);
  });
}
