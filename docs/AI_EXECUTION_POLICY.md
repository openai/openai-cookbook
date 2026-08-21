# AI Execution Policy

This policy governs AI-assisted work in this repository. It favors small,
recoverable executions with verifiable outcomes.

## Execution contract

One execution must have one narrowly scoped objective. One task must produce
one pull request. Before implementation begins, record:

| Field | Required content |
| --- | --- |
| Scope | The single objective, allowed paths, and explicit exclusions |
| Evidence | Existing files, issues, commits, pull requests, or checkpoints inspected |
| Tests | Focused checks that prove the requested artifact works |
| Stop condition | The exact artifact or external blocker that ends the execution |
| Recovery point | The branch, commit, pull request, checkpoint, or clean base to resume from |

Do not broaden the execution after this contract is set. A new objective is a
new task and a new pull request.

## Inspect and recover first

Inspect targeted existing work before creating new work. Reuse a recoverable
branch, commit, pull request, or checkpoint instead of rebuilding it.

Do not rescan the whole repository unless targeted inspection cannot establish
the required state. When a full rescan is necessary, document the reason and
the evidence it is intended to find.

## Data boundary

Secrets and private operational values must not appear in code, prompts, logs,
commits, or pull request text. Use documented placeholders or approved secret
stores, and redact sensitive evidence before it becomes durable repository
history.

## Authorization boundary

Without explicit, task-specific authorization, do not change:

- Gmail or external messaging;
- Beds24 or other booking data;
- monitoring or scheduled tasks;
- deployments or runtime configuration;
- access, permissions, or credentials;
- payments or financial operations;
- legal or tax data.

Authorization for one protected action does not authorize adjacent actions.
Keep the implementation inside the stated scope and preserve fail-closed
behavior at the boundary.

## Completion

Stop after the requested artifact is produced and validated. Do not deploy,
merge, message external parties, or begin another task unless the execution
contract explicitly authorizes that action.

Completed work must reduce the context required by the next task. End with the
compact checkpoint defined in
[`CHECKPOINT_PROTOCOL.md`](CHECKPOINT_PROTOCOL.md), including reusable evidence,
test results, and the exact recovery point.
