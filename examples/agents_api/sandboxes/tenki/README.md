# Tenki sandboxes

Run Agents API tasks with `codex exec-server` in [Tenki](https://tenki.cloud)
sandboxes, microVMs that boot in about two seconds:

- [Application-managed](application_managed/README.md): create a worker, run a
  task, pause the worker between two turns, read the output, and clean up the
  worker and session.
- [Webhook-managed](webhook_managed/README.md): deploy a controller that
  provisions workers and resumes paused workers when a session needs a
  connection.

Both modes use [sandbox.py](sandbox.py) for worker creation and executor launch,
and both do three things the same way:

1. **Workers start from a golden image.** [build_snapshot.py](build_snapshot.py)
   installs the Codex CLI once and snapshots the result. Set the printed
   `TENKI_SNAPSHOT_ID` and every worker restores from it in about a second,
   with `codex` already installed, so the executor connects a few seconds after
   the session asks for it. Without the variable, each worker installs the CLI
   itself, which adds about ten seconds and a download per worker.
2. **Workers pause between turns instead of terminating.** A paused Tenki
   sandbox keeps its memory and disk and uses no compute. Resuming returns the
   same sandbox, with the same ID and files, in about two seconds. The
   application-managed example pauses between its two turns; the webhook
   handler resumes a paused worker when OpenAI asks for a connection.
3. **Only the executor key enters a worker.** `start_executor` passes
   `OPENAI_EXECUTOR_API_KEY` as `CODEX_API_KEY` in the launch command's
   environment. It is not part of the worker's definition, so it is not stored
   as sandbox configuration or in snapshots taken from the worker. The
   application key, Tenki key, and webhook signing secret stay in the
   application or the controller.

## Set up

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/). Each
   script declares its dependencies inline, including the
   [`tenki`](https://pypi.org/project/tenki/) SDK.
2. Create a Tenki API key (`tk_...`) at [app.tenki.cloud](https://app.tenki.cloud)
   and export it as `TENKI_API_KEY`. The SDK infers the workspace from the key.
3. Build the golden image and export its ID. Run this from the Cookbook
   repository root; it takes about 20 seconds:

   ```bash
   uv run examples/agents_api/sandboxes/tenki/build_snapshot.py
   ```

   Example output:

   ```text
   Installed: codex-cli 0.166.0-alpha.6
   Snapshot: 1d2beec7-08ee-40fe-be55-038cb82d1fb8 (READY)

   export TENKI_SNAPSHOT_ID=1d2beec7-08ee-40fe-be55-038cb82d1fb8
   ```

   Rebuild to pick up a new Codex release, then swap the ID. The old snapshot
   stays until you delete it with `tenki sandbox snapshot delete <id>`, so
   workers created from it keep working through the switch.

The builder is a one-core, 1 GiB sandbox because a restored sandbox is never
smaller than the snapshot it restores. Workers are created with two cores and
2 GiB; a worker may be larger than the image, never smaller.

## Credentials

| Variable | Where it is used |
| --- | --- |
| `TENKI_API_KEY` | Application and controller. Creates, pauses, resumes, and terminates workers. |
| `TENKI_SNAPSHOT_ID` | Optional. The golden image from `build_snapshot.py`. |
| `OPENAI_API_KEY` | Application and controller. Never enters a worker. |
| `OPENAI_EXECUTOR_API_KEY` | A restricted [environment key](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#authentication), passed to each worker's executor as `CODEX_API_KEY`. |
| `OPENAI_WEBHOOK_SECRET` | Controller only. Verifies deliveries from your OpenAI project. |

The two OpenAI keys must have the same owner, organization, and project.

## Worker lifecycle

| Call | Effect |
| --- | --- |
| `client.create(snapshot_id=..., metadata={"agents-session-id": ...})` | Boot a worker from the golden image, tagged with its session. |
| `sandbox.pause()` then `sandbox.wait_paused()` | Snapshot memory and disk and release the VM. Takes about six seconds. |
| `sandbox.resume()` then `sandbox.wait_ready()` | Bring the same worker back. Takes about two seconds. |
| `client.list()` | Find a session's worker by its metadata, running or paused. |
| `sandbox.terminate()` | Release the worker for good. |

Workers have a `max_duration`, after which Tenki terminates a running worker,
and a `pause_retention`, after which a paused worker can no longer be resumed.
The `max_duration` clock does not run while a worker is paused. Set
`max_duration` above your longest turn and `pause_retention` above the longest
gap between turns. Tenki sandboxes do not pause on idle; these examples pause
explicitly.

A new Tenki sandbox already has a Codex CLI at `/usr/local/bin/codex`. The
Agents API self-hosted guide uses the `alpha` channel, so the install replaces
it with `@openai/codex@alpha` and records the installed version in
`/home/tenki/.codex-executor-version`; a worker with that file skips the install.

## References

- [Tenki documentation](https://tenki.cloud/docs)
- [Tenki Python SDK](https://github.com/LuxorLabs/tenki-sdk-python)
- [Golden image and pause/resume examples](https://github.com/LuxorLabs/cookbook) in the Tenki cookbook
