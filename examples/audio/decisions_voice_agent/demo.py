"""Run the offline fixture through the public evaluator's handoff contract."""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

# Resolve only this script's trusted sibling modules, including on Python hosts
# that omit the script directory from sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from agent import ExampleBackend, ScriptedRouter, SupportAgent  # noqa: E402
from mcp_tools import LocalMCPTools  # noqa: E402


async def main() -> None:
    backend = ExampleBackend(SupportAgent(ScriptedRouter(), LocalMCPTools()))

    async def emit(event: dict) -> None:
        print(json.dumps(event))

    print("Offline scripted routing fixture + local MCP; no model or audio session.")
    try:
        # The adapter accepts the real DelegationHandoff. A namespace lets this
        # standalone demo run without importing the evaluator's audio dependencies.
        handoff = SimpleNamespace(
            task="Resolve the current user request from the voice conversation.",
            transcript_srt="1\n00:00:00,000 --> 00:00:01,000\nUSER: Where is my order?",
            follow_up=False,
        )
        print(await backend.run(handoff, emit))
    finally:
        await backend.close()


if __name__ == "__main__":
    asyncio.run(main())
