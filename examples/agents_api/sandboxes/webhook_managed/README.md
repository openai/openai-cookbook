# Webhook-managed sandboxes

Run the agent through the Agents API and let a webhook handler in your sandbox
provider account start and reconnect its sandbox.

## How it works

- **Application:** [client.py](client.py) creates sessions, sends input, and streams
  results. The same client works with every provider below; it imports no provider SDK.
- **Provider handler:** deployed once, it receives OpenAI webhooks and starts or
  reconnects the sandbox executor when an environment connection is required.

## Choose a handler

| Provider | Handler code | Setup |
| --- | --- | --- |
| Modal | [handler.py](modal/handler.py) | [Deploy](modal/README.md) |
| Vercel | [api/webhook.ts](vercel/api/webhook.ts) and [api/provision.ts](vercel/api/provision.ts) | [Deploy](vercel/README.md) |
| Cloudflare | [src/index.ts](cloudflare/src/index.ts) | [Deploy](cloudflare/README.md) |
| Blaxel | [handler.py](blaxel/handler.py) | [Deploy](blaxel/README.md) |
| Daytona | [handler.py](daytona/handler.py) | [Deploy](daytona/README.md) |
| E2B | [handler.py](e2b/handler.py) | [Deploy](e2b/README.md) |
| DigitalOcean | [handler.py](digitalocean/handler.py) | [Deploy](digitalocean/README.md) |

Complete the setup below, deploy one provider's handler, then run the shared
client. For direct provisioning from your application, use
[application-managed sandboxes](../application_managed/README.md).

## Set up once

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and run the
   commands below from the Cookbook repository root. Each Python script declares its
   dependencies inline; `uv run` installs them automatically.
2. Set your application's `OPENAI_API_KEY`, then create an agent:

   ```bash
   uv run examples/agents_api/sandboxes/webhook_managed/client.py --create-agent sandbox-demo
   ```

   Example output:

   ```json
   {"agent_id": "agent_..."}
   ```

   Set `OPENAI_AGENT_ID` to the returned `agent_id`, replacing the placeholder below.
   If you already have an agent, use its ID instead.

   ```bash
   export OPENAI_AGENT_ID="agent_..."
   ```

   Use the same ID in your application and handler. `OPENAI_AGENT_ID` is a filter
   specific to these examples: the handler ignores sessions for other agents.
   The default model is `gpt-5.6-sol`; use `--model` when creating an agent with a
   different supported model.
3. Follow one provider's README to configure credentials, deploy its handler, and
   register the webhook. Enable `agent.session.action_required` and
   `agent.session.failed`, then install the signing secret before running a session.

### Credentials

| Variable | Where it is used |
| --- | --- |
| `OPENAI_API_KEY` | Application and controller. The application creates sessions; the controller reads their current state. |
| `OPENAI_EXECUTOR_API_KEY` | Passed to each worker as `CODEX_API_KEY`. Grant **List models → Read** and set other permissions to **None**. |
| `OPENAI_WEBHOOK_SECRET` | Controller only. Verifies deliveries from your OpenAI project. |

The two API keys must have the same organization, project, and user or service-account
owner. Your network policies must allow API requests from the sandbox provider.
Keep the application key and signing secret out of worker sandboxes. Configure
provider credentials as described in its README.

When changing either API key, update the provider's stored credentials and redeploy
the handler. Keep the existing webhook signing secret. A key from the same project
but a different user or service account cannot register the session's executor.

## Run and reconnect

```bash
uv run examples/agents_api/sandboxes/webhook_managed/client.py \
  --agent-id "$OPENAI_AGENT_ID" \
  --input "Use the shell to write hello to /workspace/hello.txt, then read it."
```

The client prints the session ID; save it as `SESSION_ID` for follow-up input.
To reconnect after stopping or pausing the sandbox, keep the API session and run:

```bash
uv run examples/agents_api/sandboxes/webhook_managed/client.py \
  --session-id "$SESSION_ID" \
  --input "Run a shell command to print hello again."
```

If the executor is offline, the new input triggers a connection-required webhook.
The handler resumes or replaces the sandbox, depending on the provider. The input
request waits for the executor; do not submit it again while it is waiting.
OpenAI waits up to five minutes; this client uses a ten-minute HTTP timeout.

## Use multiple providers

Each handler manages sessions for one `OPENAI_AGENT_ID`. If you deploy more than
one provider in the same OpenAI project, assign a different agent to each. Do not
let multiple handlers provision the same session.

## Lifecycle and cleanup

- `action_required` with `environment_connection`: retrieve current state, then
  start or reconnect only if that action still exists.
- `failed`: clean up the sandbox only if the current session is still failed.
- Other events: ignored. These examples do not shut down on `idle`.

Workers have a 30-minute lifetime or timeout by default. This can interrupt an
active turn; set limits above your expected task duration. E2B refreshes its
running timeout on reconnect; Daytona's TTL counts from creation. See each
provider's README for persistence behavior. Replacing a sandbox does not restore
its files or replay interrupted commands.

The Blaxel, Daytona, and E2B controllers also have time limits. Keep the controller
available while sessions need it. For a long-running deployment, provide persistent
controller hosting and queue storage, monitor provisioning failures, and reconcile
jobs that exhaust their retries.

When finished, stop/delete provider compute **and** delete the API session:

```bash
uv run examples/agents_api/sandboxes/webhook_managed/client.py --session-id "$SESSION_ID" --delete
```

Stop new input before cleanup. There is no session-deletion webhook, so removing
the API session does not release provider resources. When retiring a controller,
remove its OpenAI webhook first. Handle input timeouts in your application; the
wakeup webhook does not guarantee recovery of a pending input after an API restart.

See [Manage Sandbox Lifecycle](https://developers.openai.com/api/docs/guides/agents-api/environments/lifecycle)
for the shared protocol and recovery limits.
