const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  COMMAND_ARGUMENTS,
  buildPromptfooEnvironment,
  configDirectoryFromEnvironment,
  main,
  securePromptfooState,
} = require("./run-promptfoo-command.cjs");

function mode(target) {
  return fs.statSync(target).mode & 0o777;
}

test("defaults Promptfoo state to the ignored private results directory", () => {
  assert.equal(
    configDirectoryFromEnvironment({}),
    path.resolve(__dirname, "results", ".promptfoo"),
  );
});

test("sets private modes on existing Promptfoo directories and files", (context) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "promptfoo-state-"));
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const resultsDirectory = path.join(root, "results");
  const configDirectory = path.join(resultsDirectory, ".promptfoo");
  const logsDirectory = path.join(configDirectory, "logs");
  const databasePath = path.join(configDirectory, "promptfoo.db");
  const logPath = path.join(logsDirectory, "promptfoo-debug.log");

  fs.mkdirSync(logsDirectory, { recursive: true, mode: 0o777 });
  fs.writeFileSync(databasePath, "database", { mode: 0o666 });
  fs.writeFileSync(logPath, "log", { mode: 0o666 });
  fs.chmodSync(resultsDirectory, 0o755);
  fs.chmodSync(configDirectory, 0o755);
  fs.chmodSync(logsDirectory, 0o755);
  fs.chmodSync(databasePath, 0o644);
  fs.chmodSync(logPath, 0o644);

  securePromptfooState({ resultsDirectory, configDirectory });

  assert.equal(mode(resultsDirectory), 0o700);
  assert.equal(mode(configDirectory), 0o700);
  assert.equal(mode(logsDirectory), 0o700);
  assert.equal(mode(databasePath), 0o600);
  assert.equal(mode(logPath), 0o600);
});

test("runs validation with private state flags and hardens files created by Promptfoo", (context) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "promptfoo-command-"));
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const resultsDirectory = path.join(root, "results");
  const configDirectory = path.join(root, "external-promptfoo");
  let invocation;

  const status = main({
    commandName: "agent-validate",
    env: {
      PATH: process.env.PATH,
      PROMPTFOO_CONFIG_DIR: configDirectory,
    },
    resultsDirectory,
    spawnImpl(command, args, options) {
      invocation = { command, args, options };
      const logsDirectory = path.join(configDirectory, "logs");
      fs.mkdirSync(logsDirectory, { recursive: true, mode: 0o777 });
      fs.writeFileSync(path.join(configDirectory, "promptfoo.db"), "database", {
        mode: 0o666,
      });
      fs.writeFileSync(path.join(logsDirectory, "promptfoo.log"), "log", {
        mode: 0o666,
      });
      return { status: 0 };
    },
  });

  assert.equal(status, 0);
  assert.equal(invocation.command, process.execPath);
  assert.deepEqual(invocation.args.slice(1), COMMAND_ARGUMENTS["agent-validate"]);
  assert.equal(invocation.options.cwd, path.resolve(__dirname, ".."));
  assert.equal(invocation.options.env.PROMPTFOO_CONFIG_DIR, configDirectory);
  assert.equal(invocation.options.env.PROMPTFOO_DISABLE_SHARING, "true");
  assert.equal(invocation.options.env.PROMPTFOO_DISABLE_TELEMETRY, "true");
  assert.equal(mode(resultsDirectory), 0o700);
  assert.equal(mode(configDirectory), 0o700);
  assert.equal(mode(path.join(configDirectory, "logs")), 0o700);
  assert.equal(mode(path.join(configDirectory, "promptfoo.db")), 0o600);
  assert.equal(mode(path.join(configDirectory, "logs", "promptfoo.log")), 0o600);
});

test("builds the same privacy controls for every credential-free command", () => {
  const env = buildPromptfooEnvironment(
    { PATH: "/usr/bin" },
    "/tmp/private-promptfoo",
  );

  assert.equal(env.PROMPTFOO_CONFIG_DIR, "/tmp/private-promptfoo");
  assert.equal(env.PROMPTFOO_DISABLE_REMOTE_GENERATION, "true");
  assert.equal(env.PROMPTFOO_DISABLE_SHARING, "true");
  assert.equal(env.PROMPTFOO_DISABLE_TELEMETRY, "true");
  assert.equal(env.PROMPTFOO_DISABLE_UPDATE, "true");
  assert.equal(env.PROMPTFOO_DISABLE_WAL_MODE, "true");
});

test("package scripts never invoke Promptfoo outside a guarded runner", () => {
  const packageJson = JSON.parse(
    fs.readFileSync(path.resolve(__dirname, "..", "package.json"), "utf8"),
  );

  for (const [name, command] of Object.entries(packageJson.scripts)) {
    if (name.startsWith("eval:")) {
      assert.doesNotMatch(command, /(?:^|\s)promptfoo(?:\s|$)/);
    }
  }
});

test("rejects unknown commands before spawning Promptfoo", () => {
  assert.throws(
    () => main({ commandName: "unknown" }),
    /Unknown Promptfoo command/,
  );
});

test("refuses to recursively harden a broad custom config directory", (context) => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "promptfoo-broad-path-"));
  context.after(() => fs.rmSync(root, { recursive: true, force: true }));

  assert.throws(
    () => securePromptfooState({
      resultsDirectory: path.join(root, "results"),
      configDirectory: path.join(root, "shared-state"),
    }),
    /dedicated Promptfoo directory/,
  );
});
