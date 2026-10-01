"""Resources and application behavior owned by the bundled assistant modules."""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from assistants.runtime import OfflineApplicationBehavior, RemoteToolObserver, ToolExecutor
from shared.paths import package_path

ASSISTANTS_DIR = package_path("assistants")


@dataclass(frozen=True, slots=True)
class AssistantResources:
    """Resolve the selected assistant's editable prompts, tools, and facts."""

    assistant_mode: str
    system_prompt_file: Path
    backend_system_prompt_file: Path
    tools_file: Path
    facts_file: Path

    def load_facts(self) -> dict[str, Any]:
        parsed = json.loads(self.facts_file.read_text(encoding="utf-8"))
        if not isinstance(parsed, dict):
            raise ValueError("Application facts must be a JSON object")
        return parsed

    def create_executor(
        self,
        initial_state: dict[str, Any],
        facts: dict[str, Any],
        *,
        remote: bool = False,
    ) -> ToolExecutor:
        if remote:
            return RemoteToolObserver(initial_state=initial_state, facts=facts)
        if self.assistant_mode == "client":
            from assistants.client.tools.restaurant import RestaurantTools
        else:
            from assistants.responses.tools.restaurant import RestaurantTools
        return RestaurantTools(initial_state=copy.deepcopy(initial_state), facts=copy.deepcopy(facts))

    def create_offline_behavior(
        self,
        *,
        conversation_context: str,
        initial_state: dict[str, Any],
        facts: dict[str, Any],
    ) -> OfflineApplicationBehavior:
        if self.assistant_mode == "client":
            from assistants.client.tools.restaurant import RestaurantOfflineBehavior
        else:
            from assistants.responses.tools.restaurant import RestaurantOfflineBehavior
        return RestaurantOfflineBehavior(
            conversation_context=conversation_context,
            initial_state=copy.deepcopy(initial_state),
            facts=copy.deepcopy(facts),
        )


def assistant_resources(*, assistant_mode: str = "responses") -> AssistantResources:
    """Load resources directly from the chosen assistant implementation."""

    if assistant_mode not in {"responses", "client"}:
        raise ValueError(f"Unknown assistant delegation mode: {assistant_mode}")
    backend = ASSISTANTS_DIR / assistant_mode
    return AssistantResources(
        assistant_mode=assistant_mode,
        system_prompt_file=ASSISTANTS_DIR / "frontend" / "prompts" / "voice.txt",
        backend_system_prompt_file=backend / "prompts" / "backend.txt",
        tools_file=backend / "tools" / "definitions.json",
        facts_file=backend / "tools" / "restaurant_facts.json",
    )
