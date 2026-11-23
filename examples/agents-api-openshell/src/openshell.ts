import { execFile } from "node:child_process";
import { mkdir, mkdtemp, rm } from "node:fs/promises";
import { join, posix, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const exampleDirectory = fileURLToPath(new URL("../../", import.meta.url));
export const WORKSPACE = "/workspace";
export const IMAGE = "cookbook/agents-api-openshell:local";

export function workspacePath(input: string): string {
  if (!input || /[\x00-\x1f\x7f\\]/u.test(input) || input.split("/").includes("..")) {
    throw new Error("Provide a path inside /workspace without traversal segments.");
  }
  const path = posix.resolve(WORKSPACE, input);
  if (!path.startsWith(WORKSPACE + "/")) {
    throw new Error("Provide a file or directory inside /workspace.");
  }
  return path;
}

async function openshell(args: string[], timeout: number, injection = {}) {
  // Keep gateway selection and local authentication configuration, strip API credentials.
  const env = { ...process.env };
  delete env.OPENAI_API_KEY;
  delete env.OPENAI_EXECUTOR_API_KEY;
  delete env.CODEX_API_KEY;
  // Rust debug output can include request details.
  delete env.RUST_LOG;
  delete env.RUST_BACKTRACE;
  return execFileAsync("openshell", ["--color", "never", ...args], {
    env: { ...env, ...injection },
    timeout,
    maxBuffer: 1024 * 1024,
  });
}

type SandboxPhase = "Pending" | "Provisioning" | "Ready" | "Stopped" | "Error" | "Completed" | "Unknown";

export class OpenShellSandbox {
  constructor(readonly name: string) {}

  async create(environmentId: string, remoteUrl: string, executorKey: string) {
    await openshell([
      "sandbox", "create", "--name", this.name, "--from", IMAGE,
      "--policy", join(exampleDirectory, "policy.yaml"), "--detach",
      "--no-auto-providers", "--timeout", "45",
      "--env-from", "CODEX_API_KEY", "--env-from", "AGENTS_ENVIRONMENT_ID",
      "--env-from", "AGENTS_REMOTE_URL", "--", "/opt/codex/bin/start-executor",
    ], 55_000, {
      CODEX_API_KEY: executorKey,
      AGENTS_ENVIRONMENT_ID: environmentId,
      AGENTS_REMOTE_URL: remoteUrl,
    });
  }

  async phase(): Promise<SandboxPhase> {
    const { stdout } = await openshell(["sandbox", "get", this.name, "-o", "json"], 7_000);
    const { phase } = JSON.parse(stdout);
    switch (phase) {
      case "Pending":
      case "Provisioning":
      case "Ready":
      case "Stopped":
      case "Error":
      case "Completed":
        return phase;
      default:
        return "Unknown";
    }
  }

  async logs(lines = 60) {
    const { stdout, stderr } = await openshell([
      "logs", this.name, "--source", "sandbox", "-n", String(lines),
    ], 12_000);
    return stdout + stderr;
  }

  async download(path: string, root = resolve("downloads")) {
    const remotePath = workspacePath(path);
    await mkdir(root, { recursive: true, mode: 0o700 });
    const destination = await mkdtemp(join(root, this.name + "-"));
    try {
      await openshell(["sandbox", "download", this.name, remotePath, destination], 30_000);
      return { directory: destination, path: join(destination, posix.basename(remotePath)) };
    } catch {
      await rm(destination, { recursive: true, force: true });
      throw new Error("Download failed. Check that the artifact exists and the sandbox is running.");
    }
  }

  async delete() {
    await openshell(["sandbox", "delete", this.name], 10_000);
  }
}
