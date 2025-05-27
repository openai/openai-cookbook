from dataclasses import dataclass
from investment_agents.fundamental import build_fundamental_agent
from investment_agents.macro import build_macro_agent
from investment_agents.quant import build_quant_agent
from investment_agents.editor import build_editor_agent, build_memo_edit_tool
from investment_agents.pm import build_head_pm_agent, SpecialistRequestInput
import asyncio

@dataclass
class InvestmentAgentsBundle:
    head_pm: object
    fundamental: object
    macro: object
    quant: object


def build_investment_agents() -> InvestmentAgentsBundle:
    fundamental = build_fundamental_agent()
    macro = build_macro_agent()
    quant = build_quant_agent()
    editor = build_editor_agent()
    memo_edit_tool = build_memo_edit_tool(editor)
    head_pm = build_head_pm_agent(fundamental, macro, quant, memo_edit_tool)
    return InvestmentAgentsBundle(
        head_pm=head_pm,
        fundamental=fundamental,
        macro=macro,
        quant=quant,
    )

