# Runloop webhook-managed sandbox

A controller Runloop devbox receives signed OpenAI webhooks and queues work in
SQLite. It starts or resumes a separate worker devbox for each API session.
OpenAI requests from both controller and workers pass through Runloop's API
gateway, so the OpenAI key is not exposed inside either devbox.

## Deploy

Create an agent using the [shared setup](../README.md#set-up-once), then set
`OPENAI_AGENT_ID`, `OPENAI_API_KEY`, `OPENAI_EXECUTOR_API_KEY`, and
`RUNLOOP_API_KEY` locally. The deployment stores them as namespaced Runloop
secrets (`agents_api_webhook_openai_api_key`,
`agents_api_webhook_openai_executor_api_key`, and
`agents_api_webhook_runloop_api_key`), creates separate OpenAI gateway
configurations for the controller and executor, and injects the Runloop key only
into the controller. As in the shared setup, make the executor key restricted to
**List models → Read** with other permissions set to **None**.

```bash
uv run examples/agents_api/sandboxes/webhook_managed/runloop/deploy.py
```

The deployment saves the controller ID in the ignored `.controller.json` beside
`deploy.py`. Register the printed URL in **OpenAI project settings → Webhooks**,
subscribing to `agent.session.action_required` and `agent.session.failed`. Set the
generated `OPENAI_WEBHOOK_SECRET` locally and deploy again to update its Runloop
secret. The configured redeployment replaces the bootstrap controller, so update
the webhook endpoint to the newly printed URL while keeping its signing secret.
Then use the [shared client](../README.md#run-and-reconnect).

The public tunnel rejects deliveries until the signing secret is installed and
verifies every signature afterward. The controller suspends after ten idle
minutes. Its lifecycle sets `resume_triggers.http=true`, so a webhook request
wakes it through the tunnel; the sender must retry the initial `503` response.

The controller needs `RUNLOOP_API_KEY` to manage worker devboxes. Workers receive
only a short-lived gateway credential backed by the restricted executor key.
The gateway adds the real OpenAI bearer credential upstream without placing it
in either devbox.

## Lifecycle and cleanup

| Current state | Handler action |
| --- | --- |
| Connection required, no worker | Create a worker and launch the executor. |
| Connection required, suspended worker | Resume it and relaunch the executor. |
| Session failed | Shut down its worker. |
| Other agent, resolved action, or idle event | Do not provision or stop compute. |

Worker devboxes shut down after 30 minutes. The controller queue survives
process restarts and suspend/resume, but not controller replacement. Deployment
reuses it when the handler, agent ID, Runloop key, and webhook secret are unchanged;
otherwise it replaces the controller and prints a new URL to register.

For final cleanup, delete the API session and shut down its worker separately.
Remove the OpenAI webhook before shutting down the controller. Delete the
`agents-api-webhook-openai-controller` and
`agents-api-webhook-openai-executor` gateway configurations and the example's
Runloop secrets if they are no longer used.

Controller logs are available through the controller devbox logs; executor logs
are in `/tmp/codex-executor.log` inside each worker.

## References

- [Runloop documentation](https://docs.runloop.ai/)
- [Runloop Python SDK](https://runloopai.github.io/api-client-python/)
