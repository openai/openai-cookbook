"""
Output guardrail that blocks answers not related to supply-chain topics.
"""
from __future__ import annotations

from pydantic import BaseModel
from agents import Agent, Runner, GuardrailFunctionOutput
from agents import output_guardrail
from agents.run_context import RunContextWrapper

class SupplyChainCheckOutput(BaseModel):
    reasoning: str
    is_supply_chain: bool


guardrail_agent = Agent(
    name="Supply-chain check",
    instructions=(
        "Check if the text is within the domain of supply-chain analytics and operations "
        "Return JSON strictly matching the SupplyChainCheckOutput schema"
    ),
    output_type=SupplyChainCheckOutput,
)


@output_guardrail
async def supply_chain_guardrail(
    ctx: RunContextWrapper, agent: Agent, output
) -> GuardrailFunctionOutput:
    """Output guardrail that blocks non-supply-chain answers"""
    text = output if isinstance(output, str) else getattr(output, "response", str(output))
    result = await Runner.run(guardrail_agent, text, context=ctx.context)
    return GuardrailFunctionOutput(
        output_info=result.final_output,
        tripwire_triggered=not result.final_output.is_supply_chain,
    )
