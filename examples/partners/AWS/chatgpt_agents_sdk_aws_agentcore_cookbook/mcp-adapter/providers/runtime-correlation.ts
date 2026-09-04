import { createHash } from "node:crypto";

import { RuntimeInvocationContext } from "./agentcore-runtime-flight-provider.js";

export function correlationSessionId(
  context: RuntimeInvocationContext | undefined,
  fallbackInvocationId: string
): string {
  const chatgptSessionId = context?.chatgptSessionId?.trim();
  if (!chatgptSessionId) return fallbackInvocationId;

  // AgentCore Runtime session IDs have a stricter contract than host metadata.
  // Hashing gives both telemetry backends the same stable, non-reversible ID.
  return `chatgpt-${createHash("sha256").update(chatgptSessionId).digest("hex")}`;
}
