# Cloudflare webhook-managed sandbox

The Worker verifies the signature and persists a wakeup in a per-session Durable
Object. Its alarm starts the Sandbox executor. Durable storage handles retries;
the session ID identifies the sandbox, and an OS lock prevents duplicate executors.

## Deploy

Use a Cloudflare account with Workers and Containers access, Node.js, and Docker.
Create the agent using the [shared setup](../README.md#set-up-once). In this directory:

```bash
npm ci
npx wrangler login
```

Set `OPENAI_AGENT_ID` in `wrangler.jsonc` to the agent ID from the shared setup.
Add secrets using the CLI's prompts:

```bash
npx wrangler secret put OPENAI_API_KEY
npx wrangler secret put OPENAI_EXECUTOR_API_KEY
npx wrangler secret put OPENAI_WEBHOOK_SECRET
npx wrangler secret put SANDBOX_CONTROL_TOKEN
npm run deploy
```

Use a separate random control token for the cleanup endpoint. For the first
deployment only, the signing value may be `pending-webhook-registration`; the
receiver rejects it. The SDK and Dockerfile use matching Sandbox versions.

Register `https://YOUR_WORKER.workers.dev/webhook` with OpenAI. Set the real signing
secret using `wrangler secret put OPENAI_WEBHOOK_SECRET`, then deploy again.
Run the [shared client](../README.md#run-and-reconnect).

Keep `OPENAI_AGENT_ID` set when redeploying; sessions for other agents are ignored.

## Stop or clean up

Call the authenticated cleanup endpoint after a turn finishes:

```python
import os
import httpx

response = httpx.delete(
    f"{os.environ['WORKER_URL']}/sandboxes/{os.environ['SESSION_ID']}",
    headers={"Authorization": f"Bearer {os.environ['SANDBOX_CONTROL_TOKEN']}"},
    timeout=60,
)
response.raise_for_status()
```

A following input triggers a new connection. Final cleanup also requires deleting
the API session. The controller schedules a maximum-lifetime cleanup alarm because
the executor keeps the container alive. Replacement containers have a fresh filesystem.
Remove the OpenAI webhook before deleting the Worker and its containers.
