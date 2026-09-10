# E2B webhook-managed sandbox

A controller in a dedicated E2B sandbox receives OpenAI webhooks and queues work
in SQLite. It starts or reconnects a separate worker sandbox for each API session.
Agent commands run only in the worker sandbox.

## Deploy

Create an agent using the [shared setup](../README.md#set-up-once). Run the
deployment command below from the Cookbook repository root.

Set `OPENAI_AGENT_ID` to the agent ID from the shared setup. Provide it alongside
`E2B_API_KEY`, `OPENAI_API_KEY`, and `OPENAI_EXECUTOR_API_KEY` through your secret
manager. The two OpenAI keys must match the session owner's organization, project,
and user or service account.

```bash
uv run examples/agents_api/sandboxes/webhook_managed/e2b/deploy.py
```

The deployment saves the controller ID in the ignored `.controller.json` beside
`deploy.py`. Keep that file to redeploy the same controller and retain its queue.
If the controller expires, remove this file before creating a replacement; its
URL changes, so update the OpenAI webhook too.

Register the printed URL in **OpenAI project settings → Webhooks**, subscribing to
`agent.session.action_required` and `agent.session.failed`. Set the generated
`OPENAI_WEBHOOK_SECRET` locally and redeploy. Then use the
[shared client](../README.md#run-and-reconnect).

E2B's Webhooks page is for outgoing sandbox lifecycle notifications; it is not
where you register this OpenAI receiver.

The public webhook endpoint verifies each delivery's signature. Worker
sandboxes disable public inbound traffic and receive only the restricted executor
key. The application key, E2B key, and signing secret stay in the controller.
Run one controller process. Its queue survives process restarts, not controller
deletion. Failed provisioning gets up to five attempts.

## Lifecycle

| Current state | Handler action |
| --- | --- |
| Connection required, no worker | Create a worker and launch the executor. |
| Connection required, paused worker | Resume the same worker and ensure its executor is running. |
| Session failed | Kill its worker, including a paused worker. |
| Other agent, resolved action, or idle event | Do not provision or stop compute. |

## Stop or clean up

The controller logs each session's sandbox ID. To release compute between turns,
pause the sandbox through E2B; the next input makes the handler resume
it. Killing it instead causes the next input to create a fresh sandbox, without
previous files. The handler finds workers by their `agents-session-id` metadata.

For final cleanup, delete the API session and kill its E2B sandbox separately,
including paused workers. Remove the OpenAI webhook before killing the controller.
Worker sandboxes have a 30-minute running timeout, refreshed on reconnect; the
controller has a one-hour timeout, extended on redeployment. The example does not
automatically pause or auto-resume the controller. Its SQLite queue survives a
process restart, not sandbox deletion. For a long-running service, provide
persistent hosting and queue storage for the controller.

Controller logs are in `/app/controller.log`; executor logs are in
`/tmp/codex-executor.log` inside each worker.
