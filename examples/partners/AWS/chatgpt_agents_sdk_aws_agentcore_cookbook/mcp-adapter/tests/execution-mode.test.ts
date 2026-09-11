import { describe, expect, it } from "vitest";

import { executionModeFromEnv } from "../providers/execution-mode.js";

describe("cookbook execution mode", () => {
  it("defaults to local", () => {
    expect(executionModeFromEnv({})).toBe("local");
  });

  it("accepts the canonical local and deployed values", () => {
    expect(executionModeFromEnv({ COOKBOOK_EXECUTION_MODE: "local" })).toBe("local");
    expect(executionModeFromEnv({ COOKBOOK_EXECUTION_MODE: "deployed" })).toBe("deployed");
  });

  it("maps legacy values without breaking existing environments", () => {
    expect(executionModeFromEnv({ FLIGHT_DATA_SOURCE: "local-agent" })).toBe("local");
    expect(executionModeFromEnv({ FLIGHT_DATA_SOURCE: "agentcore-runtime" })).toBe("deployed");
  });

  it("fails fast when canonical and legacy settings disagree", () => {
    expect(() => executionModeFromEnv({
      COOKBOOK_EXECUTION_MODE: "local",
      FLIGHT_DATA_SOURCE: "agentcore-runtime"
    })).toThrow("conflicts");
  });

  it("rejects unknown canonical and legacy values", () => {
    expect(() => executionModeFromEnv({ COOKBOOK_EXECUTION_MODE: "remote" }))
      .toThrow("local or deployed");
    expect(() => executionModeFromEnv({ FLIGHT_DATA_SOURCE: "stub" }))
      .toThrow("local-agent or agentcore-runtime");
  });
});
