# topic_guardrail.py
from typing import List

from pydantic import BaseModel

from agents import (  # type: ignore  (SDK imports)
    Agent,
    GuardrailFunctionOutput,
    RunContextWrapper,
    Runner,
    TResponseInputItem,
    input_guardrail,
)

# ---------------------------------------------------------------------------
# 1. Tiny classifier agent → “Is this prompt about AI?”
# ---------------------------------------------------------------------------


class TopicCheckOutput(BaseModel):
    """Structured result returned by the classifier."""

    is_about_ai: bool  # True → prompt is AI-related
    reasoning: str  # short rationale (useful for logs)


topic_guardrail_agent = Agent(
    name="Topic guardrail (AI)",
    instructions=(
        "You are a binary classifier. "
        "Reply with is_about_ai = true **only** when the user's request is mainly "
        "about artificial-intelligence research, applications, tooling, ethics, "
        "policy, or market trends. "
        "Return is_about_ai = false for all other domains (finance, biology, history, etc.)."
    ),
    model="gpt-4.1-mini",  # lightweight, fast
    output_type=TopicCheckOutput,
)

# ---------------------------------------------------------------------------
# 2. Guardrail function (decorated) that wraps the classifier
# ---------------------------------------------------------------------------


@input_guardrail
async def ai_topic_guardrail(
    ctx: RunContextWrapper[None],
    agent: Agent,
    input: str | List[TResponseInputItem],
) -> GuardrailFunctionOutput:
    result = await Runner.run(topic_guardrail_agent, input, context=ctx.context)

    output = GuardrailFunctionOutput(
        output_info=result.final_output,
        tripwire_triggered=not result.final_output.is_about_ai,
    )

    return output


# Optional: tidy public surface
__all__ = ["ai_topic_guardrail", "TopicCheckOutput"]
