# Application-managed Blaxel sandbox

The application creates an Agents API session and a Blaxel sandbox, starts
`codex exec-server`, and asks the agent to turn `brief.txt` into `plan.md`.
It prints the plan, deletes the sandbox, and deletes the session.

## Run

Set `BL_API_KEY`, `BL_WORKSPACE`, `OPENAI_API_KEY`, and a separate restricted
`OPENAI_EXECUTOR_API_KEY`. The OpenAI keys must have the same owner,
organization, and project. Only the executor key enters the sandbox.
Set `BL_REGION` to choose a region; the default is `us-pdx-1`.

From the Cookbook repository root:

```bash
uv run examples/agents_api/sandboxes/application_managed/blaxel/main.py
```

Dependencies are declared inline. The script allows six minutes for setup and
execution and attempts both cleanup operations on failure. The sandbox has a
ten-minute TTL. If creation times out before returning a sandbox, check Blaxel
for `agents-api-<last 12 characters of the printed session ID>` before retrying.

For follow-up turns, keep both resources until the application is finished.
Do not attach a provisioning webhook handler to these sessions.

## References

- [Blaxel sandbox documentation](https://docs.blaxel.ai/Sandboxes/Overview)
- [Blaxel Python SDK](https://github.com/blaxel-ai/sdk-python)
- [Webhook-managed example](../../webhook_managed/blaxel/README.md)
