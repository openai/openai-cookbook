"""
FastAPI wrapper that exposes the agent as a streaming `/chat` endpoint.
"""

import os
import asyncio
import logging
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from agents.exceptions import (
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
)
from agents import Agent, Runner, gen_trace_id, trace
from agents.mcp import MCPServerStreamableHttp, MCPServerStreamableHttpParams
from agents.model_settings import ModelSettings
from databricks_mcp import DatabricksOAuthClientProvider
from databricks.sdk import WorkspaceClient

from supply_chain_guardrails import supply_chain_guardrail

CATALOG = os.getenv("MCP_VECTOR_CATALOG", "main")
SCHEMA = os.getenv("MCP_VECTOR_SCHEMA", "supply_chain_db")
FUNCTIONS_PATH = os.getenv("MCP_FUNCTIONS_PATH", "main/supply_chain_db")
DATABRICKS_PROFILE = os.getenv("DATABRICKS_PROFILE", "DEFAULT")
HTTP_TIMEOUT = 30.0  # seconds

app = FastAPI()

# Allow local dev front‑end
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str


async def build_mcp_servers():
    """Initialise Databricks MCP vector & UC‑function servers."""
    ws = WorkspaceClient(profile=DATABRICKS_PROFILE)
    token = DatabricksOAuthClientProvider(ws).get_token()

    base = ws.config.host
    vector_url = f"{base}/api/2.0/mcp/vector-search/{CATALOG}/{SCHEMA}"
    fn_url = f"{base}/api/2.0/mcp/functions/{FUNCTIONS_PATH}"

    async def _proxy_tool(request_json: dict, url: str):
        import httpx

        headers = {"Authorization": f"Bearer {token}"}
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.post(url, json=request_json, headers=headers)
            resp.raise_for_status()
            return resp.json()

    headers = {"Authorization": f"Bearer {token}"}

    servers = [
        MCPServerStreamableHttp(
            MCPServerStreamableHttpParams(
                url=vector_url,
                headers=headers,
                timeout=HTTP_TIMEOUT,
            ),
            name="vector_search",
            client_session_timeout_seconds=60,
        ),
        MCPServerStreamableHttp(
            MCPServerStreamableHttpParams(
                url=fn_url,
                headers=headers,
                timeout=HTTP_TIMEOUT,
            ),
            name="uc_functions",
            client_session_timeout_seconds=60,
        ),
    ]

    # Ensure servers are initialized before use
    await asyncio.gather(*(s.connect() for s in servers))
    return servers


@app.post("/chat")
async def chat_endpoint(req: ChatRequest):
    try:
        servers = await build_mcp_servers()

        agent = Agent(
            name="Assistant",
            instructions="Use the tools to answer the questions.",
            mcp_servers=servers,
            model_settings=ModelSettings(tool_choice="required"),
            output_guardrails=[supply_chain_guardrail],
        )

        trace_id = gen_trace_id()

        async def agent_stream():
            logging.info(f"[AGENT_STREAM] Input message: {req.message}")
            try:
                with trace(workflow_name="Databricks MCP Example", trace_id=trace_id):
                    result = await Runner.run(starting_agent=agent, input=req.message)
                    logging.info(f"[AGENT_STREAM] Raw agent result: {result}")
                    try:
                        logging.info(
                            f"[AGENT_STREAM] RunResult __dict__: {getattr(result, '__dict__', str(result))}"
                        )
                        raw_responses = getattr(result, "raw_responses", None)
                        logging.info(f"[AGENT_STREAM] RunResult raw_responses: {raw_responses}")
                    except Exception as log_exc:
                        logging.warning(f"[AGENT_STREAM] Could not log RunResult details: {log_exc}")
                    yield result.final_output
            except InputGuardrailTripwireTriggered:
                # Off-topic question denied by guardrail
                yield "Sorry, I can only help with supply-chain questions."
            except OutputGuardrailTripwireTriggered:
                # Out-of-scope answer blocked by guardrail
                yield "Sorry, I can only help with supply-chain questions."
            except Exception:
                logging.exception("[AGENT_STREAM] Exception during agent run")
                yield "[ERROR] Exception during agent run. Check backend logs for details."

        return StreamingResponse(agent_stream(), media_type="text/plain")

    except Exception:
        logging.exception("chat_endpoint failed")
        return StreamingResponse(
            (line.encode() for line in ["Internal server error 🙈"]),
            media_type="text/plain",
            status_code=500,
        )