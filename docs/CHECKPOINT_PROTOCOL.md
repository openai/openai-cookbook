# Checkpoint Protocol

A checkpoint is the durable handoff for one execution. It must be compact,
non-sensitive, and sufficient to resume without repeating completed work.

## Required checkpoint

Record these fields:

| Field | Required content |
| --- | --- |
| Objective | The one narrowly scoped objective |
| Status | `not started`, `in progress`, `blocked`, or `complete` |
| Scope | Allowed paths/actions and explicit exclusions |
| Evidence | Targeted files, commits, pull requests, or external facts already verified |
| Changes | Changed paths and a concise description |
| Tests | Exact commands and results |
| Stop condition | Whether the requested artifact or exact external blocker was reached |
| Recovery point | Branch, commit, pull request, or clean base plus the next safe action |

Never include secrets or private operational values. Redact sensitive evidence
and reference its approved source instead.

## Start

1. Read the latest checkpoint and the task request.
2. Inspect only the targeted paths and repository objects needed to verify it.
3. Reuse any recoverable branch, commit, pull request, or checkpoint.
4. Define scope, evidence, tests, stop condition, and recovery point.
5. If a whole-repository rescan is necessary, document the reason before it
   runs.

## Update

Update the checkpoint when the recovery point changes, a test establishes new
evidence, or an exact blocker is found. Prefer verified identifiers and concise
results over copied logs.

One execution still has one objective, and one task still has one pull request.
Do not use a checkpoint to smuggle a second task into the current execution.

## Stop and hand off

Stop immediately when the stop condition is met. The final checkpoint must:

- identify the produced artifact or exact blocker;
- preserve the reusable recovery point;
- distinguish verified facts from pending work;
- state the focused tests and their results;
- omit unrelated inventory and raw log dumps;
- reduce the context the next task must reconstruct.

Do not begin another task after writing the checkpoint.
