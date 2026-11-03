# Application-managed Tenki sandbox

The application creates an Agents API session and a Tenki worker from the golden
image, starts `codex exec-server`, and asks the agent to turn `brief.txt` into
`plan.md`. It then pauses the worker, resumes it, runs a second turn that edits
`plan.md`, prints the result, terminates the worker, and deletes the session.

## Run

Complete the [provider setup](../README.md#set-up) first. Set `TENKI_API_KEY`,
`TENKI_SNAPSHOT_ID`, `OPENAI_API_KEY`, and a separate restricted
`OPENAI_EXECUTOR_API_KEY`. The OpenAI keys must have the same owner,
organization, and project. Only the executor key enters the worker.

From the Cookbook repository root:

```bash
uv run examples/agents_api/sandboxes/tenki/application_managed/main.py
```

Dependencies are declared inline. The script allows ten minutes for setup and
both turns and attempts both cleanup operations on failure. The worker has a
15-minute `max_duration` and a one-hour `pause_retention`. If creation times out
before returning an ID, run `tenki sandbox list` and look for a sandbox whose
`agents-session-id` metadata matches the printed session ID before retrying.

Between the turns the script stops the executor, pauses the worker, and resumes
it. `plan.md` is still there, because a pause keeps the disk and memory. The
script then launches a fresh executor; the second input connects to it and the
turn runs in the same workspace.

If `TENKI_SNAPSHOT_ID` is unset, the worker installs the Codex alpha itself
before the executor starts, which adds about ten seconds.

For follow-up turns, keep both resources until the application is finished.
Do not attach a provisioning webhook handler to these sessions.

## References

- [Tenki documentation](https://tenki.cloud/docs)
- [Tenki Python SDK](https://github.com/LuxorLabs/tenki-sdk-python)
- [Webhook-managed example](../webhook_managed/README.md)
