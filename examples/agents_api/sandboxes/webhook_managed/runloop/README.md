# Runloop webhook-managed sandbox

A controller in a dedicated Runloop devbox receives signed OpenAI webhooks and
queues work in SQLite. It starts or resumes a separate worker devbox for each
API session. Agent commands run only in the worker.

## Deploy

Create an agent using the [shared setup](../README.md#set-up-once). Set
`OPENAI_AGENT_ID`, `OPENAI_API_KEY`, `OPENAI_EXECUTOR_API_KEY`, and `RUNLOOP_API_KEY`
locally. Use an
[environment key](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#authentication)
for `OPENAI_EXECUTOR_API_KEY`.

Run from the Cookbook repository root:

```bash
uv run examples/agents_api/sandboxes/webhook_managed/runloop/deploy.py
```

Register the printed URL in **OpenAI project settings → Webhooks**, subscribing to
`agent.session.action_required` and `agent.session.failed`. Set the generated
`OPENAI_WEBHOOK_SECRET` locally and deploy again. **Update the webhook URL to the
newly printed address**, keeping its signing secret. Then use the
[shared client](../README.md#run-and-reconnect).

Deployment stores credentials in Runloop secrets with the `agents_api_webhook_`
prefix. The controller accesses OpenAI through a Runloop gateway; workers receive
only the environment key as `CODEX_API_KEY` and connect directly to OpenAI.
The endpoint rejects deliveries until configured and verifies every signature.

The controller ID is saved in `.controller.json`. Changing the handler, agent ID,
Runloop key, or signing secret replaces the controller and changes its URL.
Otherwise deployment reuses it.

## Lifecycle

| Current state | Handler action |
| --- | --- |
| Connection required, no worker | Create a worker and launch the executor. |
| Connection required, suspended worker | Resume it and relaunch the executor. |
| Session failed | Shut down its worker. |
| Other agent, resolved action, or idle event | Do not provision or stop compute. |

The handler waits up to 60 seconds for connection before completing a queued job.
Failed startup gets up to five attempts. Run one controller process; its queue
survives process restarts and suspend/resume, but not controller replacement.

## Stop or clean up

Suspend a worker between turns to retain its files. The next input wakes it
through a webhook. Workers shut down after 30 minutes. The controller suspends
after ten idle minutes; HTTP requests wake it, with the first request returning
`503` for OpenAI to retry.

For final cleanup, delete the API session and shut down its worker separately.
Remove the OpenAI webhook before shutting down the controller. Delete the
`agents-api-webhook-openai-controller` gateway and the example's Runloop secrets
when no longer used.

Find controller logs in the Runloop devbox logs and executor logs in
`/tmp/codex-executor.log` inside each worker.

## References

- [Runloop documentation](https://docs.runloop.ai/)
- [Runloop Python SDK](https://runloopai.github.io/api-client-python/)
