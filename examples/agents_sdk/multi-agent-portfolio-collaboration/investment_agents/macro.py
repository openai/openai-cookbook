from agents import Agent, WebSearchTool, ModelSettings
from tools import get_fred_series
from utils import load_prompt, DISCLAIMER

default_model = "gpt-4.1"
default_search_context = "medium"
RECENT_DAYS = 45

def build_macro_agent():
    tool_retry_instructions = load_prompt("tool_retry_prompt.md")
    macro_prompt = load_prompt("macro_base.md", RECENT_DAYS=RECENT_DAYS)
    return Agent(
        name="Macro Analysis Agent",
        instructions=(macro_prompt + DISCLAIMER + tool_retry_instructions),
        tools=[WebSearchTool(search_context_size=default_search_context), get_fred_series],
        model=default_model,
        model_settings=ModelSettings(parallel_tool_calls=True, temperature=0),
    ) 