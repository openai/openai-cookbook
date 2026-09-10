# Application-managed Modal sandbox

The application builds an image remotely, starts a Modal sandbox, connects the
executor, runs the agent against `sample_report.txt`, and cleans up both resources.

## Run

Set `OPENAI_API_KEY` and a separate restricted `OPENAI_EXECUTOR_API_KEY`. Use keys
with the same owner, organization, and project. From the Cookbook repository root:

```bash
uv tool run --from 'modal[api-proxy-support]>=1.3.4,<2' modal setup
uv run examples/agents_api/sandboxes/application_managed/modal/main.py
```

The Modal SDK uses the active profile in `~/.modal.toml`; `MODAL_TOKEN_ID` and
`MODAL_TOKEN_SECRET` override it when set. The sandbox has a 15-minute maximum
lifetime and no inbound port: `codex exec-server` connects outbound to OpenAI.

For a Modal-hosted handler that provisions compute from OpenAI webhooks, use the
[webhook-managed Modal example](../../webhook_managed/modal/README.md).
