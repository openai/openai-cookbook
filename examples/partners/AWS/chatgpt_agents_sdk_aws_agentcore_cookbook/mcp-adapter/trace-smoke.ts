import { pathToFileURL } from "node:url";

import { RuntimeInvoker } from "./providers/agentcore-runtime-flight-provider.js";
import { createRuntimeInvoker } from "./providers/create-flight-provider.js";
import { executionModeFromEnv } from "./providers/execution-mode.js";
import { tracingModeFromEnvironment } from "./providers/local-agent-invoker.js";
import { RuntimeRequestSchema, RuntimeResponseSchema } from "./schemas/flight.js";

export async function runTraceSmoke(invokeRuntime?: RuntimeInvoker) {
  const executionMode = executionModeFromEnv();
  // A local .env selects the remote transport, not the Runtime's exporters.
  const tracingMode = executionMode === "local"
    ? tracingModeFromEnvironment()
    : "unknown";
  const request = RuntimeRequestSchema.parse({
    action: "get_live_status",
    flight_number: process.env.COOKBOOK_TRACE_FLIGHT_NUMBER?.trim() || "ELZ1628"
  });
  const startedAt = new Date().toISOString();
  const response = RuntimeResponseSchema.parse(
    await (invokeRuntime ?? createRuntimeInvoker())(request)
  );
  if (response.executionMode !== executionMode) {
    throw new Error("Trace smoke response does not match the selected execution mode");
  }
  if (response.action !== request.action) {
    throw new Error("Trace smoke response does not match the requested action");
  }
  const correlationId = response.trace?.runtimeSessionId;
  const invocationId = response.trace?.invocationId;
  if (!correlationId || !invocationId) {
    throw new Error("Trace smoke response is missing session/invocation correlation IDs");
  }

  return {
    response,
    trace_verification: {
      correlation_id: correlationId,
      invocation_id: invocationId,
      started_at: startedAt,
      execution_mode: executionMode,
      tracing_mode: tracingMode,
      tracing_mode_source: executionMode === "local" ? "local_launcher" : "runtime_not_observed",
      destinations: {
        aws: {
          status: "not_checked",
          next_action: "Run verify_traces.py with this correlation ID after ingestion."
        },
        openai: tracingMode === "aws"
          ? {
            status: "not_configured",
            next_action: "AWS-only local mode does not export to OpenAI Traces."
          }
          : {
            status: "not_checked",
            next_action: tracingMode === "dual"
              ? "A named verifier must confirm this correlation ID in OpenAI Traces."
              : "Ask the Runtime owner to confirm its aws/dual configuration; local settings do not configure it."
          }
      }
    }
  };
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  console.log(JSON.stringify(await runTraceSmoke()));
}
