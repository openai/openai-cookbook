# Application-managed Docker sandbox

The application builds a local image, starts the executor, runs the agent against
`sample_report.txt`, and cleans up the container and API session.

## Run

Start Docker and set `OPENAI_API_KEY` and a separate restricted
`OPENAI_EXECUTOR_API_KEY`. Use keys with the same owner, organization, and project.
From the Cookbook repository root:

```bash
uv run examples/agents_api/sandboxes/application_managed/docker/main.py
```

The [Dockerfile](Dockerfile) installs Codex and copies the sample into `/workspace`.
This is a local development example, not a hardened multi-tenant sandbox.

To manage cloud compute through OpenAI webhooks, use the
[webhook-managed examples](../../webhook_managed/README.md).
