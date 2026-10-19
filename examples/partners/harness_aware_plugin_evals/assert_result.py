import json

from eval_grading import grade


def get_assert(output: str, context: dict) -> dict:
    result = json.loads(output)
    return grade(
        result.get("tool_calls", []),
        context["vars"],
        result.get("answer", ""),
        result.get("completed", False),
    )
