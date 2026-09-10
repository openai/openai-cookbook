# Application-managed Cloudflare sandbox

The Python application creates an Agents API session and calls your Cloudflare
Worker to start a sandbox. The Worker runs `codex exec-server` and returns the
agent's generated `plan.md`. The application then destroys the sandbox and
deletes the session. Provisioning is driven by the application, not webhooks.

Cloudflare's sandbox SDK runs inside a Worker. The small Worker in this example
provides authenticated start, file-read, and destroy routes for the Python client.

## Deploy the Worker

You need Cloudflare Workers Paid with Containers enabled, Node.js, and Docker
running for the image build.

```bash
cd examples/agents_api/sandboxes/application_managed/cloudflare
npm ci
npx wrangler login
npm run deploy
npx wrangler secret put OPENAI_EXECUTOR_API_KEY
npx wrangler secret put SANDBOX_CONTROL_TOKEN
```

Use a restricted executor key and a separate random control token. Keep the
application's `OPENAI_API_KEY` outside the Worker and sandbox. The OpenAI keys
must have the same owner, organization, and project.

## Run the application

Set `OPENAI_API_KEY`, `SANDBOX_CONTROL_TOKEN` (the same value stored in the
Worker), and `CLOUDFLARE_SANDBOX_WORKER_URL` to the deployed Worker URL.
From the Cookbook repository root:

```bash
uv run examples/agents_api/sandboxes/application_managed/cloudflare/main.py
```

Python dependencies are declared inline. The script allows six minutes for
setup and execution and attempts both cleanup operations on failure. The Worker
also sets a ten-minute idle timeout. If the application is interrupted, send an
authenticated `DELETE /sandboxes/<printed session ID>` to the Worker and delete
the Agents API session.

For follow-up turns, keep both resources until the application is finished.
Do not attach a provisioning webhook handler to these sessions. When finished
with this deployment, run `npx wrangler delete` from the Worker directory.

## References

- [Cloudflare Sandbox documentation](https://developers.cloudflare.com/sandbox/)
- [Background processes](https://developers.cloudflare.com/sandbox/guides/background-processes/)
- [Webhook-managed example](../../webhook_managed/cloudflare/README.md)
