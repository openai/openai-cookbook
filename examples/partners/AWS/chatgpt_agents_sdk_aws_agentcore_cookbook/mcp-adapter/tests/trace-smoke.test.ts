import { execFileSync } from "node:child_process";
import {
  copyFileSync,
  cpSync,
  mkdirSync,
  mkdtempSync,
  rmSync,
  symlinkSync,
  writeFileSync
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import {
  BedrockAgentCoreClient,
  InvokeAgentRuntimeCommand,
  InvokeAgentRuntimeCommandOutput
} from "@aws-sdk/client-bedrock-agentcore";
import { afterEach, describe, expect, it, vi } from "vitest";

import { runTraceSmoke } from "../trace-smoke.js";

const adapterDirectory = fileURLToPath(new URL("..", import.meta.url));
const localResponse = {
  provider: "agentcore-runtime",
  executionMode: "local",
  action: "get_live_status",
  data: {
    flight: {
      flightNumber: "ELZ1628",
      origin: "DAL",
      destination: "MDW",
      travelDate: "2099-09-21",
      status: "ON_TIME",
      summary: "Read-only sample status."
    }
  },
  trace: { runtimeSessionId: "actual-session-123", invocationId: "actual-invocation-456" }
};

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllEnvs();
});

describe("selected-route trace smoke", () => {
  it.each(["aws", "dual"])("reports actual correlation without claiming %s delivery", async (mode) => {
    vi.stubEnv("COOKBOOK_EXECUTION_MODE", "local");
    vi.stubEnv("FLIGHT_DATA_SOURCE", undefined);
    vi.stubEnv("COOKBOOK_TRACING_MODE", mode);
    vi.stubEnv("COOKBOOK_TRACE_FLIGHT_NUMBER", "ELZ1628");
    const invoke = vi.fn(async () => localResponse);

    const report = await runTraceSmoke(invoke);

    expect(invoke).toHaveBeenCalledWith({ action: "get_live_status", flight_number: "ELZ1628" });
    expect(report.trace_verification).toMatchObject({
      correlation_id: "actual-session-123",
      invocation_id: "actual-invocation-456",
      execution_mode: "local",
      tracing_mode: mode,
      tracing_mode_source: "local_launcher",
      destinations: {
        aws: { status: "not_checked" },
        openai: { status: mode === "aws" ? "not_configured" : "not_checked" }
      }
    });
    expect(Number.isNaN(Date.parse(report.trace_verification.started_at))).toBe(false);
  });

  it("uses the real deployed transport without local model credentials or a local worker", async () => {
    vi.stubEnv("COOKBOOK_EXECUTION_MODE", "deployed");
    vi.stubEnv("FLIGHT_DATA_SOURCE", undefined);
    vi.stubEnv("COOKBOOK_TRACING_MODE", "dual");
    vi.stubEnv("COOKBOOK_TRACE_FLIGHT_NUMBER", undefined);
    vi.stubEnv("AGENTCORE_RUNTIME_AGENT_ARN", "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/test");
    vi.stubEnv("AGENTCORE_RUNTIME_REGION", "us-east-1");
    vi.stubEnv("AWS_REGION", "us-west-2");
    vi.stubEnv("OPENAI_API_KEY", undefined);
    vi.stubEnv("OPENAI_BASE_URL", undefined);
    vi.stubEnv("OPENAI_TRACE_API_KEY", undefined);
    vi.stubEnv("UV_BIN", "/no-local-worker-exists");
    const runtimeOutput: InvokeAgentRuntimeCommandOutput = {
      $metadata: { requestId: "aws-request-123" },
      statusCode: 200,
      contentType: "application/json",
      runtimeSessionId: "returned-runtime-session-123",
      response: {
        transformToString: async () => JSON.stringify({
          ...localResponse,
          executionMode: "deployed",
          trace: undefined
        })
      } as InvokeAgentRuntimeCommandOutput["response"]
    };
    // The SDK's final send overload is callback-based; this call uses its Promise overload.
    const send = vi.spyOn(BedrockAgentCoreClient.prototype, "send")
      .mockResolvedValue(runtimeOutput as never);

    const report = await runTraceSmoke();

    expect(send).toHaveBeenCalledOnce();
    const command = send.mock.calls[0]![0] as InvokeAgentRuntimeCommand;
    expect(command).toBeInstanceOf(InvokeAgentRuntimeCommand);
    const payload = JSON.parse(Buffer.from(command.input.payload as Uint8Array).toString("utf8"));
    expect(payload).toEqual({
      request: { action: "get_live_status", flight_number: "ELZ1628" },
      invocation_id: command.input.runtimeSessionId,
      execution_mode: "deployed"
    });
    expect(report.trace_verification).toMatchObject({
      correlation_id: "returned-runtime-session-123",
      invocation_id: payload.invocation_id,
      execution_mode: "deployed",
      tracing_mode: "unknown",
      tracing_mode_source: "runtime_not_observed",
      destinations: { aws: { status: "not_checked" }, openai: { status: "not_checked" } }
    });
    const client = send.mock.contexts[0] as BedrockAgentCoreClient;
    expect(await client.config.region()).toBe("us-east-1");
    expect(report.response.executionMode).toBe("deployed");
  });

  it("rejects missing correlation, the wrong route, or the wrong action", async () => {
    vi.stubEnv("COOKBOOK_EXECUTION_MODE", "local");
    vi.stubEnv("FLIGHT_DATA_SOURCE", undefined);
    vi.stubEnv("COOKBOOK_TRACING_MODE", "aws");

    await expect(runTraceSmoke(async () => ({ ...localResponse, trace: undefined })))
      .rejects.toThrow("missing session/invocation correlation IDs");
    await expect(runTraceSmoke(async () => ({ ...localResponse, executionMode: "deployed" })))
      .rejects.toThrow("does not match the selected execution mode");
    await expect(runTraceSmoke(async () => ({ ...localResponse, action: "get_upcoming_status" })))
      .rejects.toThrow("does not match the requested action");
  });

  it("runs the documented npm entrypoint through the instrumented local launcher", () => {
    // Exercise the exact nested npm command in an isolated checkout with dummy
    // configuration. The fake uv worker verifies its launch contract; Python's
    // in-memory span test separately exercises the real SDK and baggage bridge.
    const repository = mkdtempSync(join(tmpdir(), "cookbook-trace-smoke-"));
    try {
      execFileSync(process.execPath, [
        resolve(adapterDirectory, "node_modules/typescript/bin/tsc"),
        "-p", resolve(adapterDirectory, "tsconfig.build.json")
      ], { cwd: adapterDirectory, stdio: "pipe" });
      mkdirSync(join(repository, "mcp-adapter"));
      mkdirSync(join(repository, "runtime-agent"));
      copyFileSync(join(adapterDirectory, "package.json"), join(repository, "mcp-adapter/package.json"));
      copyFileSync(
        resolve(adapterDirectory, "../runtime-agent/package.json"),
        join(repository, "runtime-agent/package.json")
      );
      cpSync(join(adapterDirectory, "dist"), join(repository, "mcp-adapter/dist"), { recursive: true });
      symlinkSync(
        join(adapterDirectory, "node_modules"),
        join(repository, "mcp-adapter/node_modules"),
        "junction"
      );
      const uv = join(repository, "fake-uv.cjs");
      writeFileSync(uv, `#!/usr/bin/env node
const assert = require("node:assert/strict");
const fs = require("node:fs");
assert.deepEqual(process.argv.slice(2), ["run", "--locked", "opentelemetry-instrument", "python", "local_invoke.py"]);
const payload = JSON.parse(fs.readFileSync(0, "utf8"));
assert.equal(payload.execution_mode, "local");
assert.equal(payload.request.action, "get_live_status");
assert.equal(payload.runtime_session_id, payload.invocation_id);
assert.ok(payload.runtime_session_id);
for (const [name, value] of Object.entries({
  AGENT_OBSERVABILITY_ENABLED: "true",
  AWS_REGION: "us-west-2",
  AWS_DEFAULT_REGION: "us-west-2",
  COOKBOOK_TRACING_MODE: "aws",
  COOKBOOK_MANUAL_OPENAI_AGENTS_INSTRUMENTATION: "true",
  OTEL_PYTHON_DISABLED_INSTRUMENTATIONS: "openai_agents",
  OTEL_PYTHON_CONFIGURATOR: "aws_configurator",
  OTEL_PYTHON_DISTRO: "aws_distro",
  OTEL_TRACES_EXPORTER: "otlp",
  OTEL_SDK_DISABLED: "false",
  OPENAI_TRACE_INCLUDE_SENSITIVE_DATA: "0",
  OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT: "false"
})) assert.equal(process.env[name], value, name);
assert.equal(process.env.OPENAI_TRACE_API_KEY, undefined);
assert.equal(process.env.OPENAI_PROJECT_ID, undefined);
assert.equal(process.env.UNRELATED_SECRET, undefined);
console.log("ADOT startup output");
console.log("COOKBOOK_LOCAL_AGENT_RESULT=" + JSON.stringify({
  ...${JSON.stringify(localResponse)},
  trace: { runtimeSessionId: payload.runtime_session_id, invocationId: payload.invocation_id }
}));
`, { mode: 0o755 });
      writeFileSync(join(repository, ".env"), [
        "COOKBOOK_EXECUTION_MODE=local",
        "COOKBOOK_TRACING_MODE=aws",
        "AWS_REGION=us-west-2",
        "OPENAI_API_KEY=offline-bedrock-key",
        "OPENAI_BASE_URL=https://bedrock-mantle.us-west-2.api.aws/v1",
        "OPENAI_TRACE_API_KEY=must-not-reach-worker",
        "OPENAI_PROJECT_ID=must-not-reach-worker",
        "UNRELATED_SECRET=must-not-reach-worker",
        `UV_BIN=${uv}`,
        `RUNTIME_AGENT_DIRECTORY=${join(repository, "runtime-agent")}`,
        ""
      ].join("\n"));
      writeFileSync(join(repository, ".npmrc"), "");

      const output = execFileSync("npm", [
        "--prefix", "runtime-agent", "run", "--silent", "trace:run"
      ], {
        cwd: repository,
        env: {
          PATH: `${dirname(process.execPath)}:${process.env.PATH ?? ""}`,
          HOME: repository,
          NPM_CONFIG_USERCONFIG: join(repository, ".npmrc"),
          NPM_CONFIG_CACHE: join(repository, ".npm-cache")
        },
        encoding: "utf8",
        timeout: 10_000
      });

      const report = JSON.parse(output);
      expect(report.trace_verification.execution_mode).toBe("local");
      expect(report.trace_verification.correlation_id).toBe(report.response.trace.runtimeSessionId);
      expect(report.trace_verification.invocation_id).toBe(report.response.trace.invocationId);
      expect(report.trace_verification.destinations.aws.status).toBe("not_checked");
      expect(report.trace_verification.destinations.openai.status).toBe("not_configured");
    } finally {
      rmSync(repository, { recursive: true, force: true });
    }
  }, 20_000);
});
