import assert from "node:assert/strict";
import { randomUUID } from "node:crypto";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { setTimeout as sleep } from "node:timers/promises";
import { redact, type EventUpdate } from "../src/events.js";
import { readCredentials, SandboxSession } from "../src/session.js";

test("Agents API executes in OpenShell, where denied egress is logged and artifacts can be downloaded", {
  skip: process.env.RUN_OPENAI_OPENSHELL_INTEGRATION !== "1",
  timeout: 360_000,
}, async (t) => {
  const credentials = readCredentials();
  const commands: Extract<EventUpdate, { kind: "command" }>[] = [];
  const session = new SandboxSession({
    ...credentials,
    onNotice: (message) => t.diagnostic(redact(message, session.sensitiveValues)),
    onEvent: (event) => {
      if (event.kind === "command") commands.push(event);
    },
  });
  const root = await mkdtemp(join(tmpdir(), "agents-openshell-"));
  t.after(async () => {
    try {
      const stopped = await session.stop();
      const reason = await session.closing;
      if (reason) t.diagnostic(redact(reason, session.sensitiveValues));
      assert.equal(stopped, true, "Session and sandbox cleanup must be confirmed");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  const nonce = `openshell-${randomUUID()}`;
  const remoteFile = "/workspace/outputs/integration.txt";
  await session.start();
  assert.equal(await session.runTurn(
    `Run exactly two shell commands. First, use printf to write ${nonce} followed by one newline into ${remoteFile}. ` +
    "Second, run /usr/bin/curl -sS --max-time 8 https://example.com/ and report its exit code. " +
    "Leave the curl exit code intact so it appears in tool activity. A denial is expected. Do not try another host.",
  ), "completed");
  assert.ok(commands.some((event) => event.phase === "finished" && event.exitCode === 0 &&
    event.command.includes(remoteFile)), "Expected a successful workspace write command");
  assert.ok(commands.some((event) => event.phase === "finished" && event.exitCode !== null &&
    event.exitCode !== 0 && event.command.includes("https://example.com/")),
    "Expected a nonzero exit for the unrelated HTTPS request");

  const downloaded = await session.sandbox.download(remoteFile, root);
  assert.equal(await readFile(downloaded.path, "utf8"), nonce + "\n");
  let denial: string | undefined;
  for (let attempt = 0; attempt < 5 && !denial; attempt++) {
    if (attempt > 0) await sleep(500);
    const logs = await session.sandbox.logs(200);
    denial = logs.split("\n").find((line) => line.includes("example.com") && /DENIED|denied/i.test(line));
  }
  assert.ok(denial, "OpenShell must log that it denied the unrelated request");
  t.diagnostic(redact(denial, session.sensitiveValues));
});
