# Application-managed DigitalOcean sandbox

The application creates an Agents API session and starts a DigitalOcean sandbox
using the `codex-agentapi` template. The template runs `codex exec-server`;
OpenAI runs the agent. The application downloads the generated `plan.md`,
destroys the sandbox, and deletes the session.

## Run

You need a sandbox-enabled DigitalOcean account with access to the
`codex-agentapi` template. [DigitalOcean Managed Agents](https://docs.digitalocean.com/products/managed-agents/)
is in public preview. Use [PyDo 0.41.0 or later](https://github.com/digitalocean/pydo/releases)
with async support (`pydo[aio]`).
The DigitalOcean CLI is not required for this flow.

Set `DIGITALOCEAN_TOKEN`, `OPENAI_API_KEY`, and a separate restricted
`OPENAI_EXECUTOR_API_KEY`. The OpenAI keys must have the same owner,
organization, and project. Only the executor key is passed to DigitalOcean.

From the Cookbook repository root:

```bash
uv run examples/agents_api/sandboxes/digitalocean/application_managed/main.py
```

Dependencies are declared inline. The script reads the shared [environment.yaml](../environment.yaml)
manifest and supplies the environment ID and executor key at runtime. Do not
log or save the resolved manifest: it contains the executor key.

The script allows ten minutes for setup and execution, then attempts both
cleanup operations. If creation times out before returning an ID, check
DigitalOcean for `agents-api-<last 12 characters of the printed session ID>`
before retrying.

For follow-up turns, keep both resources until the application is finished.
Do not attach a provisioning webhook handler to these sessions.

## References

- [DigitalOcean sandbox setup example](https://github.com/digitalocean/pydo/tree/main/examples/agents/doc_python_sdk)
- [DigitalOcean Python SDK](https://github.com/digitalocean/pydo)
- [Webhook-managed example](../webhook_managed/README.md)
