import { createHmac, timingSafeEqual } from "node:crypto";
import type { Request, Response } from "express";

const CLIENT_SECRETS_URL =
  "https://api.openai.com/v1/realtime/client_secrets";

export type SessionRouteConfig = {
  openAIApiKey: string;
  demoAppToken: string;
  safetyIdentifierSecret: string;
  fetchImpl?: typeof fetch;
};

export function createSessionHandler(config: SessionRouteConfig) {
  const fetchImpl = config.fetchImpl ?? fetch;

  return async (request: Request, response: Response): Promise<void> => {
    response.setHeader("Cache-Control", "no-store");

    if (!constantTimeTokenMatch(request, config.demoAppToken)) {
      response.status(401).json({ error: "Unauthorized" });
      return;
    }

    const principal = request.header("x-demo-user");
    if (!principal || !/^[A-Za-z0-9_-]{1,128}$/.test(principal)) {
      response.status(400).json({ error: "Invalid demo principal" });
      return;
    }

    const safetyIdentifier = createHmac(
      "sha256",
      config.safetyIdentifierSecret,
    )
      .update(principal)
      .digest("hex");

    let openAIResponse: globalThis.Response;
    try {
      openAIResponse = await fetchImpl(CLIENT_SECRETS_URL, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${config.openAIApiKey}`,
          "Content-Type": "application/json",
          "OpenAI-Safety-Identifier": safetyIdentifier,
        },
        body: JSON.stringify({
          expires_after: { anchor: "created_at", seconds: 60 },
          session: {
            type: "realtime",
            model: "gpt-realtime-2.1",
            output_modalities: ["audio"],
            instructions:
              "You are a concise, low-stakes task-capture assistant. Never claim a note was saved until the tool output confirms it. Ask for confirmation before proposing a save.",
            tools: [
              {
                type: "function",
                name: "save_task_note",
                description:
                  "Propose a task note. The mobile UI must obtain explicit user approval before saving it.",
                parameters: {
                  type: "object",
                  additionalProperties: false,
                  properties: {
                    title: { type: "string", maxLength: 120 },
                    details: { type: "string", maxLength: 1000 },
                  },
                  required: ["title", "details"],
                },
              },
            ],
            tool_choice: "auto",
          },
        }),
      });
    } catch {
      response
        .status(502)
        .json({ error: "Could not create a Realtime client secret" });
      return;
    }

    if (!openAIResponse.ok) {
      response
        .status(502)
        .json({ error: "Could not create a Realtime client secret" });
      return;
    }

    const payload = (await openAIResponse.json()) as {
      value?: unknown;
      expires_at?: unknown;
    };
    if (typeof payload.value !== "string") {
      response.status(502).json({ error: "Invalid Realtime response" });
      return;
    }

    response.status(200).json({
      client_secret: payload.value,
      expires_at: payload.expires_at,
    });
  };
}

function constantTimeTokenMatch(request: Request, expected: string): boolean {
  const authorization = request.header("authorization") ?? "";
  const supplied = authorization.startsWith("Bearer ")
    ? authorization.slice("Bearer ".length)
    : "";
  const expectedBuffer = Buffer.from(expected);
  const suppliedBuffer = Buffer.from(supplied);
  return (
    expectedBuffer.length === suppliedBuffer.length &&
    timingSafeEqual(expectedBuffer, suppliedBuffer)
  );
}
