# Cloudflare webhook-managed sandbox

The Worker verifies the signature and persists a wakeup in a per-session Durable
Object. Its alarm starts the Sandbox executor. Durable storage handles retries;
the session ID identifies the sandbox, and an OS lock prevents duplicate executors.

## Deploy

Complete the [provider setup](../README.md#prerequisites).
Create the agent using the [shared setup](../../webhook_managed.md#set-up-once)
with this mode's `client.py`. Starting at the Cookbook repository root:

```bash
cd examples/agents_api/sandboxes/cloudflare
uv run webhook_managed/client.py --create-agent cloudflare-webhook-example
```

Set a unique Worker name and `OPENAI_AGENT_ID` in `webhook_managed/wrangler.jsonc`.
Stay in the Cloudflare provider directory for the remaining commands. Deploy
and add secrets using the CLI's prompts:

```bash
npm run deploy:webhook
npx wrangler secret put OPENAI_API_KEY --config webhook_managed/wrangler.jsonc
npx wrangler secret put OPENAI_EXECUTOR_API_KEY --config webhook_managed/wrangler.jsonc
npx wrangler secret put OPENAI_WEBHOOK_SECRET --config webhook_managed/wrangler.jsonc
npx wrangler secret put SANDBOX_CONTROL_TOKEN --config webhook_managed/wrangler.jsonc
```

Use a separate random control token for the cleanup endpoint. For the first
deployment only, the signing value may be `pending-webhook-registration`; the
receiver rejects it. The SDK and Dockerfile use matching Sandbox versions.

Register `https://YOUR_WORKER.workers.dev/webhook` with OpenAI. Set the real signing
secret using `npx wrangler secret put OPENAI_WEBHOOK_SECRET --config webhook_managed/wrangler.jsonc`.
Run the [client and reconnect flow](../../webhook_managed.md#run-and-reconnect)
with the provider-local client:

```bash
uv run webhook_managed/client.py --agent-id "$OPENAI_AGENT_ID"
uv run webhook_managed/client.py --session-id "$SESSION_ID" --input "Run another shell command."
```

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
Remove the OpenAI webhook before deleting the Worker and its containers:

```bash
npx wrangler delete --config webhook_managed/wrangler.jsonc
```

See the [application-managed mode](../application_managed/README.md) for direct provisioning.
