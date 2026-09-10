import { DurableObject } from "cloudflare:workers";
import { getSandbox, type Sandbox as SandboxType } from "@cloudflare/sandbox";
import OpenAI from "openai";

export { Sandbox } from "@cloudflare/sandbox";

interface Env {
  Sandbox: DurableObjectNamespace<SandboxType>;
  Sessions: DurableObjectNamespace<SessionController>;
  OPENAI_API_KEY: string;
  OPENAI_EXECUTOR_API_KEY: string;
  OPENAI_WEBHOOK_SECRET: string;
  OPENAI_AGENT_ID: string;
  SANDBOX_CONTROL_TOKEN: string;
}

type Job = {
  sessionId: string;
  version: number;
  attempts: number;
  pending: boolean;
};

// Durable Object storage and alarms provide the small provisioning queue.
export class SessionController extends DurableObject<Env> {
  async wake(sessionId: string) {
    const previous = await this.ctx.storage.get<Job>("job");
    await this.ctx.storage.put("job", {
      ...previous,
      sessionId,
      version: (previous?.version ?? 0) + 1,
      attempts: 0,
      pending: true,
    });
    await this.ctx.storage.setAlarm(Date.now());
  }

  async stop(sessionId: string) {
    await getSandbox(this.env.Sandbox, sessionId).destroy();
    await this.ctx.storage.deleteAlarm();
    await this.ctx.storage.deleteAll();
  }

  async alarm() {
    const job = await this.ctx.storage.get<Job>("job");
    if (!job) return;
    const expiresAt = await this.ctx.storage.get<number>("expiresAt");
    if (expiresAt && Date.now() >= expiresAt) return this.stop(job.sessionId);
    if (!job.pending) return;
    try {
      await this.reconcile(job.sessionId);
      const current = await this.ctx.storage.get<Job>("job");
      if (current?.version !== job.version) return; // A newer wakeup already scheduled an alarm.
      job.pending = false;
      await this.ctx.storage.put("job", job);
      const deadline = await this.ctx.storage.get<number>("expiresAt");
      if (deadline) await this.ctx.storage.setAlarm(deadline);
    } catch (error) {
      console.error(
        JSON.stringify({
          session_id: job.sessionId,
          error_type: (error as Error).name,
        }),
      );
      const current = await this.ctx.storage.get<Job>("job");
      if (current?.version !== job.version) return;
      if (++job.attempts >= 5) job.pending = false;
      await this.ctx.storage.put("job", job);
      if (job.pending) await this.ctx.storage.setAlarm(Date.now() + 10_000);
      else {
        const deadline = await this.ctx.storage.get<number>("expiresAt");
        if (deadline) await this.ctx.storage.setAlarm(deadline);
      }
    }
  }

  private async reconcile(sessionId: string): Promise<boolean> {
    const response = await fetch(
      `https://api.openai.com/v1/agents/sessions/${encodeURIComponent(sessionId)}`,
      {
        headers: {
          Authorization: `Bearer ${this.env.OPENAI_API_KEY}`,
          "OpenAI-Beta": "agents=v1",
        },
        signal: AbortSignal.timeout(30_000),
      },
    );
    if (response.status === 404) return false;
    if (!response.ok)
      throw new Error(`Session lookup failed: ${response.status}`);
    const session = (await response.json()) as {
      status: string;
      agent: { id: string };
      environment: { type: string };
      required_actions: { type: string; environment_id?: string }[];
    };
    if (
      session.environment.type !== "self_hosted" ||
      session.agent.id !== this.env.OPENAI_AGENT_ID
    )
      return false;
    const sandbox = getSandbox(this.env.Sandbox, sessionId, {
      enableDefaultSession: false,
      keepAlive: true,
    });
    if (session.status === "failed") {
      await sandbox.destroy();
      await this.ctx.storage.delete("expiresAt");
      return false;
    }
    const action = session.required_actions.find(
      (a) => a.type === "environment_connection",
    );
    if (!action?.environment_id) return false;
    // Record the cleanup deadline before provisioning, including partial failures.
    if (!(await this.ctx.storage.get("expiresAt")))
      await this.ctx.storage.put("expiresAt", Date.now() + 30 * 60_000);
    // A deterministic sandbox ID and an OS lock prevent duplicate executors.
    const command = [
      "flock",
      "-n",
      "/tmp/codex-executor.lock",
      "codex",
      "exec-server",
      "--remote",
      "https://api.openai.com/v1/agents/api",
      "--environment-id",
      action.environment_id,
    ]
      .map((arg) => `'${arg.replaceAll("'", "'\\''")}'`)
      .join(" ");
    await sandbox.startProcess(command, {
      cwd: "/workspace",
      env: { CODEX_API_KEY: this.env.OPENAI_EXECUTOR_API_KEY },
    });
    console.log(JSON.stringify({ session_id: sessionId, action: "started" }));
    return true;
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const path = new URL(request.url).pathname;
    if (request.method === "GET" && path === "/health")
      return Response.json({ ok: true });
    if (request.method === "DELETE" && path.startsWith("/sandboxes/")) {
      if (
        !env.SANDBOX_CONTROL_TOKEN ||
        request.headers.get("authorization") !==
          `Bearer ${env.SANDBOX_CONTROL_TOKEN}`
      )
        return new Response("Unauthorized", { status: 401 });
      const sessionId = decodeURIComponent(path.slice("/sandboxes/".length));
      await env.Sessions.getByName(sessionId).stop(sessionId);
      return Response.json({ stopped: sessionId });
    }
    if (request.method !== "POST" || path !== "/webhook")
      return new Response("Not found", { status: 404 });
    if (
      !env.OPENAI_WEBHOOK_SECRET ||
      env.OPENAI_WEBHOOK_SECRET === "pending-webhook-registration"
    )
      return new Response("Webhook not configured", { status: 503 });
    const payload = await request.text();
    const verifier = new OpenAI({
      apiKey: "unused",
      webhookSecret: env.OPENAI_WEBHOOK_SECRET,
    });
    try {
      await verifier.webhooks.verifySignature(payload, request.headers);
    } catch {
      return new Response("Invalid signature", { status: 400 });
    }
    const event = JSON.parse(payload);
    if (
      event.type === "agent.session.failed" ||
      (event.type === "agent.session.action_required" &&
        event.data.required_action.type === "environment_connection")
    )
      await env.Sessions.getByName(event.data.id).wake(event.data.id);
    return Response.json({ ok: true });
  },
};
