# query_expansion_agent.py
from agents import Agent, Runner
from pydantic import BaseModel
from typing import Literal
from agents.run import RunConfig
from typing import Optional
from ..guardrails.topic_content_guardrail import ai_topic_guardrail

class QueryExpansion(BaseModel):
    """Structured output model for the query-expansion agent."""

    expanded_query: str
    questions: str
    is_task_clear: Literal["yes", "no"]


class QueryExpansionAgent:
    """A wrapper class that internally creates an `agents.Agent` instance on construction.

    Example
    -------
    >>> query_agent = QueryExpansionAgent()
    >>> prompt = "Draft a research report on the latest trends in AI in the last 5 years."
    >>> expanded_prompt = query_agent.task(prompt)
    >>> print(expanded_prompt)
    """

    _DEFAULT_NAME = "Query Expansion Agent"

    _DEFAULT_INSTRUCTIONS = """You are a helpful agent who receives a raw research prompt from the user.

    1. Determine whether the task is sufficiently clear to proceed (“task clarity”).
    2. If the task is missing timeframe of the research or the industry/domain, ask the user for the missing information.
    3. If the task *is* clear, expand the prompt into a single, well-structured paragraph that makes the research request specific, actionable, and self-contained • Do **not** add any qualifiers or meta-commentary; write only the improved prompt itself.
    4. If the task *is not* clear, generate concise clarifying questions that will make the request actionable.  Prioritize questions about:
    • Domain / industry focus  
    • Timeframe (e.g., current year 2025, last 5 years, last 10 years, or all time)  
    • Any other missing constraints or desired perspectives

    Return your response **exclusively** as a JSON object with these exact fields:

    ```json
    {
    "expanded_query": "",
    "questions": "",
    "is_task_clear": "yes" | "no"
    }
    ```

    When "is_task_clear" is "yes", populate "expanded_query" with the enhanced one-paragraph prompt and leave "questions" empty.

    When "is_task_clear" is "no", populate "questions" with your list of clarifying questions and leave "expanded_query" empty.

    """

    def __init__(self, *, model: str = "o4-mini", tools: list | None = None, name: str | None = None,
                 instructions: str | None = None, input_guardrails: list | None = None):

        # Initialise the underlying `agents.Agent` with a structured `output_type` so it
        # returns a validated `QueryExpansion` instance instead of a raw string.
        self._agent = Agent(
            name=name or self._DEFAULT_NAME,
            instructions=instructions or self._DEFAULT_INSTRUCTIONS,
            tools=tools or [],
            model=model,
            output_type=QueryExpansion,
            input_guardrails=input_guardrails or [ai_topic_guardrail],
        )
        self._last_result = None

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    
    @property
    def agent(self) -> Agent:  # type: ignore[name-defined]
        """Return the underlying ``agents.Agent`` instance."""
        return self._agent

    async def task(self, prompt: str) -> QueryExpansion:
        """Fire-and-forget API that auto-threads each call."""

        cfg = RunConfig(tracing_disabled=True)

        # ── First turn ──────────────────────────────────────────────
        if self._last_result is None:
            self._last_result = await Runner.run(
                self._agent, prompt, run_config=cfg
            )
        # ── Later turns ─────────────────────────────────────────────
        else:
            new_input = (
                self._last_result.to_input_list() +
                [{"role": "user", "content": prompt}]
            )
            self._last_result = await Runner.run(
                self._agent, new_input, run_config=cfg
            )

        return self._last_result.final_output  
