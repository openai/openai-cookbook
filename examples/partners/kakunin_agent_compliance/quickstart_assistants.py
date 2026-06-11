"""
Example demonstrating cryptographic compliance checking and runtime scope validation
for the OpenAI Assistants API using Kakunin.
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv
from openai import OpenAI
from kakunin import Kakunin
from kakunin.exceptions import ScopeViolationError
from kakunin.integrations.openai_assistants import handle_assistants_requires_action

# Load environment keys
load_dotenv()


def query_market_prices(symbol: str) -> str:
    """Query current prices for a ticker symbol."""
    print(f"[Tool Executed] query_market_prices: {symbol}")
    return f"Price for {symbol}: $150.00"


def execute_market_trade(symbol: str, amount: int) -> str:
    """Execute a market buy order."""
    print(f"[Tool Executed] execute_market_trade: Buying {amount} shares of {symbol}")
    return f"Successfully bought {amount} shares of {symbol}"


async def main() -> None:
    kak_api_key = os.getenv("KAK_API_KEY")
    openai_api_key = os.getenv("OPENAI_API_KEY")

    if not kak_api_key or not openai_api_key:
        print("Error: Please set KAK_API_KEY and OPENAI_API_KEY environment variables.")
        sys.exit(1)

    openai_client = OpenAI(api_key=openai_api_key)

    print("Registering agent in Kakunin...")
    async with Kakunin(api_key=kak_api_key) as kakunin_client:
        agent_record = await kakunin_client.agents.create(
            name="Assistants-Compliance-Trader",
            model="gpt-4o",
            version="1.0.0",
            model_hash="sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        )
        await kakunin_client.agents.certify(agent_record.id)
        
        # Initialize OpenAI Assistant
        assistant = openai_client.beta.assistants.create(
            name="Compliance-Aware Stock Trader",
            instructions="You are a helpful stock trader. Use functions to query prices and buy shares.",
            model="gpt-4o",
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "query_market_prices",
                        "description": "Query current prices for a ticker symbol.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string", "description": "Ticker symbol"}
                            },
                            "required": ["symbol"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "execute_market_trade",
                        "description": "Execute a market buy order.",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "symbol": {"type": "string", "description": "Ticker symbol"},
                                "amount": {"type": "integer", "description": "Amount to buy"}
                            },
                            "required": ["symbol", "amount"]
                        }
                    }
                }
            ]
        )

        thread = openai_client.beta.threads.create()
        
        openai_client.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content="Check price of GOOG, then buy 5 shares."
        )

        run = openai_client.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=assistant.id
        )

        print("\n--- Running Assistants Loop ---")
        while True:
            run = openai_client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            print(f"Run status: {run.status}")

            if run.status == "requires_action":
                tool_outputs = await handle_assistants_requires_action(
                    kakunin=kakunin_client,
                    agent_id=agent_record.id,
                    run=run,
                    tool_scopes_mapping={
                        "query_market_prices": ["market.read"],
                        "execute_market_trade": ["trade.execute"],
                    },
                    tool_funcs={
                        "query_market_prices": query_market_prices,
                        "execute_market_trade": execute_market_trade,
                    },
                    catch_exceptions=True
                )
                openai_client.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread.id,
                    run_id=run.id,
                    tool_outputs=tool_outputs
                )
            elif run.status == "completed":
                messages = openai_client.beta.threads.messages.list(thread_id=thread.id)
                print(f"\nResponse:\n{messages.data[0].content[0].text.value}")
                break
            elif run.status in ["failed", "cancelled"]:
                print(f"Execution failed with status: {run.status}")
                break

            await asyncio.sleep(1)

        # Cleanup
        openai_client.beta.assistants.delete(assistant.id)


if __name__ == "__main__":
    asyncio.run(main())
