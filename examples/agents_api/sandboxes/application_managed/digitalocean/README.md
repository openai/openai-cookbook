# Application-managed DigitalOcean sandbox

The application creates an Agents API session and starts a DigitalOcean sandbox
using the `codex-agentapi` template. The template runs `codex exec-server`;
OpenAI runs the agent. The application downloads the generated `plan.md`,
destroys the sandbox, and deletes the session.

## Run

You need access to DigitalOcean's Agent Harness Runtime preview and the
`codex-agentapi` template. This example uses the [PyDo beta SDK](https://github.com/digitalocean/pydo/releases/tag/v0.40.0-beta.7).

Set `DIGITALOCEAN_TOKEN`, `OPENAI_API_KEY`, and a separate restricted
`OPENAI_EXECUTOR_API_KEY`. The OpenAI keys must have the same owner,
organization, and project. Only the executor key is passed to DigitalOcean.

From the Cookbook repository root:

```bash
uv run examples/agents_api/sandboxes/application_managed/digitalocean/main.py
```

Dependencies are declared inline. The script reads the flat [agents.yaml](agents.yaml)
manifest and supplies the environment ID and executor key at runtime. Do not
log or save the resolved manifest: it contains the executor key.

The script allows ten minutes for setup and execution, then attempts both
cleanup operations. If creation times out before returning an ID, check
DigitalOcean for `agents-api-<last 12 characters of the printed session ID>`
before retrying.

For follow-up turns, keep both resources until the application is finished.
Do not attach a provisioning webhook handler to these sessions.

## References

- [DigitalOcean sandbox setup example](https://github.com/digitalocean/pydo/tree/v0.40.0-beta.7/examples/agents/doc_python_sdk)
- [DigitalOcean Python SDK](https://github.com/digitalocean/pydo)
- [Webhook-managed example](../../webhook_managed/digitalocean/README.md)
