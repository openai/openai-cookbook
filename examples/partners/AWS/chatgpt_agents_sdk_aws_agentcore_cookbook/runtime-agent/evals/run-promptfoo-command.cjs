const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const RUNTIME_DIRECTORY = path.resolve(__dirname, "..");
const RESULTS_DIRECTORY = path.join(__dirname, "results");
const DEFAULT_CONFIG_DIRECTORY = path.join(RESULTS_DIRECTORY, ".promptfoo");
const PROMPTFOO_ENTRYPOINT = path.join(
  RUNTIME_DIRECTORY,
  "node_modules",
  "promptfoo",
  "dist",
  "src",
  "entrypoint.js",
);
const COMMAND_ARGUMENTS = {
  "agent-validate": [
    "validate",
    "config",
    "--config",
    "promptfooconfig.agent.cjs",
  ],
  "offline-run": [
    "eval",
    "--config",
    "promptfooconfig.cjs",
    "--no-cache",
    "--no-share",
  ],
  "offline-validate": [
    "validate",
    "-c",
    "promptfooconfig.cjs",
  ],
};

function configDirectoryFromEnvironment(env) {
  const configured = env.PROMPTFOO_CONFIG_DIR?.trim();
  return configured
    ? path.resolve(RUNTIME_DIRECTORY, configured)
    : DEFAULT_CONFIG_DIRECTORY;
}

function secureTree(target) {
  const metadata = fs.lstatSync(target);
  if (metadata.isSymbolicLink()) {
    throw new Error(`Refusing to use a symbolic link for Promptfoo state: ${target}`);
  }
  if (metadata.isDirectory()) {
    fs.chmodSync(target, 0o700);
    for (const entry of fs.readdirSync(target)) {
      secureTree(path.join(target, entry));
    }
    return;
  }
  if (metadata.isFile()) {
    fs.chmodSync(target, 0o600);
    return;
  }
  throw new Error(`Unsupported Promptfoo state entry: ${target}`);
}

function isWithin(target, parent) {
  const resolvedTarget = path.resolve(target);
  const resolvedParent = path.resolve(parent);
  return (
    resolvedTarget === resolvedParent
    || resolvedTarget.startsWith(`${resolvedParent}${path.sep}`)
  );
}

function assertSafeStateDirectories(resultsDirectory, configDirectory) {
  const resolvedResults = path.resolve(resultsDirectory);
  const resolvedConfig = path.resolve(configDirectory);
  if (resolvedResults === path.parse(resolvedResults).root) {
    throw new Error("Refusing to use a filesystem root for Promptfoo results");
  }
  if (
    !isWithin(resolvedConfig, resolvedResults)
    && !path.basename(resolvedConfig).toLowerCase().includes("promptfoo")
  ) {
    throw new Error(
      "PROMPTFOO_CONFIG_DIR must be inside the cookbook results directory "
      + "or name a dedicated Promptfoo directory",
    );
  }
}

function securePromptfooState({
  resultsDirectory = RESULTS_DIRECTORY,
  configDirectory = DEFAULT_CONFIG_DIRECTORY,
} = {}) {
  assertSafeStateDirectories(resultsDirectory, configDirectory);
  fs.mkdirSync(resultsDirectory, { recursive: true, mode: 0o700 });
  fs.mkdirSync(configDirectory, { recursive: true, mode: 0o700 });
  secureTree(resultsDirectory);
  if (!isWithin(configDirectory, resultsDirectory)) {
    secureTree(configDirectory);
  }
}

function buildPromptfooEnvironment(env, configDirectory) {
  return {
    ...env,
    PROMPTFOO_CONFIG_DIR: configDirectory,
    PROMPTFOO_DISABLE_REMOTE_GENERATION: "true",
    PROMPTFOO_DISABLE_SHARING: "true",
    PROMPTFOO_DISABLE_TELEMETRY: "true",
    PROMPTFOO_DISABLE_UPDATE: "true",
    PROMPTFOO_DISABLE_WAL_MODE: "true",
  };
}

function main({
  commandName = process.argv[2],
  env = process.env,
  resultsDirectory = RESULTS_DIRECTORY,
  spawnImpl = spawnSync,
} = {}) {
  const commandArguments = COMMAND_ARGUMENTS[commandName];
  if (!commandArguments) {
    throw new Error(
      `Unknown Promptfoo command ${JSON.stringify(commandName)}; expected `
      + Object.keys(COMMAND_ARGUMENTS).join(", "),
    );
  }

  const configDirectory = configDirectoryFromEnvironment(env);
  const previousUmask = process.umask(0o077);
  let result;
  try {
    securePromptfooState({ resultsDirectory, configDirectory });
    result = spawnImpl(
      process.execPath,
      [PROMPTFOO_ENTRYPOINT, ...commandArguments],
      {
        cwd: RUNTIME_DIRECTORY,
        env: buildPromptfooEnvironment(env, configDirectory),
        stdio: "inherit",
      },
    );
  } finally {
    try {
      securePromptfooState({ resultsDirectory, configDirectory });
    } finally {
      process.umask(previousUmask);
    }
  }

  if (result.error) {
    throw result.error;
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
  COMMAND_ARGUMENTS,
  DEFAULT_CONFIG_DIRECTORY,
  RESULTS_DIRECTORY,
  buildPromptfooEnvironment,
  configDirectoryFromEnvironment,
  assertSafeStateDirectories,
  main,
  securePromptfooState,
  secureTree,
};
