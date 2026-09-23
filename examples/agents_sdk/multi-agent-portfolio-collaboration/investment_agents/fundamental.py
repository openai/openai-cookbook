from agents import Agent, WebSearchTool, ModelSettings
from utils import load_prompt, DISCLAIMER, repo_path
from pathlib import Path

default_model = "gpt-4.1"
default_search_context = "medium"
RECENT_DAYS = 15

def build_fundamental_agent():
    tool_retry_instructions = load_prompt("tool_retry_prompt.md")
    fundamental_prompt = load_prompt("fundamental_base.md", RECENT_DAYS=RECENT_DAYS)
    # Set up the Yahoo Finance MCP server
    from agents.mcp import MCPServerStdio
    server_path = str(repo_path("mcp/yahoo_finance_server.py"))
    yahoo_mcp_server = MCPServerStdio(
        params={"command": "python", "args": [server_path]},
        client_session_timeout_seconds=300,
        cache_tools_list=True,
    )
    
    return Agent(
        name="Fundamental Analysis Agent",
        instructions=(fundamental_prompt + DISCLAIMER + tool_retry_instructions),
        mcp_servers=[yahoo_mcp_server],
        tools=[WebSearchTool(search_context_size=default_search_context)],
        model=default_model,
        model_settings=ModelSettings(parallel_tool_calls=True, temperature=0),
    ) 