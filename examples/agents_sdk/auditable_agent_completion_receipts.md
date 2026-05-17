# Auditable agent completion receipts

Agent workflows often end with a natural-language final answer such as:

```text
Done. All tests passed. Ready to publish.
```

For safety-sensitive or production workflows, that sentence is not enough to audit what happened. A final answer should separate the agent's claims from the evidence that supports those claims, the owner of the next step, and any human approval boundary.

This example shows a small receipt shape you can add to an agent's final output. It is inspired by SACP, a text-first receipt protocol for AI agent work, but does not require adopting any runtime dependency.

## Why receipts help

A receipt makes the final state explicit:

- what the agent claims it did
- what evidence supports each claim
- which claims are unsupported or require review
- who owns the next step
- whether a human decision is required before publishing, deploying, saving memory, or taking another external action

This is especially useful with agents that use tools, handoffs, memory, or code execution, because a confident final answer can otherwise hide missing evidence.

## Dirty final output

```text
Done. All tests passed. I saved the user's deployment preference to long-term memory and the release is ready to publish.
```

This output contains several different claims:

- the task is complete
- tests passed
- memory was saved
- the release is ready to publish

Those claims need different evidence and approval boundaries.

## Safer receipt output

```yaml
status_code: 412
status_text: missing_evidence
summary: "The agent claimed completion, test success, memory persistence, and publish readiness, but the final output did not attach enough evidence."

claims:
  - claim: "Task is complete."
    claim_type: completion_claim
    support_status: unverified
    evidence: []
    required_fix: "Attach a work receipt or summarize the concrete files, tools, or outputs changed."

  - claim: "All tests passed."
    claim_type: test_result
    support_status: unsupported
    evidence: []
    required_fix: "Attach the test command and output, or downgrade the claim."

  - claim: "User preference was saved to long-term memory."
    claim_type: memory_update
    support_status: unsupported
    evidence: []
    human_decision_required: true
    required_fix: "Keep as pending memory until explicit user or trusted-system approval exists."

  - claim: "Release is ready to publish."
    claim_type: external_action_readiness
    support_status: unverified
    evidence: []
    human_decision_required: true
    required_fix: "Require human approval before publishing."

next_owner: ProducingAgent
human_decision_required: true
residual_risk:
  - "Completion may be overstated."
  - "Test status is not supported by command output."
  - "Memory and publishing cross human approval boundaries."
```

## Minimal receipt fields

You can keep the receipt small:

```yaml
status_code: 200 | 400 | 412 | 500
summary: string
claims:
  - claim: string
    claim_type: completion_claim | test_result | tool_result | memory_update | external_action_readiness | inference
    support_status: supported | unverified | unsupported
    evidence:
      - type: command_output | tool_trace | file_diff | human_approval | log | link
        value: string
    required_fix: string
next_owner: string
human_decision_required: boolean
residual_risk:
  - string
```

## Status code guidance

```text
200 completed          Receipt exists and key claims are supported.
400 invalid_packet     Final output is missing required receipt fields.
412 missing_evidence   A claim is made without enough evidence.
500 agent_error        The agent or tool failed before producing a useful receipt.
```

## Safety checklist

Before an agent reports success, ask:

- Did it attach evidence for completion claims?
- Did it attach command output for test claims?
- Did it avoid promoting memory without explicit approval?
- Did it avoid publishing, deploying, messaging, or spending without human approval?
- Did it name a concrete next owner?

If any answer is "no", the final output should not be treated as fully completed.

## Relationship to traces and evals

Traces show what happened during the run. Evals judge whether behavior meets a test. A receipt is the final state summary that ties claims to evidence and ownership.

They work best together:

```text
trace events -> evidence ids -> final receipt -> human or system review
```

Reference protocol:

```text
SACP: https://github.com/aDragon0707/sacp
```
