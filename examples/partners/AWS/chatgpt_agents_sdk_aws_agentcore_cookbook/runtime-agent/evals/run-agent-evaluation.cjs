const { spawnSync } = require("node:child_process");
const { randomUUID } = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const {
  allowedChildEnvironment,
  tracingModeFromEnvironment,
} = require("./agents-sdk-provider.cjs");

const RUNTIME_DIRECTORY = path.resolve(__dirname, "..");
const RESULTS_DIRECTORY = path.join(__dirname, "results");
const RUNNER_ENV_NAMES = [
  "PROMPTFOO_AGENT_EVALUATION_CASE_IDS",
  "PROMPTFOO_AGENT_EVALUATION_TIMEOUT_MS",
  "RUN_PROMPTFOO_AGENT_EVALUATION",
];

function buildResultPath(now = new Date(), id = randomUUID()) {
  const timestamp = now.toISOString().replace(/[:.]/g, "-");
  return path.join(
    RESULTS_DIRECTORY,
    `promptfoo-agent-${timestamp}-${id.slice(0, 8)}.json`,
  );
}

function buildRunnerEnvironment(env, configDirectory) {
  const tracingMode = tracingModeFromEnvironment(env);
  const runnerEnv = allowedChildEnvironment(env);
  if (tracingMode === "aws") {
    delete runnerEnv.OPENAI_TRACE_API_KEY;
    delete runnerEnv.OPENAI_PROJECT_ID;
  }
  for (const name of RUNNER_ENV_NAMES) {
    if (env[name] !== undefined) {
      runnerEnv[name] = env[name];
    }
  }
  return {
    ...runnerEnv,
    COOKBOOK_TRACING_MODE: tracingMode,
    PROMPTFOO_CONFIG_DIR: configDirectory,
    PROMPTFOO_DISABLE_REMOTE_GENERATION: "true",
    PROMPTFOO_DISABLE_SHARING: "true",
    PROMPTFOO_DISABLE_TELEMETRY: "true",
    PROMPTFOO_DISABLE_UPDATE: "true",
    PROMPTFOO_DISABLE_WAL_MODE: "true",
  };
}

function main({ spawnImpl = spawnSync } = {}) {
  process.umask(0o077);
  fs.mkdirSync(RESULTS_DIRECTORY, { recursive: true, mode: 0o700 });
  const configDirectory = path.join(RESULTS_DIRECTORY, ".promptfoo");
  fs.mkdirSync(configDirectory, { recursive: true, mode: 0o700 });

  const outputPath = buildResultPath();
  const entrypoint = path.join(
    RUNTIME_DIRECTORY,
    "node_modules",
    "promptfoo",
    "dist",
    "src",
    "entrypoint.js",
  );
  const env = buildRunnerEnvironment(process.env, configDirectory);
  const result = spawnImpl(
    process.execPath,
    [
      entrypoint,
      "eval",
      "--config",
      "promptfooconfig.agent.cjs",
      "--no-cache",
      "--no-share",
      "--no-write",
      "--max-concurrency",
      "1",
      "--no-progress-bar",
      "--output",
      outputPath,
    ],
    {
      cwd: RUNTIME_DIRECTORY,
      env,
      stdio: "inherit",
    },
  );
  if (result.error) {
    throw result.error;
  }
  if (result.status === 0) {
    console.log(`Saved private local evaluation report: ${outputPath}`);
  }
  return result.status ?? 1;
}

if (require.main === module) {
  try {
    process.exitCode = main();
  } catch (error) {
    console.error(error instanceof Error ? error.message : String(error));
    process.exitCode = 1;
  }
}

module.exports = {
  RESULTS_DIRECTORY,
  buildRunnerEnvironment,
  buildResultPath,
  main,
};
