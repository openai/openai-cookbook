"""Safe, ID-correlated backend response evidence in standalone viewers."""

from __future__ import annotations

import json
from pathlib import Path

from run_harness.tests.test_run_visualization import _run_fixture, _write_jsonl
from run_harness.visualization.delegations import build_delegation_details
from run_harness.visualization.export_viewer import build_view_data, export_viewer


def created(identifier: str, offset: int, *, target: str = "client", response_id: str = "") -> dict:
    item = {"id": identifier, "target": target, "content": [{"text": "PRIVATE_REQUEST"}]}
    if response_id:
        item["response_id"] = response_id
    return {"type": "session.delegation.created", "offset_ms": offset, "delegation": item}


def response(identifier: str, owner: str = "", *, previous: str = "") -> dict:
    event = {"type": "response.created", "response": {"id": identifier, "previous_response_id": previous}}
    if owner:
        event["delegation_id"] = owner
    return event


def message(identifier: str, text: str, owner: str = "") -> dict:
    event = {
        "type": "response.output_item.done",
        "item": {
            "id": identifier,
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text}],
        },
    }
    if owner:
        event["delegation_id"] = owner
    return event


def write_trace(path: Path, events: list[dict]) -> None:
    _write_jsonl(path, [{"source": "assistant_gpt_live", "event": event} for event in events])


def test_three_client_handoffs_can_have_only_one_application_tool(tmp_path: Path) -> None:
    results = _run_fixture(tmp_path, with_ticks=False, with_turns=False)
    event_path = tmp_path / "events/restaurant_booking_complete.jsonl"
    events = []
    for index, text in enumerate(("What name and time?", "What time on the corrected date?", "Booked."), 1):
        owner = f"private-delegation-{index}"
        rid = f"private-response-{index}"
        events.extend([created(owner, index * 100), response(rid, owner)])
        if index == 3:
            for kind in ("tool.called", "tool.completed"):
                events.append(
                    {
                        "type": kind,
                        "delegation_id": owner,
                        "call_id": "PRIVATE_CALL_ID",
                        "name": "create_reservation",
                        "arguments": {"secret": "PRIVATE_ARGUMENT"},
                        "result": {"secret": "PRIVATE_TOOL_RESULT"},
                    }
                )
            events.extend(
                [{"type": "response.completed", "response": {"id": rid}}, response("private-response-4", owner)]
            )
        events.extend(
            [
                {
                    "type": "response.output_item.done",
                    "delegation_id": owner,
                    "item": {
                        "type": "reasoning",
                        "summary": [{"text": "PRIVATE_REASONING"}],
                        "encrypted_content": "PRIVATE_ENCRYPTED",
                    },
                },
                {
                    "type": "response.output_text.done",
                    "delegation_id": owner,
                    "item_id": f"message-{index}",
                    "text": text,
                },
                message(f"message-{index}", text, owner),
                {"type": "client_delegation.completed", "delegation_id": owner, "text": text},
            ]
        )
    write_trace(event_path, events)
    with event_path.open("a") as stream:
        stream.write(
            json.dumps({"source": "caller_gpt_live", "event": message("caller", "PRIVATE_CALLER_BACKEND")}) + "\n"
        )
    scenario = build_view_data(results)["scenarios"][0]
    assert [x["responses"] for x in scenario["delegations"]] == [
        ["What name and time?"],
        ["What time on the corrected date?"],
        ["Booked."],
    ]
    assert [x["responseCount"] for x in scenario["delegations"]] == [1, 1, 2]
    assert [x["toolCount"] for x in scenario["delegations"]] == [0, 0, 1]
    assert scenario["delegations"][2]["tools"] == [
        {"name": "create_reservation", "status": "completed", "toolIndex": 1}
    ]
    assert [x["timeMs"] for x in scenario["delegationEvents"]] == [100, 200, 300]
    html = export_viewer(results).read_text()
    for private in (
        "PRIVATE_REQUEST",
        "PRIVATE_ARGUMENT",
        "PRIVATE_TOOL_RESULT",
        "PRIVATE_CALL_ID",
        "PRIVATE_REASONING",
        "PRIVATE_ENCRYPTED",
        "PRIVATE_CALLER_BACKEND",
        "private-delegation",
        "private-response",
    ):
        assert private not in html
    assert 'id="transcript-list"' in html
    assert 'id="delegation-list"' not in html
    assert "No application tool calls recorded" in html


def test_managed_response_ids_and_continuations_keep_overlapping_handoffs_separate(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_trace(
        path,
        [
            created("d1", 100, target="responses", response_id="r1"),
            created("d2", 200, target="responses", response_id="r2"),
            response("r1"),
            response("r2"),
            message("ambiguous", "DO_NOT_GUESS"),
            {"type": "response.output_item.added", "response_id": "r2", "item": {"id": "m2", "type": "message"}},
            message("m2", "Second handoff."),
            {"type": "response.completed", "response": {"id": "r2"}},
            message("m1", "First handoff."),
            {"type": "tool.completed", "response_id": "r1", "call_id": "c1", "name": "lookup"},
            {"type": "response.completed", "response": {"id": "r1"}},
            response("r3", previous="r1"),
            message("m3", "First follow-up."),
            {"type": "response.completed", "response": {"id": "r3"}},
        ],
    )
    details = build_delegation_details(path, [])
    assert details[0]["responses"] == ["First handoff.", "First follow-up."]
    assert details[0]["responseCount"] == 2
    assert details[0]["toolCount"] == 1
    assert details[1]["responses"] == ["Second handoff."]
    assert details[1]["toolCount"] == 0
    assert "DO_NOT_GUESS" not in json.dumps(details)


def test_managed_tool_output_identifies_a_unique_follow_up_response(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    write_trace(
        path,
        [
            created("d1", 100, target="responses", response_id="r1"),
            response("r1"),
            {"type": "tool.completed", "response_id": "r1", "call_id": "c1", "name": "lookup"},
            {"type": "response.completed", "response": {"id": "r1"}},
            {"type": "delegation.function_call_output.created", "item": {"call_id": "c1", "output": "PRIVATE_RESULT"}},
            response("r2"),
            message("m2", "The lookup succeeded."),
            {"type": "response.completed", "response": {"id": "r2"}},
        ],
    )
    details = build_delegation_details(path, [])
    assert details[0]["responseCount"] == 2
    assert details[0]["responses"] == ["The lookup succeeded."]
    assert details[0]["tools"] == [{"name": "lookup", "status": "completed"}]
    assert "PRIVATE_RESULT" not in json.dumps(details)


def test_ambiguous_tool_continuations_are_not_assigned(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    events = []
    for index in (1, 2):
        events.extend(
            [
                created(f"d{index}", index * 100, target="responses", response_id=f"r{index}"),
                response(f"r{index}"),
                {"type": "tool.completed", "response_id": f"r{index}", "call_id": f"c{index}", "name": "lookup"},
                {"type": "response.completed", "response": {"id": f"r{index}"}},
            ]
        )
    events.extend(
        [
            {"type": "delegation.function_call_output.created", "item": {"call_id": "c1"}},
            {"type": "delegation.function_call_output.created", "item": {"call_id": "c2"}},
            response("unidentified"),
            message("unknown", "DO_NOT_GUESS"),
        ]
    )
    write_trace(path, events)
    assert "DO_NOT_GUESS" not in json.dumps(build_delegation_details(path, []))


def test_missing_trace_keeps_timing_without_claiming_no_tools(tmp_path: Path) -> None:
    details = build_delegation_details(tmp_path / "missing.jsonl", [{"timeMs": 120, "target": "client"}])
    assert details == [
        {
            "timeMs": 120,
            "target": "client",
            "status": "unavailable",
            "responseCount": None,
            "responses": [],
            "toolCount": None,
            "tools": [],
            "provenance": "timeline_only",
        }
    ]


def test_final_response_text_cannot_break_out_of_the_embedded_json(tmp_path: Path) -> None:
    results = _run_fixture(tmp_path)
    text = '</script><script>alert("unsafe")</script>'
    write_trace(
        tmp_path / "events/restaurant_booking_complete.jsonl",
        [
            created("d1", 100),
            response("r1", "d1"),
            {"type": "client_delegation.completed", "delegation_id": "d1", "text": text},
        ],
    )
    assert build_view_data(results)["scenarios"][0]["delegations"][0]["responses"] == [text]
    html = export_viewer(results).read_text()
    assert text not in html
    assert "\\u003c/script>" in html


def test_native_wrapped_responses_use_relay_timing_and_keep_function_evidence(tmp_path):
    from run_harness.visualization.delegations import build_delegation_details

    events = [
        {
            "type": "session.delegation.created",
            "delegation": {"id": "d", "target": "responses", "response_id": "r"},
            "_relay_receipt": {"media_ms": 100},
        },
        {
            "type": "response.event",
            "delegation_id": None,
            "event": {"type": "response.created", "response": {"id": "r"}},
        },
        {"type": "tool.called", "response_id": "r", "call_id": "c", "name": "lookup", "offset_ms": 110},
        {"type": "tool.completed", "response_id": "r", "call_id": "c", "name": "lookup", "offset_ms": 200},
        {
            "type": "response.event",
            "delegation_id": "d",
            "event": {"type": "response.completed", "response": {"id": "r", "output": []}},
        },
    ]
    trace = tmp_path / "events.jsonl"
    trace.write_text("\n".join(json.dumps({"source": "assistant_gpt_live", "event": event}) for event in events))
    details = build_delegation_details(trace, [{"timeMs": 100, "target": "responses"}])
    assert len(details) == 1
    assert details[0]["timeMs"] == 100 and details[0]["responseCount"] == 1
    assert details[0]["toolCount"] == 1 and details[0]["tools"][0]["name"] == "lookup"
