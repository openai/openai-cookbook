"""
CLI assistant that uses Databricks MCP Vector Search and UC Functions via the OpenAI Agents SDK.
"""

import asyncio
import os
import httpx
from typing import Dict, Any
from agents import Agent, Runner, function_tool, gen_trace_id, trace
from agents.exceptions import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
)
from agents.model_settings import ModelSettings
from databricks_mcp import DatabricksOAuthClientProvider
from databricks.sdk import WorkspaceClient
from supply_chain_guardrails import supply_chain_guardrail

CATALOG = os.getenv("MCP_VECTOR_CATALOG", "main")
SCHEMA = os.getenv("MCP_VECTOR_SCHEMA", "supply_chain_db")
FUNCTIONS_PATH = os.getenv("MCP_FUNCTIONS_PATH", "main/supply_chain_db")
DATABRICKS_PROFILE = os.getenv("DATABRICKS_PROFILE", "DEFAULT")
HTTP_TIMEOUT = 30.0  # seconds


async def _databricks_ctx():
    """Return (workspace, PAT token, base_url)."""
    ws = WorkspaceClient(profile=DATABRICKS_PROFILE)
    token = DatabricksOAuthClientProvider(ws).get_token()
    return ws, token, ws.config.host


@function_tool
async def vector_search(query: str) -> Dict[str, Any]:
    """Query Databricks MCP Vector Search index."""
    ws, token, base_url = await _databricks_ctx()
    url = f"{base_url}/api/2.0/mcp/vector-search/{CATALOG}/{SCHEMA}"
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(url, json={"query": query}, headers=headers)
        resp.raise_for_status()
        return resp.json()


@function_tool
async def uc_function(function_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Invoke a Databricks Unity Catalog function with parameters."""
    ws, token, base_url = await _databricks_ctx()
    url = f"{base_url}/api/2.0/mcp/functions/{FUNCTIONS_PATH}"
    headers = {"Authorization": f"Bearer {token}"}
    payload = {"function": function_name, "params": params}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        return resp.json()


async def run_agent():
    agent = Agent(
        name="Assistant",
        instructions="You are a supply-chain assistant for Databricks MCP; you must answer **only** questions that are **strictly** about supply-chain data, logistics, inventory, procurement, demand forecasting, etc; for every answer you must call one of the registered tools; if the user asks anything not related to supply chain, reply **exactly** with 'Sorry, I can only help with supply-chain questions'.",
        tools=[vector_search, uc_function],
        model_settings=ModelSettings(model="gpt-4o", tool_choice="required"),
        output_guardrails=[supply_chain_guardrail],
    )

    print("Databricks MCP assistant ready. Type a question or 'exit' to quit.")

    while True:
        user_input = input("You: ").strip()
        if user_input.lower() in {"exit", "quit"}:
            break

        trace_id = gen_trace_id()
        with trace(workflow_name="Databricks MCP Agent", trace_id=trace_id):
            try:
                result = await Runner.run(starting_agent=agent, input=user_input)
                print("Assistant:", result.final_output)
            except InputGuardrailTripwireTriggered:
                print("Assistant: Sorry, I can only help with supply-chain questions.")
            except OutputGuardrailTripwireTriggered:
                print("Assistant: Sorry, I can only help with supply-chain questions.")


def main():
    asyncio.run(run_agent())


if __name__ == "__main__":
    main()