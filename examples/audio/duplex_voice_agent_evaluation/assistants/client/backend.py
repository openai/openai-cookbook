"""Provider-agnostic contracts for application-owned GPT Live delegation."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

ApplicationEvent = dict[str, Any]
EventCallback = Callable[[ApplicationEvent], Awaitable[None]]
ToolCallback = Callable[[str, dict[str, Any], str], Awaitable[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class DelegationHandoff:
    """The application-owned task and actual incremental voice transcript."""

    task: str
    transcript_srt: str
    follow_up: bool = False

    def as_prompt(self) -> str:
        context = "since the previous delegation" if self.follow_up else "so far"
        transcript = self.transcript_srt or "(No additional transcript has arrived.)"
        return (
            f"Voice conversation {context}, rendered as timestamped SRT:\n\n{transcript}\n\n"
            f"Delegated-work instructions:\n{self.task}"
        )


@runtime_checkable
class ApplicationBackend(Protocol):
    """Any application-owned model, agent framework, or backend service."""

    async def run(self, handoff: DelegationHandoff, emit: EventCallback) -> str: ...

    async def close(self) -> None: ...
