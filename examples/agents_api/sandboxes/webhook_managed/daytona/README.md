# Daytona webhook-managed sandbox

A controller in a dedicated Daytona sandbox receives OpenAI webhooks and queues
work in SQLite. It starts or reconnects a separate worker sandbox for each API
session. Agent commands run only in the worker sandbox.

Workers use Daytona's default JavaScript snapshot. Setup creates `/workspace` for
the `daytona` user and installs the Codex alpha under that user's `.local` directory.

## Deploy

Create an agent using the [shared setup](../README.md#set-up-once). Run the
deployment command below from the Cookbook repository root.

Set `OPENAI_AGENT_ID` to the agent ID from the shared setup. Provide it alongside
`DAYTONA_API_KEY`, `OPENAI_API_KEY`, and `OPENAI_EXECUTOR_API_KEY` through your secret
manager. The two OpenAI keys must match the session owner's organization, project,
and user or service account. Optional `DAYTONA_API_URL` and `DAYTONA_TARGET` are
passed to the controller.

```bash
uv run examples/agents_api/sandboxes/webhook_managed/daytona/deploy.py
```

Register the printed URL in **OpenAI project settings → Webhooks**, subscribing to
`agent.session.action_required` and `agent.session.failed`. Set the generated
`OPENAI_WEBHOOK_SECRET` locally and run the deployment command again. Use the
[shared client](../README.md#run-and-reconnect) to create sessions and submit work.

Do not register this URL in Daytona's Webhooks page: that page sends Daytona
lifecycle notifications outward, rather than receiving OpenAI events.

The public endpoint rejects requests until the signing secret is installed and
checks every delivery's signature. Only the controller receives application and
Daytona credentials; session sandboxes receive only the restricted executor key.
Run one controller process. Its queue survives process restarts, not controller
deletion. Failed provisioning gets up to five attempts.

## Lifecycle

| Current state | Handler action |
| --- | --- |
| Connection required, no worker | Create a worker and launch the executor. |
| Connection required, stopped worker | Start the same worker and relaunch the executor. |
| Session failed | Delete its worker. |
| Other agent, resolved action, or idle event | Do not provision or stop compute. |

## Stop or clean up

The controller logs each session's sandbox ID. To release compute between turns,
stop that sandbox in Daytona. The next input wakes it through the
webhook. Stopping retains its filesystem but ends running processes. Deleting it
instead causes the next input to create a fresh sandbox without previous files.

For final cleanup, delete the API session and its Daytona sandbox separately.
Remove the OpenAI webhook before deleting the `agents-api-webhook-daytona`
controller. Worker sandboxes have a 30-minute wall-clock TTL; the controller has
a two-hour TTL, extended on redeployment. Expiration destroys the sandbox and
its local queue and files. For a long-running service, provide persistent hosting
and queue storage for the controller.
If the controller expires, redeploy it and update the OpenAI webhook with the new URL.
See [Daytona lifecycle settings](https://www.daytona.io/docs/sandboxes#wall-clock-ttl).

Controller logs are in `/app/controller.log`; executor logs are in
`/tmp/codex-executor.log` inside each worker.
