import { QueueClient } from "@vercel/queue";
import { APIError, Sandbox } from "@vercel/sandbox";

const queue = new QueueClient({ region: "iad1" });

export default queue.handleNodeCallback<{ sessionId: string }>(
  async ({ sessionId }) => {
    const response = await fetch(
      `https://api.openai.com/v1/agents/sessions/${encodeURIComponent(sessionId)}`,
      {
        headers: {
          Authorization: `Bearer ${process.env.OPENAI_API_KEY}`,
          "OpenAI-Beta": "agents=v1",
        },
        signal: AbortSignal.timeout(30_000),
      },
    );
    if (response.status === 404) return;
    if (!response.ok)
      throw new Error(`Session lookup failed: ${response.status}`);
    const session = await response.json();
    if (
      session.environment.type !== "self_hosted" ||
      session.agent.id !== process.env.OPENAI_AGENT_ID
    )
      return;
    const name = `agents-${sessionId}`;
    if (session.status === "failed") {
      try {
        await (await Sandbox.get({ name })).delete();
      } catch (error) {
        if (!(error instanceof APIError && error.response.status === 404))
          throw error;
      }
      return;
    }
    const action = session.required_actions.find(
      (a: { type: string }) => a.type === "environment_connection",
    );
    if (!action) return;
    const sandbox = await Sandbox.getOrCreate({
      name,
      runtime: "node24",
      timeout: 30 * 60_000,
    });
    // Locks make retried/concurrent jobs harmless, including a retry after creation.
    const setup = await sandbox.runCommand({
      cmd: "flock",
      args: [
        "-w",
        "120",
        "/tmp/codex-setup.lock",
        "sh",
        "-c",
        "mkdir -p /workspace && chown vercel-sandbox /workspace && (command -v codex || npm install -g @openai/codex@alpha)",
      ],
      sudo: true,
    });
    if (setup.exitCode !== 0) throw new Error("Executor setup failed");
    await sandbox.runCommand({
      cmd: "flock",
      args: [
        "-n",
        "/tmp/codex-executor.lock",
        "codex",
        "exec-server",
        "--remote",
        "https://api.openai.com/v1/agents/api",
        "--environment-id",
        action.environment_id,
      ],
      cwd: "/workspace",
      detached: true,
      env: { CODEX_API_KEY: process.env.OPENAI_EXECUTOR_API_KEY! },
    });
    console.log(
      JSON.stringify({
        session_id: sessionId,
        sandbox_name: name,
        action: "started",
      }),
    );
  },
  { visibilityTimeoutSeconds: 240 },
);
