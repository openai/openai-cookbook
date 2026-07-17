#!/usr/bin/env python3
"""Return concise repository context for a Codex SessionStart hook."""

import json
import sys


def main() -> None:
    event = json.load(sys.stdin)
    current_directory = event.get("cwd", "the current workspace")
    output = {
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": (
                f"Session started in {current_directory}. "
                "Run npm test after changing JavaScript."
            ),
        }
    }
    json.dump(output, sys.stdout)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
