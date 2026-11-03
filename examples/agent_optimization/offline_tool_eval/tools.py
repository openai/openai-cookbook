"""Deterministic fake tool router for offline agent evaluation.

Why this exists: evaluating a tool-calling agent against live APIs is slow,
flaky, and expensive. This router gives every registered tool a deterministic,
in-memory implementation so the full harness runs offline with ``pytest`` and
produces identical numbers on every run.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ToolCall:
    tool: str
    args: dict
    output: str = ""
    ok: bool = True


@dataclass
class ToolRouter:
    """Registry + dispatcher. Unknown tools return ok=False (agent error)."""

    _handlers: dict = field(default_factory=dict)
    calls: list = field(default_factory=list)

    def register(self, name, handler):
        self._handlers[name] = handler

    def dispatch(self, tool: str, args: dict) -> ToolCall:
        call = ToolCall(tool=tool, args=args)
        handler = self._handlers.get(tool)
        if handler is None:
            call.ok = False
            call.output = f"error: unknown tool '{tool}'"
        else:
            try:
                call.output = handler(args)
            except Exception as exc:  # noqa: BLE001 - router must never crash the run
                call.ok = False
                call.output = f"error: {exc}"
        self.calls.append(call)
        return call


def default_router() -> ToolRouter:
    """Small fake workspace: file search, file read, calculator, invoice check."""
    files = {
        "invoice_042.json": '{"subtotal": 5340, "shipping": 180, "total": 6420}',
        "notes.txt": "net-30 terms, vendor Acme",
    }
    router = ToolRouter()
    router.register("search_files", lambda a: str([f for f in files if a.get("q", "") in f]))
    router.register(
        "read_file",
        lambda a: files.get(a.get("name", ""), "error: file not found"),
    )
    router.register("calc", lambda a: str(eval(a.get("expr", "0"), {"__builtins__": {}})))
    router.register(
        "check_total",
        lambda a: str(float(a.get("subtotal", 0)) + float(a.get("shipping", 0))),
    )
    return router
