# Application-managed Runloop sandbox

The application creates an Agents API session and a Runloop devbox, starts
`codex exec-server`, and asks the agent to turn `brief.txt` into `plan.md`.
It prints the plan, shuts down the devbox, and deletes the session.

## Run

Set `RUNLOOP_API_KEY`, `OPENAI_API_KEY`, and a separate restricted
`OPENAI_EXECUTOR_API_KEY`. The OpenAI keys must have the same owner,
organization, and project. Only the executor key enters the devbox. See
[executor authentication](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#authentication).

From the Cookbook repository root, run with [uv](https://docs.astral.sh/uv/):

```bash
uv run examples/agents_api/sandboxes/application_managed/runloop/main.py
```

The script declares its dependencies inline, including the Agents API SDK.
It allows five minutes for setup and execution, then attempts cleanup of both
resources. The devbox also has a ten-minute lifetime as a fallback if the
application exits unexpectedly.

This example uses application-managed provisioning. Do not attach a provisioning
webhook handler to its sessions. For follow-up turns, keep the session and devbox
alive until the application is finished.

## References

- [Runloop documentation](https://docs.runloop.ai/)
- [Runloop Python SDK](https://runloopai.github.io/api-client-python/)
