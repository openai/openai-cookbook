import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.realtime_harness_utils import (
    RealtimeResponseError,
    collect_realtime_response,
)


class FakeEvent:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def model_dump(self) -> dict:
        return self._payload


class FakeResponseResource:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create(self, response=None) -> None:
        self.calls.append({"response": response})


class FakeConversationItemResource:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def create(self, item: dict) -> None:
        self.calls.append(item)


class FakeConversationResource:
    def __init__(self) -> None:
        self.item = FakeConversationItemResource()


class FakeConnection:
    def __init__(self, payloads: list[dict], *, stall_seconds: float = 0.0) -> None:
        self._payloads = [FakeEvent(payload) for payload in payloads]
        self._stall_seconds = stall_seconds
        self.response = FakeResponseResource()
        self.conversation = FakeConversationResource()

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._payloads:
            return self._payloads.pop(0)
        if self._stall_seconds > 0:
            await asyncio.sleep(self._stall_seconds)
        raise StopAsyncIteration


def test_collect_realtime_response_times_out() -> None:
    async def run_test() -> None:
        connection = FakeConnection([], stall_seconds=1.0)

        try:
            await collect_realtime_response(
                connection,
                {},
                response_timeout_seconds=0.01,
            )
        except RealtimeResponseError as exc:
            assert exc.failure_stage == "response_timeout"
        else:
            raise AssertionError("Expected realtime timeout to raise")

    asyncio.run(run_test())


def test_collect_realtime_response_raises_on_error_event() -> None:
    async def run_test() -> None:
        connection = FakeConnection(
            [
                {
                    "type": "error",
                    "error": {
                        "type": "server_error",
                        "code": "bad_request",
                        "message": "Something went wrong",
                    },
                }
            ]
        )

        try:
            await collect_realtime_response(connection, {})
        except RealtimeResponseError as exc:
            assert exc.failure_stage == "response_error"
            assert exc.error_code == "bad_request"
        else:
            raise AssertionError("Expected realtime error event to raise")

    asyncio.run(run_test())


def test_collect_realtime_response_requires_completed_status() -> None:
    async def run_test() -> None:
        connection = FakeConnection(
            [
                {
                    "type": "response.done",
                    "response": {
                        "status": "incomplete",
                        "status_details": {"reason": "max_output_tokens"},
                        "output": [],
                        "usage": {},
                    },
                }
            ]
        )

        try:
            await collect_realtime_response(connection, {})
        except RealtimeResponseError as exc:
            assert exc.failure_stage == "response_status"
            assert exc.response_status == "incomplete"
        else:
            raise AssertionError("Expected non-completed response to raise")

    asyncio.run(run_test())


def test_collect_realtime_response_returns_completed_response() -> None:
    async def run_test() -> None:
        connection = FakeConnection(
            [
                {"type": "response.output_text.delta", "delta": "Hello"},
                {
                    "type": "response.done",
                    "response": {
                        "status": "completed",
                        "output": [],
                        "usage": {
                            "output_tokens": 4,
                            "output_token_details": {
                                "audio_tokens": 0,
                                "text_tokens": 4,
                            },
                        },
                    },
                },
            ]
        )

        result = await collect_realtime_response(connection, {})

        assert result["assistant_text"] == "Hello"
        assert result["usage"]["output_tokens"] == 4

    asyncio.run(run_test())
