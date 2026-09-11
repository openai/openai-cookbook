# Application-managed Vercel sandbox

The application creates an Agents API session and a Vercel sandbox, starts
`codex exec-server`, and asks the agent to turn `brief.txt` into `plan.md`.
It prints the plan, destroys the sandbox, and deletes the session.

## Run

Set `VERCEL_TOKEN`, `VERCEL_TEAM_ID`, `VERCEL_PROJECT_ID`, `OPENAI_API_KEY`, and
a separate restricted `OPENAI_EXECUTOR_API_KEY`. The OpenAI keys must have the
same owner, organization, and project. Only the executor key enters the sandbox.

From the Cookbook repository root:

```bash
uv run examples/agents_api/sandboxes/application_managed/vercel/main.py
```

Dependencies are declared inline. The script allows six minutes for setup and
execution and attempts both cleanup operations on failure. It creates a
non-persistent sandbox with a ten-minute execution limit. If creation times out,
check Vercel for `agents-api-<last 12 characters of the printed session ID>`
before retrying.

For follow-up turns, keep both resources until the application is finished.
Do not attach a provisioning webhook handler to these sessions.

## References

- [Vercel Sandbox documentation](https://vercel.com/docs/sandbox)
- [Vercel Sandbox SDK reference](https://vercel.com/docs/sandbox/sdk-reference)
- [Webhook-managed example](../../webhook_managed/vercel/README.md)
