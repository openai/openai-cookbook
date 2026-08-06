# Build an OpenAI agent that edits formula WorkPapers with Bilig MCP

This example shows how to connect an OpenAI Agents SDK agent to a local [Bilig WorkPaper](https://github.com/proompteng/bilig) MCP server. The agent can update input cells, recalculate formulas, read computed outputs, and persist the workbook as JSON without driving Excel, Google Sheets, or browser automation.

The no-key smoke test runs first and calls the MCP tools directly. Set `RUN_OPENAI_AGENT=1` with `OPENAI_API_KEY` when you want the script to run an agent turn through the same MCP server.

## What this proves

- Launch a local stdio MCP server from Python with `MCPServerStdio`.
- Expose only the WorkPaper tools needed for a quote/pricing workflow.
- Edit `Inputs!B3`, recalculate dependent `Summary` formulas, and read the new outputs.
- Persist the WorkPaper JSON and verify the restored state matches the calculated output.
- Keep the OpenAI API call optional so reviewers can validate the core MCP flow locally.

## Prerequisites

- Python 3.10+
- Node.js 22+
- npm

## Run it

```bash
cd examples/mcp/bilig_workpaper_mcp_agent
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

Optional agent run:

```bash
export OPENAI_API_KEY=...
export OPENAI_MODEL=gpt-5.4
export RUN_OPENAI_AGENT=1
python main.py
```

By default, the script creates a temporary WorkPaper file. To inspect the persisted JSON afterward, set a path:

```bash
BILIG_WORKPAPER_PATH=./quote.workpaper.json python main.py
```

## Expected smoke output

The deterministic section prints the discovered MCP tools and a compact proof similar to:

```json
{
  "edited_cell": "Inputs!B3",
  "expected_arr_before": 60000,
  "expected_arr_after": 96000,
  "persisted": true,
  "restored_matches_after": true
}
```

## Safety notes

This sample starts the MCP server with `--writable` against a local demo file. For production agents, use a per-user file or storage boundary, expose only the tools the agent needs, and add approval for write tools that affect customer, financial, or irreversible state.

## References

- [OpenAI Agents SDK MCP documentation](https://openai.github.io/openai-agents-python/mcp/)
- [Bilig WorkPaper MCP server](https://github.com/proompteng/bilig)
