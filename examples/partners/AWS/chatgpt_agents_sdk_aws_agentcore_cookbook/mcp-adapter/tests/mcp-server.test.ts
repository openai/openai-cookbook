import { request as httpRequest } from "node:http";
import { AddressInfo } from "node:net";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";
import { InMemoryTransport } from "@modelcontextprotocol/sdk/inMemory.js";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentCoreRuntimeFlightProvider } from "../providers/agentcore-runtime-flight-provider.js";
import {
  createFlightMcpHttpServer,
  createFlightMcpServer,
  FLIGHT_WIDGET_URI,
  LEGACY_FLIGHT_WIDGET_URI,
  loopbackRequestPolicy,
  startFlightMcpServer
} from "../server.js";

const statusResponse = {
  provider: "agentcore-runtime" as const,
  executionMode: "deployed" as const,
  action: "get_upcoming_status" as const,
  data: {
    flight: {
      flightNumber: "ELZ4321",
      origin: "DAL",
      destination: "MDW",
      travelDate: "2099-09-21",
      status: "ON_TIME",
      summary: "Sample trip is on time."
    }
  }
};

const closers: Array<() => Promise<void>> = [];
afterEach(async () => {
  while (closers.length) await closers.pop()!();
  vi.unstubAllEnvs();
});

async function connectedClient() {
  const provider = new AgentCoreRuntimeFlightProvider(async () => statusResponse);
  const server = createFlightMcpServer(provider);
  const client = new Client({ name: "cookbook-test-client", version: "0.1.0" });
  const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
  await server.connect(serverTransport);
  await client.connect(clientTransport);
  closers.push(async () => client.close(), async () => server.close());
  return client;
}

async function requestStatus(url: string, headers: Record<string, string>): Promise<number> {
  return new Promise<number>((resolve, reject) => {
    const request = httpRequest(url, { headers }, (response) => {
      response.resume();
      resolve(response.statusCode ?? 0);
    });
    request.once("error", reject);
    request.end();
  });
}

describe("loopback MCP request boundary", () => {
  it("allows loopback hosts for CLI, tunnel, and local Inspector traffic", () => {
    expect(loopbackRequestPolicy("127.0.0.1:8787", undefined, 8787))
      .toEqual({ allowed: true });
    expect(loopbackRequestPolicy("localhost:8787", "http://localhost:6274", 8787))
      .toEqual({ allowed: true, corsOrigin: "http://localhost:6274" });
    expect(loopbackRequestPolicy("[::1]:8787", "http://[::1]:6274", 8787))
      .toEqual({ allowed: true, corsOrigin: "http://[::1]:6274" });
  });

  it("rejects non-loopback, mismatched-port, and hostile browser requests", () => {
    expect(loopbackRequestPolicy("attacker.example:8787", undefined, 8787))
      .toEqual({ allowed: false });
    expect(loopbackRequestPolicy("127.0.0.1:9999", undefined, 8787))
      .toEqual({ allowed: false });
    expect(loopbackRequestPolicy("127.0.0.1:80", undefined, 8787))
      .toEqual({ allowed: false });
    expect(loopbackRequestPolicy("127.0.0.1:8787", "https://attacker.example", 8787))
      .toEqual({ allowed: false });
    expect(loopbackRequestPolicy("127.0.0.1:8787", "null", 8787))
      .toEqual({ allowed: false });
  });
});

describe("Flight MCP server", () => {
  it("fails startup when canonical and legacy execution modes conflict", () => {
    vi.stubEnv("COOKBOOK_EXECUTION_MODE", "local");
    vi.stubEnv("FLIGHT_DATA_SOURCE", "agentcore-runtime");

    expect(() => startFlightMcpServer()).toThrow("conflicts");
  });

  it("lists exactly three annotated read-only tools", async () => {
    const client = await connectedClient();
    const tools = await client.listTools();

    expect(tools.tools.map((tool) => tool.name)).toEqual([
      "search_flights",
      "get_upcoming_status",
      "get_live_status"
    ]);
    for (const tool of tools.tools) {
      expect(tool.annotations).toMatchObject({
        readOnlyHint: true,
        destructiveHint: false,
        openWorldHint: false,
        idempotentHint: true
      });
      expect(tool._meta).toMatchObject({
        ui: { resourceUri: FLIGHT_WIDGET_URI },
        "openai/outputTemplate": FLIGHT_WIDGET_URI
      });
    }
  });

  it("registers a versioned, self-contained MCP Apps widget resource", async () => {
    const client = await connectedClient();
    const resources = await client.listResources();
    expect(resources.resources).toEqual(expect.arrayContaining([
      expect.objectContaining({ uri: FLIGHT_WIDGET_URI, mimeType: "text/html;profile=mcp-app" }),
      expect.objectContaining({
        uri: LEGACY_FLIGHT_WIDGET_URI,
        mimeType: "text/html;profile=mcp-app"
      })
    ]));

    const resource = await client.readResource({ uri: FLIGHT_WIDGET_URI });
    const content = resource.contents[0];
    if (!("text" in content)) throw new Error("Expected a text MCP Apps resource");
    expect(content.mimeType).toBe("text/html;profile=mcp-app");
    expect(content.text).toContain("ui/notifications/tool-result");
    expect(content.text).toContain("--widget-safe-area: 20px");
    expect(content.text).toContain("textContent");
    expect(content.text).toContain("Eliza Airlines flight information");
    expect(content.text).toContain("Cookbook agent");
    expect(content.text).toContain("#3A3A3A");
    expect(content.text).toContain("#FFFFFF");
    expect(content.text).toContain("#F6D2C5");
    expect(content.text).toContain("#DFC2B8");
    expect(content.text).toContain("#EE9F84");
    expect(content.text).toContain("#D84D1E");
    expect(content.text).toContain('font-family: "Libre Baskerville"');
    expect(content.text).toMatch(
      /main\s*\{[^}]*background: var\(--eliza-white\);[^}]*border-radius: 16px;/s
    );
    expect(content.text).toContain("Status: ${flight.status");
    expect(content.text).toMatch(
      /\.error\s*\{[^}]*border-inline-start: 3px solid var\(--eliza-accent-4\);[^}]*color: var\(--eliza-charcoal\);/s
    );
    expect(content.text).not.toContain("#16803a");
    expect(content.text).not.toContain("#b42318");
    expect(content.text).not.toContain(">AgentCore Runtime<");
    expect(content.text).not.toMatch(/<script[^>]+src=/);
    expect(content._meta).toMatchObject({
      ui: {
        prefersBorder: true,
        csp: { connectDomains: [], resourceDomains: [] }
      }
    });

    const compatibilityResource = await client.readResource({ uri: LEGACY_FLIGHT_WIDGET_URI });
    expect(compatibilityResource.contents[0]).toMatchObject({
      uri: LEGACY_FLIGHT_WIDGET_URI,
      mimeType: "text/html;profile=mcp-app"
    });
  });

  it("calls the upcoming-status tool through the MCP protocol", async () => {
    const client = await connectedClient();
    const tools = await client.listTools();
    const upcomingTool = tools.tools.find((tool) => tool.name === "get_upcoming_status");

    expect(upcomingTool).toMatchObject({
      description: expect.stringContaining("takes no arguments"),
      inputSchema: {
        type: "object",
        description: "No arguments are accepted. Call this tool with an empty object.",
        properties: {},
        additionalProperties: false
      },
      outputSchema: {
        properties: {
          provider: expect.objectContaining({
            description: expect.stringContaining("Deprecated compatibility field")
          }),
          executionMode: expect.objectContaining({
            enum: ["local", "deployed"]
          })
        },
        required: expect.arrayContaining(["provider", "executionMode"])
      }
    });

    const result = await client.callTool({ name: "get_upcoming_status", arguments: {} });

    expect(result.structuredContent).toMatchObject({
      provider: "agentcore-runtime",
      executionMode: "deployed",
      action: "get_upcoming_status",
      flight: { flightNumber: "ELZ4321", status: "ON_TIME" }
    });
  });

  it("forwards the ChatGPT conversation ID as invocation context", async () => {
    let observedSessionId: string | undefined;
    const provider = new AgentCoreRuntimeFlightProvider(async (_request, context) => {
      observedSessionId = context?.chatgptSessionId;
      return statusResponse;
    });
    const server = createFlightMcpServer(provider);
    const client = new Client({ name: "cookbook-test-client", version: "0.1.0" });
    const [clientTransport, serverTransport] = InMemoryTransport.createLinkedPair();
    await server.connect(serverTransport);
    await client.connect(clientTransport);
    closers.push(async () => client.close(), async () => server.close());

    await client.callTool({
      name: "get_upcoming_status",
      arguments: {},
      _meta: { "openai/session": "anonymous-chatgpt-conversation" }
    });

    expect(observedSessionId).toBe("anonymous-chatgpt-conversation");
  });

  it("rejects invalid tool inputs before provider invocation", async () => {
    const client = await connectedClient();
    const result = await client.callTool({
      name: "search_flights",
      arguments: { origin: "DAL" }
    });

    expect(result.isError).toBe(true);
  });

  it("serves the MCP protocol over Streamable HTTP", async () => {
    const provider = new AgentCoreRuntimeFlightProvider(async () => statusResponse);
    const httpServer = createFlightMcpHttpServer(() => provider);
    await new Promise<void>((resolve) => httpServer.listen(0, "127.0.0.1", resolve));
    closers.push(async () => new Promise<void>((resolve, reject) => {
      httpServer.close((error) => error ? reject(error) : resolve());
    }));

    const { port } = httpServer.address() as AddressInfo;
    const rootUrl = `http://127.0.0.1:${port}/`;
    await expect(fetch(rootUrl)).resolves.toMatchObject({ status: 200 });

    const preflight = await fetch(`http://127.0.0.1:${port}/mcp`, {
      method: "OPTIONS",
      headers: { origin: "http://localhost:6274" }
    });
    expect(preflight.status).toBe(204);
    expect(preflight.headers.get("access-control-allow-origin"))
      .toBe("http://localhost:6274");
    expect(preflight.headers.get("access-control-allow-origin")).not.toBe("*");

    const hostileOrigin = await fetch(rootUrl, {
      headers: { origin: "https://attacker.example" }
    });
    expect(hostileOrigin.status).toBe(403);

    await expect(requestStatus(rootUrl, { host: "attacker.example" })).resolves.toBe(403);

    const client = new Client({ name: "http-test-client", version: "0.1.0" });
    await client.connect(new StreamableHTTPClientTransport(
      new URL(`http://127.0.0.1:${port}/mcp`)
    ));
    closers.push(async () => client.close());

    const tools = await client.listTools();
    expect(tools.tools).toHaveLength(3);
    const result = await client.callTool({ name: "get_upcoming_status", arguments: {} });
    expect(result.structuredContent).toMatchObject({ action: "get_upcoming_status" });
  });
});
