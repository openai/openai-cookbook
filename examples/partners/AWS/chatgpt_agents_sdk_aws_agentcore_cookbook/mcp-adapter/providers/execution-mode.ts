export type CookbookExecutionMode = "local" | "deployed";

const LEGACY_MODE_MAP: Record<string, CookbookExecutionMode> = {
  "local-agent": "local",
  "agentcore-runtime": "deployed"
};

export function executionModeFromEnv(
  env: NodeJS.ProcessEnv = process.env
): CookbookExecutionMode {
  const configuredMode = env.COOKBOOK_EXECUTION_MODE?.trim();
  if (configuredMode && configuredMode !== "local" && configuredMode !== "deployed") {
    throw new Error("COOKBOOK_EXECUTION_MODE must be local or deployed");
  }
  const canonicalMode: CookbookExecutionMode | undefined =
    configuredMode === "local" || configuredMode === "deployed"
      ? configuredMode
      : undefined;

  const legacyDataSource = env.FLIGHT_DATA_SOURCE?.trim();
  const legacyMode = legacyDataSource ? LEGACY_MODE_MAP[legacyDataSource] : undefined;
  if (legacyDataSource && !legacyMode) {
    throw new Error("FLIGHT_DATA_SOURCE must be local-agent or agentcore-runtime");
  }
  if (canonicalMode && legacyMode && canonicalMode !== legacyMode) {
    throw new Error(
      "COOKBOOK_EXECUTION_MODE conflicts with legacy FLIGHT_DATA_SOURCE"
    );
  }

  return canonicalMode || legacyMode || "local";
}
