"""RUN scenarios declare a whole-conversation delegation reference count."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from run_harness.evaluate import DEFAULT_DATA_JSON, _golden
from run_harness.scenarios import load_run_dataset, validate_run_scenario
from shared.metrics.reporting import build_metric_row
from shared.reporting.results import build_result_item
from shared.scenarios import Scenario

EXPECTED_COUNTS = {
    "restaurant_booking_complete": 1,
    "restaurant_booking_missing_name": 1,
    "restaurant_booking_missing_time": 1,
    "restaurant_date_correction": 1,
    "restaurant_party_correction": 1,
    "restaurant_unavailable": 3,
    "restaurant_cancel_authorized": 1,
    "restaurant_cancel_unauthorized": 0,
    "restaurant_multiple_corrections": 1,
    "restaurant_interrupted_alternative": 3,
    "restaurant_cancel_corrected_authorization": 1,
}


def _scenario() -> dict:
    return load_run_dataset(DEFAULT_DATA_JSON).scenarios[0].model_dump(mode="json")


def test_every_bundled_run_scenario_has_an_explicit_delegation_count() -> None:
    raw = json.loads(DEFAULT_DATA_JSON.read_text())
    assert {item["id"]: item["expected"]["golden_path"]["delegations"] for item in raw["scenarios"]} == EXPECTED_COUNTS
    for scenario in load_run_dataset(DEFAULT_DATA_JSON).scenarios:
        assert _golden(scenario)["delegations"] == EXPECTED_COUNTS[scenario.id]


@pytest.mark.parametrize("missing", ["omitted", "null"])
def test_run_rejects_an_implicit_delegation_count(tmp_path: Path, missing: str) -> None:
    payload = _scenario()
    golden = payload["expected"]["golden_path"]
    if missing == "omitted":
        golden.pop("delegations")
    else:
        golden["delegations"] = None
    path = tmp_path / "scenarios.json"
    path.write_text(json.dumps({"schema_version": "1.0", "scenarios": [payload]}))

    with pytest.raises(ValueError, match=r"expected\.golden_path\.delegations"):
        load_run_dataset(path)
    with pytest.raises(ValueError, match=r"expected\.golden_path\.delegations"):
        _golden(Scenario.model_validate(payload))


@pytest.mark.parametrize(
    ("policy", "count", "error"),
    [("required", 0, "positive"), ("forbidden", 1, "zero"), ("optional", -1, "greater than or equal to 0")],
)
def test_run_rejects_counts_inconsistent_with_the_policy(policy: str, count: int, error: str) -> None:
    payload = _scenario()
    payload["expected"]["delegation"] = policy
    payload["expected"]["tools"]["required"] = []
    payload["expected"]["golden_path"]["delegations"] = count
    with pytest.raises(ValueError, match=error):
        validate_run_scenario(Scenario.model_validate(payload))


@pytest.mark.parametrize(("policy", "count"), [("required", 3), ("optional", 0), ("optional", 2), ("forbidden", 0)])
def test_run_accepts_explicit_policy_compatible_counts(policy: str, count: int) -> None:
    payload = _scenario()
    payload["expected"]["delegation"] = policy
    payload["expected"]["tools"]["required"] = []
    payload["expected"]["golden_path"]["delegations"] = count
    scenario = validate_run_scenario(Scenario.model_validate(payload))
    assert _golden(scenario)["delegations"] == count


def test_reference_count_is_reported_without_becoming_an_exact_success_gate(tmp_path: Path) -> None:
    payload = _scenario()
    payload["expected"]["golden_path"]["delegations"] = 3
    scenario = validate_run_scenario(Scenario.model_validate(payload))
    row = build_metric_row(
        task={"task_completed": True, "delegation_required": True},
        efficiency={"delegation_count": 2},
        interaction={},
        golden=_golden(scenario),
    )
    item = build_result_item({"id": scenario.id, **row}, run_dir=tmp_path, scenario_id_key="id")
    assert item["metrics"]["task"]["delegations"] == {"actual": 2, "expected": 3}
    assert item["metrics"]["task"]["delegation_accuracy"] == 1.0
    assert item["metrics"]["task"]["task_completed"] is True


def test_single_turn_scenarios_can_keep_the_implicit_default() -> None:
    scenario = Scenario(
        id="single", title="Single", interaction="single_turn", input={"text": "Hello"}, expected={"answer": "Hello"}
    )
    assert scenario.expected.golden_path.delegations is None
