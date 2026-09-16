# Agents API examples

Complete applications and sandbox integrations for the Agents API. Each application
README walks through the implementation and explains how to run it.

## Applications

| Example | What it does |
| --- | --- |
| [SRE bot](https://github.com/openai/openai-cookbook/tree/main/examples/agents_api/apps/sev_bot) | Investigate alerts and request approval for recovery actions. |
| [Slack bot](https://github.com/openai/openai-cookbook/tree/main/examples/agents_api/apps/slack_bot) | Answer requests using conversation history and connected workplace tools. |
| [Data analyst](https://github.com/openai/openai-cookbook/tree/main/examples/agents_api/apps/data_analyst) | Answer questions with read-only warehouse queries. |
| [GitHub issue investigator](https://github.com/openai/openai-cookbook/tree/main/examples/agents_api/apps/github_issues) | Reproduce reported bugs and prepare findings for GitHub. |
| [Document reviewer](https://github.com/openai/openai-cookbook/tree/main/examples/agents_api/apps/document_review) | Review invoices and contracts with policy skills and specialist agents. |

## Sandbox integrations

- [Application-managed](https://github.com/openai/openai-cookbook/tree/main/examples/agents_api/sandboxes/application_managed): your application
  starts and stops the sandbox directly.
- [Webhook-managed](https://github.com/openai/openai-cookbook/tree/main/examples/agents_api/sandboxes/webhook_managed): a deployed handler
  provisions the sandbox while a shared client calls the Agents API.

See the [sandbox overview](https://github.com/openai/openai-cookbook/tree/main/examples/agents_api/sandboxes) to choose a provisioning mode.

## Run an example

Run commands from the Cookbook repository root. Each example's README covers
dependencies, credentials, sample inputs, and cleanup. Python entry points declare
their dependencies inline for [uv](https://docs.astral.sh/uv/).

The application examples require Python 3.14. Provider examples declare their
supported Python version in each script.

These examples use the official OpenAI Python SDK's `client.beta.agents`
and `sessions.stream()`, available in `openai>=3.13.0` on PyPI.

Create sessions with the standard client:

```python
from openai import OpenAI

client = OpenAI()

session = client.beta.agents.sessions.create(
    agent={"model": "gpt-5.6-sol"},
    environment={"type": "self_hosted", "workspace_directory": "/workspace"},
)
```

The sandbox examples then start `codex exec-server` with the returned
`session.environment.id` and `session.environment.remote_url`, stream a turn,
and clean up. Async applications use `AsyncOpenAI` with the same
`client.beta.agents` resources and `await` for requests.

Keep credentials in environment variables or the example's local `.env` file.
Use a separate restricted `OPENAI_EXECUTOR_API_KEY` for sandbox execution. Follow
the [executor authentication requirements](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#authentication).
The executor key needs `api.agents.environments.connect`, and its IP restrictions
must allow requests from your sandbox's outbound network.

## Documentation

- [Agents API overview](https://developers.openai.com/api/docs/guides/agents-api/overview)
- [Self-hosted sandboxes](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted)
- [Sandbox lifecycle](https://developers.openai.com/api/docs/guides/agents-api/environments/lifecycle)
