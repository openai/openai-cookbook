import { getSandbox, type Sandbox as SandboxType } from "@cloudflare/sandbox";

export { Sandbox } from "@cloudflare/sandbox";

interface Env {
  Sandbox: DurableObjectNamespace<SandboxType>;
  OPENAI_EXECUTOR_API_KEY: string;
  SANDBOX_CONTROL_TOKEN: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (
      !env.SANDBOX_CONTROL_TOKEN ||
      request.headers.get("authorization") !== `Bearer ${env.SANDBOX_CONTROL_TOKEN}`
    ) {
      return new Response("Unauthorized", { status: 401 });
    }
    const match = new URL(request.url).pathname.match(
      /^\/sandboxes\/(sess_[A-Za-z0-9_-]+)(\/plan)?$/,
    );
    if (!match) return new Response("Not found", { status: 404 });

    const sandbox = getSandbox(env.Sandbox, match[1], {
      sleepAfter: "10m",
    });
    if (request.method === "DELETE" && !match[2]) {
      await sandbox.destroy();
      return Response.json({ deleted: true });
    }
    if (request.method === "GET" && match[2]) {
      const file = await sandbox.readFile("/workspace/plan.md");
      return new Response(file.content, {
        headers: { "content-type": "text/plain; charset=utf-8" },
      });
    }
    if (request.method !== "POST" || match[2]) {
      return new Response("Method not allowed", { status: 405 });
    }
    const { environment_id, remote_url } = (await request.json()) as {
      environment_id?: string;
      remote_url?: string;
    };
    if (!environment_id || !/^ccarenv_[A-Za-z0-9_-]+$/.test(environment_id)) {
      return new Response("Invalid environment_id", { status: 400 });
    }
    if (!remote_url || !/^https:\/\/api\.openai\.com\/[A-Za-z0-9/_-]+$/.test(remote_url)) {
      return new Response("Invalid remote_url", { status: 400 });
    }
    await sandbox.writeFile(
      "/workspace/brief.txt",
      "Migrate a synchronous Python service to async without changing its API.\n",
    );
    await sandbox.startProcess(
      `flock -n /tmp/executor.lock codex exec-server --remote ${remote_url} --environment-id ${environment_id}`,
      { cwd: "/workspace", env: { CODEX_API_KEY: env.OPENAI_EXECUTOR_API_KEY } },
    );
    return Response.json({ started: match[1] });
  },
};
