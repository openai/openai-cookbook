import asyncio
import json
import os

from dotenv import load_dotenv
from fastmcp import Client
from openai import AsyncOpenAI

load_dotenv()

SYSTEM_PROMPT = (
    "Answer the user's question using the BLS data returned by the available MCP tools. "
    "Call `resolve` to map the requested economic indicator to a BLS series, choose "
    "the best candidate, and then call `fetch_bls_data` to retrieve its observations. "
    "Do not invent a series ID or value. If several candidates tie for the best confidence "
    "and measure different things, name them and ask the user which one they want. "
    "Give a concise final answer."
)


def tool_result_text(result) -> str:
    text = "".join(getattr(block, "text", "") for block in (result.content or []))
    return text or json.dumps(getattr(result, "data", None))


async def run_agent(
    query: str,
    model: str,
    reasoning_effort: str | None,
    mcp_url: str,
    max_steps: int = 4,
) -> dict:
    recorded_calls = []
    conversation = [{"role": "user", "content": query}]

    async with AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"]) as openai, Client(mcp_url) as mcp:
        mcp_tools = await mcp.list_tools()
        tools = [
            {
                "type": "function",
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema,
            }
            for tool in mcp_tools
        ]

        request = {
            "model": model,
            "instructions": SYSTEM_PROMPT,
            "tools": tools,
            "tool_choice": "auto",
            "store": False,
            "include": ["reasoning.encrypted_content"],
        }
        if reasoning_effort:
            request["reasoning"] = {"effort": reasoning_effort}

        for step in range(max_steps + 1):
            response = await openai.responses.create(input=conversation, **request)
            function_calls = [item for item in response.output if item.type == "function_call"]
            if not function_calls:
                return {
                    "answer": response.output_text,
                    "tool_calls": recorded_calls,
                    "completed": True,
                }
            if step == max_steps:
                break

            # The API rejects round-tripped items that still carry null-valued fields.
            conversation += [item.model_dump(exclude_none=True) for item in response.output]
            for call in function_calls:
                arguments = json.loads(call.arguments or "{}")
                result = await mcp.call_tool(call.name, arguments)
                recorded_calls.append({"name": call.name, "arguments": arguments, "result": result.structured_content})
                conversation.append(
                    {
                        "type": "function_call_output",
                        "call_id": call.call_id,
                        "output": tool_result_text(result),
                    }
                )

    return {
        "answer": "",
        "tool_calls": recorded_calls,
        "completed": False,
    }


def call_api(prompt: str, options: dict, context: dict) -> dict:
    config = options["config"]
    result = asyncio.run(
        run_agent(
            query=prompt,
            model=config["model"],
            reasoning_effort=config.get("model_reasoning_effort", ""),
            mcp_url=config["mcp_url"],
        )
    )
    return {"output": json.dumps(result)}
