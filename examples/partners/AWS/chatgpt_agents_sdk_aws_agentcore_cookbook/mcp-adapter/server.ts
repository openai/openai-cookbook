import { readFileSync } from "node:fs";
import { createServer, Server as HttpServer } from "node:http";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

import {
  registerAppResource,
  registerAppTool,
  RESOURCE_MIME_TYPE
} from "@modelcontextprotocol/ext-apps/server";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { z } from "zod";

import { AgentCoreRuntimeFlightProvider } from "./providers/agentcore-runtime-flight-provider.js";
import { createFlightProvider } from "./providers/create-flight-provider.js";
import { executionModeFromEnv } from "./providers/execution-mode.js";
import {
  AirportCodeSchema,
  ExecutionModeSchema,
  FlightSchema,
  TripStatusSchema
} from "./schemas/flight.js";

const DeprecatedProviderSchema = z.literal("agentcore-runtime")
  .describe("Deprecated compatibility field; use executionMode.");
export const FLIGHT_WIDGET_URI = "ui://flight-status/flight-widget-v2.html";
export const LEGACY_FLIGHT_WIDGET_URI = "ui://flight-status/flight-widget-v1.html";
const SearchOutputShape = {
  provider: DeprecatedProviderSchema,
  executionMode: ExecutionModeSchema,
  action: z.literal("search_flights"),
  flights: z.array(FlightSchema),
  summary: z.string()
};
const UpcomingOutputShape = {
  provider: DeprecatedProviderSchema,
  executionMode: ExecutionModeSchema,
  action: z.literal("get_upcoming_status"),
  flight: TripStatusSchema
};
const LiveOutputShape = {
  provider: DeprecatedProviderSchema,
  executionMode: ExecutionModeSchema,
  action: z.literal("get_live_status"),
  flight: TripStatusSchema
};
const NoArgumentsSchema = z.object({})
  .strict()
  .describe("No arguments are accepted. Call this tool with an empty object.");
const ReadOnlyAnnotations = {
  readOnlyHint: true,
  destructiveHint: false,
  openWorldHint: false,
  idempotentHint: true
} as const;
const LOOPBACK_HOSTNAMES = new Set(["127.0.0.1", "localhost", "[::1]"]);

export interface LoopbackRequestPolicy {
  allowed: boolean;
  corsOrigin?: string;
}

function loopbackUrl(value: string): URL | undefined {
  if (!value || value !== value.trim()) return undefined;
  try {
    const url = new URL(`mcp://${value}`);
    if (
      url.username
      || url.password
      || !["", "/"].includes(url.pathname)
      || url.search
      || url.hash
    ) {
      return undefined;
    }
    return url;
  } catch {
    return undefined;
  }
}

function isLoopbackOrigin(value: string): boolean {
  try {
    const url = new URL(value);
    return (
      ["http:", "https:"].includes(url.protocol)
      && LOOPBACK_HOSTNAMES.has(url.hostname.toLowerCase())
      && value === url.origin
    );
  } catch {
    return false;
  }
}

export function loopbackRequestPolicy(
  hostHeader: string | undefined,
  originHeader: string | undefined,
  localPort: number | undefined
): LoopbackRequestPolicy {
  const host = hostHeader ? loopbackUrl(hostHeader) : undefined;
  if (
    !host
    || !LOOPBACK_HOSTNAMES.has(host.hostname.toLowerCase())
    || (host.port && localPort !== undefined && Number(host.port) !== localPort)
  ) {
    return { allowed: false };
  }
  if (originHeader === undefined) {
    return { allowed: true };
  }
  if (!isLoopbackOrigin(originHeader)) {
    return { allowed: false };
  }
  return { allowed: true, corsOrigin: originHeader };
}

function toolResult(result: Awaited<ReturnType<AgentCoreRuntimeFlightProvider["call"]>>) {
  return {
    content: [{ type: "text" as const, text: JSON.stringify(result.structuredContent) }],
    structuredContent: result.structuredContent,
    _meta: result._meta
  };
}

function chatgptInvocationContext(extra: { _meta?: Record<string, unknown> }) {
  const value = extra._meta?.["openai/session"];
  return typeof value === "string" && value.trim()
    ? { chatgptSessionId: value.trim() }
    : undefined;
}

export function createFlightMcpServer(
  provider: AgentCoreRuntimeFlightProvider = createFlightProvider()
): McpServer {
  const server = new McpServer(
    { name: "agentcore-flight-tools", version: "0.1.0" },
    {
      instructions:
        "Use these read-only tools to search sample flights and inspect upcoming or live status. When checking a search result, pass its flight number, route, and travel date to get_live_status. No booking or other write action is available."
    }
  );

  const widgetHtml = readFileSync(
    resolve(process.env.FLIGHT_WIDGET_PATH ?? "public/flight-widget.html"),
    "utf8"
  );
  for (const resourceUri of [FLIGHT_WIDGET_URI, LEGACY_FLIGHT_WIDGET_URI]) {
    registerAppResource(
      server,
      `Flight status widget (${resourceUri === FLIGHT_WIDGET_URI ? "current" : "compatibility"})`,
      resourceUri,
      {
        description: "Renders read-only flight search and status results.",
        _meta: {
          ui: {
            prefersBorder: true,
            csp: { connectDomains: [], resourceDomains: [] }
          },
          "openai/widgetDescription":
            "A compact read-only card for flight options and flight status."
        }
      },
      async () => ({
        contents: [{
          uri: resourceUri,
          mimeType: RESOURCE_MIME_TYPE,
          text: widgetHtml,
          _meta: {
            ui: {
              prefersBorder: true,
              csp: { connectDomains: [], resourceDomains: [] }
            },
            "openai/widgetDescription":
              "A compact read-only card for flight options and flight status."
          }
        }]
      })
    );
  }

  registerAppTool(
    server,
    "search_flights",
    {
      title: "Search flights",
      description: "Use this when the user wants read-only flight options for a route and date.",
      inputSchema: {
        origin: AirportCodeSchema.describe("Three-letter uppercase origin airport code"),
        destination: AirportCodeSchema.describe("Three-letter uppercase destination airport code"),
        travel_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).describe("Travel date in YYYY-MM-DD format")
      },
      outputSchema: SearchOutputShape,
      annotations: ReadOnlyAnnotations,
      _meta: {
        ui: { resourceUri: FLIGHT_WIDGET_URI },
        "openai/outputTemplate": FLIGHT_WIDGET_URI,
        "openai/toolInvocation/invoking": "Searching sample flights…",
        "openai/toolInvocation/invoked": "Flight options ready."
      }
    },
    async ({ origin, destination, travel_date }, extra) =>
      toolResult(await provider.call(
        { action: "search_flights", origin, destination, travel_date },
        chatgptInvocationContext(extra)
      ))
  );

  registerAppTool(
    server,
    "get_upcoming_status",
    {
      title: "Get upcoming flight status",
      description:
        "Returns the read-only status of the predefined sample upcoming trip. This tool takes no arguments.",
      inputSchema: NoArgumentsSchema,
      outputSchema: UpcomingOutputShape,
      annotations: ReadOnlyAnnotations,
      _meta: {
        ui: { resourceUri: FLIGHT_WIDGET_URI },
        "openai/outputTemplate": FLIGHT_WIDGET_URI,
        "openai/toolInvocation/invoking": "Checking the upcoming trip…",
        "openai/toolInvocation/invoked": "Upcoming status ready."
      }
    },
    async (_args, extra) => toolResult(await provider.call(
      { action: "get_upcoming_status" },
      chatgptInvocationContext(extra)
    ))
  );

  registerAppTool(
    server,
    "get_live_status",
    {
      title: "Get live flight status",
      description:
        "Use this when the user wants read-only live status for a flight number or route. After a search, pass the selected result's flight number, route, and travel date.",
      inputSchema: {
        flight_number: z.string().min(1).optional(),
        origin: AirportCodeSchema.describe("Three-letter uppercase origin airport code").optional(),
        destination: AirportCodeSchema.describe("Three-letter uppercase destination airport code").optional(),
        travel_date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional()
      },
      outputSchema: LiveOutputShape,
      annotations: ReadOnlyAnnotations,
      _meta: {
        ui: { resourceUri: FLIGHT_WIDGET_URI },
        "openai/outputTemplate": FLIGHT_WIDGET_URI,
        "openai/toolInvocation/invoking": "Checking live flight status…",
        "openai/toolInvocation/invoked": "Live status ready."
      }
    },
    async ({ flight_number, origin, destination, travel_date }, extra) =>
      toolResult(
        await provider.call({
          action: "get_live_status",
          flight_number,
          origin,
          destination,
          travel_date
        }, chatgptInvocationContext(extra))
      )
  );

  return server;
}

export function createFlightMcpHttpServer(
  providerFactory: () => AgentCoreRuntimeFlightProvider = () => createFlightProvider()
): HttpServer {
  return createServer(async (req, res) => {
    // Keep the unauthenticated development listener local: CLI and tunnel
    // clients omit Origin, while a browser-based Inspector uses a loopback Origin.
    const access = loopbackRequestPolicy(
      req.headers.host,
      req.headers.origin,
      req.socket.localPort
    );
    if (!access.allowed) {
      res.writeHead(403, { "content-type": "text/plain; charset=utf-8" });
      res.end("Forbidden");
      return;
    }
    if (access.corsOrigin) {
      res.setHeader("access-control-allow-origin", access.corsOrigin);
      res.setHeader("vary", "Origin");
    }

    const url = new URL(req.url ?? "/", `http://${req.headers.host ?? "localhost"}`);
    if (req.method === "GET" && url.pathname === "/") {
      res.writeHead(200, { "content-type": "application/json" });
      res.end(JSON.stringify({ status: "ok", mcp: "/mcp" }));
      return;
    }
    if (req.method === "OPTIONS" && url.pathname === "/mcp") {
      res.writeHead(204, {
        "access-control-allow-methods": "POST, GET, DELETE, OPTIONS",
        "access-control-allow-headers": "content-type,mcp-session-id",
        "access-control-expose-headers": "Mcp-Session-Id"
      });
      res.end();
      return;
    }
    if (url.pathname !== "/mcp" || !req.method || !["POST", "GET", "DELETE"].includes(req.method)) {
      res.writeHead(404).end("Not Found");
      return;
    }

    res.setHeader("access-control-expose-headers", "Mcp-Session-Id");
    let server: McpServer | undefined;
    let transport: StreamableHTTPServerTransport | undefined;
    try {
      server = createFlightMcpServer(providerFactory());
      transport = new StreamableHTTPServerTransport({
        sessionIdGenerator: undefined,
        enableJsonResponse: true
      });
      await server.connect(transport);
      await transport.handleRequest(req, res);
    } catch (error) {
      console.error("MCP request failed", error);
      if (!res.headersSent) {
        res.writeHead(500, { "content-type": "application/json" });
        res.end(JSON.stringify({
          jsonrpc: "2.0",
          error: { code: -32603, message: "Internal server error" },
          id: null
        }));
      }
    } finally {
      await transport?.close();
      await server?.close();
    }
  });
}

export function startFlightMcpServer(port = Number(process.env.PORT ?? 8787)): HttpServer {
  executionModeFromEnv();
  const httpServer = createFlightMcpHttpServer();
  httpServer.listen(port, "127.0.0.1", () => {
    console.log(`Flight MCP server listening on http://127.0.0.1:${port}/mcp`);
  });
  return httpServer;
}

const isMain = process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  startFlightMcpServer();
}
