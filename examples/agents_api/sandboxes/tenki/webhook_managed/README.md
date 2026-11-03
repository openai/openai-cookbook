# Tenki webhook-managed sandbox

A controller in a dedicated Tenki sandbox receives OpenAI webhooks and queues
work in SQLite. It starts a worker for each API session, or resumes the
session's paused worker. Agent commands run only in the worker.

## Deploy

Complete the [provider setup](../README.md#set-up) and create an agent using the
[shared setup](../../webhook_managed.md#set-up-once). Run the deployment command
below from the Cookbook repository root.

Set `OPENAI_AGENT_ID` to the agent ID from the shared setup. Provide it alongside
`TENKI_API_KEY`, `TENKI_SNAPSHOT_ID`, `OPENAI_API_KEY`, and
`OPENAI_EXECUTOR_API_KEY` through your secret manager. The two OpenAI keys must
match the session owner's organization, project, and user or service account.

```bash
uv run examples/agents_api/sandboxes/tenki/webhook_managed/deploy.py
```

The deployment finds an existing controller by its `agents-webhook-controller`
metadata, so running it again updates the same controller and keeps its queue.

Register the printed URL in **OpenAI project settings → Webhooks**, subscribing to
`agent.session.action_required` and `agent.session.failed`. Set the generated
`OPENAI_WEBHOOK_SECRET` locally and run the deployment command again. Then use
the [run and reconnect guide](../../webhook_managed.md#run-and-reconnect) with
this provider's client:

```bash
uv run examples/agents_api/sandboxes/tenki/webhook_managed/client.py --agent-id "$OPENAI_AGENT_ID"
```

The public endpoint rejects requests until the signing secret is installed and
checks every delivery's signature. Workers disable inbound traffic and receive
only the restricted executor key, in the executor's environment. The application
key, Tenki key, and signing secret are passed to the controller process's
environment and are not stored in the controller sandbox's configuration.
Run one controller process. Its queue survives process restarts, not controller
termination. Failed provisioning gets up to five attempts.

## Lifecycle

| Current state | Handler action |
| --- | --- |
| Connection required, no worker | Create a worker from the golden image and launch the executor. |
| Connection required, paused worker | Resume the same worker and launch a fresh executor. |
| Connection required, running worker | Replace its executor. |
| Session failed | Terminate its worker, including a paused worker. |
| Other agent, resolved action, or idle event | Do not provision or stop compute. |

## Stop or clean up

The controller logs each session's sandbox ID. To release compute between turns,
pause that worker:

```bash
tenki sandbox pause <sandbox-id>
```

The next input makes the handler resume it, with its files and memory intact,
in about two seconds. Terminating it instead causes the next input to create a
fresh worker without previous files. The handler finds workers by their
`agents-session-id` metadata.

For final cleanup, delete the API session and terminate its worker separately,
including a paused worker. Workers have a 30-minute `max_duration` and a
24-hour `pause_retention`. The controller is a sticky sandbox: it has no
lifetime limit and runs until you terminate it, so remove the OpenAI webhook
and then run `tenki sandbox terminate <controller-id>` when you retire it.
Its SQLite queue survives a process restart, not termination. For a
long-running service, provide persistent hosting and queue storage for the
controller.

Controller logs are in `/home/tenki/controller/controller.log`; executor logs
are in `/tmp/codex-executor.log` inside each worker, recreated on each launch.
