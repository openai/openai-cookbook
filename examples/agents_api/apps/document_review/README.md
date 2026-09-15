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

## Agents API capabilities

Sandbox, Multi-agent, Skills, Workspace files, Turn history, Streaming.

### Review documents in parallel

Enable multi-agent execution so the coordinator delegates individual invoices and contracts to specialist subagents instead of reviewing a batch sequentially.

### Discover reusable policy skills

Mount an accounts-payable policy into the sandbox and register its capability root. Every specialist discovers the same skill instead of duplicating policy rules in application prompts.

### Work directly with mounted files

Input documents are mounted read-only, while specialists write reports to a separate output directory that remains available after the sandbox exits.

### Produce durable batch artifacts

Each document gets a machine-readable JSON report, and the coordinating agent produces a consolidated summary for the complete batch.

### Keep approval with a person

The agent identifies risks and recommends a decision, but your application retains authority over payment approval and contract acceptance.

## Application flow

1. Document folder.
2. Mounted policy skill.
3. Agent coordinator.
4. Specialist subagents.
5. Review artifacts.
6. Human approvals.

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

## Implementation walkthrough

This walkthrough covers mounted documents, reusable policy skills, specialist subagents, structured review artifacts, and human approvals.

Follow the setup instructions above, then use the source links below to explore each part of the application.

### 1. Set up

Clone the repository, copy the example's environment template, and build the Docker image that connects an isolated workspace to the Agents API.

### 2. Prepare the document folders

Separate source documents from generated artifacts. The input mount is read-only; the output mount is writable and preserves reports on the host. Use an empty output folder for each batch.

With Docker Desktop, keep both folders under your home directory so the sandbox can access them.

Read the implementation in [sandbox.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/document_review/sandbox.py).

### 3. Add a reusable review skill

Keep your accounts-payable rules in a standard `SKILL.md` file. The included `expense-review-policy` skill defines invoice checks, contract risks, decision statuses, and required report fields.

The skill is mounted at runtime, so updating the policy does not require rebuilding the Docker image.

Read the implementation in [skills/expense-review-policy/SKILL.md](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/document_review/skills/expense-review-policy/SKILL.md).

### 4. Create a multi-agent review session

Enable multi-agent execution, register the policy skill's capability directory, and tell the coordinating `gpt-5.6-luna` agent to have each specialist apply the discovered skill.

Read the implementation in [agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/document_review/agent.py).

### 5. Mount the documents and policy skill

Start the sandbox with separate document, policy, and artifact mounts. Documents and the reusable skill remain read-only, while specialists write reports into the output directory.

Pass the separate restricted executor key as `CODEX_API_KEY` at runtime. Do not bake credentials into your image or print them in application logs.

Read the implementation in [sandbox.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/document_review/sandbox.py).

### 6. Delegate the document reviews

Ask the coordinator to delegate the batch across specialist subagents. Each specialist discovers and applies the mounted policy before inspecting its document and writing a report.

Read the implementation in [agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/document_review/agent.py).

### 7. Inspect retained command activity

Export retained commands and their turn IDs from the coordinator and each specialist before deleting the session. A null subagent ID identifies the coordinator; specialist commands come from their own retained item histories.

This is not a complete audit of specialist work. Command text can contain document content; protect the activity file like the reports.

Read the implementation in [agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/document_review/agent.py).

### 8. Collect the review artifacts

Read each specialist's report from the mounted output directory, then load the coordinator's consolidated summary. Mark every document as awaiting human approval.

Read the implementation in [agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/document_review/agent.py).

### 9. Inspect the review artifact

Each document gets its own report. For the invoice, the reviewing specialist records the arithmetic error, missing purchase order, and suspicious payment change.

Read the implementation in [agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/document_review/agent.py).

### 10. Leave approval with a person

Inspect the generated reports before approving any invoice or contract. The agent identifies risks and recommendations but never executes an approval.

Read the implementation in [agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/document_review/agent.py).

### 11. Clean up the session

Stop the temporary sandbox and delete the Agents API session. The generated reports remain in the mounted output folder after the container exits.

Read the implementation in [agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/document_review/agent.py).

### 12. Run the sample batch

Review the included invoice and contract together. Specialists inspect both documents and leave individual reports plus a consolidated summary in `review-output`.

## Example result

Two specialist subagents discover the mounted policy, review the batch, write individual artifacts, and leave every approval with a human reviewer.

The following illustrates a possible result; model-generated findings depend on the inputs and connected sources.

```text
Policy applied: AP-104
Documents reviewed: 2
Subagents created: 2

review-output/
  invoice.json    $900 overcharge; missing PO; changed bank details
  contract.json   Automatic renewal; unlimited liability; data sharing
  summary.json    Consolidated findings and recommended next steps
  review-activity.json    Command history with specialist IDs

Status: awaiting human approval
```

## Next steps

- Replace the sample skill with your team's accounts-payable or contract-review policy.
- Replace the local Docker container with your preferred isolated sandbox provider.
- Add application tools for vendor records, purchase orders, contract policies, or payment verification.
- Authenticate reviewers and persist every decision in your existing approval and audit system.

## Related documentation

- [Sandbox providers](https://developers.openai.com/api/docs/guides/agents-api/environments/self-hosted#sandbox-providers): Choose a local or hosted provider for isolated document-review workspaces.


## Files

- [main.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/document_review/main.py): Command-line arguments and the batch summary.
- [agent.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/document_review/agent.py): Specialist reviews, report validation, and activity export.
- [sandbox.py](https://github.com/openai/openai-cookbook/blob/main/examples/agents_api/apps/document_review/sandbox.py): Document, artifact, and skill mounts.
