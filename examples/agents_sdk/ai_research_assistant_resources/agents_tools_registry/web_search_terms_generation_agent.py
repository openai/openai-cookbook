from pydantic import BaseModel
from agents import Agent, Runner, RunConfig

_NUM_SEARCH_TERMS = 5

class SearchTerms(BaseModel):
    """Structured output model for search-terms suggestions."""

    Search_Queries: list[str]


class WebSearchTermsGenerationAgent:
    _DEFAULT_NAME = "Search Terms Agent"

    # Template for building default instructions at runtime.
    # NOTE: Double braces are used so that ``str.format`` leaves the JSON braces intact.
    _DEFAULT_INSTRUCTIONS_TEMPLATE = """You are a helpful agent assigned a research task. Your job is to provide the top 
        {num_search_terms} Search Queries relevant to the given topic in this year (2025). The output should be in JSON format.

        Example format provided below:
        <START OF EXAMPLE>
        {{
        "Search_Queries": [
            "Top ranked auto insurance companies US 2025 by market capitalization",
            "Geico rates and comparison with other auto insurance companies",
            "Insurance premiums of top ranked companies in the US in 2025", 
            "Total cost of insuring autos in US 2025", 
            "Top customer service feedback for auto insurance in 2025"
        ]
        }}
        </END OF EXAMPLE>
        """
    

    def __init__(
        self,
        num_search_terms: int = _NUM_SEARCH_TERMS,
        *, 
        model: str = "gpt-4.1",
        tools: list | None = None,
        name: str | None = None,
        instructions: str | None = None,
    ):
        # Store number of search terms for potential future use
        self._num_search_terms = num_search_terms

        # Build default instructions if none were provided.
        final_instructions = (
            instructions
            or self._DEFAULT_INSTRUCTIONS_TEMPLATE.format(
                num_search_terms=num_search_terms
            )
        )

        self._agent = Agent(
            name=name or self._DEFAULT_NAME,
            instructions=final_instructions,
            tools=tools or [],
            model=model,
            output_type=SearchTerms,
        )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------

    @property
    def agent(self) -> Agent:  # type: ignore[name-defined]
        """Return the underlying ``agents.Agent`` instance."""

        return self._agent

    async def task(self, prompt: str) -> SearchTerms:  # type: ignore[name-defined]
        """Execute the agent synchronously and return the structured ``SearchTerms`` output."""
        cfg = RunConfig(tracing_disabled=True)
        result = await Runner.run(self._agent, prompt, run_config=cfg)
        return result.final_output