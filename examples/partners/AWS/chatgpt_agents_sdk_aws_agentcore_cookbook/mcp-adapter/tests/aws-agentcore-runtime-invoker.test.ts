import {
  InvokeAgentRuntimeCommand,
  InvokeAgentRuntimeCommandOutput
} from "@aws-sdk/client-bedrock-agentcore";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createAgentCoreRuntimeInvoker,
  runtimeConfigFromEnv,
  SendAgentCoreCommand
} from "../providers/aws-agentcore-runtime-invoker.js";
import { RuntimeResponseSchema } from "../schemas/flight.js";

const runtimeBody = {
  provider: "agentcore-runtime",
  action: "get_upcoming_status",
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

afterEach(() => {
  vi.unstubAllEnvs();
});

function output(body: string, statusCode = 200): InvokeAgentRuntimeCommandOutput {
  return {
    $metadata: { requestId: "aws-request-123" },
    statusCode,
    traceId: "aws-trace-123",
    runtimeSessionId: "runtime-session-123",
    contentType: "application/json",
    response: {
      transformToString: async () => body
    } as InvokeAgentRuntimeCommandOutput["response"]
  };
}

describe("AWS AgentCore Runtime invoker", () => {
  it("loads an existing Runtime ARN and optional qualifier from the environment", () => {
    vi.stubEnv(
      "AGENTCORE_RUNTIME_AGENT_ARN",
      "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/existing_agent"
    );
    vi.stubEnv("AGENTCORE_RUNTIME_REGION", "us-east-1");
    vi.stubEnv("AWS_REGION", "us-west-2");
    vi.stubEnv("AGENTCORE_RUNTIME_QUALIFIER", "DEFAULT");

    expect(runtimeConfigFromEnv()).toEqual({
      agentRuntimeArn:
        "arn:aws:bedrock-agentcore:us-east-1:123456789012:runtime/existing_agent",
      region: "us-east-1",
      qualifier: "DEFAULT",
      runtimeUserId: undefined
    });
  });

  it("uses AWS_REGION when an AgentCore-specific region is not set", () => {
    vi.stubEnv("AGENTCORE_RUNTIME_AGENT_ARN", "arn:test");
    vi.stubEnv("AGENTCORE_RUNTIME_REGION", "");
    vi.stubEnv("AWS_REGION", "eu-west-1");

    expect(runtimeConfigFromEnv().region).toBe("eu-west-1");
  });

  it("uses AWS_DEFAULT_REGION when neither higher-priority region is set", () => {
    vi.stubEnv("AGENTCORE_RUNTIME_AGENT_ARN", "arn:test");
    vi.stubEnv("AGENTCORE_RUNTIME_REGION", "");
    vi.stubEnv("AWS_REGION", "");
    vi.stubEnv("AWS_DEFAULT_REGION", "eu-central-1");

    expect(runtimeConfigFromEnv().region).toBe("eu-central-1");
  });

  it("requires an existing Runtime ARN", () => {
    vi.stubEnv("AGENTCORE_RUNTIME_AGENT_ARN", " ");

    expect(() => runtimeConfigFromEnv()).toThrow(
      "Missing AGENTCORE_RUNTIME_AGENT_ARN"
    );
  });

  it("sends the typed request and preserves real response metadata", async () => {
    const commands: InvokeAgentRuntimeCommand[] = [];
    const send: SendAgentCoreCommand = async (command) => {
      commands.push(command);
      return output(JSON.stringify(runtimeBody));
    };
    const invoke = createAgentCoreRuntimeInvoker({
      agentRuntimeArn: "arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/flight_status_agent",
      region: "us-west-2",
      qualifier: "DEFAULT"
    }, send, () => "runtime-session-generated-1234567890");

    await expect(invoke({ action: "get_upcoming_status" })).resolves.toEqual({
      ...runtimeBody,
      executionMode: "deployed",
      trace: {
        traceId: "aws-trace-123",
        requestId: "aws-request-123",
        runtimeSessionId: "runtime-session-123",
        invocationId: "runtime-session-generated-1234567890"
      }
    });

    expect(commands).toHaveLength(1);
    const command = commands[0]!;
    expect(command).toBeInstanceOf(InvokeAgentRuntimeCommand);
    expect(command.input).toMatchObject({
      agentRuntimeArn: "arn:aws:bedrock-agentcore:us-west-2:123456789012:runtime/flight_status_agent",
      qualifier: "DEFAULT",
      contentType: "application/json",
      accept: "application/json",
      runtimeSessionId: "runtime-session-generated-1234567890"
    });
    expect(command.input.payload).toBeInstanceOf(Uint8Array);
    expect(JSON.parse(Buffer.from(command.input.payload as Uint8Array).toString("utf8")))
      .toEqual({
        request: { action: "get_upcoming_status" },
        invocation_id: "runtime-session-generated-1234567890",
        execution_mode: "deployed"
      });
    expect(command.input.runtimeUserId).toBeUndefined();
  });

  it("overrides a stale Runtime mode with the selected deployed route", async () => {
    const invoke = createAgentCoreRuntimeInvoker({
      agentRuntimeArn: "arn:test",
      region: "us-west-2"
    }, async () => output(JSON.stringify({
      ...runtimeBody,
      executionMode: "local"
    })), () => "runtime-session-generated-1234567890");

    await expect(invoke({ action: "get_upcoming_status" })).resolves.toMatchObject({
      executionMode: "deployed"
    });
  });

  it("reuses one AgentCore session for multiple calls in a ChatGPT conversation", async () => {
    const commands: InvokeAgentRuntimeCommand[] = [];
    const invocationIds = ["invocation-1", "invocation-2"];
    const invoke = createAgentCoreRuntimeInvoker({
      agentRuntimeArn: "arn:test",
      region: "us-west-2"
    }, async (command) => {
      commands.push(command);
      return output(JSON.stringify(runtimeBody));
    }, () => invocationIds.shift()!);

    const context = { chatgptSessionId: "anonymous-chatgpt-conversation" };
    const first = RuntimeResponseSchema.parse(
      await invoke({ action: "get_upcoming_status" }, context)
    );
    const second = RuntimeResponseSchema.parse(
      await invoke({ action: "get_upcoming_status" }, context)
    );

    expect(commands[0]!.input.runtimeSessionId).toBe(commands[1]!.input.runtimeSessionId);
    expect(commands[0]!.input.runtimeSessionId).toMatch(/^chatgpt-[a-f0-9]{64}$/);
    const payloads = commands.map((command) => JSON.parse(
      Buffer.from(command.input.payload as Uint8Array).toString("utf8")
    ));
    expect(payloads).toEqual([
      {
        request: { action: "get_upcoming_status" },
        invocation_id: "invocation-1",
        execution_mode: "deployed"
      },
      {
        request: { action: "get_upcoming_status" },
        invocation_id: "invocation-2",
        execution_mode: "deployed"
      }
    ]);
    expect([first.trace?.invocationId, second.trace?.invocationId]).toEqual([
      "invocation-1",
      "invocation-2"
    ]);
  });

  it("rejects unsuccessful and malformed responses", async () => {
    const failed = createAgentCoreRuntimeInvoker({
      agentRuntimeArn: "arn:test",
      region: "us-west-2"
    }, async () => output("{}", 503));
    await expect(failed({ action: "get_upcoming_status" })).rejects.toThrow("HTTP 503");

    const malformed = createAgentCoreRuntimeInvoker({
      agentRuntimeArn: "arn:test",
      region: "us-west-2"
    }, async () => output("not-json"));
    await expect(malformed({ action: "get_upcoming_status" })).rejects.toThrow("invalid JSON");
  });

  it("does not invent a runtime user identity", () => {
    vi.stubEnv("AGENTCORE_RUNTIME_AGENT_ARN", "arn:test");
    vi.stubEnv("AGENTCORE_RUNTIME_USER_ID", "");

    expect(runtimeConfigFromEnv().runtimeUserId).toBeUndefined();
  });
});
