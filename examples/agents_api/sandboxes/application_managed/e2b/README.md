# Application-managed E2B sandbox

The application creates an Agents API session and an E2B sandbox, starts
`codex exec-server`, and asks the agent to turn `brief.txt` into `plan.md`.
It prints the plan, kills the sandbox, and deletes the session.

## Run

Set `E2B_API_KEY`, `OPENAI_API_KEY`, and a separate restricted
`OPENAI_EXECUTOR_API_KEY`. The OpenAI keys must have the same owner,
organization, and project. Only the executor key enters the sandbox.

From the Cookbook repository root:

```bash
uv run examples/agents_api/sandboxes/application_managed/e2b/main.py
```

Dependencies are declared inline. The script allows six minutes for setup and
execution and attempts both cleanup operations on failure. The sandbox has a
ten-minute timeout. If creation times out before returning an ID, check E2B for
the `agents-session-id` metadata matching the printed session ID before retrying.

For follow-up turns, keep both resources until the application is finished.
Do not attach a provisioning webhook handler to these sessions.

## References

- [E2B documentation](https://e2b.dev/docs)
- [E2B SDK reference](https://e2b.dev/docs/sdk-reference)
- [Webhook-managed example](../../webhook_managed/e2b/README.md)
