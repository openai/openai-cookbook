# Modal webhook-managed sandbox

The endpoint verifies OpenAI signatures and queues work for a Modal function.
One provisioning worker processes requests in order and reuses named sandboxes.

## Deploy

From the Cookbook repository root:

```bash
uvx modal setup
```

Create the agent using the [shared setup](../README.md#set-up-once), then create
these secrets in Modal's dashboard:

| Secret name | Variables |
| --- | --- |
| `agents-api-webhook-modal-controller` | `OPENAI_API_KEY`, `OPENAI_AGENT_ID` — agent ID from the shared setup |
| `agents-api-webhook-modal-executor` | `CODEX_API_KEY` — the restricted executor key |
| `agents-api-webhook-modal-signing` | `OPENAI_WEBHOOK_SECRET` |

Use `pending-webhook-registration` for the signing value only while obtaining the
endpoint URL. The handler explicitly rejects this placeholder. Never put real
credentials in source files.

```bash
uv run examples/agents_api/sandboxes/webhook_managed/modal/handler.py
```

Register the printed URL with OpenAI, store the generated signing secret, and run
the deployment command again. Then use the [shared client](../README.md#run-and-reconnect).

When rotating keys, edit the existing secrets and redeploy. With the CLI, use
`uvx modal secret create --force` to replace values; the Python API's
`allow_existing=True` does not update an existing secret.

## Stop or clean up

The sandbox name is the API session ID. Terminate it in the Modal dashboard, or
run this with Modal credentials available:

```python
import asyncio
import os
import modal


async def stop():
    try:
        sandbox = await modal.Sandbox.from_name.aio(
            "agents-api-webhook-modal", os.environ["SESSION_ID"]
        )
    except modal.exception.NotFoundError:
        return
    await sandbox.terminate.aio()


asyncio.run(stop())
```

For final cleanup, also delete the API session. Remove the OpenAI webhook before
stopping the deployed Modal app. Replacement sandboxes start with a fresh filesystem;
the example does not attach a persistent volume.
