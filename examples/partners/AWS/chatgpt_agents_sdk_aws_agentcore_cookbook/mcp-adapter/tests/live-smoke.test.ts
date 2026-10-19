import { describe, expect, it } from "vitest";

import { runLiveSmoke } from "../live-smoke.js";
import { AgentCoreRuntimeFlightProvider } from "../providers/agentcore-runtime-flight-provider.js";
import { RuntimeRequest } from "../schemas/flight.js";

const TEST_TRAVEL_DATE = "2099-09-21";

describe("primary demo smoke", () => {
  it("checks the first configured-date result without changing its identity", async () => {
    const requests: RuntimeRequest[] = [];
    const provider = new AgentCoreRuntimeFlightProvider(async (request) => {
      requests.push(request);
      if (request.action === "search_flights") {
        return {
          provider: "agentcore-runtime",
          executionMode: "deployed",
          action: "search_flights",
          data: {
            flights: [{
              flightNumber: "ELZ1234",
              origin: request.origin,
              destination: request.destination,
              travelDate: request.travel_date,
              departTime: "08:15",
              arriveTime: "10:05",
              fareUsd: 149
            }],
            summary: "One read-only sample option."
          }
        };
      }
      if (request.action !== "get_live_status") {
        throw new Error(`Unexpected action: ${request.action}`);
      }
      return {
        provider: "agentcore-runtime",
        executionMode: "deployed",
        action: "get_live_status",
        data: {
          flight: {
            flightNumber: request.flight_number,
            origin: request.origin,
            destination: request.destination,
            travelDate: request.travel_date,
            status: "ON_TIME",
            summary: "Mock live status is on time."
          }
        }
      };
    });

    await expect(runLiveSmoke(provider, "", TEST_TRAVEL_DATE)).resolves.toMatchObject({
      executionMode: "deployed",
      action: "get_live_status",
      flight: {
        flightNumber: "ELZ1234",
        origin: "DAL",
        destination: "MDW",
        travelDate: TEST_TRAVEL_DATE
      }
    });
    expect(requests).toEqual([
      {
        action: "search_flights",
        origin: "DAL",
        destination: "MDW",
        travel_date: TEST_TRAVEL_DATE
      },
      {
        action: "get_live_status",
        flight_number: "ELZ1234",
        origin: "DAL",
        destination: "MDW",
        travel_date: TEST_TRAVEL_DATE
      }
    ]);
  });

  it("fails when a deployed Runtime changes the selected flight date", async () => {
    const provider = new AgentCoreRuntimeFlightProvider(async (request) => {
      if (request.action === "search_flights") {
        return {
          provider: "agentcore-runtime",
          executionMode: "deployed",
          action: "search_flights",
          data: {
            flights: [{
              flightNumber: "ELZ1234",
              origin: "DAL",
              destination: "MDW",
              travelDate: TEST_TRAVEL_DATE,
              departTime: "08:15",
              arriveTime: "10:05",
              fareUsd: 149
            }],
            summary: "One read-only sample option."
          }
        };
      }
      if (request.action !== "get_live_status") {
        throw new Error(`Unexpected action: ${request.action}`);
      }
      return {
        provider: "agentcore-runtime",
        executionMode: "deployed",
        action: "get_live_status",
        data: {
          flight: {
            flightNumber: "ELZ1234",
            origin: "DAL",
            destination: "MDW",
            // Preserve the original regression as the explicit rejected value.
            travelDate: "2099-06-21",
            status: "ON_TIME",
            summary: "Stale live status."
          }
        }
      };
    });

    await expect(runLiveSmoke(provider, "", TEST_TRAVEL_DATE)).rejects.toThrow(
      "did not preserve the selected search result"
    );
  });
});
