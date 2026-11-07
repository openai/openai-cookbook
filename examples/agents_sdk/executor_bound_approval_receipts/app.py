"""OpenAI Agents SDK approval flow with an executor-checked receipt."""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from typing import Any

from agents import Agent, Runner, ToolGuardrailFunctionOutput
from agents.decorators import tool, tool_input_guardrail
from agents.tool_context import ToolContext
from receipt_ledger import ReceiptError, ReceiptLedger


@dataclass
class AppContext:
    ledger: ReceiptLedger
    executed_transfers: list[dict[str, Any]] = field(default_factory=list)


@tool_input_guardrail
def require_exact_approval(data) -> ToolGuardrailFunctionOutput:
    context: ToolContext[AppContext] = data.context
    try:
        receipt = context.context.ledger.consume(
            tool_name=context.tool_name,
            tool_call_id=context.tool_call_id,
            raw_arguments=context.tool_arguments,
        )
    except ReceiptError as exc:
        return ToolGuardrailFunctionOutput.raise_exception(str(exc))
    return ToolGuardrailFunctionOutput.allow(
        {"approval_receipt_id": receipt.receipt_id}
    )


@tool(needs_approval=True, tool_input_guardrails=[require_exact_approval])
def transfer_funds(
    context: ToolContext[AppContext], amount_usd: int, destination: str
) -> dict[str, Any]:
    """Transfer funds to a destination account after exact approval."""
    transfer = {"amount_usd": amount_usd, "destination": destination}
    context.context.executed_transfers.append(transfer)
    return {"status": "submitted", **transfer}


def _call_id(interruption) -> str:
    raw_item = interruption.raw_item
    if isinstance(raw_item, dict):
        return str(raw_item["call_id"])
    return str(raw_item.call_id)


async def main() -> None:
    secret = os.environ["APPROVAL_RECEIPT_SECRET"].encode()
    app_context = AppContext(ledger=ReceiptLedger(secret))
    agent = Agent[AppContext](
        name="Treasury assistant",
        instructions="Propose the requested transfer and wait for application approval.",
        tools=[transfer_funds],
    )

    result = await Runner.run(
        agent,
        "Transfer $8,200 to vendor account acct_2471.",
        context=app_context,
    )
    state = result.to_state()

    for interruption in result.interruptions:
        # Replace this local decision with your authenticated reviewer workflow.
        app_context.ledger.issue(
            tool_name=interruption.name or "unknown_tool",
            tool_call_id=_call_id(interruption),
            raw_arguments=interruption.arguments or "{}",
            reviewer="finance-operator@example.com",
        )
        state.approve(interruption)

    resumed = await Runner.run(agent, state)
    print(resumed.final_output)
    print(app_context.executed_transfers)


if __name__ == "__main__":
    asyncio.run(main())
