# Cloudflare sandboxes

Choose who starts and reconnects the executor:

- [Application-managed](application_managed/README.md): a Python application calls
  authenticated Worker routes to start a sandbox, read its output, and destroy it.
- [Webhook-managed](webhook_managed/README.md): a signed OpenAI webhook wakes a
  Durable Object controller that provisions and reconnects the sandbox.

Both modes share the `Dockerfile`, npm dependencies, TypeScript configuration,
and `executor.ts`. Each mode keeps its own Worker entrypoint and Wrangler
configuration because authentication and lifecycle management differ.

## Prerequisites

Use a Cloudflare account with Workers Paid and Containers enabled, Node.js, and
Docker running for image builds. Use separate Worker names for the two modes and
for tests; do not deploy over an existing application.

Install and check both Workers from this directory:

```bash
npm ci
npm run check
npx wrangler login
```

The pinned Sandbox SDK version matches the Docker image. When upgrading it,
update both together. Set a separate restricted `OPENAI_EXECUTOR_API_KEY` for
the sandbox. Keep the application/session-read key out of the container.

Follow a mode's README for its configuration, deployment, and cleanup commands.
