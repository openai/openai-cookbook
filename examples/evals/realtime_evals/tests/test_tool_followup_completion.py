"""Offline regressions for terminal events after mocked tool execution."""

import asyncio
import base64
import io
import json
import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.realtime_harness_utils import (
    RealtimeResponseError,
    collect_realtime_response,
)
from test_realtime_harness_utils import FakeConnection


def completed_tool_round(number):
    return {
        "type": "response.done",
        "response": {
            "status": "completed",
            "output": [
                {
                    "type": "function_call",
                    "call_id": f"synthetic-{number}",
                    "name": "lookup",
                    "arguments": json.dumps({"number": number}),
                }
            ],
            "usage": {"output_tokens": 2},
        },
    }


def completed_answer():
    return {
        "type": "response.done",
        "response": {
            "status": "completed",
            "output": [],
            "usage": {"output_tokens": 3},
        },
    }


@pytest.mark.parametrize("rounds", [1, 2])
@pytest.mark.parametrize("partial", ["none", "text", "audio"])
def test_tool_followup_requires_its_own_terminal_event(rounds, partial):
    events = [completed_tool_round(number) for number in range(rounds)]
    if partial == "text":
        events.append(
            {"type": "response.output_text.delta", "delta": "Unfinished answer"}
        )
    if partial == "audio":
        events.append(
            {
                "type": "response.output_audio.delta",
                "delta": base64.b64encode(b"\0\0").decode(),
            }
        )
    connection = FakeConnection(events)
    log = io.StringIO()
    with pytest.raises(RealtimeResponseError) as error:
        asyncio.run(
            collect_realtime_response(
                connection,
                {},
                tool_mocks={"lookup": {"value": "synthetic"}},
                log_file=log,
            )
        )
    assert error.value.failure_stage == "response_missing_done"
    assert len(connection.response.calls) == rounds + 1
    assert len(connection.conversation.item.calls) == rounds
    assert len(log.getvalue().splitlines()) == len(events)


@pytest.mark.parametrize("rounds", [1, 2])
def test_completed_followup_preserves_segments_tools_and_usage(rounds):
    events = [completed_tool_round(number) for number in range(rounds)]
    events += [
        {"type": "response.output_text.delta", "delta": "Complete answer"},
        completed_answer(),
    ]
    connection = FakeConnection(events)
    result = asyncio.run(
        collect_realtime_response(connection, {}, tool_mocks={"lookup": {"value": 1}})
    )
    assert result["assistant_text"] == "Complete answer"
    assert len(result["response_segments"]) == rounds + 1
    assert len(result["tool_calls"]) == rounds
    assert result["usage"]["output_tokens"] == rounds * 2 + 3
    assert result["response_done_time_ms"] is not None
    assert len(connection.response.calls) == rounds + 1


def test_tool_response_without_mocks_does_not_require_a_followup():
    connection = FakeConnection([completed_tool_round(0)])
    result = asyncio.run(collect_realtime_response(connection, {}))
    assert len(result["tool_calls"]) == 1
    assert result["usage"]["output_tokens"] == 2
    assert len(connection.response.calls) == 1
    assert connection.conversation.item.calls == []


def test_empty_stream_keeps_existing_missing_done_error():
    with pytest.raises(RealtimeResponseError) as error:
        asyncio.run(collect_realtime_response(FakeConnection([]), {}, tool_mocks={}))
    assert error.value.failure_stage == "response_missing_done"


def test_failed_followup_preserves_response_status_error():
    failed = completed_answer()
    failed["response"]["status"] = "failed"
    with pytest.raises(RealtimeResponseError) as error:
        asyncio.run(
            collect_realtime_response(
                FakeConnection([completed_tool_round(0), failed]), {}, tool_mocks={}
            )
        )
    assert error.value.failure_stage == "response_status"
    assert error.value.response_status == "failed"
