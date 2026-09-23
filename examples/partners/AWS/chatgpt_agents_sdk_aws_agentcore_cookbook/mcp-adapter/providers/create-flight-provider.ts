import { AgentCoreRuntimeFlightProvider, RuntimeInvoker } from "./agentcore-runtime-flight-provider.js";
import { createAgentCoreRuntimeInvokerFromEnv } from "./aws-agentcore-runtime-invoker.js";
import { executionModeFromEnv } from "./execution-mode.js";
import { createLocalAgentInvoker } from "./local-agent-invoker.js";

export function createRuntimeInvoker(executionMode = executionModeFromEnv()): RuntimeInvoker {
  return executionMode === "deployed"
    ? createAgentCoreRuntimeInvokerFromEnv()
    : createLocalAgentInvoker();
}

export function createFlightProvider(invokeRuntime?: RuntimeInvoker) {
  const executionMode = executionModeFromEnv();
  return new AgentCoreRuntimeFlightProvider(
    invokeRuntime ?? createRuntimeInvoker(executionMode)
  );
}
