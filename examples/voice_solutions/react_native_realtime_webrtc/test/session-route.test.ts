import express from "express";
import request from "supertest";
import { describe, expect, it, vi } from "vitest";
import { createSessionHandler } from "../src/server/session-route.js";

function buildApp(fetchImpl: typeof fetch) {
  const app = express();
  app.post(
    "/session",
    createSessionHandler({
      openAIApiKey: "server-key-for-test",
      demoAppToken: "local-app-token",
      safetyIdentifierSecret: "separate-safety-secret",
      fetchImpl,
    }),
  );
  return app;
}

describe("session route", () => {
  it("rejects unauthenticated requests before contacting OpenAI", async () => {
    const fetchImpl = vi.fn<typeof fetch>();
    const response = await request(buildApp(fetchImpl)).post("/session");

    expect(response.status).toBe(401);
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("mints a scoped secret with a non-identifying safety value", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () =>
      Response.json({ value: "ek_test", expires_at: 1_800_000_000 }),
    );
    const response = await request(buildApp(fetchImpl))
      .post("/session")
      .set("Authorization", "Bearer local-app-token")
      .set("X-Demo-User", "user_123");

    expect(response.status).toBe(200);
    expect(response.headers["cache-control"]).toBe("no-store");
    expect(response.body).toEqual({
      client_secret: "ek_test",
      expires_at: 1_800_000_000,
    });

    const [, init] = fetchImpl.mock.calls[0]!;
    const headers = new Headers(init?.headers);
    const safetyIdentifier = headers.get("OpenAI-Safety-Identifier");
    expect(safetyIdentifier).toMatch(/^[a-f0-9]{64}$/);
    expect(safetyIdentifier).not.toContain("user_123");

    const body = JSON.parse(String(init?.body));
    expect(body.session.model).toBe("gpt-realtime-2.1");
    expect(body.expires_after.seconds).toBe(60);
    expect(body.session.tools[0].name).toBe("save_task_note");
  });

  it("returns a generic gateway error when token minting fails", async () => {
    const fetchImpl = vi.fn<typeof fetch>(async () => {
      throw new Error("network detail that must not leak");
    });
    const response = await request(buildApp(fetchImpl))
      .post("/session")
      .set("Authorization", "Bearer local-app-token")
      .set("X-Demo-User", "user_123");

    expect(response.status).toBe(502);
    expect(JSON.stringify(response.body)).not.toContain("network detail");
  });
});
