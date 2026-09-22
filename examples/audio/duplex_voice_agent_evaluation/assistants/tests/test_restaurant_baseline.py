"""Parity and independent safety contracts for the bundled comparison assistants."""

from __future__ import annotations

import ast
import copy
from importlib.util import resolve_name
from typing import Any

import pytest

from assistants.config import assistant_default_tools, assistant_prompt
from assistants.resources import ASSISTANTS_DIR, assistant_resources
from assistants.runtime import AsyncToolRuntime, ToolExecutionResult
from shared.scenarios import ScenarioDataset

MODES = ("responses", "client")
SLOT = {"date": "2026-08-07", "time": "19:00", "party_size": 2}
BOOKING = {"guest_name": "Maya", **SLOT}
INITIAL = {
    "authorized_reservation_ids": ["R-100"],
    "reservations": [
        {"reservation_id": "R-100", "guest_name": "Maya", "cancelled": False},
        {"reservation_id": "R-200", "guest_name": "Noah", "cancelled": False},
    ],
}


def executor(mode: str, initial: dict | None = None):
    resources = assistant_resources(assistant_mode=mode)
    return resources.create_executor(initial if initial is not None else {}, resources.load_facts())


def test_bundled_resources_match_without_sharing_backend_files() -> None:
    managed, client = (assistant_resources(assistant_mode=mode) for mode in MODES)
    assert managed.system_prompt_file == client.system_prompt_file
    for field in ("backend_system_prompt_file", "tools_file", "facts_file"):
        left, right = getattr(managed, field), getattr(client, field)
        assert left != right and not left.samefile(right), field
    assert assistant_prompt("backend", assistant_mode="responses") == assistant_prompt(
        "backend", assistant_mode="client"
    )
    assert managed.load_facts() == client.load_facts()
    schemas = assistant_default_tools(assistant_mode="responses")
    assert schemas == assistant_default_tools(assistant_mode="client")
    assert {tool["name"]: tool["parameters"]["required"] for tool in schemas} == {
        "check_availability": ["date", "time", "party_size"],
        "create_reservation": ["guest_name", "date", "time", "party_size"],
        "cancel_reservation": ["reservation_id"],
    }


@pytest.mark.parametrize("mode", MODES)
def test_resource_fact_loads_are_independent(mode: str) -> None:
    resources = assistant_resources(assistant_mode=mode)
    original = resources.load_facts()
    changed = resources.load_facts()
    changed["availability_overrides"][0]["available"] = True
    assert resources.load_facts() == original
    other = assistant_resources(assistant_mode="client" if mode == "responses" else "responses")
    assert other.load_facts() == original


def test_custom_business_facts_do_not_change_the_other_assistant() -> None:
    managed_resources = assistant_resources(assistant_mode="responses")
    client_resources = assistant_resources(assistant_mode="client")
    custom = client_resources.load_facts()
    custom["availability_overrides"][0]["available"] = True
    managed = managed_resources.create_executor({}, managed_resources.load_facts())
    client = client_resources.create_executor({}, custom)
    custom["availability_overrides"][0]["available"] = False
    unavailable_slot = {**SLOT, "time": "21:00", "party_size": 6}
    assert managed.execute("check_availability", unavailable_slot, call_id="managed")["available"] is False
    assert client.execute("check_availability", unavailable_slot, call_id="client")["available"] is True


@pytest.mark.parametrize("mode", MODES)
def test_offline_behavior_respects_authorization_and_latest_visible_correction(mode: str) -> None:
    resources = assistant_resources(assistant_mode=mode)
    behavior = resources.create_offline_behavior(
        conversation_context="Maya requested a reservation for two on August 7 at 7 p.m.",
        initial_state=INITIAL,
        facts=resources.load_facts(),
    )
    assert behavior.infer_tool_call("Actually, make it for four on August 8 at 8 p.m.") == (
        "create_reservation",
        {**BOOKING, "date": "2026-08-08", "time": "20:00", "party_size": 4},
    )
    assert behavior.infer_tool_call("Cancel R-200.") is None
    assert "aren't authorized" in behavior.direct_answer("Cancel R-200.")
    assert behavior.infer_tool_call("Cancel R-200. Correction: cancel R-100.") == (
        "cancel_reservation",
        {"reservation_id": "R-100"},
    )
    assert behavior.infer_tool_call("What are your hours?") is None
    assert resources.load_facts()["hours"] in behavior.direct_answer("What are your hours?")
    assert behavior.final_answer({"ok": False}) == "I couldn't complete that restaurant request."


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(
    ("arguments", "available"),
    [
        (SLOT, True),
        ({**SLOT, "time": "21:00", "party_size": 6}, False),
        ({**SLOT, "time": "21:00", "party_size": 6, "seating": " PATIO "}, False),
    ],
    ids=["available", "unavailable", "normalized-seating"],
)
def test_availability_is_read_only(mode: str, arguments: dict, available: bool) -> None:
    tool = executor(mode, INITIAL)
    before = tool.snapshot()
    normalized = {**arguments}
    if "seating" in normalized:
        normalized["seating"] = "patio"
    expected = {"ok": True, **normalized, "available": available}
    assert tool.execute("check_availability", arguments, call_id="availability") == expected
    assert tool.snapshot() == before
    assert tool.executions == [
        {
            "call_id": "availability",
            "name": "check_availability",
            "arguments": arguments,
            "status": "completed",
            "output": expected,
        }
    ]


@pytest.mark.parametrize("mode", MODES)
def test_creation_records_normalized_state_and_distinct_ids(mode: str) -> None:
    initial = {"reservations": [], "authorized_reservation_ids": [], "untouched": {"value": 1}}
    tool = executor(mode, initial)
    arguments = {**BOOKING, "guest_name": " Maya ", "seating": " PATIO "}
    normalized = {**BOOKING, "seating": "patio"}
    first = {"reservation_id": "R-001", **normalized, "cancelled": False}
    second = {"reservation_id": "R-002", **BOOKING, "cancelled": False}
    assert tool.execute("create_reservation", arguments, call_id="one") == {
        "ok": True,
        "reservation_created": True,
        **first,
    }
    assert tool.snapshot() == {**initial, "reservations": [first], "reservation_created": True, **normalized}
    assert tool.execute("create_reservation", BOOKING, call_id="two") == {
        "ok": True,
        "reservation_created": True,
        **second,
    }
    assert tool.snapshot()["reservations"] == [first, second]
    assert [item["call_id"] for item in tool.executions] == ["one", "two"]
    assert all(item["status"] == "completed" for item in tool.executions)
    assert initial == {"reservations": [], "authorized_reservation_ids": [], "untouched": {"value": 1}}


@pytest.mark.parametrize("mode", MODES)
def test_cancellation_changes_only_the_authorized_reservation(mode: str) -> None:
    tool = executor(mode, INITIAL)
    expected = copy.deepcopy(INITIAL)
    expected["reservations"][0]["cancelled"] = True
    expected.update(reservation_id="R-100", cancelled=True)
    output = {"ok": True, "reservation_id": "R-100", "cancelled": True}
    assert tool.execute("cancel_reservation", {"reservation_id": " R-100 "}, call_id="cancel") == output
    assert tool.snapshot() == expected
    assert tool.executions[0]["output"] == output
    before_log = copy.deepcopy(tool.executions)
    with pytest.raises(ValueError, match="already cancelled"):
        tool.execute("cancel_reservation", {"reservation_id": "R-100"}, call_id="repeat")
    assert tool.snapshot() == expected
    assert tool.executions == before_log


INVALID_CASES = [
    pytest.param("unknown", {}, {}, "Unauthorized restaurant tool", id="unknown-tool"),
    pytest.param("create_reservation", [], {}, "JSON object", id="non-object-arguments"),
    *(
        pytest.param(
            "create_reservation", {k: v for k, v in BOOKING.items() if k != field}, {}, field, id=f"missing-{field}"
        )
        for field in BOOKING
    ),
    *(
        pytest.param("create_reservation", {**BOOKING, field: value}, {}, message, id=label)
        for field, value, message, label in [
            ("guest_name", " ", "guest_name", "blank-name"),
            ("date", "2026-02-30", "ISO date", "invalid-date"),
            ("time", "25:00", "HH:MM", "invalid-time"),
            ("party_size", True, "positive party_size", "boolean-size"),
            ("party_size", 0, "positive party_size", "zero-size"),
            ("party_size", -1, "positive party_size", "negative-size"),
            ("party_size", "2", "positive party_size", "string-size"),
            ("seating", " ", "seating", "blank-seating"),
        ]
    ),
    pytest.param("create_reservation", BOOKING, {"reservations": {}}, "must be a list", id="invalid-create-state"),
    pytest.param("cancel_reservation", {}, INITIAL, "reservation_id", id="missing-cancel-id"),
    pytest.param("cancel_reservation", {"reservation_id": "R-200"}, INITIAL, "Not authorized", id="other-customer"),
    pytest.param(
        "cancel_reservation",
        {"reservation_id": "R-100"},
        {**INITIAL, "authorized_reservation_ids": "R-100"},
        "Not authorized",
        id="invalid-authorization",
    ),
    pytest.param(
        "cancel_reservation",
        {"reservation_id": "R-999"},
        {**INITIAL, "authorized_reservation_ids": ["R-999"]},
        "does not exist",
        id="missing-reservation",
    ),
    pytest.param(
        "cancel_reservation",
        {"reservation_id": "R-100"},
        {**INITIAL, "reservations": {}},
        "must be a list",
        id="invalid-cancel-state",
    ),
]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize(("name", "arguments", "initial", "message"), INVALID_CASES)
def test_invalid_operations_cannot_mutate_state_or_record_success(
    mode: str,
    name: str,
    arguments: Any,
    initial: dict,
    message: str,
) -> None:
    tool = executor(mode, initial)
    before = tool.snapshot()
    with pytest.raises(ValueError, match=message):
        tool.execute(name, arguments, call_id="denied")
    assert tool.snapshot() == before
    assert tool.executions == []


@pytest.mark.parametrize("mode", MODES)
async def test_runtime_reports_denied_operations_as_failures(mode: str) -> None:
    tool = executor(mode, INITIAL)
    runtime = AsyncToolRuntime(tool)
    results: list[ToolExecutionResult] = []

    async def collect(result: ToolExecutionResult) -> None:
        results.append(result)

    try:
        runtime.submit("cancel_reservation", {"reservation_id": "R-200"}, call_id="denied", on_result=collect)
        await runtime.wait()
        assert len(results) == 1 and results[0].error
        assert results[0].output["ok"] is False
        assert tool.snapshot() == INITIAL
        assert [item["status"] for item in tool.executions] == ["failed"]
        assert tool.executions[0]["call_id"] == "denied"
    finally:
        await runtime.close()


def test_backend_classes_state_and_execution_records_are_independent(monkeypatch: pytest.MonkeyPatch) -> None:
    initial = {"reservations": [], "metadata": {"owner": "original"}}
    managed, client = (executor(mode, initial) for mode in MODES)
    assert type(managed) is not type(client)
    assert type(managed).__module__ == "assistants.responses.tools.restaurant"
    assert type(client).__module__ == "assistants.client.tools.restaurant"
    arguments = copy.deepcopy(BOOKING)
    output = managed.execute("create_reservation", arguments, call_id="managed")
    arguments["guest_name"] = output["guest_name"] = "changed"
    projected = managed.snapshot()
    projected["reservations"][0]["guest_name"] = "changed"
    assert managed.snapshot()["reservations"][0]["guest_name"] == "Maya"
    assert managed.executions[0]["arguments"]["guest_name"] == "Maya"
    assert managed.executions[0]["output"]["guest_name"] == "Maya"
    assert client.snapshot() == initial and client.executions == []
    monkeypatch.setattr(type(client), "execute", lambda *args, **kwargs: {"variant": "client-only"})
    assert client.execute("anything", {}, call_id="variant") == {"variant": "client-only"}
    assert managed.execute("check_availability", SLOT, call_id="managed-unchanged")["available"] is True


def test_domain_modules_cannot_import_the_other_backend_or_evaluator() -> None:
    for mode in MODES:
        forbidden = (
            f"assistants.{'client' if mode == 'responses' else 'responses'}",
            "crawl_harness",
            "walk_harness",
            "run_harness",
            "shared.grading",
            "shared.scenarios",
        )
        for path in (ASSISTANTS_DIR / mode / "tools").glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else []
                if isinstance(node, ast.ImportFrom):
                    module = resolve_name("." * node.level + (node.module or ""), f"assistants.{mode}.tools")
                    names.extend([module, *(f"{module}.{alias.name}" for alias in node.names)])
                assert not any(
                    name == prefix or name.startswith(prefix + ".") for name in names for prefix in forbidden
                ), f"Domain ownership boundary crossed in {path}: {names}"


@pytest.mark.parametrize("phase", ["crawl", "walk", "run"])
def test_offline_baseline_matches_for_all_bundled_visible_inputs(phase: str) -> None:
    path = ASSISTANTS_DIR.parent / f"{phase}_harness/data/scenarios.json"
    scenarios = ScenarioDataset.model_validate_json(path.read_text()).scenarios
    assert scenarios
    for scenario in scenarios:
        # Only caller-visible context and authorized application inputs reach the fixture.
        behaviors = [
            assistant_resources(assistant_mode=mode).create_offline_behavior(
                conversation_context=scenario.conversation_context,
                initial_state=scenario.application.initial_state,
                facts=assistant_resources(assistant_mode=mode).load_facts(),
            )
            for mode in MODES
        ]
        assert type(behaviors[0]) is not type(behaviors[1])
        calls = [behavior.infer_tool_call(scenario.input.text) for behavior in behaviors]
        assert calls[0] == calls[1], scenario.id
        assert behaviors[0].direct_answer(scenario.input.text) == behaviors[1].direct_answer(scenario.input.text), (
            scenario.id
        )
        if calls[0] is None:
            continue
        outcomes = []
        for mode, behavior, call in zip(MODES, behaviors, calls, strict=True):
            tool = executor(mode, scenario.application.initial_state)
            name, arguments = call
            try:
                output = tool.execute(name, arguments, call_id="baseline")
            except ValueError as exc:
                output = {"ok": False, "error": str(exc)}
            outcomes.append((output, tool.snapshot(), tool.executions, behavior.final_answer(output)))
        assert outcomes[0] == outcomes[1], scenario.id
