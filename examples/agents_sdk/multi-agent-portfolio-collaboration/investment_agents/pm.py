from agents import Agent, ModelSettings, function_tool, Runner
from utils import load_prompt, DISCLAIMER
from dataclasses import dataclass
from pydantic import BaseModel
import json
import asyncio


class SpecialistRequestInput(BaseModel):
    section: str  # e.g., 'fundamental', 'macro', 'quant', or 'pm'
    user_question: str
    guidance: str

# Core async functions for each specialist
async def specialist_analysis_func(agent, input: SpecialistRequestInput):
    result = await Runner.run(
        starting_agent=agent,
        input=json.dumps(input.model_dump()),
        max_turns=75,
    )
    return result.final_output

async def run_all_specialists_parallel(
    fundamental, macro, quant,
    fundamental_input: SpecialistRequestInput,
    macro_input: SpecialistRequestInput,
    quant_input: SpecialistRequestInput
):
    results = await asyncio.gather(
        specialist_analysis_func(fundamental, fundamental_input),
        specialist_analysis_func(macro, macro_input),
        specialist_analysis_func(quant, quant_input)
    )
    return {
        "fundamental": results[0],
        "macro": results[1],
        "quant": results[2]
    }

def build_head_pm_agent(fundamental, macro, quant, memo_edit_tool):
    def make_agent_tool(agent, name, description):
        @function_tool(name_override=name, description_override=description)
        async def agent_tool(input: SpecialistRequestInput):
            return await specialist_analysis_func(agent, input)
        return agent_tool
    fundamental_tool = make_agent_tool(fundamental, "fundamental_analysis", "Generate the Fundamental Analysis section.")
    macro_tool = make_agent_tool(macro, "macro_analysis", "Generate the Macro Environment section.")
    quant_tool = make_agent_tool(quant, "quantitative_analysis", "Generate the Quantitative Analysis section.")

    @function_tool(name_override="run_all_specialists_parallel", description_override="Run all three specialist analyses (fundamental, macro, quant) in parallel and return their results as a dict.")
    async def run_all_specialists_tool(fundamental_input: SpecialistRequestInput, macro_input: SpecialistRequestInput, quant_input: SpecialistRequestInput):
        return await run_all_specialists_parallel(
            fundamental, macro, quant,
            fundamental_input, macro_input, quant_input
        )

    return Agent(
        name="Head Portfolio Manager Agent",
        instructions=(
            load_prompt("pm_base.md") + DISCLAIMER
        ),
        model="gpt-4.1",
        #Reasoning model
        #model="o4-mini",
        tools=[fundamental_tool, macro_tool, quant_tool, memo_edit_tool, run_all_specialists_tool],
        # Settings for a reasoning model
        #model_settings=ModelSettings(parallel_tool_calls=True, reasoning={"summary": "auto", "effort": "high"}, tool_choice="auto")
        model_settings=ModelSettings(parallel_tool_calls=True, tool_choice="auto", temperature=0)
    ) 