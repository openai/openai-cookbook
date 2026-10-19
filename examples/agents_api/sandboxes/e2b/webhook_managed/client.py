# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "openai>=3.13.0",
# ]
# ///

"""Use Agents API without importing a sandbox provider SDK."""

from __future__ import annotations

import argparse
import asyncio
import json

from openai import AsyncOpenAI


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--create-agent", metavar="NAME")
    parser.add_argument("--agent-id")
    parser.add_argument("--session-id")
    parser.add_argument("--delete", action="store_true")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--workspace", default="/workspace")
    parser.add_argument(
        "--input", default="Run a shell command to print hello from the sandbox."
    )
    args = parser.parse_args()

    async with AsyncOpenAI(timeout=600) as client:
        if args.create_agent:
            agent = await client.beta.agents.create(
                model=args.model, name=args.create_agent
            )
            print(json.dumps({"agent_id": agent.id}))
            return
        if args.delete:
            if not args.session_id:
                parser.error(
                    "--delete requires --session-id; stop provider compute separately"
                )
            await client.beta.agents.sessions.delete(args.session_id)
            print(json.dumps({"deleted": args.session_id}))
            return
        if args.session_id:
            session = await client.beta.agents.sessions.retrieve(args.session_id)
        else:
            if not args.agent_id:
                parser.error(
                    "Pass --agent-id from --create-agent, or an existing --session-id"
                )
            session = await client.beta.agents.sessions.create(
                agent_id=args.agent_id,
                environment={
                    "type": "self_hosted",
                    "workspace_directory": args.workspace,
                },
            )
        print(json.dumps({"session_id": session.id}), flush=True)
        completed = False
        async with client.beta.agents.sessions.stream(
            session.id, input=args.input
        ) as events:
            async for event in events:
                if event.type in {
                    "agent.session.turn.failed",
                    "agent.session.turn.cancelled",
                    "agent.session.failed",
                }:
                    raise RuntimeError(f"Agent failed: {event.type}")
                if event.type == "agent.session.turn.output_text.delta":
                    print(event.delta, end="", flush=True)
                if event.type == "agent.session.turn.completed":
                    completed = True
        if not completed:
            raise RuntimeError("Stream ended without a completed turn")
        print()


if __name__ == "__main__":
    asyncio.run(main())
