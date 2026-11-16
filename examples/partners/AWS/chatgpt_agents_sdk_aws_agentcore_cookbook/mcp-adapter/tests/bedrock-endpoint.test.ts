import { describe, expect, it } from "vitest";

import { validateBedrockEnvironment } from "../providers/bedrock-endpoint.js";

const validEnvironment = {
  AWS_REGION: "us-west-2",
  OPENAI_BASE_URL: "https://bedrock-mantle.us-west-2.api.aws/v1"
};

describe("Bedrock endpoint validation", () => {
  it("accepts the exact endpoint for the configured region", () => {
    expect(validateBedrockEnvironment(validEnvironment)).toEqual({
      endpoint: validEnvironment.OPENAI_BASE_URL,
      region: "us-west-2"
    });
  });

  it.each([
    "http://bedrock-mantle.us-west-2.api.aws/v1",
    "https://evil.example/bedrock-mantle.us-west-2.api.aws/v1",
    "https://bedrock-mantle.us-west-2.api.aws.evil.example/v1",
    "https://user:password@bedrock-mantle.us-west-2.api.aws/v1",
    "https://bedrock-mantle.us-west-2.api.aws\\@evil.example/v1",
    "https://bedrock-mantle.us-west-2.api.aws:443/v1",
    "https://bedrock-mantle.us-west-2.api.aws/v1?bedrock=true",
    "https://bedrock-mantle.us-west-2.api.aws/v1#fragment",
    "https://bedrock-mantle.us-east-1.api.aws/v1",
    "not a url",
    ""
  ])("rejects an unapproved endpoint before process creation: %s", (endpoint) => {
    expect(() => validateBedrockEnvironment({
      ...validEnvironment,
      OPENAI_BASE_URL: endpoint
    })).toThrow("not an approved AWS Bedrock endpoint");
  });

  it("rejects conflicting AWS region variables", () => {
    expect(() => validateBedrockEnvironment({
      ...validEnvironment,
      AWS_DEFAULT_REGION: "us-east-1"
    })).toThrow("must match");
  });
});
