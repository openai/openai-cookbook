import type { IncomingMessage, ServerResponse } from "node:http";
import OpenAI from "openai";
import { QueueClient } from "@vercel/queue";

const queue = new QueueClient({ region: "iad1" });

export default async function webhook(
  req: IncomingMessage,
  res: ServerResponse,
) {
  if (req.method !== "POST") return res.writeHead(405).end();
  const secret = process.env.OPENAI_WEBHOOK_SECRET;
  if (!secret || secret === "pending-webhook-registration")
    return res.writeHead(503).end("Webhook not configured");
  const chunks: Buffer[] = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
  const payload = Buffer.concat(chunks).toString("utf8");
  const headers = new Headers();
  for (const [name, value] of Object.entries(req.headers)) {
    if (value !== undefined)
      headers.set(name, Array.isArray(value) ? value.join(",") : value);
  }
  const verifier = new OpenAI({ apiKey: "unused", webhookSecret: secret });
  try {
    await verifier.webhooks.verifySignature(payload, headers);
  } catch {
    return res.writeHead(400).end("Invalid signature");
  }
  const event = JSON.parse(payload);
  if (
    event.type === "agent.session.failed" ||
    (event.type === "agent.session.action_required" &&
      event.data.required_action.type === "environment_connection")
  ) {
    await queue.send(
      "sandbox-wakeup",
      { sessionId: event.data.id },
      { idempotencyKey: event.id },
    );
  }
  res.writeHead(200).end("ok");
}
