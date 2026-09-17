export interface ValidatedBedrockEnvironment {
  endpoint: string;
  region: string;
}

export function validateBedrockEnvironment(
  env: NodeJS.ProcessEnv
): ValidatedBedrockEnvironment {
  const awsRegion = env.AWS_REGION?.trim();
  const awsDefaultRegion = env.AWS_DEFAULT_REGION?.trim();
  if (awsRegion && awsDefaultRegion && awsRegion !== awsDefaultRegion) {
    throw new Error("AWS_REGION and AWS_DEFAULT_REGION must match");
  }
  const region = awsRegion || awsDefaultRegion;
  if (!region) throw new Error("AWS_REGION or AWS_DEFAULT_REGION is required");
  if (!/^[a-z0-9]+(?:-[a-z0-9]+)+$/.test(region)) {
    throw new Error("The configured AWS region is invalid");
  }

  const endpoint = env.OPENAI_BASE_URL?.trim();
  const canonical = `https://bedrock-mantle.${region}.api.aws/v1`;
  if (!endpoint || endpoint !== env.OPENAI_BASE_URL || endpoint.includes("\\")) {
    throw new Error("OPENAI_BASE_URL is not an approved AWS Bedrock endpoint");
  }
  let parsed: URL;
  try {
    parsed = new URL(endpoint);
  } catch {
    throw new Error("OPENAI_BASE_URL is not an approved AWS Bedrock endpoint");
  }
  if (
    parsed.protocol !== "https:"
    || parsed.username
    || parsed.password
    || parsed.port
    || parsed.search
    || parsed.hash
    || parsed.hostname !== `bedrock-mantle.${region}.api.aws`
    || parsed.pathname !== "/v1"
    || endpoint !== canonical
  ) {
    throw new Error("OPENAI_BASE_URL is not an approved AWS Bedrock endpoint");
  }
  return { endpoint, region };
}
