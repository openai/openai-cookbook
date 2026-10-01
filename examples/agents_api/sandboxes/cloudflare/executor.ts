import type { Sandbox } from "@cloudflare/sandbox";

export async function startExecutor(
  sandbox: Sandbox,
  environment: { id: string; remote_url: string },
  executorKey: string,
) {
  const command = [
    "flock",
    "-n",
    "/tmp/codex-executor.lock",
    "codex",
    "exec-server",
    "--remote",
    environment.remote_url,
    "--environment-id",
    environment.id,
  ]
    .map((arg) => `'${arg.replaceAll("'", "'\\''")}'`)
    .join(" ");
  return sandbox.startProcess(command, {
    cwd: "/workspace",
    env: { CODEX_API_KEY: executorKey },
  });
}
