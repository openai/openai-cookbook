const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const path = require("node:path");
const { PassThrough } = require("node:stream");
const test = require("node:test");

const AgentsSdkProvider = require("./agents-sdk-provider.cjs");
const {
  buildAgentProcessSpec,
  parseStructuredResult,
  runAgentProcess,
  sanitizeDiagnostic,
  validatedBedrockEnvironment,
} = AgentsSdkProvider;

const baseEnv = {
  AWS_REGION: "us-west-2",
  COOKBOOK_DEMO_TRAVEL_DATE: "2099-09-21",
  FLIGHT_DATA_SOURCE: "agentcore-runtime",
  COOKBOOK_TRACING_MODE: "aws",
  OPENAI_API_KEY: "bedrock-model-key",
  OPENAI_BASE_URL: "https://bedrock-mantle.us-west-2.api.aws/v1",
  RUN_PROMPTFOO_AGENT_EVALUATION: "1",
};
const request = { action: "get_upcoming_status" };
const context = {
  vars: {
    case_id: "upcoming-status",
    expected_action: "get_upcoming_status",
  },
};

function structuredOutput(runtimeSessionId, invocationId) {
  return `COOKBOOK_LOCAL_AGENT_RESULT=${JSON.stringify({
    provider: "agentcore-runtime",
    executionMode: "local",
    action: "get_upcoming_status",
    data: { flight: { flightNumber: "ELZ4321", status: "ON_TIME" } },
    trace: { runtimeSessionId, invocationId },
  })}`;
}

function createFakeChild({ closeOnSignal = "SIGTERM", errorOnSignal } = {}) {
  const child = new EventEmitter();
  child.stdout = new PassThrough();
  child.stderr = new PassThrough();
  child.stdin = new PassThrough();
  child.signals = [];
  child.kill = (signal) => {
    child.signals.push(signal);
    if (signal === errorOnSignal) {
      queueMicrotask(() => child.emit("error", new Error(`Could not send ${signal}`)));
    }
    if (signal === closeOnSignal) {
      queueMicrotask(() => child.emit("close", null, signal));
    }
    return true;
  };
  return child;
}

test("invokes one actual agent case and moves correlation into metadata", async () => {
  const observed = [];
  const ids = ["session-123", "invocation-456"];
  const provider = new AgentsSdkProvider(
    { id: "local-agents-sdk" },
    {
      env: baseEnv,
      idFactory: () => ids.shift(),
      runProcess: async (input) => {
        observed.push(input);
        return structuredOutput(input.runtimeSessionId, input.invocationId);
      },
    },
  );

  const result = await provider.callApi(JSON.stringify(request), context);

  assert.equal(provider.id(), "local-agents-sdk");
  assert.deepEqual(result.output, {
    provider: "agentcore-runtime",
    executionMode: "local",
    action: "get_upcoming_status",
    data: { flight: { flightNumber: "ELZ4321", status: "ON_TIME" } },
  });
  assert.deepEqual(result.metadata, {
    evaluation_case_id: "upcoming-status",
    runtime_session_id: "promptfoo-session-123",
    invocation_id: "promptfoo-upcoming-status-invocation-456",
  });
  assert.deepEqual(observed, [{
    request,
    runtimeSessionId: "promptfoo-session-123",
    invocationId: "promptfoo-upcoming-status-invocation-456",
    abortSignal: undefined,
    env: baseEnv,
  }]);
});

test("guard failure prevents an agent invocation", async () => {
  let invoked = false;
  const provider = new AgentsSdkProvider({}, {
    env: { ...baseEnv, RUN_PROMPTFOO_AGENT_EVALUATION: "0" },
    idFactory: () => "id",
    runProcess: async () => {
      invoked = true;
      return "";
    },
  });

  const result = await provider.callApi(JSON.stringify(request), context);

  assert.equal(invoked, false);
  assert.match(result.error, /RUN_PROMPTFOO_AGENT_EVALUATION=1 is required/);
});

test("reports missing environment names without credential values", async () => {
  const provider = new AgentsSdkProvider({}, {
    env: { RUN_PROMPTFOO_AGENT_EVALUATION: "1" },
    idFactory: () => "id",
  });

  const result = await provider.callApi(JSON.stringify(request), context);

  assert.match(result.error, /OPENAI_API_KEY/);
  assert.match(result.error, /OPENAI_BASE_URL/);
  assert.match(result.error, /AWS_REGION or AWS_DEFAULT_REGION/);
});

test("requires a trace key only when dual tracing is explicit", async () => {
  const provider = new AgentsSdkProvider({}, {
    env: { ...baseEnv, COOKBOOK_TRACING_MODE: "dual" },
    idFactory: () => "id",
  });

  const result = await provider.callApi(JSON.stringify(request), context);

  assert.match(result.error, /OPENAI_TRACE_API_KEY/);
});

test("rejects reuse of the Bedrock model credential for explicit dual tracing", async () => {
  const provider = new AgentsSdkProvider({}, {
    env: {
      ...baseEnv,
      COOKBOOK_TRACING_MODE: "dual",
      OPENAI_TRACE_API_KEY: baseEnv.OPENAI_API_KEY,
    },
    idFactory: () => "id",
  });

  const result = await provider.callApi(JSON.stringify(request), context);

  assert.match(result.error, /must use separate credentials/);
});

test("validates the exact Bedrock endpoint before invoking the agent", async () => {
  assert.deepEqual(validatedBedrockEnvironment(baseEnv), {
    endpoint: "https://bedrock-mantle.us-west-2.api.aws/v1",
    region: "us-west-2",
  });

  for (const endpoint of [
    "http://bedrock-mantle.us-west-2.api.aws/v1",
    "https://bedrock-mantle.us-west-2.api.aws.evil.example/v1",
    "https://user:password@bedrock-mantle.us-west-2.api.aws/v1",
    "https://bedrock-mantle.us-west-2.api.aws\\@evil.example/v1",
    "https://bedrock-mantle.us-west-2.api.aws:443/v1",
    "https://bedrock-mantle.us-east-1.api.aws/v1",
  ]) {
    assert.throws(
      () => validatedBedrockEnvironment({ ...baseEnv, OPENAI_BASE_URL: endpoint }),
      /not an approved AWS Bedrock endpoint/,
    );
  }
});

test("rejects an unapproved endpoint before starting the evaluation process", async () => {
  let invoked = false;
  const provider = new AgentsSdkProvider({}, {
    env: {
      ...baseEnv,
      OPENAI_BASE_URL: "https://bedrock-mantle.us-west-2.api.aws.evil.example/v1",
    },
    idFactory: () => "id",
    runProcess: async () => {
      invoked = true;
      return "";
    },
  });

  const result = await provider.callApi(JSON.stringify(request), context);

  assert.equal(invoked, false);
  assert.match(result.error, /not an approved AWS Bedrock endpoint/);
});

test("rejects malformed input and action drift before invocation", async () => {
  let invocations = 0;
  const provider = new AgentsSdkProvider({}, {
    env: baseEnv,
    idFactory: () => "id",
    runProcess: async () => {
      invocations += 1;
      return "";
    },
  });

  assert.match((await provider.callApi("not-json", context)).error, /not valid JSON/);
  assert.match(
    (await provider.callApi(
      JSON.stringify({ action: "get_live_status" }),
      context,
    )).error,
    /does not match/,
  );
  assert.equal(invocations, 0);
});

test("rejects missing, duplicate, malformed, and mismatched structured results", () => {
  assert.throws(
    () => parseStructuredResult("startup output", "session", "invocation"),
    /no structured result/,
  );
  const valid = structuredOutput("session", "invocation");
  assert.throws(
    () => parseStructuredResult(`${valid}\n${valid}`, "session", "invocation"),
    /multiple structured results/,
  );
  assert.throws(
    () => parseStructuredResult(
      "COOKBOOK_LOCAL_AGENT_RESULT=not-json",
      "session",
      "invocation",
    ),
    /invalid structured JSON/,
  );
  assert.throws(
    () => parseStructuredResult(valid, "other-session", "invocation"),
    /mismatched correlation IDs/,
  );
});

test("builds the existing instrumented subprocess with safe forced settings", () => {
  const spec = buildAgentProcessSpec({
    request,
    runtimeSessionId: "session",
    invocationId: "invocation",
    env: baseEnv,
  });

  assert.equal(spec.command, "uv");
  assert.deepEqual(spec.args, [
    "run",
    "--locked",
    "opentelemetry-instrument",
    "python",
    "local_invoke.py",
  ]);
  assert.equal(spec.env.COOKBOOK_EXECUTION_MODE, "local");
  assert.equal(spec.env.COOKBOOK_DEMO_TRAVEL_DATE, "2099-09-21");
  assert.equal(spec.env.COOKBOOK_FORCE_LOCAL_TOOLS, "0");
  assert.equal(spec.env.COOKBOOK_MANUAL_OPENAI_AGENTS_INSTRUMENTATION, "true");
  assert.equal(spec.env.COOKBOOK_TRACING_MODE, "aws");
  assert.equal(spec.env.OTEL_PYTHON_DISABLED_INSTRUMENTATIONS, "openai_agents");
  assert.equal(spec.env.OPENAI_TRACE_API_KEY, undefined);
  assert.equal(spec.env.OPENAI_TRACE_INCLUDE_SENSITIVE_DATA, "0");
  assert.equal(spec.env.OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT, "false");
  assert.equal(spec.env.FLIGHT_DATA_SOURCE, undefined);
  assert.equal(spec.env.UNRELATED_SECRET, undefined);
  assert.equal(spec.env.OTEL_EXPORTER_OTLP_ENDPOINT, undefined);
  assert.match(spec.env.OTEL_RESOURCE_ATTRIBUTES, /evaluation\.framework=promptfoo/);
  assert.deepEqual(JSON.parse(spec.input), {
    request,
    runtime_session_id: "session",
    invocation_id: "invocation",
    execution_mode: "local",
  });
});

test("forwards OpenAI trace credentials only for explicit dual tracing", () => {
  const spec = buildAgentProcessSpec({
    request,
    runtimeSessionId: "session",
    invocationId: "invocation",
    env: {
      ...baseEnv,
      COOKBOOK_TRACING_MODE: "dual",
      OPENAI_PROJECT_ID: "proj_platform",
      OPENAI_TRACE_API_KEY: "openai-trace-key",
    },
  });

  assert.equal(spec.env.COOKBOOK_TRACING_MODE, "dual");
  assert.equal(spec.env.OPENAI_TRACE_API_KEY, "openai-trace-key");
  assert.equal(spec.env.OPENAI_PROJECT_ID, "proj_platform");
});

test("passes only approved parent environment values to the child", () => {
  const spec = buildAgentProcessSpec({
    request,
    runtimeSessionId: "session",
    invocationId: "invocation",
    env: {
      ...baseEnv,
      AWS_PROFILE: "agentcore-dev",
      PATH: "/usr/bin",
      UV_CACHE_DIR: "/tmp/uv-cache",
      UNRELATED_SECRET: "must-not-reach-child",
      OTEL_EXPORTER_OTLP_ENDPOINT: "https://stale.example",
    },
  });

  assert.equal(spec.env.AWS_PROFILE, "agentcore-dev");
  assert.equal(spec.env.PATH, "/usr/bin");
  assert.equal(spec.env.UV_CACHE_DIR, "/tmp/uv-cache");
  assert.equal(spec.env.UV_INDEX_URL, undefined);
  assert.equal(spec.env.UNRELATED_SECRET, undefined);
  assert.equal(spec.env.OTEL_EXPORTER_OTLP_ENDPOINT, undefined);
});

test("waits for termination and escalates a timed-out process", async () => {
  const child = createFakeChild({ closeOnSignal: "SIGKILL" });
  const result = runAgentProcess({
    request,
    runtimeSessionId: "session",
    invocationId: "invocation",
    env: baseEnv,
  }, {
    spawnImpl: () => child,
    timeoutMsOverride: 5,
    terminationGraceMs: 5,
  });

  await assert.rejects(result, /timed out/);
  assert.deepEqual(child.signals, ["SIGTERM", "SIGKILL"]);
});

test("keeps SIGKILL escalation armed when SIGTERM emits an error", async () => {
  const child = createFakeChild({
    closeOnSignal: "SIGKILL",
    errorOnSignal: "SIGTERM",
  });
  const result = runAgentProcess({
    request,
    runtimeSessionId: "session",
    invocationId: "invocation",
    env: baseEnv,
  }, {
    spawnImpl: () => child,
    timeoutMsOverride: 5,
    terminationGraceMs: 5,
  });

  await assert.rejects(result, /timed out/);
  assert.deepEqual(child.signals, ["SIGTERM", "SIGKILL"]);
});

test("rejects at the final deadline when SIGKILL errors without close", {
  timeout: 250,
}, async () => {
  const child = createFakeChild({
    closeOnSignal: null,
    errorOnSignal: "SIGKILL",
  });
  const result = runAgentProcess({
    request,
    runtimeSessionId: "session",
    invocationId: "invocation",
    env: baseEnv,
  }, {
    spawnImpl: () => child,
    timeoutMsOverride: 5,
    terminationGraceMs: 5,
  });

  await assert.rejects(result, /timed out after 5ms/);
  assert.deepEqual(child.signals, ["SIGTERM", "SIGKILL"]);
});

test("terminates an aborted process before rejecting", async () => {
  const child = createFakeChild();
  const controller = new AbortController();
  const result = runAgentProcess({
    request,
    runtimeSessionId: "session",
    invocationId: "invocation",
    abortSignal: controller.signal,
    env: baseEnv,
  }, {
    spawnImpl: () => child,
  });

  controller.abort();

  await assert.rejects(result, /was aborted/);
  assert.deepEqual(child.signals, ["SIGTERM"]);
});

test("terminates a process whose output exceeds the bounded buffer", async () => {
  const child = createFakeChild();
  const result = runAgentProcess({
    request,
    runtimeSessionId: "session",
    invocationId: "invocation",
    env: baseEnv,
  }, {
    spawnImpl: () => child,
  });

  child.stdout.write("x".repeat(1_048_577));

  await assert.rejects(result, /exceeded 1 MiB/);
  assert.deepEqual(child.signals, ["SIGTERM"]);
});

test("redacts passed credentials and bearer tokens from diagnostics", () => {
  const environment = {
    ...baseEnv,
    AWS_CUSTOM_CREDENTIAL: "custom-credential-value",
    OPENAI_TRACE_API_KEY: "openai-trace-key",
  };
  const diagnostic = sanitizeDiagnostic(
    "key=bedrock-model-key trace=openai-trace-key "
      + "custom=custom-credential-value Bearer abc123",
    environment,
  );

  assert.doesNotMatch(
    diagnostic,
    /bedrock-model-key|openai-trace-key|custom-credential-value|abc123/,
  );
  assert.match(diagnostic, /REDACTED/);
});

test("redacts credentials embedded in proxy and package-index URLs", () => {
  const diagnostic = sanitizeDiagnostic(
    "proxy=https://proxy-user:proxy-password@proxy.example "
      + "index=https://index-token@packages.example/simple",
    baseEnv,
  );

  assert.doesNotMatch(
    diagnostic,
    /proxy-user|proxy-password|index-token/,
  );
  assert.match(
    diagnostic,
    /https:\/\/\[REDACTED\]@proxy\.example/,
  );
  assert.match(
    diagnostic,
    /https:\/\/\[REDACTED\]@packages\.example/,
  );
});

test("Promptfoo loads the configured CommonJS provider without invoking it", async () => {
  process.env.PROMPTFOO_CONFIG_DIR = path.join(
    __dirname,
    "results",
    ".promptfoo-provider-test",
  );
  process.env.PROMPTFOO_DISABLE_TELEMETRY = "true";
  process.env.PROMPTFOO_DISABLE_UPDATE = "true";
  const { loadApiProviders } = require("promptfoo");
  const config = require("../promptfooconfig.agent.cjs");

  const providers = await loadApiProviders(config.providers, {
    basePath: path.resolve(__dirname, ".."),
  });

  assert.equal(providers.length, 1);
  assert.equal(providers[0].id(), "local-agents-sdk");
});
