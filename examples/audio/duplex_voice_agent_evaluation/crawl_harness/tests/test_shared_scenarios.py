"""Regression coverage for the JSON scenario contract shared by all harnesses."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crawl_harness.evaluate import load_dataset as load_crawl_dataset
from run_harness.evaluate import load_run_scenarios
from shared.scenarios import Scenario, ScenarioDataset, load_scenario_dataset
from walk_harness.evaluate import load_dataset as load_walk_dataset

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("module", "interaction", "count"),
    [("crawl_harness", "single_turn", 21), ("walk_harness", "single_turn", 26), ("run_harness", "multi_turn", 11)],
)
def test_each_module_uses_the_same_versioned_scenario_contract(module: str, interaction: str, count: int) -> None:
    dataset = load_scenario_dataset(PROJECT_ROOT / module / "data/scenarios.json")

    assert dataset.schema_version == "1.0"
    assert len(dataset.scenarios) == count
    assert all(scenario.interaction == interaction for scenario in dataset.scenarios)


@pytest.mark.parametrize(
    "condition",
    ["clean", "noisy", "telephony", "background_speech", "echo", "packet_loss", "realistic"],
)
def test_recordings_accept_all_supported_audio_realism_conditions(condition: str) -> None:
    original = load_scenario_dataset(PROJECT_ROOT / "walk_harness/data/scenarios.json").scenarios[0]
    scenario_data = original.model_dump(mode="json")
    scenario_data["input"]["recordings"][0]["condition"] = condition

    scenario = Scenario.model_validate(scenario_data)

    assert scenario.input.recordings[0].condition == condition


def test_every_bundled_dataset_uses_the_same_explicit_task_identity_and_top_level_shape() -> None:
    allowed_types = {"booking", "availability", "cancellation", "clarification", "information", "refusal"}
    core_fields = {"id", "title", "type", "interaction", "tags", "input", "application", "expected"}

    for module in ("crawl_harness", "walk_harness", "run_harness"):
        payload = json.loads((PROJECT_ROOT / module / "data/scenarios.json").read_text(encoding="utf-8"))
        assert set(payload) == {"schema_version", "scenarios"}
        for scenario in payload["scenarios"]:
            assert core_fields <= set(scenario)
            assert scenario["type"] in allowed_types
            assert "diagnostic_terms" not in scenario["expected"]
            if module == "run_harness":
                assert scenario["interaction"] == "multi_turn"
                assert "simulation_parameters" in scenario
                assert "procedure" in scenario["expected"]
            else:
                assert scenario["interaction"] == "single_turn"
                assert "simulation_parameters" not in scenario


def test_recorded_scenarios_match_their_synthetic_definition_except_for_audio() -> None:
    synthetic = {
        scenario.id: scenario.model_dump(mode="json", exclude_none=True)
        for scenario in load_scenario_dataset(PROJECT_ROOT / "crawl_harness/data/scenarios.json").scenarios
    }
    recorded = load_scenario_dataset(PROJECT_ROOT / "walk_harness/data/scenarios.json").scenarios

    for scenario in recorded:
        actual = scenario.model_dump(mode="json", exclude_none=True)
        generation = actual["input"]["recordings"][0].get("metadata", {}).get("generation", {})
        source_id = generation.get("source_scenario_id", scenario.id)
        actual["id"] = source_id
        actual["input"].pop("recordings")
        expected = synthetic[source_id]
        expected["input"].pop("recordings", None)
        assert actual == expected


def test_explicit_scenario_type_is_independent_of_tag_order() -> None:
    original = load_scenario_dataset(PROJECT_ROOT / "run_harness/data/scenarios.json").scenarios[0]
    payload = original.model_dump(mode="json")
    payload["tags"] = ["restaurant", "correction", "booking"]
    payload["type"] = "booking"

    assert Scenario.model_validate(payload).scenario_type == "booking"


def test_one_mixed_catalog_can_be_shared_by_every_module(tmp_path: Path) -> None:
    datasets = [
        load_scenario_dataset(PROJECT_ROOT / module / "data/scenarios.json")
        for module in ("crawl_harness", "walk_harness", "run_harness")
    ]
    synthetic = datasets[0].scenarios[1].model_dump(mode="json")
    recorded = datasets[1].scenarios[0].model_dump(mode="json")
    recording_path = PROJECT_ROOT / "walk_harness/data" / recorded["input"]["recordings"][0]["path"]
    recorded["input"]["recordings"][0]["path"] = str(recording_path.resolve())
    conversational = datasets[2].scenarios[0].model_dump(mode="json")
    catalog_path = tmp_path / "scenarios.json"
    catalog_path.write_text(
        json.dumps({"schema_version": "1.0", "scenarios": [synthetic, recorded, conversational]}),
        encoding="utf-8",
    )

    assert [scenario.id for scenario in load_crawl_dataset(catalog_path)] == [synthetic["id"], recorded["id"]]
    assert [scenario.id for scenario in load_walk_dataset(catalog_path)] == [recorded["id"]]
    assert [scenario.id for scenario in load_run_scenarios(catalog_path)] == [conversational["id"]]


def test_prior_conversation_can_use_structured_history_without_a_summary() -> None:
    original = load_scenario_dataset(PROJECT_ROOT / "crawl_harness/data/scenarios.json").scenarios[0]
    scenario_data = original.model_dump(mode="json")
    scenario_data["input"]["context"] = {
        "history": [
            {"role": "user", "text": "I need a table for two."},
            {"role": "assistant", "text": "Which evening works for you?"},
        ]
    }

    scenario = Scenario.model_validate(scenario_data)

    assert scenario.input.context is not None
    assert [item.role for item in scenario.input.context.history] == ["user", "assistant"]
    assert scenario.context_mode == "history"
    assert scenario.conversation_context == "user: I need a table for two.\nassistant: Which evening works for you?"


def test_forbidden_delegation_cannot_require_a_tool_call() -> None:
    original = load_scenario_dataset(PROJECT_ROOT / "crawl_harness/data/scenarios.json").scenarios[0]
    scenario_data = original.model_dump(mode="json")
    scenario_data["expected"]["delegation"] = "forbidden"

    with pytest.raises(ValueError, match="cannot forbid delegation and require a tool"):
        Scenario.model_validate(scenario_data)


def test_critical_procedure_steps_cannot_be_optional() -> None:
    original = load_scenario_dataset(PROJECT_ROOT / "run_harness/data/scenarios.json").scenarios[0]
    scenario_data = original.model_dump(mode="json")
    scenario_data["expected"]["procedure"]["steps"][0].update({"critical": True, "required": False})

    with pytest.raises(ValueError, match="critical procedure steps must be required"):
        Scenario.model_validate(scenario_data)


def test_single_turn_scenarios_reject_simulated_caller_behavior() -> None:
    original = load_scenario_dataset(PROJECT_ROOT / "crawl_harness/data/scenarios.json").scenarios[0]
    scenario_data = original.model_dump(mode="json")
    scenario_data["simulation_parameters"] = {"goal": "Make a reservation."}

    with pytest.raises(ValueError, match="single-turn scenarios must not define simulation parameters"):
        Scenario.model_validate(scenario_data)


def test_single_turn_scenarios_support_multiple_ordered_application_tools() -> None:
    original = load_scenario_dataset(PROJECT_ROOT / "crawl_harness/data/scenarios.json").scenarios[0]
    scenario_data = original.model_dump(mode="json")
    reservation = scenario_data["expected"]["tools"]["required"][0]
    scenario_data["expected"]["tools"]["required"] = [
        {
            "name": "check_availability",
            "arguments": {"date": "2026-08-07", "time": "19:00", "party_size": 2},
        },
        reservation,
    ]

    scenario = Scenario.model_validate(scenario_data)

    assert [tool.name for tool in scenario.expected.tools.required] == [
        "check_availability",
        "create_reservation",
    ]


def test_multi_turn_scenarios_do_not_accept_prerecorded_conversations() -> None:
    original = load_scenario_dataset(PROJECT_ROOT / "run_harness/data/scenarios.json").scenarios[0]
    scenario_data = original.model_dump(mode="json")
    scenario_data["input"]["recordings"] = [{"id": "recorded", "path": "conversation.wav"}]

    with pytest.raises(ValueError, match="recorded multi-turn interactions require a live human caller"):
        Scenario.model_validate(scenario_data)


def test_dataset_rejects_duplicate_scenario_identifiers() -> None:
    original = load_scenario_dataset(PROJECT_ROOT / "crawl_harness/data/scenarios.json").scenarios[0]

    with pytest.raises(ValueError, match="scenario ids must be unique"):
        ScenarioDataset.model_validate({"schema_version": "1.0", "scenarios": [original, original]})
