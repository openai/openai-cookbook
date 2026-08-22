import express from "express";
import { createSessionHandler } from "./session-route.js";

const requiredEnvironment = [
  "OPENAI_API_KEY",
  "DEMO_APP_TOKEN",
  "SAFETY_IDENTIFIER_SECRET",
] as const;

for (const name of requiredEnvironment) {
  if (!process.env[name]) throw new Error(`${name} is required`);
}

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "8kb" }));
app.post(
  "/session",
  createSessionHandler({
    openAIApiKey: process.env.OPENAI_API_KEY!,
    demoAppToken: process.env.DEMO_APP_TOKEN!,
    safetyIdentifierSecret: process.env.SAFETY_IDENTIFIER_SECRET!,
  }),
);

const port = Number(process.env.PORT ?? 3000);
const host = process.env.HOST ?? "127.0.0.1";
app.listen(port, host, () => {
  console.log(`Local session server listening on http://${host}:${port}`);
});
