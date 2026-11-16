"""Compatibility launcher; trace smoke uses the same selected route as the MCP adapter."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    repository = Path(__file__).resolve().parents[1]
    entrypoint = repository / "mcp-adapter" / "dist" / "trace-smoke.js"
    if not entrypoint.is_file():
        print(
            "Build the MCP adapter first, from the repository root: "
            "npm --prefix mcp-adapter run build",
            file=sys.stderr,
        )
        return 2
    try:
        return subprocess.run(
            ["node", f"--env-file={repository / '.env'}", str(entrypoint)],
            check=False,
        ).returncode
    except FileNotFoundError:
        print("Node.js 24 or later is required for the trace smoke launcher.", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
