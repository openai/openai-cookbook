import asyncio
import base64
import io
import json
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import pytest

from assistants.client.assistant import ClientDelegatedAssistant
from assistants.errors import LiveResponseError
from assistants.frontend.assistant import LiveFrontend
from assistants.frontend.transport import build_context_append
from assistants.resources import assistant_resources
from assistants.responses.assistant import ResponsesManagedAssistant
from run_harness.evaluate import (
    DEFAULT_ASSISTANT_OPENING_PROMPT_PATH,
    DEFAULT_DATA_JSON,
    _read_assistant_opening_prompt,
    load_run_scenarios,
    parse_args,
    run_evals,
)
from run_harness.simulation.gpt_live_participants import SimulatorControlTools
from run_harness.simulation.gpt_live_runner import DualGptLiveRunner
from run_harness.simulation.models import Settings
from shared.observability.trace import record_event


class ScriptedParticipant:
    def __init__(self, label: str, events: list[dict[str, Any]] | None = None) -> None:
        self.agent_id = label
        self.events = asyncio.Queue()
        self.initial_events = events or []
        self.appended_contexts: list[str] = []

    async def start(self) -> None:
        for event in self.initial_events:
            await self.events.put(event)

    async def trigger_opening(self, _text: str) -> None:
        return None

    async def append_context(self, text: str) -> None:
        self.appended_contexts.append(text)

    async def send_audio(self, _pcm: bytes) -> None:
        return None

    async def incoming(self) -> AsyncIterator[dict[str, Any]]:
        while (event := await self.events.get()) is not None:
            yield event

    async def wait_for_tools(self) -> None:
        return None

    async def close(self) -> None:
        await self.events.put({"type": "session.closed", "usage": {"seconds": 0.0}, "reason": "client_request"})
        await self.events.put(None)


def test_context_append_preserves_the_exact_nonempty_text() -> None:
    text = "  Greet the caller now.\n"

    event = build_context_append(text)
    assert event.pop("event_id")
    assert event == {"type": "session.commentary.append", "content": text, "delegation_id": None}
    with pytest.raises(ValueError, match="nonempty"):
        build_context_append(" \n\t")


def test_both_assistant_architectures_share_the_frontend_context_method() -> None:
    assert ResponsesManagedAssistant.append_context is LiveFrontend.append_context
    assert ClientDelegatedAssistant.append_context is LiveFrontend.append_context


def test_trace_redacts_echoed_session_context() -> None:
    log = io.StringIO()
    record_event(
        log,
        {
            "type": "session.context.appended",
            "content": [{"type": "input_text", "text": "private opening instruction"}],
        },
        started_at=time.monotonic(),
        event_index_state={"value": 0},
        source="live_frontend",
        direction="server_to_client",
    )

    saved = json.loads(log.getvalue())
    assert saved["event"]["content"] == "[redacted session context]"
    assert "private opening instruction" not in log.getvalue()


def test_cli_prompt_loader_preserves_raw_text_and_bundles_an_example(tmp_path: Path) -> None:
    raw = " \nGreet the caller using this instruction.\n "
    custom = tmp_path / "opening.txt"
    custom.write_text(raw, encoding="utf-8")

    args = parse_args(["--assistant-opening-prompt", str(custom)])

    assert args.assistant_opening_prompt == custom
    assert _read_assistant_opening_prompt(custom) == raw
    assert _read_assistant_opening_prompt(DEFAULT_ASSISTANT_OPENING_PROMPT_PATH)


@pytest.mark.asyncio
@pytest.mark.parametrize("contents", [None, " \n\t"])
async def test_invalid_prompt_fails_before_creating_artifacts(tmp_path: Path, contents: str | None) -> None:
    prompt = tmp_path / "invalid.txt"
    if contents is not None:
        prompt.write_text(contents, encoding="utf-8")
    results = tmp_path / "results"
    args = parse_args(
        [
            "--offline",
            "--no-judge",
            "--results-dir",
            str(results),
            "--assistant-opening-prompt",
            str(prompt),
        ]
    )

    with pytest.raises(ValueError, match="[Aa]ssistant opening prompt"):
        await run_evals(args)
    assert not results.exists()


@pytest.mark.asyncio
async def test_dual_gpt_live_caller_cannot_speak_before_assistant_opening() -> None:
    scenario = load_run_scenarios(DEFAULT_DATA_JSON, scenario_id="restaurant_booking_complete")[0]
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    caller_pcm = (1_200).to_bytes(2, byteorder="little", signed=True) * 480
    caller = ScriptedParticipant(
        "caller",
        [
            {
                "type": "session.output_audio.delta",
                "start_ms": 0,
                "end_ms": 20,
                "delta": base64.b64encode(caller_pcm).decode(),
            }
        ],
    )
    assistant = ScriptedParticipant("assistant")
    runner = DualGptLiveRunner(
        scenario,
        caller=caller,
        assistant=assistant,
        caller_tools=SimulatorControlTools(),
        application_tools=application,
        tick_ms=20,
        max_duration_s=0.1,
        real_time=False,
        offline=True,
        assistant_opening_prompt="greet first",
    )

    with pytest.raises(LiveResponseError, match="caller spoke before") as caught:
        await runner.run()
    assert caught.value.failure_stage == "assistant_opening"
    assert assistant.appended_contexts == ["greet first"]


@pytest.mark.asyncio
async def test_live_dual_gpt_live_assistant_first_uses_frontend_only_caller(monkeypatch: pytest.MonkeyPatch) -> None:
    from run_harness.simulation import gpt_live

    scenario = load_run_scenarios(DEFAULT_DATA_JSON, scenario_id="restaurant_booking_complete")[0]
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    caller_arguments: dict[str, Any] = {}
    runner_arguments: dict[str, Any] = {}

    class FakeCaller:
        def __init__(self, **kwargs: Any) -> None:
            self.agent_id = kwargs["model"]
            caller_arguments.update(kwargs)

    class FakeAssistant:
        def __init__(self, **kwargs: Any) -> None:
            self.agent_id = kwargs["settings"].agent_model
            self.settings = kwargs["settings"]

    class FakeRunner:
        def __init__(self, *_args: Any, **kwargs: Any) -> None:
            runner_arguments.update(kwargs)

        async def run(self) -> str:
            return "result"

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(gpt_live, "GptLiveCallerParticipant", FakeCaller)
    monkeypatch.setattr(gpt_live, "EvaluatedGptLiveParticipant", FakeAssistant)
    monkeypatch.setattr(gpt_live, "DualGptLiveRunner", FakeRunner)
    settings = Settings(assistant_opening_prompt="greet first")

    result = await gpt_live.run_gpt_live_conversation(
        scenario,
        settings,
        tool_executor=application,
        offline=False,
        simulator_model="caller-model",
        simulator_voice="",
        drain_ms=1_500,
    )

    assert result == "result"
    assert runner_arguments["assistant_opening_prompt"] == "greet first"
    assert caller_arguments["model"] == "caller-model"
    assert scenario.input.text in caller_arguments["instructions"]
    assert "Wait for the other participant to greet you" in caller_arguments["instructions"]
    assert "settings" not in caller_arguments
    assert "opening_audio" not in runner_arguments


@pytest.mark.asyncio
async def test_offline_dual_gpt_live_assistant_first_orders_turns_and_sanitizes_metadata(tmp_path: Path) -> None:
    raw = "  Greet the caller immediately.\n"
    prompt = tmp_path / "opening.txt"
    prompt.write_text(raw, encoding="utf-8")
    args = parse_args(
        [
            "--offline",
            "--no-judge",
            "--scenario",
            "restaurant_booking_complete",
            "--results-dir",
            str(tmp_path / "results"),
            "--assistant-opening-prompt",
            str(prompt),
        ]
    )

    run_dir = await run_evals(args)
    saved = json.loads((run_dir / "transcripts" / "restaurant_booking_complete.json").read_text(encoding="utf-8"))
    report_text = (run_dir / "results.json").read_text(encoding="utf-8")
    transcript_lines = saved["transcript"].splitlines()

    assert transcript_lines[0].startswith("ASSISTANT ")
    assert transcript_lines[1].startswith("USER ")
    assert saved["caller_actions"]["OPENING"] == 1
    assert saved["run_metadata"]["first_speaker"] == "assistant"
    assert "assistant_opening_prompt_sha256" not in saved["run_metadata"]
    assert "assistant_opening_prompt_sha256" not in report_text
    assert raw not in report_text
    assert str(prompt) not in report_text
