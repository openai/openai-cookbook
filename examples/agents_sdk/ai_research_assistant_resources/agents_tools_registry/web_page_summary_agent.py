# web_page_summary_agent.py

from agents import Agent, Runner, RunConfig


class WebPageSummaryAgent:
    _DEFAULT_NAME = "Web Page Summary Agent"

    # NOTE: Placeholders will be filled at construction time so that the agent carries
    # all contextual instructions. The task method will then only need the raw content.
    _DEFAULT_INSTRUCTIONS = """You are an AI assistant tasked with summarising provided web page content. 
        "Return a concise summary in {character_limit} characters or less focused on '{search_term}'. "
        "Only output the summary text; do not include any qualifiers or metadata."""

    def __init__(
        self,
        search_term: str,
        character_limit: int = 1000,
        *,
        model: str = "gpt-4.1",
        tools: list | None = None,
        name: str | None = None,
        instructions: str | None = None,
    ) -> None:
        # Format instructions with the dynamic values unless explicitly overridden.
        formatted_instructions = instructions or self._DEFAULT_INSTRUCTIONS.format(
            search_term=search_term, character_limit=character_limit
        )

        self._agent = Agent(
            name=name or self._DEFAULT_NAME,
            instructions=formatted_instructions,
            tools=tools or [],
            model=model,
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def agent(self) -> Agent:  # type: ignore[name-defined]
        """Return the underlying :class:`agents.Agent` instance."""
        
        return self._agent

    async def task(self, content: str) -> str:
        
        cfg = RunConfig(tracing_disabled=True)
        
        result = await Runner.run(self._agent, content, run_config=cfg)
        return result.final_output