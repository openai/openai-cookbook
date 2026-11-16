import json

from eval_grading import grade


def _raw(context: dict) -> dict | None:
    """Codex run payload, or None when the provider response cannot be read."""
    raw = (context.get("providerResponse") or {}).get("raw", {})
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return None
    return raw if isinstance(raw, dict) else None


def _arguments(item: dict) -> dict:
    arguments = item.get("arguments")
    return arguments if isinstance(arguments, dict) else {}


def get_assert(output: str, context: dict) -> dict:
    raw = _raw(context)
    if raw is None:
        return {"pass": False, "score": 0.0, "reason": "could not read the Codex item trace"}

    mcp_items = [item for item in raw.get("items", []) if item.get("type") == "mcp_tool_call"]
    for item in mcp_items:
        if item.get("error") or item.get("status") == "failed":
            return {
                "pass": False,
                "score": 0.0,
                "reason": f"MCP tool call failed: {item.get('tool')}",
            }

    calls = [
        {
            "name": item.get("tool"),
            "arguments": _arguments(item),
            "result": (item.get("result") or {}).get("structured_content"),
        }
        for item in mcp_items
    ]
    errored = (context.get("providerResponse") or {}).get("error")
    completed = not errored and bool((raw.get("finalResponse") or "").strip())
    return grade(calls, context["vars"], output, completed)
