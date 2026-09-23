import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createFlightProvider } from "../providers/create-flight-provider.js";
import { RuntimeRequestSchema } from "../schemas/flight.js";

function stubRuntimeEnv() {
  vi.stubEnv("FLIGHT_DATA_SOURCE", "agentcore-runtime");
  vi.stubEnv(
    "AGENTCORE_RUNTIME_AGENT_ARN",
    "arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/flight_status_agent"
  );
}

const sampleStatus = (flightNumber: string) => ({
  flightNumber,
  origin: "DAL",
  destination: "MDW",
  travelDate: "2099-09-21",
  status: "ON_TIME",
  summary: "Sample flight is on time."
});

describe("AgentCore Runtime MCP adapter contract", () => {
  beforeEach(() => {
    vi.stubEnv("COOKBOOK_EXECUTION_MODE", "");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("maps a validated Runtime response into MCP structuredContent", async () => {
    stubRuntimeEnv();
    const provider = createFlightProvider(async () => ({
      provider: "agentcore-runtime",
      executionMode: "deployed",
      action: "search_flights",
      data: {
        flights: [{
          flightNumber: "ELZ1234",
          origin: "DAL",
          destination: "MDW",
          travelDate: "2099-09-21",
          departTime: "08:15",
          arriveTime: "10:05",
          fareUsd: 149
        }],
        summary: "One read-only sample option."
      },
      trace: { traceId: "fixture-trace", requestId: "fixture-request" }
    }));

    await expect(provider.call({
      action: "search_flights",
      origin: "DAL",
      destination: "MDW",
      travel_date: "2099-09-21"
    })).resolves.toEqual({
      structuredContent: {
        provider: "agentcore-runtime",
        executionMode: "deployed",
        action: "search_flights",
        flights: [{
          flightNumber: "ELZ1234",
          origin: "DAL",
          destination: "MDW",
          travelDate: "2099-09-21",
          departTime: "08:15",
          arriveTime: "10:05",
          fareUsd: 149
        }],
        summary: "One read-only sample option."
      },
      _meta: { traceId: "fixture-trace", requestId: "fixture-request" }
    });
  });

  it("maps upcoming and live status actions", async () => {
    stubRuntimeEnv();
    const provider = createFlightProvider(async (request) => ({
      provider: "agentcore-runtime",
      executionMode: "deployed",
      action: request.action,
      data: {
        flight: sampleStatus(request.action === "get_live_status" ? "ELZ1628" : "ELZ4321")
      }
    }));

    await expect(provider.call({ action: "get_upcoming_status" })).resolves.toMatchObject({
      structuredContent: { action: "get_upcoming_status", flight: { flightNumber: "ELZ4321" } }
    });
    await expect(provider.call({ action: "get_live_status", flight_number: "ELZ1628" }))
      .resolves.toMatchObject({
        structuredContent: { action: "get_live_status", flight: { flightNumber: "ELZ1628" } }
      });
  });

  it("rejects missing fields, lowercase airport codes, extras, and write-like actions", () => {
    expect(() => RuntimeRequestSchema.parse({ action: "search_flights", origin: "DAL" }))
      .toThrow();
    expect(() => RuntimeRequestSchema.parse({
      action: "search_flights",
      origin: "dal",
      destination: "MDW",
      travel_date: "2099-09-21"
    })).toThrow();
    expect(() => RuntimeRequestSchema.parse({ action: "get_upcoming_status", extra: true }))
      .toThrow();
    expect(() => RuntimeRequestSchema.parse({ action: "get_live_status" })).toThrow();
    expect(() => RuntimeRequestSchema.parse({ action: "book_flight" })).toThrow();
  });

  it("requires explicit provider and default invoker configuration", () => {
    vi.stubEnv("FLIGHT_DATA_SOURCE", "stub");
    expect(() => createFlightProvider(async () => ({}))).toThrow(
      "FLIGHT_DATA_SOURCE must be local-agent or agentcore-runtime"
    );

    vi.stubEnv("FLIGHT_DATA_SOURCE", "agentcore-runtime");
    vi.stubEnv("AGENTCORE_RUNTIME_AGENT_ARN", "");
    expect(() => createFlightProvider()).toThrow("Missing AGENTCORE_RUNTIME_AGENT_ARN");
  });

  it("rejects malformed action-specific Runtime output", async () => {
    stubRuntimeEnv();
    const provider = createFlightProvider(async () => ({
      provider: "agentcore-runtime",
      executionMode: "deployed",
      action: "get_upcoming_status",
      data: { flight: { flightNumber: "ELZ4321", status: "ON_TIME" } }
    }));

    await expect(provider.call({ action: "get_upcoming_status" })).rejects.toThrow();
  });
});
