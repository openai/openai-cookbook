"""Application resources and explicit offline protocol fixtures."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from assistants.examples.verification.application import VerificationTools
from assistants.runtime import OfflineApplicationBehavior
from shared.scenarios import Scenario, load_scenario_dataset

RESOURCE_DIR = Path(__file__).resolve().parent
SCENARIOS_PATH = RESOURCE_DIR / "scenarios.json"

# Invented backend records are independent of the caller text and evaluator labels.
_PRIVATE_FIXTURES = {
    "dob_match": ("1990-09-05", True),
    "dob_mismatch": ("1990-09-05", True),
    "dob_incomplete": ("1990-09-05", True),
    "dob_correction": ("1992-09-01", True),
    "person_requested": ("1990-09-05", True),
    "no_person_request": ("1990-09-05", True),
    "person_request_canceled": ("1990-09-05", True),
    "person_transfer_failure": ("1990-09-05", False),
}

# These scripts exercise protocol plumbing, not language understanding or audio.
_SCRIPTED_CALLS = {
    "My date of birth is September fifth, nineteen ninety.": (
        "verify_date_of_birth",
        {"date_of_birth": "1990-09-05"},
    ),
    "My date of birth is September first, nineteen ninety-two.": (
        "verify_date_of_birth",
        {"date_of_birth": "1992-09-01"},
    ),
    "September fifth, nineteen ninety. Sorry, September first, nineteen ninety-two.": (
        "verify_date_of_birth",
        {"date_of_birth": "1992-09-01"},
    ),
    "Please transfer me to a person.": (
        "transfer_to_human",
        {"reason": "Caller requested a human."},
    ),
    "Please connect me to a human.": (
        "transfer_to_human",
        {"reason": "Caller requested a human."},
    ),
}
_SCRIPTED_REPLIES = {
    "September first.": "What year were you born?",
    "I do not want to talk to a person. Please keep helping me here.": (
        "Of course. I will keep helping you here. What do you need?"
    ),
    "Please transfer me to a person. Actually, cancel that. Keep me with the automated assistant.": (
        "Understood. I will keep helping you here and will not transfer you."
    ),
}


class ScriptedVerificationBehavior:
    """Replay a known visible request without consulting scenario expectations."""

    def infer_tool_call(self, user_text: str) -> tuple[str, dict[str, Any]] | None:
        if user_text in _SCRIPTED_CALLS:
            return copy.deepcopy(_SCRIPTED_CALLS[user_text])
        if user_text in _SCRIPTED_REPLIES:
            return None
        raise ValueError("No offline fixture for this caller text")

    def direct_answer(self, user_text: str) -> str:
        if user_text not in _SCRIPTED_REPLIES:
            raise ValueError("No offline direct-answer fixture for this caller text")
        return _SCRIPTED_REPLIES[user_text]

    def final_answer(self, output: dict[str, Any]) -> str:
        if "matched" in output:
            if output["matched"]:
                return "Your date of birth matches the record. You are verified."
            return "That date of birth does not match the record. You are not verified."
        if output.get("result") == "transferred":
            return "The simulated transfer to a human is complete."
        if output.get("result") == "already_transferred":
            return "The simulated transfer to a human was already completed."
        return "The transfer did not complete. I can keep helping you here."


@dataclass(frozen=True, slots=True)
class VerificationResources:
    """Supply public prompts and a private local application to the harness."""

    record: str = field(repr=False)
    transfer_available: bool = True
    assistant_mode: ClassVar[str] = "responses"
    system_prompt_file: ClassVar[Path] = RESOURCE_DIR / "frontend.txt"
    backend_system_prompt_file: ClassVar[Path] = RESOURCE_DIR / "backend.txt"
    tools_file: ClassVar[Path] = RESOURCE_DIR / "tools.json"
    facts_file: ClassVar[None] = None

    def load_facts(self) -> dict[str, Any]:
        return {}

    def create_executor(
        self,
        initial_state: dict[str, Any],
        facts: dict[str, Any],
        *,
        remote: bool = False,
    ) -> VerificationTools:
        if remote:
            raise ValueError("The verification example supports only the local Responses executor")
        return VerificationTools(initial_state, self.record, self.transfer_available)

    def create_offline_behavior(
        self,
        *,
        conversation_context: str,
        initial_state: dict[str, Any],
        facts: dict[str, Any],
    ) -> OfflineApplicationBehavior:
        return ScriptedVerificationBehavior()


def resources_for_scenario(scenario_id: str) -> VerificationResources:
    """Select an explicit synthetic backend fixture, never an expected outcome."""
    try:
        record, transfer_available = _PRIVATE_FIXTURES[scenario_id]
    except KeyError:
        raise ValueError(f"Unknown verification scenario: {scenario_id}") from None
    return VerificationResources(record, transfer_available)


def load_scenarios() -> list[Scenario]:
    """Load the single authoritative scenario and expectation catalog."""
    return load_scenario_dataset(SCENARIOS_PATH).scenarios
