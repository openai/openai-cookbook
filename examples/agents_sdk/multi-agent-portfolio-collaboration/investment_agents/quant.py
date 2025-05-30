from agents import Agent, ModelSettings
from tools import run_code_interpreter, get_fred_series, read_file, list_output_files
from utils import load_prompt, DISCLAIMER, repo_path
from pathlib import Path

default_model = "gpt-4.1"

def build_quant_agent():
    tool_retry_instructions = load_prompt("tool_retry_prompt.md")
    quant_prompt = load_prompt("quant_base.md")
    # Set up the Yahoo Finance MCP server
    from agents.mcp import MCPServerStdio
    server_path = str(repo_path("mcp/yahoo_finance_server.py"))
    yahoo_mcp_server = MCPServerStdio(
        params={"command": "python", "args": [server_path]},
        client_session_timeout_seconds=300,
        cache_tools_list=True,
    )
    
    return Agent(
        name="Quantitative Analysis Agent",
        instructions=(quant_prompt + DISCLAIMER + tool_retry_instructions),
        mcp_servers=[yahoo_mcp_server],
        tools=[run_code_interpreter, get_fred_series, read_file, list_output_files],
        model=default_model,
        model_settings=ModelSettings(parallel_tool_calls=True, temperature=0),
    ) 