"""
Example demonstrating cryptographic compliance checking and runtime scope validation
for OpenAI Swarm multi-agent systems using Kakunin.
"""

from __future__ import annotations

import asyncio
import os
import sys

from dotenv import load_dotenv
from swarm import Agent
from kakunin import Kakunin
from kakunin.exceptions import ScopeViolationError
from kakunin.integrations.openai_swarm import KakuninSwarm

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

    print("Registering agent in Kakunin...")
    async with Kakunin(api_key=kak_api_key) as kakunin_client:
        agent_record = await kakunin_client.agents.create(
            name="Swarm-Compliance-Trader",
            model="gpt-4o",
            version="1.0.0",
            model_hash="sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            metadata={"scopes": ["market.read", "trade.execute"]},
        )
        await kakunin_client.agents.certify(agent_record.id)
        
        # Instantiate KakuninSwarm
        swarm = KakuninSwarm(kakunin=kakunin_client, agent_id=agent_record.id)

        agent = Agent(
            name="Compliance Trader",
            instructions="You are an automated stock trader with access to market tools.",
            functions=[query_market_prices, execute_market_trade],
        )

        tool_scopes_mapping = {
            "query_market_prices": ["market.read"],
            "execute_market_trade": ["trade.execute"],
        }

        print("\n--- Running Swarm Agent (Safe Query) ---")
        try:
            res = swarm.run(
                agent=agent,
                messages=[{"role": "user", "content": "What is the price of AAPL?"}],
                tool_scopes_mapping=tool_scopes_mapping,
            )
            print(f"Response: {res.messages[-1]['content']}")
        except ScopeViolationError as e:
            print(f"Blocked by Kakunin: {e}")

        print("\n--- Running Swarm Agent (Execution Query) ---")
        try:
            res = swarm.run(
                agent=agent,
                messages=[{"role": "user", "content": "Buy 5 shares of AAPL"}],
                tool_scopes_mapping=tool_scopes_mapping,
            )
            print(f"Response: {res.messages[-1]['content']}")
        except ScopeViolationError as e:
            print(f"Blocked by Kakunin: {e}")


if __name__ == "__main__":
    asyncio.run(main())
