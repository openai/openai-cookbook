import { z } from "zod";

const AirportCodeSchema = z.string().length(3).regex(/^[A-Z]{3}$/);
const TravelDateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);

export const RuntimeActionSchema = z.enum([
  "search_flights",
  "get_upcoming_status",
  "get_live_status"
]);

const SearchFlightsRequestSchema = z.object({
  action: z.literal("search_flights"),
  origin: AirportCodeSchema,
  destination: AirportCodeSchema,
  travel_date: TravelDateSchema
}).strict();

const UpcomingStatusRequestSchema = z.object({
  action: z.literal("get_upcoming_status")
}).strict();

const LiveStatusRequestSchema = z.object({
  action: z.literal("get_live_status"),
  origin: AirportCodeSchema.optional(),
  destination: AirportCodeSchema.optional(),
  travel_date: TravelDateSchema.optional(),
  flight_number: z.string().min(1).optional()
}).strict();

export const RuntimeRequestSchema = z.discriminatedUnion("action", [
  SearchFlightsRequestSchema,
  UpcomingStatusRequestSchema,
  LiveStatusRequestSchema
]).superRefine((request, ctx) => {
  if (
    request.action === "get_live_status" &&
    !request.flight_number &&
    !request.origin &&
    !request.destination
  ) {
    ctx.addIssue({
      code: z.ZodIssueCode.custom,
      message: "get_live_status needs a flight number or route hint",
      path: ["flight_number"]
    });
  }
});

export const FlightSchema = z.object({
  flightNumber: z.string().min(1),
  origin: AirportCodeSchema,
  destination: AirportCodeSchema,
  travelDate: TravelDateSchema,
  departTime: z.string().regex(/^\d{2}:\d{2}$/),
  arriveTime: z.string().regex(/^\d{2}:\d{2}$/),
  fareUsd: z.number().int().nonnegative()
}).strict();

export const TripStatusSchema = z.object({
  flightNumber: z.string().min(1),
  origin: AirportCodeSchema,
  destination: AirportCodeSchema,
  travelDate: TravelDateSchema,
  status: z.string().min(1),
  summary: z.string().min(1)
}).strict();

export const RuntimeTraceSchema = z.object({
  traceId: z.string().min(1).optional(),
  requestId: z.string().min(1).optional(),
  runtimeSessionId: z.string().min(1).optional(),
  invocationId: z.string().min(1).optional()
}).strict();

export const ExecutionModeSchema = z.enum(["local", "deployed"]);
const DeprecatedProviderSchema = z.literal("agentcore-runtime")
  .describe("Deprecated compatibility field; use executionMode.");

const ResponseBase = {
  provider: DeprecatedProviderSchema,
  executionMode: ExecutionModeSchema,
  trace: RuntimeTraceSchema.optional()
};

const SearchFlightsResponseSchema = z.object({
  ...ResponseBase,
  action: z.literal("search_flights"),
  data: z.object({
    flights: z.array(FlightSchema),
    summary: z.string().min(1)
  }).strict()
}).strict();

const UpcomingStatusResponseSchema = z.object({
  ...ResponseBase,
  action: z.literal("get_upcoming_status"),
  data: z.object({ flight: TripStatusSchema }).strict()
}).strict();

const LiveStatusResponseSchema = z.object({
  ...ResponseBase,
  action: z.literal("get_live_status"),
  data: z.object({ flight: TripStatusSchema }).strict()
}).strict();

export const RuntimeResponseSchema = z.discriminatedUnion("action", [
  SearchFlightsResponseSchema,
  UpcomingStatusResponseSchema,
  LiveStatusResponseSchema
]);

export const McpStructuredContentSchema = z.discriminatedUnion("action", [
  z.object({
    provider: DeprecatedProviderSchema,
    executionMode: ExecutionModeSchema,
    action: z.literal("search_flights"),
    flights: z.array(FlightSchema),
    summary: z.string().min(1)
  }).strict(),
  z.object({
    provider: DeprecatedProviderSchema,
    executionMode: ExecutionModeSchema,
    action: z.literal("get_upcoming_status"),
    flight: TripStatusSchema
  }).strict(),
  z.object({
    provider: DeprecatedProviderSchema,
    executionMode: ExecutionModeSchema,
    action: z.literal("get_live_status"),
    flight: TripStatusSchema
  }).strict()
]);

export type RuntimeRequest = z.infer<typeof RuntimeRequestSchema>;
export type RuntimeResponse = z.infer<typeof RuntimeResponseSchema>;
export type McpStructuredContent = z.infer<typeof McpStructuredContentSchema>;
