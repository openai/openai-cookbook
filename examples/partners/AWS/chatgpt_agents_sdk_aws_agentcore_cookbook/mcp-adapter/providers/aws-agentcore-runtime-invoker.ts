import { randomUUID } from "node:crypto";

import {
  BedrockAgentCoreClient,
  InvokeAgentRuntimeCommand,
  InvokeAgentRuntimeCommandOutput
} from "@aws-sdk/client-bedrock-agentcore";

import { RuntimeRequest } from "../schemas/flight.js";
import {
  RuntimeInvocationContext,
  RuntimeInvoker
} from "./agentcore-runtime-flight-provider.js";
import { correlationSessionId } from "./runtime-correlation.js";

export interface AgentCoreRuntimeConfig {
  agentRuntimeArn: string;
  region: string;
  qualifier?: string;
  runtimeUserId?: string;
}

export type SendAgentCoreCommand = (
  command: InvokeAgentRuntimeCommand
) => Promise<InvokeAgentRuntimeCommandOutput>;

export type RuntimeSessionIdFactory = () => string;

export function runtimeConfigFromEnv(): AgentCoreRuntimeConfig {
  const agentRuntimeArn = process.env.AGENTCORE_RUNTIME_AGENT_ARN?.trim();
  if (!agentRuntimeArn) {
    throw new Error("Missing AGENTCORE_RUNTIME_AGENT_ARN for AgentCore Runtime provider");
  }

  return {
    agentRuntimeArn,
    region:
      process.env.AGENTCORE_RUNTIME_REGION?.trim() ||
      process.env.AWS_REGION?.trim() ||
      process.env.AWS_DEFAULT_REGION?.trim() ||
      "us-west-2",
    qualifier: process.env.AGENTCORE_RUNTIME_QUALIFIER?.trim() || undefined,
    runtimeUserId: process.env.AGENTCORE_RUNTIME_USER_ID?.trim() || undefined
  };
}

export function createAgentCoreRuntimeInvoker(
  config: AgentCoreRuntimeConfig,
  sendCommand?: SendAgentCoreCommand,
  sessionIdFactory: RuntimeSessionIdFactory = randomUUID
): RuntimeInvoker {
  const client = sendCommand ? undefined : new BedrockAgentCoreClient({ region: config.region });
  const send = sendCommand ?? ((command: InvokeAgentRuntimeCommand) => client!.send(command));

  return async (request: RuntimeRequest, context?: RuntimeInvocationContext) => {
    const invocationId = sessionIdFactory();
    const runtimeSessionId = correlationSessionId(context, invocationId);
    const command = new InvokeAgentRuntimeCommand({
      agentRuntimeArn: config.agentRuntimeArn,
      qualifier: config.qualifier,
      runtimeUserId: config.runtimeUserId,
      contentType: "application/json",
      accept: "application/json",
      runtimeSessionId,
      payload: Buffer.from(JSON.stringify({
        request,
        invocation_id: invocationId,
        execution_mode: "deployed"
      }), "utf8")
    });
    const output = await send(command);

    if (output.statusCode !== undefined && (output.statusCode < 200 || output.statusCode >= 300)) {
      throw new Error(`AgentCore Runtime returned HTTP ${output.statusCode}`);
    }
    if (!output.response) {
      throw new Error("AgentCore Runtime returned an empty response");
    }

    const body = await output.response.transformToString();
    let parsed: unknown;
    try {
      parsed = JSON.parse(body);
    } catch {
      throw new Error("AgentCore Runtime returned invalid JSON");
    }
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
      throw new Error("AgentCore Runtime returned a non-object JSON response");
    }

    return {
      ...parsed,
      executionMode: "deployed",
      trace: {
        traceId: output.traceId,
        requestId: output.$metadata.requestId,
        runtimeSessionId: output.runtimeSessionId ?? runtimeSessionId,
        invocationId
      }
    };
  };
}

export function createAgentCoreRuntimeInvokerFromEnv(): RuntimeInvoker {
  return createAgentCoreRuntimeInvoker(runtimeConfigFromEnv());
}
