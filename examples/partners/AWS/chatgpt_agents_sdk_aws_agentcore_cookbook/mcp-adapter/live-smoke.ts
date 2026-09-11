import { pathToFileURL } from "node:url";

import { demoTravelDate } from "./demo-date.js";
import { AgentCoreRuntimeFlightProvider } from "./providers/agentcore-runtime-flight-provider.js";
import { createFlightProvider } from "./providers/create-flight-provider.js";
import {
  McpStructuredContent,
  RuntimeRequestSchema
} from "./schemas/flight.js";

export async function runLiveSmoke(
  provider: Pick<AgentCoreRuntimeFlightProvider, "call"> = createFlightProvider(),
  rawRequest: string | undefined = process.env.COOKBOOK_LIVE_REQUEST,
  travelDate: string = demoTravelDate()
): Promise<McpStructuredContent> {
  if (rawRequest?.trim()) {
    const request = RuntimeRequestSchema.parse(JSON.parse(rawRequest));
    return (await provider.call(request)).structuredContent;
  }

  const search = await provider.call({
    action: "search_flights",
    origin: "DAL",
    destination: "MDW",
    travel_date: travelDate
  });
  if (search.structuredContent.action !== "search_flights") {
    throw new Error("Demo smoke search returned the wrong action");
  }
  const firstFlight = search.structuredContent.flights[0];
  if (!firstFlight) {
    throw new Error("Demo smoke search returned no flight options");
  }

  const status = await provider.call({
    action: "get_live_status",
    flight_number: firstFlight.flightNumber,
    origin: firstFlight.origin,
    destination: firstFlight.destination,
    travel_date: firstFlight.travelDate
  });
  if (status.structuredContent.action !== "get_live_status") {
    throw new Error("Demo smoke status returned the wrong action");
  }
  const statusFlight = status.structuredContent.flight;
  if (
    statusFlight.flightNumber !== firstFlight.flightNumber
    || statusFlight.origin !== firstFlight.origin
    || statusFlight.destination !== firstFlight.destination
    || statusFlight.travelDate !== firstFlight.travelDate
  ) {
    throw new Error("Demo smoke status did not preserve the selected search result");
  }
  return status.structuredContent;
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  // Print only domain content. Trace/session identifiers remain out of notebook output.
  console.log(JSON.stringify(await runLiveSmoke()));
}
