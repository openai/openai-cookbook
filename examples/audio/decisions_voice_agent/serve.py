"""Serve /ws/assistant locally; provider routing requires explicit --router luna.

Install with ``uv sync --extra live``. Set OPENAI_CLIENT_ASSISTANT_TOKEN to a
separate random secret of at least 32 characters. Luna also needs OPENAI_API_KEY.
The default scripted router and all imports make no provider calls. A caller
must connect the service to a separately configured GPT-Live frontend.
Pass --mcp for a real local stdio MCP lookup; otherwise the service calls the
same synthetic fixture functions directly, without MCP transport.
"""

import argparse
import os
import sys
from pathlib import Path

# Use only this entry point's trusted sibling modules on safe-path Python hosts.
sys.path.insert(0, str(Path(__file__).resolve().parent))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--router", choices=("scripted", "luna"), default="scripted")
    parser.add_argument("--mcp", action="store_true", help="Use real local stdio MCP lookups")
    parser.add_argument("--port", type=int, default=8795)
    args = parser.parse_args(argv)
    if not 0 <= args.port <= 65535:
        parser.error("--port must be in [0, 65535]; 0 chooses an available local port")
    return args


def create_local_app(router: str = "scripted", *, mcp: bool = False):
    """Build the app without creating a provider client or sending a request."""
    from assistants.client.security import service_token

    from agent import ScriptedRouter
    from voice_service import create_support_app

    token = service_token()  # Require the shared, dedicated token environment variable.
    executor_factory = None
    if mcp:
        from mcp_tools import MCPExecutor

        executor_factory = MCPExecutor
    if router == "scripted":
        return create_support_app(ScriptedRouter, token=token, executor_factory=executor_factory)
    if router != "luna":
        raise ValueError("Router must be scripted or luna")
    if not os.environ.get("OPENAI_API_KEY", "").strip():
        raise ValueError("OPENAI_API_KEY is required for --router luna")

    def luna_factory():
        # One owned SDK client per accepted connection, created only when the
        # service configures its backend. Keep SDK environment/proxy defaults.
        from openai import AsyncOpenAI

        from luna_router import LunaRouter

        class OwnedLunaRouter(LunaRouter):
            def __init__(self):
                self.owned_client = AsyncOpenAI(max_retries=0, timeout=5)
                super().__init__(self.owned_client, complete_history=True)

            async def close(self):
                await self.owned_client.close()

        return OwnedLunaRouter()

    return create_support_app(luna_factory, token=token, executor_factory=executor_factory)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    try:
        from aiohttp import web

        app = create_local_app(args.router, mcp=args.mcp)
    except ModuleNotFoundError as error:
        raise SystemExit("Install service dependencies with: uv sync --extra live") from error
    except ValueError as error:
        raise SystemExit(str(error)) from error
    # No host argument: this single-user sample always binds to loopback.
    web.run_app(app, host="127.0.0.1", port=args.port, access_log=None)


if __name__ == "__main__":
    main()
