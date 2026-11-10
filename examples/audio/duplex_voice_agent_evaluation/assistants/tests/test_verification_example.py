"""Application contracts for the synthetic verification example."""

from __future__ import annotations

import json

import pytest

from assistants.examples.verification.application import VerificationTools
from assistants.examples.verification.resources import VerificationResources, load_scenarios, resources_for_scenario
from assistants.runtime import AsyncToolRuntime, ToolExecutionResult

INITIAL = {"verified": False, "transferred": False, "verification_checks": 0, "transfer_count": 0}
DATE_ARGUMENTS = {"date_of_birth": "1990-09-05"}
TRANSFER_ARGUMENTS = {"reason": "The caller requested a person."}


def test_same_request_is_checked_against_the_private_application_record() -> None:
    matching = VerificationTools(INITIAL, record="1990-09-05")
    mismatching = VerificationTools(INITIAL, record="1984-04-23")

    assert matching.execute("verify_date_of_birth", DATE_ARGUMENTS, call_id="match") == {
        "ok": True,
        "matched": True,
        "verified": True,
    }
    assert mismatching.execute("verify_date_of_birth", DATE_ARGUMENTS, call_id="mismatch") == {
        "ok": True,
        "matched": False,
        "verified": False,
    }
    assert matching.snapshot() == {**INITIAL, "verified": True, "verification_checks": 1}
    assert mismatching.snapshot() == {**INITIAL, "verification_checks": 1}
    assert INITIAL == {"verified": False, "transferred": False, "verification_checks": 0, "transfer_count": 0}
    assert all(item["status"] == "completed" for item in matching.executions + mismatching.executions)


def test_resources_keep_the_record_out_of_public_facts_and_observable_state() -> None:
    private_date = "1984-04-23"
    resources = VerificationResources(record=private_date)
    public_facts = resources.load_facts()
    executor = resources.create_executor(INITIAL, public_facts)
    public_material = json.dumps({"facts": public_facts, "state": executor.snapshot()})
    public_material += resources.system_prompt_file.read_text() + resources.backend_system_prompt_file.read_text()
    public_material += resources.tools_file.read_text()

    assert private_date not in public_material
    assert executor.execute("verify_date_of_birth", {"date_of_birth": private_date}, call_id="private") == {
        "ok": True,
        "matched": True,
        "verified": True,
    }
    assert private_date not in json.dumps(executor.snapshot())


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("verify_date_of_birth", {"date_of_birth": "1990-02-30"}),
        ("verify_date_of_birth", {"date_of_birth": "September fifth, 1990"}),
        ("verify_date_of_birth", {}),
        ("transfer_to_human", {"reason": " "}),
        ("unregistered_tool", {}),
    ],
)
def test_invalid_operations_leave_state_and_execution_history_unchanged(name: str, arguments: dict) -> None:
    executor = VerificationTools(INITIAL, record="1990-09-05")

    with pytest.raises(ValueError):
        executor.execute(name, arguments, call_id="invalid")

    assert executor.snapshot() == INITIAL
    assert executor.executions == []


def test_call_id_replay_is_idempotent_and_conflicting_reuse_is_rejected() -> None:
    executor = VerificationTools(INITIAL, record="1990-09-05")
    first = executor.execute("verify_date_of_birth", DATE_ARGUMENTS, call_id="same")

    assert executor.execute("verify_date_of_birth", dict(DATE_ARGUMENTS), call_id="same") == first
    assert executor.snapshot()["verification_checks"] == 1
    assert len(executor.executions) == 1
    with pytest.raises(ValueError):
        executor.execute("verify_date_of_birth", {"date_of_birth": "1992-09-01"}, call_id="same")
    assert executor.snapshot()["verification_checks"] == 1
    assert len(executor.executions) == 1


def test_distinct_repeated_transfer_requests_record_one_transfer_effect() -> None:
    executor = VerificationTools(INITIAL, record="1990-09-05")

    assert executor.execute("transfer_to_human", TRANSFER_ARGUMENTS, call_id="first") == {
        "ok": True,
        "result": "transferred",
        "transferred": True,
    }
    assert executor.execute("transfer_to_human", TRANSFER_ARGUMENTS, call_id="second") == {
        "ok": True,
        "result": "already_transferred",
        "transferred": True,
    }
    assert executor.snapshot() == {**INITIAL, "transferred": True, "transfer_count": 1}
    assert [item["call_id"] for item in executor.executions] == ["first", "second"]


def test_transfer_service_failure_is_returned_without_a_transfer_effect() -> None:
    executor = VerificationTools(INITIAL, record="1990-09-05", transfer_available=False)

    assert executor.execute("transfer_to_human", TRANSFER_ARGUMENTS, call_id="unavailable") == {
        "ok": False,
        "result": "transfer_failed",
        "transferred": False,
    }
    assert executor.snapshot() == INITIAL
    assert executor.executions[0]["status"] == "completed"


async def test_native_runtime_records_invalid_arguments_as_a_failed_invocation() -> None:
    executor = VerificationTools(INITIAL, record="1990-09-05")
    runtime = AsyncToolRuntime(executor)
    results: list[ToolExecutionResult] = []

    async def collect(result: ToolExecutionResult) -> None:
        results.append(result)

    try:
        runtime.submit("verify_date_of_birth", {"date_of_birth": "1990-02-30"}, call_id="bad", on_result=collect)
        await runtime.wait()
        assert len(results) == 1 and results[0].error
        assert results[0].output["ok"] is False
        assert executor.snapshot() == INITIAL
        assert [item["status"] for item in executor.executions] == ["failed"]
    finally:
        await runtime.close()


def test_evaluator_expectations_do_not_drive_the_offline_behavior() -> None:
    scenario = next(row for row in load_scenarios() if row.id == "dob_mismatch")
    resources = resources_for_scenario(scenario.id)
    behavior = resources.create_offline_behavior(
        conversation_context=scenario.conversation_context,
        initial_state=scenario.application.initial_state,
        facts=resources.load_facts(),
    )
    scenario.expected.answer = "EVALUATOR_ONLY_ANSWER"
    scenario.expected.tools.required.clear()
    scenario.expected.state = {"verified": True}

    assert behavior.infer_tool_call(scenario.input.text) == (
        "verify_date_of_birth",
        {"date_of_birth": "1992-09-01"},
    )
    assert "EVALUATOR_ONLY_ANSWER" not in behavior.final_answer({"ok": True, "matched": False, "verified": False})
