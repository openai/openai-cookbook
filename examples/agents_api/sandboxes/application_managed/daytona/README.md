# Application-managed Daytona sandbox

The application creates an Agents API session and a Daytona sandbox, starts
`codex exec-server`, and asks the agent to turn `brief.txt` into `plan.md`.
It downloads the plan, deletes the sandbox, and deletes the session.

## Run

Set `DAYTONA_API_KEY`, `OPENAI_API_KEY`, and a separate restricted
`OPENAI_EXECUTOR_API_KEY`. The OpenAI keys must have the same owner,
organization, and project. Only the executor key enters the sandbox.

From the Cookbook repository root:

```bash
uv run examples/agents_api/sandboxes/application_managed/daytona/main.py
```

Dependencies are declared inline. The script allows six minutes for setup and
execution and attempts both cleanup operations on failure. The sandbox has a
ten-minute TTL. If creation times out before returning a sandbox, check Daytona
for `agents-api-<last 12 characters of the printed session ID>` before retrying.

For follow-up turns, keep both resources until the application is finished.
Do not attach a provisioning webhook handler to these sessions.

## References

- [Daytona documentation](https://www.daytona.io/docs/)
- [Daytona Python SDK](https://www.daytona.io/docs/en/python-sdk/)
- [Webhook-managed example](../../webhook_managed/daytona/README.md)
