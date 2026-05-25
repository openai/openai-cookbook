import asyncio
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from agents import Agent, Runner
from agents.mcp import MCPServerStdio, create_static_tool_filter
from agents.model_settings import ModelSettings


BILIG_PACKAGE = "@bilig/workpaper@0.94.0"
SUMMARY_RANGE = "Summary!A1:B5"
INPUT_SHEET = "Inputs"
INPUT_CELL = "B3"
NEW_WIN_RATE = 0.4
DEFAULT_OPENAI_MODEL = "gpt-5.4"

ALLOWED_TOOLS = [
    "list_sheets",
    "read_range",
    "read_cell",
    "set_cell_contents",
    "get_cell_display_value",
    "export_workpaper_document",
    "validate_formula",
]


def build_bilig_server(workpaper_path: Path) -> MCPServerStdio:
    """Launch the Bilig WorkPaper MCP server over stdio."""

    return MCPServerStdio(
        name="Bilig WorkPaper",
        params={
            "command": "npm",
            "args": [
                "exec",
                "--yes",
                "--package",
                BILIG_PACKAGE,
                "--",
                "bilig-workpaper-mcp",
                "--workpaper",
                str(workpaper_path),
                "--init-demo-workpaper",
                "--writable",
            ],
        },
        cache_tools_list=True,
        client_session_timeout_seconds=20,
        tool_filter=create_static_tool_filter(allowed_tool_names=ALLOWED_TOOLS),
    )


def structured(result: Any) -> dict[str, Any]:
    if getattr(result, "structuredContent", None):
        return result.structuredContent

    text = result.content[0].text
    return json.loads(text)


def cell_value(cell: Any) -> Any:
    if isinstance(cell, dict) and "value" in cell:
        return cell["value"]
    return cell


def summary_value(summary: dict[str, Any], label: str) -> Any:
    for row in summary["values"][1:]:
        row_label = cell_value(row[0])
        if row_label == label:
            return cell_value(row[1])

    raise ValueError(f"Could not find {label!r} in {SUMMARY_RANGE}")


async def run_mcp_smoke(workpaper_path: Path) -> dict[str, Any]:
    async with build_bilig_server(workpaper_path) as server:
        tools = await server.list_tools()
        tool_names = [tool.name for tool in tools]

        missing = sorted(set(ALLOWED_TOOLS) - set(tool_names))
        if missing:
            raise RuntimeError(f"Missing expected Bilig MCP tools: {missing}")

        before = structured(
            await server.call_tool("read_range", {"range": SUMMARY_RANGE})
        )
        edit = structured(
            await server.call_tool(
                "set_cell_contents",
                {
                    "sheetName": INPUT_SHEET,
                    "address": INPUT_CELL,
                    "value": NEW_WIN_RATE,
                },
            )
        )
        after = structured(
            await server.call_tool("read_range", {"range": SUMMARY_RANGE})
        )
        exported = structured(
            await server.call_tool("export_workpaper_document", {"includeConfig": True})
        )

        return {
            "tools": tool_names,
            "edited_cell": edit["editedCell"],
            "expected_arr_before": summary_value(before, "Expected ARR"),
            "expected_arr_after": summary_value(after, "Expected ARR"),
            "target_gap_after": summary_value(after, "Target gap"),
            "persisted": edit["checks"]["persisted"],
            "restored_matches_after": edit["checks"]["restoredMatchesAfter"],
            "exported_bytes": exported["serializedBytes"],
            "workpaper_path": str(workpaper_path),
        }


async def run_agent(workpaper_path: Path) -> str:
    async with build_bilig_server(workpaper_path) as server:
        agent = Agent(
            name="Formula WorkPaper agent",
            instructions=(
                "You update formula-backed WorkPapers through MCP tools. "
                "First inspect the workbook, then set Inputs!B3 to 0.4, "
                "read Summary!A1:B5, export the document, and report the "
                "Expected ARR plus whether persistence was verified."
            ),
            mcp_servers=[server],
            model=os.environ.get("OPENAI_MODEL", DEFAULT_OPENAI_MODEL),
            model_settings=ModelSettings(tool_choice="required"),
        )

        result = await Runner.run(
            agent,
            "Update the win rate in the quote workbook and verify the recalculated outputs.",
        )
        return str(result.final_output)


async def main() -> None:
    configured_path = os.environ.get("BILIG_WORKPAPER_PATH")

    with tempfile.TemporaryDirectory() as tmpdir:
        workpaper_path = (
            Path(configured_path)
            if configured_path
            else Path(tmpdir) / "quote.workpaper.json"
        )
        workpaper_path.parent.mkdir(parents=True, exist_ok=True)

        smoke = await run_mcp_smoke(workpaper_path)
        print("Deterministic MCP smoke:")
        print(json.dumps(smoke, indent=2))

        if os.environ.get("RUN_OPENAI_AGENT") != "1":
            print(
                "\nSet RUN_OPENAI_AGENT=1 and OPENAI_API_KEY to run the optional agent turn."
            )
            return

        if not os.environ.get("OPENAI_API_KEY"):
            print("\nOPENAI_API_KEY is not set; skipping the optional agent run.")
            return

        print("\nAgent run:")
        print(await run_agent(workpaper_path))


if __name__ == "__main__":
    asyncio.run(main())
