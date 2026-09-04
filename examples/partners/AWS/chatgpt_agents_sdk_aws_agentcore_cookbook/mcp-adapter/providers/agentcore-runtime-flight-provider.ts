import {
  McpStructuredContentSchema,
  RuntimeRequest,
  RuntimeRequestSchema,
  RuntimeResponse,
  RuntimeResponseSchema
} from "../schemas/flight.js";

export interface RuntimeInvocationContext {
  chatgptSessionId?: string;
}

export type RuntimeInvoker = (
  request: RuntimeRequest,
  context?: RuntimeInvocationContext
) => Promise<unknown>;

export class AgentCoreRuntimeFlightProvider {
  constructor(private readonly invokeRuntime: RuntimeInvoker) {}

  async call(request: RuntimeRequest, context?: RuntimeInvocationContext) {
    const validatedRequest = RuntimeRequestSchema.parse(request);
    const raw = await this.invokeRuntime(validatedRequest, context);
    const runtimeResponse: RuntimeResponse = RuntimeResponseSchema.parse(raw);
    const structuredContent = McpStructuredContentSchema.parse({
      provider: runtimeResponse.provider,
      executionMode: runtimeResponse.executionMode,
      action: runtimeResponse.action,
      ...runtimeResponse.data
    });

    return {
      structuredContent,
      _meta: runtimeResponse.trace ?? {}
    };
  }
}
