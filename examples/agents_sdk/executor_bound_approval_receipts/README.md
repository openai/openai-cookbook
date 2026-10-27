# Add accountable receipts to Agents SDK approvals

The OpenAI Agents SDK already [pauses a `needs_approval` tool](https://openai.github.io/openai-agents-python/human_in_the_loop/) before it executes and binds the decision to a specific tool call in `RunState`. This example adds an application-owned receipt for teams that also need to answer:

- What exact action did the reviewer approve?
- Who approved it, and when did the approval expire?
- Was the approval consumed more than once?
- What record can the executor retain after the run resumes?

The pattern joins the SDK's native approval interruption with a [tool input guardrail](https://openai.github.io/openai-agents-python/guardrails/#tool-guardrails):

```text
tool call → SDK interruption → reviewer decision → authenticated receipt
          → RunState approval → tool input guardrail consumes receipt → effect
```

The tool guardrail runs after approval and immediately before the function tool executes. It recomputes the digest from `tool_name`, `tool_call_id`, and the canonical JSON arguments. Missing, expired, changed, replayed, or tampered receipts fail closed.

## Run the example

Set the API key and receipt-authentication secret, then run the app:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r examples/agents_sdk/executor_bound_approval_receipts/requirements.txt
export OPENAI_API_KEY="..."
export APPROVAL_RECEIPT_SECRET="replace-with-at-least-32-random-bytes"
python examples/agents_sdk/executor_bound_approval_receipts/app.py
```

The sample uses an in-memory ledger and an HMAC key controlled by the application. That proves which application issued the receipt; it does not by itself prove that a named person used a hardware-held key. In production, use a transactional store, authenticate the reviewer, protect the signing key, and define reconciliation for a provider result that becomes indeterminate after receipt consumption.

Run the offline negative tests without an API call:

```bash
pytest -q examples/agents_sdk/executor_bound_approval_receipts/test_receipt_ledger.py
```

The tests cover changed arguments, wrong call IDs, expiry, replay, and receipt tampering.

## Why keep the receipt outside the model

The model may propose an action and explain it, but it should not mint or consume its own authorization. The application owns reviewer identity, receipt policy, the signing key, and the final execution boundary. This keeps approval enforcement separate from prompt compliance.

This example adapts the executor-bound approval pattern and adversarial cases developed by [EMILIA Protocol](https://github.com/emiliaprotocol/emilia-protocol/pull/451) to the Agents SDK's native `needs_approval`, `RunState`, `ToolContext`, and tool-guardrail surfaces.
