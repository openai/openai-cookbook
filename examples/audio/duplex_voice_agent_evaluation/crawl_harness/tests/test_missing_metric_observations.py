"""An unobserved count is not an observed zero or a perfect score."""

from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from crawl_harness import evaluate as crawl_evaluate
from run_harness import evaluate as run_evaluate
from shared.metrics.evidence import evidence_scores
from shared.metrics.reporting import build_metric_row
from shared.reporting.results import build_result_item
from walk_harness import evaluate as walk_evaluate

MISSING = object()
GOLDEN = {
    "total_turns": 2,
    "tool_calls": [{"name": "lookup", "count": 1}],
    "delegations": 1,
    "delegation_policy": "required",
}


def row(*, efficiency=None, golden=None, task=None, evidence=None):
    return build_metric_row(
        task={"task_completed": False, **(task or {})},
        efficiency=efficiency or {},
        golden=GOLDEN if golden is None else golden,
        interaction={},
        evidence=evidence,
    )


@pytest.mark.parametrize("missing", [MISSING, None], ids=["absent", "null"])
@pytest.mark.parametrize(
    "field,metric,accuracy",
    [
        ("unique_tool_invocation_count", "tool_calls", "tool_accuracy"),
        ("delegation_count", "delegations", "delegation_accuracy"),
        ("total_turns", "turns", None),
    ],
)
def test_missing_actual_count_is_not_zero_and_has_no_dependent_score(field, metric, accuracy, missing):
    efficiency = {
        "unique_tool_invocation_count": 1,
        "delegation_count": 1,
        "total_turns": 2,
        "matched_tool_call_count": 1,
    }
    if missing is MISSING:
        efficiency.pop(field)
    else:
        efficiency[field] = missing
    result = row(efficiency=efficiency, task={"delegation_observed": True, "delegation_required": True})
    assert result[metric] is None
    if accuracy is not None:
        assert result[accuracy] is None


@pytest.mark.parametrize("missing", [MISSING, None], ids=["absent", "null"])
@pytest.mark.parametrize(
    "field,metric", [("tool_calls", "tool_calls"), ("delegations", "delegations"), ("total_turns", "turns")]
)
def test_missing_expected_count_does_not_invent_an_expected_zero(field, metric, missing):
    golden = deepcopy(GOLDEN)
    if missing is MISSING:
        golden.pop(field)
    else:
        golden[field] = missing
    result = row(efficiency={"unique_tool_invocation_count": 1, "delegation_count": 1, "total_turns": 2}, golden=golden)
    assert result[metric] is None
    if field == "tool_calls":
        assert result["tool_accuracy"] is None


def test_empty_observation_and_expectation_have_no_count_metrics_or_accuracies():
    result = row(efficiency={}, golden={})
    assert {
        key: result[key] for key in ("tool_calls", "delegations", "turns", "tool_accuracy", "delegation_accuracy")
    } == {
        "tool_calls": None,
        "delegations": None,
        "turns": None,
        "tool_accuracy": None,
        "delegation_accuracy": None,
    }


def test_explicit_zero_remains_zero_and_can_satisfy_no_tools_and_forbidden_delegation():
    result = row(
        efficiency={"unique_tool_invocation_count": 0, "delegation_count": 0, "total_turns": 0},
        golden={"tool_calls": [], "delegations": 0, "total_turns": 0, "delegation_policy": "forbidden"},
    )
    assert result["tool_calls"] == "0/0"
    assert result["delegations"] == "0/0"
    assert result["turns"] == "0/0"
    assert result["tool_accuracy"] == 1.0
    assert result["delegation_accuracy"] == 1.0


def test_explicit_zero_with_required_actions_is_a_known_failure():
    result = row(efficiency={"unique_tool_invocation_count": 0, "delegation_count": 0, "total_turns": 0})
    assert result["tool_calls"] == "0/1"
    assert result["delegations"] == "0/1"
    assert result["turns"] == "0/2"
    assert result["tool_accuracy"] == 0.0
    assert result["delegation_accuracy"] == 0.0


@pytest.mark.parametrize("observed", [False, True])
def test_boolean_delegation_observation_does_not_fabricate_an_exact_count(observed):
    result = row(task={"delegation_observed": observed})
    assert result["delegations"] is None
    assert result["delegation_accuracy"] is None


@pytest.mark.parametrize("invalid", [False, True, "0", -1, 0.25, float("nan"), float("inf")])
def test_invalid_count_values_are_not_coerced_into_observed_counts(invalid):
    result = row(
        efficiency={"unique_tool_invocation_count": invalid, "delegation_count": invalid, "total_turns": invalid}
    )
    for metric in ("tool_calls", "delegations", "turns", "tool_accuracy", "delegation_accuracy"):
        assert result[metric] is None


@pytest.mark.parametrize("missing", [MISSING, None], ids=["absent", "null"])
def test_missing_match_count_without_alternative_evidence_is_not_an_observed_zero(missing):
    efficiency = {"unique_tool_invocation_count": 1}
    if missing is not MISSING:
        efficiency["matched_tool_call_count"] = missing
    result = row(efficiency=efficiency)
    assert result["tool_calls"] == "1/1"
    assert result["tool_accuracy"] is None


def test_explicit_coverage_remains_alternative_matching_evidence_for_known_counts():
    result = row(efficiency={"unique_tool_invocation_count": 1}, task={"tool_call_coverage": 1.0})
    assert result["tool_accuracy"] == 1.0


@pytest.mark.parametrize("coverage", [None, False, float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_coverage_cannot_supply_missing_match_evidence(coverage):
    result = row(efficiency={"unique_tool_invocation_count": 1}, task={"tool_call_coverage": coverage})
    assert result["tool_accuracy"] is None


def test_explicit_null_prohibited_count_cannot_be_assumed_clear_for_a_passing_score():
    result = row(
        efficiency={"unique_tool_invocation_count": 1, "matched_tool_call_count": 1},
        task={"prohibited_tool_call_count": None},
    )
    assert result["tool_accuracy"] is None


def test_known_prohibited_call_is_a_failure_even_when_other_counts_are_unknown():
    result = row(task={"prohibited_tool_call_count": 1})
    assert result["tool_calls"] is None
    assert result["tool_accuracy"] == 0.0


def test_known_task_match_count_is_valid_evidence_when_efficiency_does_not_contain_one():
    result = row(efficiency={"unique_tool_invocation_count": 1}, task={"matched_tool_call_count": 1})
    assert result["tool_accuracy"] == 1.0


def test_explicit_null_match_count_is_not_replaced_by_another_source():
    result = row(
        efficiency={"unique_tool_invocation_count": 1, "matched_tool_call_count": None},
        task={"matched_tool_call_count": 1},
    )
    assert result["tool_accuracy"] is None


def test_explicit_zero_matches_is_a_known_failure():
    result = row(efficiency={"unique_tool_invocation_count": 1, "matched_tool_call_count": 0})
    assert result["tool_accuracy"] == 0.0


def test_a_null_expected_tool_multiplicity_is_not_one():
    result = row(
        efficiency={"unique_tool_invocation_count": 1}, golden={"tool_calls": [{"name": "lookup", "count": None}]}
    )
    assert result["tool_calls"] is None
    assert result["tool_accuracy"] is None


def test_an_expected_tool_without_multiplicity_still_means_one_required_call():
    result = row(
        efficiency={"unique_tool_invocation_count": 1, "matched_tool_call_count": 1},
        golden={"tool_calls": [{"name": "lookup"}]},
    )
    assert result["tool_calls"] == "1/1"
    assert result["tool_accuracy"] == 1.0


def test_policy_score_does_not_require_an_exact_expected_delegation_count():
    result = row(efficiency={"delegation_count": 0}, golden={"delegations": None, "delegation_policy": "forbidden"})
    assert result["delegations"] is None
    assert result["delegation_accuracy"] == 1.0


def test_a_known_actual_delegation_count_without_a_known_policy_has_no_accuracy():
    result = row(efficiency={"delegation_count": 0}, golden={})
    assert result["delegation_accuracy"] is None


def test_evidence_override_cannot_promote_unknown_observations_into_scores():
    result = row(evidence={"tool_accuracy": 1.0, "delegation_accuracy": 1.0})
    assert result["tool_accuracy"] is None
    assert result["delegation_accuracy"] is None


def test_explicit_unassessed_override_can_withhold_an_otherwise_available_score():
    result = row(
        efficiency={"unique_tool_invocation_count": 1, "matched_tool_call_count": 1, "delegation_count": 1},
        evidence={"tool_accuracy": None, "delegation_accuracy": None},
    )
    assert result["tool_accuracy"] is None
    assert result["delegation_accuracy"] is None


def test_direct_evidence_scores_also_preserve_absent_counts():
    assert evidence_scores({}, {}, GOLDEN) == {"tool_accuracy": None, "delegation_accuracy": None}


@pytest.mark.parametrize("observed", [False, True], ids=["missing", "observed-zero"])
def test_portable_report_preserves_missing_versus_explicit_zero(tmp_path, observed):
    efficiency = {"unique_tool_invocation_count": 0, "delegation_count": 0, "total_turns": 0} if observed else {}
    metrics = row(
        efficiency=efficiency,
        golden={"tool_calls": [], "delegations": 0, "total_turns": 0, "delegation_policy": "forbidden"},
    )
    report = build_result_item(
        {"example_id": "observation-boundary", "status": "failed", **metrics},
        run_dir=tmp_path,
        scenario_id_key="example_id",
    )
    for field in ("tool_calls", "delegations", "turns"):
        assert report["metrics"]["task"][field] == ({"actual": 0, "expected": 0} if observed else None)
    for field in ("tool_accuracy", "delegation_accuracy"):
        assert report["metrics"]["task"][field] == (1.0 if observed else None)


@pytest.mark.parametrize("policy", [[], {}, ["required"], {"required": True}, "unsupported", 0, False])
def test_invalid_policy_is_unknown_even_with_a_known_expected_count(policy):
    result = row(efficiency={"delegation_count": 0}, golden={"delegations": 0, "delegation_policy": policy})
    assert result["delegations"] == "0/0"
    assert result["delegation_accuracy"] is None


@pytest.mark.parametrize(
    "pair",
    [
        {"actual": False, "expected": 0},
        {"actual": 0, "expected": True},
        {"actual": -1, "expected": 0},
        {"actual": 0, "expected": -1},
        {"actual": 0.0, "expected": 0},
        {"actual": "0", "expected": 0},
        {"actual": 0},
        {"actual": 0, "expected": None},
        "-1/0",
        "0/-1",
        "0/0/0",
        "0.0/0",
        "True/0",
        "0/",
        None,
    ],
)
def test_portable_report_rejects_invalid_count_pairs(tmp_path, pair):
    report = build_result_item(
        {
            "example_id": "invalid-count-pair",
            "task_completed": False,
            "tool_calls": pair,
            "delegations": pair,
            "turns": pair,
        },
        run_dir=tmp_path,
        scenario_id_key="example_id",
    )
    for metric in ("tool_calls", "delegations", "turns"):
        assert report["metrics"]["task"][metric] is None


@pytest.mark.parametrize(
    "pair,expected",
    [
        ("0/0", {"actual": 0, "expected": 0}),
        ({"actual": 0, "expected": 0}, {"actual": 0, "expected": 0}),
        ("2/3", {"actual": 2, "expected": 3}),
        ({"actual": 2, "expected": 3}, {"actual": 2, "expected": 3}),
    ],
)
def test_portable_report_retains_known_integer_count_pairs(tmp_path, pair, expected):
    report = build_result_item(
        {"example_id": "valid-count-pair", "task_completed": False, "tool_calls": pair},
        run_dir=tmp_path,
        scenario_id_key="example_id",
    )
    assert report["metrics"]["task"]["tool_calls"] == expected


@pytest.mark.parametrize("harness", ["crawl", "walk", "run"])
def test_failed_scenario_before_observation_has_no_zero_counts_or_accuracies(tmp_path, harness):
    failure = RuntimeError("input setup failed before any observation")
    if harness == "run":
        scenario = run_evaluate.load_run_scenarios(run_evaluate.DEFAULT_DATA_JSON, max_examples=1)[0]
        failed = run_evaluate.failed_row(
            scenario,
            failure,
            offline=True,
            args=SimpleNamespace(condition="clean", model="fixture", backend_model="fixture"),
        )
        scenario_key = "scenario_id"
    elif harness == "crawl":
        scenario = crawl_evaluate.load_dataset(crawl_evaluate.DEFAULT_DATA_JSON)[0]
        failed = crawl_evaluate.build_failed_result(
            scenario,
            tmp_path / "audio",
            tmp_path / "events",
            tmp_path / "transcripts",
            crawl_evaluate.build_error_info(failure, "input_setup"),
        ).to_result_row()
        scenario_key = "example_id"
    else:
        scenario = walk_evaluate.load_dataset(walk_evaluate.DEFAULT_DATA_JSON)[0]
        failed = walk_evaluate._failed_result(
            scenario,
            audio_dir=tmp_path / "audio",
            events_dir=tmp_path / "events",
            transcripts_dir=tmp_path / "transcripts",
            exc=failure,
        ).to_result_row()
        scenario_key = "example_id"
    report = build_result_item(failed, run_dir=tmp_path, scenario_id_key=scenario_key)
    assert report["status"] == "infrastructure_error"
    for metric in ("tool_calls", "delegations", "turns", "tool_accuracy", "delegation_accuracy"):
        assert report["metrics"]["task"][metric] is None
