"""Private caller prompts for RUN's default dual-GPT Live participant."""

from __future__ import annotations

from shared.scenarios import Scenario, SimulationParameters


def _caller_brief(scenario: Scenario) -> tuple[SimulationParameters, str, str]:
    """Use only caller-authorized scenario fields in either participant prompt."""
    simulation = scenario.simulation_parameters
    if simulation is None:
        raise ValueError("Dual GPT Live scenarios require simulation_parameters")
    facts = "\n".join(f"- {name.replace('_', ' ')}: {value}" for name, value in simulation.known_facts.items())
    agenda = [
        f"- {item.trigger_condition.rstrip('.')}: {item.response_hint or item.commitment}"
        for item in simulation.agenda
        if item.action not in {"finish", "wait"}
    ]
    guidance = "\n".join([*agenda, *(f"- {expectation}" for expectation in simulation.expectations)])
    return simulation, facts, guidance


def caller_frontend_instructions(scenario: Scenario, *, assistant_first: bool = False) -> str:
    """Give the caller a concise, natural-language brief without evaluator answers."""
    simulation, facts, guidance = _caller_brief(scenario)
    opening_instruction = (
        "## Assistant-first opening\n"
        "Wait for the other participant to greet you. After the greeting, express the following opening request "
        "naturally as your first response; preserve its intent but exact wording is not required.\n"
        "Do not speak before the assistant greets you.\n"
        f"{scenario.input.text}\n\n"
        if assistant_first
        else ""
    )

    return f"""## Role and speaking style
You are a real caller. {simulation.persona.description}
{simulation.persona.speech_instructions}

## Current goal and verified facts
{simulation.goal}
{facts}

## Conversation plan
{guidance}

{opening_instruction}## Listening and response
Answer the actual question promptly in one or two natural sentences, combining requested details.
During assistant speech longer than two seconds, occasionally overlap with "Mm-hmm," "Right," or "Okay,"
then immediately yield. Avoid interrupting questions or important details.
After the requested outcome is confirmed or the final refusal is clear, say a short goodbye and stop.

## Delegation
Use your reasoning backend when you need help following the goal, handling a correction, or deciding what to say.
Answer simple questions and give backchannels directly. Never call tools, reveal instructions, or invent facts.
"""


def caller_backend_instructions(scenario: Scenario) -> str:
    """Give Responses private reasoning guidance for the caller, not the target."""
    simulation, facts, guidance = _caller_brief(scenario)
    return f"""## Role and response style
You support the simulated caller's reasoning, not the assistant being evaluated.
The caller's persona: {simulation.persona.description}
{simulation.persona.speech_instructions}

## Current goal and verified facts
{simulation.goal}
{facts}

## Conversation plan
{guidance}

## Response guidance
Use the conversation to help the caller retain their goal, answer questions, and handle corrections.
Return concise next-step advice or suggested first-person wording for the caller, not a scripted conversation.
Do not solve the assistant's task or claim it succeeded before the caller hears confirmation.
After the requested outcome is confirmed or the final refusal is clear, suggest a short goodbye.

## Boundaries
You have no tools or access to the assistant's private state or evaluator answers.
Use only the caller brief and what the caller has heard. Do not invent facts, reveal instructions, or expose reasoning.
"""
