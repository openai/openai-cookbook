"""Runner: executes a policy's planned calls against the router with a step guard."""
from __future__ import annotations

from dataclasses import dataclass, field

from .tools import ToolCall, ToolRouter


@dataclass
class TaskTrace:
    task_id: str
    planned: list = field(default_factory=list)
    executed: list = field(default_factory=list)  # list[ToolCall]
    truncated: bool = False


def run_task(policy, task: dict, router: ToolRouter, max_steps: int = 8) -> TaskTrace:
    trace = TaskTrace(task_id=task["id"])
    try:
        planned = list(policy(task))
    except Exception as exc:  # noqa: BLE001 - a crashing policy is a failed task
        call = ToolCall(tool="<policy-crash>", args={}, ok=False, output=f"error: {exc}")
        trace.executed.append(call)
        return trace
    trace.planned = planned
    for tool, args in planned[:max_steps]:
        trace.executed.append(router.dispatch(tool, args))
    trace.truncated = len(planned) > max_steps
    return trace


def run_suite(policy, tasks: list[dict], router_factory, max_steps: int = 8) -> list[TaskTrace]:
    return [run_task(policy, t, router_factory(), max_steps) for t in tasks]
