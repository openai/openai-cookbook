const assert = require("node:assert/strict");
const path = require("node:path");
const test = require("node:test");

const {
  RESULTS_DIRECTORY,
  buildRunnerEnvironment,
  buildResultPath,
} = require("./run-agent-evaluation.cjs");

test("uses a unique timestamped path inside the ignored results directory", () => {
  const resultPath = buildResultPath(
    new Date("2026-07-25T12:34:56.789Z"),
    "12345678-aaaa-bbbb-cccc-dddddddddddd",
  );

  assert.equal(path.dirname(resultPath), RESULTS_DIRECTORY);
  assert.equal(
    path.basename(resultPath),
    "promptfoo-agent-2026-07-25T12-34-56-789Z-12345678.json",
  );
  assert.doesNotMatch(resultPath, /latest/);
});

test("uses AWS-only tracing by default and drops unneeded platform credentials", () => {
  const env = buildRunnerEnvironment({
    AWS_PROFILE: "agentcore-dev",
    HTTPS_PROXY: "https://proxy.example",
    OPENAI_API_KEY: "model-key",
    OPENAI_TRACE_API_KEY: "trace-key",
    PATH: "/usr/bin",
    PROMPTFOO_AGENT_EVALUATION_CASE_IDS: "upcoming-status",
    PROMPTFOO_AGENT_EVALUATION_TIMEOUT_MS: "120000",
    RUN_PROMPTFOO_AGENT_EVALUATION: "1",
    UNRELATED_PROJECT_TOKEN: "must-not-reach-promptfoo",
    UV_CACHE_DIR: "/tmp/uv-cache",
    UV_INDEX_URL: "https://user:password@packages.example/simple",
  }, "/tmp/private-promptfoo");

  assert.equal(env.AWS_PROFILE, "agentcore-dev");
  assert.equal(env.OPENAI_API_KEY, "model-key");
  assert.equal(env.OPENAI_TRACE_API_KEY, undefined);
  assert.equal(env.COOKBOOK_TRACING_MODE, "aws");
  assert.equal(env.PROMPTFOO_AGENT_EVALUATION_CASE_IDS, "upcoming-status");
  assert.equal(env.PROMPTFOO_AGENT_EVALUATION_TIMEOUT_MS, "120000");
  assert.equal(env.RUN_PROMPTFOO_AGENT_EVALUATION, "1");
  assert.equal(env.UV_CACHE_DIR, "/tmp/uv-cache");
  assert.equal(env.UV_INDEX_URL, undefined);
  assert.equal(env.UNRELATED_PROJECT_TOKEN, undefined);
  assert.equal(env.PROMPTFOO_CONFIG_DIR, "/tmp/private-promptfoo");
  assert.equal(env.PROMPTFOO_DISABLE_REMOTE_GENERATION, "true");
  assert.equal(env.PROMPTFOO_DISABLE_SHARING, "true");
});

test("preserves the OpenAI trace credential for explicit dual tracing", () => {
  const env = buildRunnerEnvironment({
    AWS_PROFILE: "agentcore-dev",
    COOKBOOK_TRACING_MODE: "dual",
    OPENAI_API_KEY: "model-key",
    OPENAI_TRACE_API_KEY: "trace-key",
  }, "/tmp/private-promptfoo");

  assert.equal(env.COOKBOOK_TRACING_MODE, "dual");
  assert.equal(env.OPENAI_TRACE_API_KEY, "trace-key");
});
