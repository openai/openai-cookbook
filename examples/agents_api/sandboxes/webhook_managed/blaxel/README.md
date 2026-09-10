# Blaxel webhook-managed sandbox

A controller sandbox exposes a signature-verified FastAPI endpoint. It saves work
to SQLite before returning `200`; one background worker starts session sandboxes.
The queue survives controller process restarts, but not deletion of the controller.

## Deploy

Create an agent using the [shared setup](../README.md#set-up-once). Run the
deployment command below from the Cookbook repository root.

Provide these environment variables through your secret manager:

- `BL_API_KEY`, `BL_WORKSPACE`: Blaxel account credentials.
- `BL_REGION`: optional region; defaults to `us-pdx-1` for controller and workers.
- `OPENAI_API_KEY`: controller/session-read credential.
- `OPENAI_AGENT_ID`: agent ID from the shared setup.
- `OPENAI_EXECUTOR_API_KEY`: restricted worker credential.
- `OPENAI_WEBHOOK_SECRET`: signing secret, once the webhook has been registered.

```bash
uv run examples/agents_api/sandboxes/webhook_managed/blaxel/deploy.py
```

The deployment creates a controller and prints its public webhook URL. Until the
signing secret is configured, the endpoint returns `503`. Register the URL with
OpenAI, set the real signing secret, and rerun deployment. Then use the
[shared client](../README.md#run-and-reconnect).

Rerun deployment after changing credentials; keep the same signing secret unless
you rotate it in OpenAI.

Only the controller receives the application and Blaxel credentials. Session
workers receive only the restricted executor key. Failed provisioning gets up to
five attempts. The controller expires after two hours. For a long-running service,
provide persistent hosting and queue storage for the controller.

## Stop or clean up

The handler logs each session's sandbox name. Delete that worker in the Blaxel
dashboard to release compute after a turn. A replacement starts with a fresh filesystem.
For final cleanup, delete the API session too.

When finished, remove the OpenAI webhook, then delete the
`agents-api-webhook-controller` sandbox and any remaining
workers created by this example. Do not delete other workspace sandboxes. Workers
are also labeled with their Agents API session ID and have a 30-minute TTL.
