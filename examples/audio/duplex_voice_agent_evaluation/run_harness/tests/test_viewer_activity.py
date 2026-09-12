"""Inline backend activity keeps exact identities and only intended evidence."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from run_harness.tests.test_run_visualization import _run_fixture, _write_jsonl
from run_harness.tests.test_viewer_delegations import created, response, write_trace
from run_harness.visualization.activity import build_backend_activity, safe_arguments
from run_harness.visualization.export_viewer import build_view_data, export_viewer


def test_call_ids_keep_repeated_tools_and_overlapping_delegations_separate(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    events = [created("d1", 100), created("d2", 150), response("r1", "d1"), response("r2", "d2")]
    turns = []
    for identifier, owner, at, date, status in (
        ("c1", "d1", 200, "2026-08-07", "completed"),
        ("c2", "d2", 210, "2026-08-08", "failed"),
    ):
        call = {"call_id": identifier, "name": "lookup", "arguments": {"date": date}}
        events.extend(
            [
                {**call, "type": "tool.called", "delegation_id": owner},
                {**call, "type": "tool." + status, "delegation_id": owner},
            ]
        )
        turns.append(
            {
                "task": {
                    "tool_calls": [
                        {**call, "event_type": "tool.called", "timestamp_ms": at},
                        {**call, "event_type": "tool." + status, "timestamp_ms": at + 50},
                    ]
                }
            }
        )
    write_trace(path, events)

    delegations, calls = build_backend_activity(path, [], turns, [])

    assert [(call["timeMs"], call["status"], call["delegationIndex"]) for call in calls] == [
        (200, "completed", 0),
        (210, "failed", 1),
    ]
    assert [call["arguments"]["date"] for call in calls] == ["2026-08-07", "2026-08-08"]
    assert [item["tools"][0]["toolIndex"] for item in delegations] == [0, 1]
    assert "call_id" not in json.dumps(calls)


def test_missing_trace_preserves_repeated_untimed_executions(tmp_path: Path) -> None:
    _, calls = build_backend_activity(
        tmp_path / "missing",
        [],
        [],
        [
            {"name": "lookup", "status": "completed", "arguments": {"id": 1}},
            {"name": "lookup", "status": "completed", "arguments": {"id": 2}},
        ],
    )
    assert [item["arguments"] for item in calls] == [{"id": 1}, {"id": 2}]
    assert all(item["timeMs"] is None for item in calls)


def test_arguments_redact_nested_credentials_and_parse_json() -> None:
    arguments = {
        "date": "2026-08-08",
        "nested": [{"api_key": "PRIVATE", "Authorization": "PRIVATE"}],
        "note": "Bearer confidential",
        "password": "PRIVATE",
    }
    clean = safe_arguments(json.dumps(arguments))
    assert clean["date"] == "2026-08-08"
    assert clean["nested"] == [{"api_key": "[redacted]", "Authorization": "[redacted]"}]
    assert "PRIVATE" not in json.dumps(clean)
    assert "confidential" not in json.dumps(clean)
    assert safe_arguments("opaque private text") is None


def test_viewer_exports_application_arguments_and_every_final_metric(tmp_path: Path) -> None:
    results = _run_fixture(tmp_path)
    report = json.loads(results.read_text())
    metrics = report["results"][0]["metrics"]
    metrics["task"].update(
        {
            "tool_calls": {"actual": 1, "expected": 2},
            "delegations": {"actual": 1, "expected": 1},
            "turns": {"actual": 7, "expected": 7},
        }
    )
    metrics["consumption"] = {
        "frontend": {},
        "backend": {
            "total_tokens": 100,
            "input": {"cached_tokens": 20},
            "output": {"reasoning_tokens": 5},
            "models": [{"model": "test-model", "total_tokens": 100}],
        },
    }
    metrics["future_group"] = {"new_metric": 42}
    results.write_text(json.dumps(report))
    scenario = build_view_data(results)["scenarios"][0]
    assert scenario["finalMetrics"] == metrics
    assert scenario["toolCalls"] == [
        {"timeMs": 500, "name": "check_availability", "status": "completed", "arguments": {"party_size": 2}}
    ]
    assert scenario["eventAnnotations"][0]["toolIndex"] == 0

    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is needed for the dependency-free viewer DOM test")
    html = export_viewer(results)
    subprocess.run([node, str(Path(__file__).with_name("viewer_dom_test.cjs")), str(html)], check=True)


def test_tool_arguments_cannot_escape_embedded_script(tmp_path: Path) -> None:
    results = _run_fixture(tmp_path)
    turns_path = tmp_path / "audio/restaurant_booking_complete/conversation.turns.jsonl"
    turns = [json.loads(line) for line in turns_path.read_text().splitlines()]
    turns[1]["task"]["tool_calls"][0]["arguments"] = {"note": "</script><script>unsafe</script>"}
    _write_jsonl(turns_path, turns)
    html = export_viewer(results).read_text()
    assert "</script><script>unsafe" not in html
    assert "\\u003c/script>" in html
