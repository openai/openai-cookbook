import datetime
import json
import os
from pathlib import Path
from contextlib import AsyncExitStack

from agents import Runner, add_trace_processor, trace
from agents.tracing.processors import BatchTraceProcessor
from utils import FileSpanExporter, output_file

from investment_agents.config import build_investment_agents

# Register exporter alongside the default backend exporter.
add_trace_processor(BatchTraceProcessor(FileSpanExporter()))

import asyncio

async def main():
    if "OPENAI_API_KEY" not in os.environ:
        raise EnvironmentError(
            "OPENAI_API_KEY not set — use %env or os.environ to set it first."
        )

    # --- customise the question (enter a Ticker for the most accurate stock data) if desired ---
    today_str = datetime.date.today().strftime("%B %d, %Y")
    question = (
        f"Today is {today_str}."
        "How would the planned interest rate reduction effect my holdings in GOOGL if they were to happen?"
        "Considering all the factors effecting it's price right now (Macro, Technical, Fundamental, etc.), what is the likelihood of a 7% return by the end of the year?"
        "Give me all the potential scenarios and the likelihood of each one happening. Account for major events like Covid, 2025 Tariffs etc."
        )
    # Build agents
    bundle = build_investment_agents()

    # Use AsyncExitStack to manage MCP server connections and cleanup
    async with AsyncExitStack() as stack:
        for agent in [getattr(bundle, "fundamental", None), getattr(bundle, "quant", None)]:
            if agent is None:
                continue
            for server in getattr(agent, "mcp_servers", []):
                await server.connect()
                await stack.enter_async_context(server)

        print("Running multi-agent workflow with tracing enabled...\n")
        # Wrap the run in a Trace and print the link immediately
        with trace(
            "Investment Research Workflow",
            metadata={"question": question[:512]}
        ) as workflow_trace:
            # Show the trace URL right away
            print(
                f"\n🔗 View the trace in the OpenAI console: "
                f"https://platform.openai.com/traces/trace?trace_id={workflow_trace.trace_id}\n"
            )

            # Run the workflow 
            response = None
            try:
                response = await asyncio.wait_for(
                    Runner.run(bundle.head_pm, question, max_turns=40),
                    timeout=1200  # 20 minutes in seconds
                )
            except asyncio.TimeoutError:
                print("\n❌ Workflow timed out after 20 minutes.")

            # Print completion message with report path
            report_path = None
            try:
                # The memo editor returns a JSON string with a 'file' key
                if hasattr(response, 'final_output'):
                    output = response.final_output
                    if isinstance(output, str):
                        data = json.loads(output)
                        if isinstance(data, dict) and 'file' in data:
                            report_path = output_file(data['file'])
            except Exception as e:
                print(f"Could not parse investment report path: {e}")

            print(f"Workflow Completed Response from Agent: {response.final_output if hasattr(response, 'final_output') else response}, investment report created: {report_path if report_path else '[unknown]'}")

if __name__ == "__main__":
    asyncio.run(main())
