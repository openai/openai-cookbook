from agents import Agent, ModelSettings, function_tool, Runner, RunContextWrapper
from tools import write_markdown, read_file, list_output_files
from utils import load_prompt, DISCLAIMER
from pydantic import BaseModel
import json

default_model = "gpt-4.1"

class MemoEditorInput(BaseModel):
    fundamental: str
    macro: str
    quant: str
    pm: str
    files: list[str]

def build_editor_agent():
    tool_retry_instructions = load_prompt("tool_retry_prompt.md")
    editor_prompt = load_prompt("editor_base.md")
    return Agent(
        name="Memo Editor Agent",
        instructions=(editor_prompt + DISCLAIMER + tool_retry_instructions),
        tools=[write_markdown, read_file, list_output_files],
        model=default_model,
        model_settings=ModelSettings(temperature=0),
    )

def build_memo_edit_tool(editor):
    @function_tool(
        name_override="memo_editor",
        description_override="Stitch analysis sections into a Markdown memo and save it. This is the ONLY way to generate and save the final investment report. All memos must be finalized through this tool.",
    )
    async def memo_edit_tool(ctx: RunContextWrapper, input: MemoEditorInput) -> str:
        result = await Runner.run(
            starting_agent=editor,
            input=json.dumps(input.model_dump()),
            context=ctx.context,
            max_turns=40,
        )
        return result.final_output
    return memo_edit_tool 