# Bulk invoice and contract review

Mount a folder of invoices and contracts alongside a reusable accounts-payable policy skill. A `gpt-5.6-luna` agent delegates each document to a specialist subagent, applies the discovered skill, writes individual reports plus a consolidated summary, and leaves every approval to a person.

```mermaid
sequenceDiagram
    participant Person
    participant App as Review command
    participant Agent as Agents API
    participant Reviewers as Specialist subagents
    participant Policy as Mounted review skill
    participant Workspace as Mounted input/output folders
    Person->>App: Submit a folder of invoices and contracts
    App->>Agent: Create one multi-agent session
    App->>Workspace: Mount input and policy read-only; output read-write
    Agent->>Reviewers: Delegate one document to each specialist
    Reviewers->>Policy: Discover and apply expense-review-policy
    Reviewers->>Workspace: Write individual JSON reports
    Agent->>Workspace: Write the consolidated summary
    App-->>Person: Write findings for human review
```

## What you need

- Python 3.14+ and `uv`.
- A sandbox: self-hosted Docker or a [third-party provider](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#sandbox-providers).
- An OpenAI API key and a separate restricted executor key.

## 1. Set up the workspace

From the repository root:

```bash
cp examples/agents_api/apps/document_review/.env.example examples/agents_api/apps/document_review/.env
docker build -t agent-api-sandbox:latest examples/agents_api/sandboxes/application_managed/docker
```

Set `OPENAI_API_KEY` and `OPENAI_EXECUTOR_API_KEY` in `examples/agents_api/apps/document_review/.env`. Use keys with the same owner, organization, and project. Only the executor key enters the sandbox. It needs `api.agents.environments.connect` and IP restrictions that allow the sandbox's outbound network. The application loads this file automatically.

To create an executor key with the required permission, open [Agents > Environments > Keys](https://platform.openai.com/agents?tab=environments&environment_view=keys) and select **Create**.

You can replace local Docker with any compatible [sandbox provider](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#sandbox-providers).

## 2. Review the document batch

```bash
uv run examples/agents_api/apps/document_review/main.py \
  --input examples/agents_api/apps/document_review/sample_documents \
  --output ./review-output
```

The input folder contains an invoice with a $900 overcharge and a contract with automatic renewal, unilateral price increases, unlimited liability, and unrestricted customer-data sharing. Specialist subagents apply the mounted policy to each document and write:

```text
review-output/
  contract.json
  invoice.json
  summary.json
  review-activity.json
```

The source folder and policy skill are mounted read-only; reports are written to `/workspace/output` and remain available on the host after the sandbox exits. With Docker Desktop, keep input and output directories under your home directory; system temporary directories may not be shared.

The command logs the session, sandbox, mounted directories, specialist subagents, and generated artifacts as the review progresses.

Invoice reports include extracted line items and a calculation. The application
checks the arithmetic before returning a report. A person must still verify that
the extracted amounts match the source document and review the recommendation.

Use an empty output folder for each run and unique document stems, such as `invoice-104.txt` and `contract-208.txt`. The names `summary` and `review-activity` are reserved.

## Inspect retained command activity

Before deleting the session, the app exports retained commands from the coordinator
and each specialist to `review-activity.json`. A `null` subagent ID identifies the
coordinator. Specialist commands come from their own item histories:

```python
async for subagent in client.beta.agents.sessions.subagents.list(session.id):
    async for item in client.beta.agents.sessions.subagents.items.list(
        subagent.id, session_id=session.id
    ):
        if item.type == "command_execution":
            print(subagent.id, item.command)
```

These records come from retained API history, not model-written reviewer names.
They are not a complete security audit. Protect this file like the reports:
commands can contain document content.

## How the policy skill works

The included policy lives at:

```text
skills/expense-review-policy/SKILL.md
```

It is mounted at `/workspace/skills/expense-review-policy/SKILL.md` and discovered through the session's capability root:

```python
environment = {
    "type": "self_hosted",
    "workspace_directory": "/workspace",
    "capability_directories": ["/workspace/skills"],
}
```

Each specialist applies `$expense-review-policy` and includes its `policy_id` and `decision` in the generated report. Replace `SKILL.md` with your own review policy without rebuilding the sandbox image.

## Make it yours

Replace the included skill with your team's own accounts-payable or contract-review policy, and use your preferred sandbox provider when you deploy the application. Keep approval in your application: the agent can recommend a decision, but it should never make payments or accept contracts on its own.

## Files

- [main.py](main.py): Command-line arguments and the batch summary.
- [agent.py](agent.py): Specialist reviews, report validation, and activity export.
- [sandbox.py](sandbox.py): Document, artifact, and skill mounts.
