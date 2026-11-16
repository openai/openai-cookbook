import asyncio
import base64
import json
from array import array
from pathlib import Path
from typing import Any

import pytest

from assistants.config import session_update
from assistants.errors import LiveResponseError
from assistants.resources import assistant_resources
from assistants.responses.assistant import ResponsesManagedAssistant
from run_harness.evaluate import DEFAULT_CONFIG_PATH, _token_counts, load_run_scenarios, parse_args, result_row
from run_harness.simulation.gpt_live_participants import (
    GptLiveCallerParticipant,
    OfflineCallerParticipant,
    OfflineRestaurantParticipant,
    SimulatorControlTools,
)
from run_harness.simulation.gpt_live_prompts import caller_backend_instructions, caller_frontend_instructions
from run_harness.simulation.gpt_live_runner import DualGptLiveRunner
from run_harness.simulation.models import Settings
from shared.reporting.results import build_result_item


def restaurant_booking():
    args = parse_args(["--config", str(DEFAULT_CONFIG_PATH), "--offline", "--no-judge"])
    return load_run_scenarios(args.data, scenario_id="restaurant_booking_complete", max_examples=0)[0]


def test_default_gpt_live_caller_reuses_run_configuration_and_scenarios() -> None:
    args = parse_args(
        [
            "--config",
            str(DEFAULT_CONFIG_PATH),
            "--offline",
            "--no-judge",
            "--scenario",
            "restaurant_booking_complete",
        ]
    )
    scenarios = load_run_scenarios(args.data, scenario_id=args.scenario, max_examples=args.max_examples)

    assert args.scenario == "restaurant_booking_complete"
    assert args.data.name == "scenarios.json"
    assert args.data.parent.name == "data"
    assert args.data.parent.parent.name == "run_harness"
    assert [scenario.id for scenario in scenarios] == ["restaurant_booking_complete"]


def test_caller_frontend_prompt_allows_reasoning_without_delegating_simple_replies() -> None:
    scenario = restaurant_booking()
    prompt = caller_frontend_instructions(scenario)

    assert scenario.simulation_parameters.goal in prompt
    assert "You are a real caller." in prompt
    assert "You are a real restaurant caller." not in prompt
    assert "## Current goal and verified facts" in prompt
    assert scenario.simulation_parameters.known_facts["guest_name"] in prompt
    assert "Use your reasoning backend" in prompt
    assert "Answer simple questions and give backchannels directly" in prompt
    assert "Never call tools" in prompt
    assert scenario.expected.answer not in prompt
    assert "finish_conversation" not in prompt


@pytest.mark.parametrize("prompt_builder", [caller_frontend_instructions, caller_backend_instructions])
def test_caller_prompts_do_not_read_evaluator_answers_or_private_application_state(prompt_builder) -> None:
    scenario = restaurant_booking()
    prompt = prompt_builder(scenario)
    scenario.expected.answer = "PRIVATE EXPECTED ANSWER"
    scenario.expected.criteria = ["PRIVATE GRADING CRITERIA"]
    scenario.expected.state = {"private_expected_state": True}
    scenario.expected.tools.required[0].arguments = {"private_expected_arguments": True}
    scenario.application.initial_state = {"private_application_state": True}

    assert prompt_builder(scenario) == prompt


@pytest.mark.parametrize("prompt_builder", [caller_frontend_instructions, caller_backend_instructions])
def test_gpt_live_caller_scenario_brief_is_concise_natural_language_without_json(prompt_builder) -> None:
    scenario = restaurant_booking()
    simulation = scenario.simulation_parameters
    prompt = prompt_builder(scenario)

    assert "## Current goal and verified facts" in prompt
    assert "## Conversation plan" in prompt
    assert simulation.persona.description in prompt
    assert simulation.persona.speech_instructions in prompt
    for name, value in simulation.known_facts.items():
        assert f"{name.replace('_', ' ')}: {value}" in prompt
    for item in simulation.agenda:
        if item.action not in {"finish", "wait"}:
            assert item.trigger_condition.rstrip(".") in prompt
            assert (item.response_hint or item.commitment) in prompt
    assert all(expectation in prompt for expectation in simulation.expectations)
    assert "{" not in prompt
    assert "}" not in prompt
    assert "completion_condition" not in prompt
    assert "backchannel_tendency" not in prompt
    assert len(prompt) < 2_000


def test_caller_backend_prompt_gives_private_caller_guidance_not_target_instructions() -> None:
    prompt = caller_backend_instructions(restaurant_booking())

    assert "You support the simulated caller's reasoning" in prompt
    assert "## Response guidance" in prompt
    assert "suggested first-person wording for the caller" in prompt
    assert "Do not solve the assistant's task" in prompt
    assert "You have no tools or access to the assistant's private state" in prompt
    assert "what the caller has heard" in prompt


def test_gpt_live_caller_uses_independent_managed_backend_without_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_LIVE_BACKEND_MODEL", "target-only-model")
    monkeypatch.setenv("OPENAI_LIVE_BACKEND_REASONING_EFFORT", "high")
    monkeypatch.setenv("OPENAI_LIVE_BACKEND_MAX_OUTPUT_TOKENS", "9000")
    monkeypatch.setenv("OPENAI_LIVE_BACKEND_VERBOSITY", "high")
    monkeypatch.setenv("OPENAI_ASSISTANT_MODE", "client")
    monkeypatch.setenv("OPENAI_CLIENT_ASSISTANT_ENDPOINT", "http://localhost:9000")
    scenario = restaurant_booking()
    participant = GptLiveCallerParticipant(
        scenario=scenario,
        endpoint="https://api.openai.com/v1/live",
        model="gpt-live-caller",
        voice="marin",
        instructions=caller_frontend_instructions(scenario),
        api_key="test-key",
    )
    event = session_update(scenario, participant._agent.config, participant._agent.settings)
    delegation = event["session"]["delegation"]

    assert isinstance(participant._agent, ResponsesManagedAssistant)
    assert delegation["type"] == "responses"
    assert delegation["responses"]["model"] == "gpt-5.6-luna"
    assert delegation["responses"]["reasoning"] == {"effort": "low"}
    assert delegation["responses"]["max_output_tokens"] == 1_024
    assert delegation["responses"]["text"] == {"verbosity": "low"}
    assert delegation["responses"]["tools"] == []
    assert delegation["responses"]["instructions"] == caller_backend_instructions(scenario)
    assert participant._agent.tool_executor is None
    assert participant._agent.controller is None
    assert participant._agent.config.client_endpoint == ""
    assert scenario.simulation_parameters.goal in event["session"]["instructions"]
    settings = Settings()
    assert settings.backend_model == "target-only-model"
    assert settings.simulator_backend_model == "gpt-5.6-luna"
    assert settings.simulator_backend_reasoning_effort == "low"


@pytest.mark.asyncio
@pytest.mark.parametrize("offline", [False, True])
async def test_run_passes_caller_backend_settings_only_to_the_live_caller(
    monkeypatch: pytest.MonkeyPatch, offline: bool
) -> None:
    from run_harness.simulation import gpt_live

    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    runner_arguments: dict[str, Any] = {}

    class FakeRunner:
        def __init__(self, *_args: Any, **kwargs: Any) -> None:
            runner_arguments.update(kwargs)

        async def run(self) -> str:
            return "result"

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(gpt_live, "DualGptLiveRunner", FakeRunner)
    settings = Settings(
        backend_model="target-backend",
        simulator_backend_model="caller-backend",
        simulator_backend_reasoning_effort="high",
    )
    result = await gpt_live.run_gpt_live_conversation(
        scenario,
        settings,
        tool_executor=application,
        offline=offline,
        simulator_model="caller-model",
        simulator_voice="marin",
        drain_ms=1_500,
    )

    assert result == "result"
    assert runner_arguments["assistant_backend_model"] == "target-backend"
    if offline:
        assert isinstance(runner_arguments["caller"], OfflineCallerParticipant)
        assert runner_arguments["simulator_backend_model"] is None
        assert runner_arguments["simulator_backend_reasoning_effort"] is None
    else:
        caller = runner_arguments["caller"]
        event = session_update(scenario, caller._agent.config, caller._agent.settings)
        assert event["session"]["delegation"]["responses"]["model"] == "caller-backend"
        assert event["session"]["delegation"]["responses"]["reasoning"] == {"effort": "high"}
        assert runner_arguments["simulator_backend_model"] == "caller-backend"
        assert runner_arguments["simulator_backend_reasoning_effort"] == "high"
        assert runner_arguments["assistant"]._agent.config.backend_model == "target-backend"


@pytest.mark.asyncio
async def test_gpt_live_caller_starts_by_appending_opening_context() -> None:
    scenario = restaurant_booking()
    participant = GptLiveCallerParticipant(
        scenario=scenario,
        endpoint="https://api.openai.com/v1/live",
        model="gpt-live-caller",
        voice="marin",
        instructions=caller_frontend_instructions(scenario),
        api_key="test-key",
    )
    sent: list[dict[str, object]] = []

    async def capture(event: dict[str, object]) -> None:
        sent.append(event)

    participant._agent._send_live = capture  # type: ignore[method-assign]
    event = await participant.trigger_opening(scenario.input.text)

    assert sent == [event]
    assert event["type"] == "session.commentary.append"
    assert "Do not wait for the assistant to speak first" in event["content"]
    assert "restaurant call" not in event["content"]
    assert event["content"].endswith(scenario.input.text)


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_participant", ["caller", "assistant"])
async def test_dual_gpt_live_startup_failures_identify_the_failed_participant(failed_participant: str) -> None:
    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    controls = SimulatorControlTools()
    caller = OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200)
    assistant = OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200)

    async def reject_start() -> None:
        raise RuntimeError("provider rejected the session")

    participant: Any = caller if failed_participant == "caller" else assistant
    participant.start = reject_start
    runner = DualGptLiveRunner(
        scenario,
        caller=caller,
        assistant=assistant,
        caller_tools=controls,
        application_tools=application,
        real_time=False,
        offline=True,
    )

    with pytest.raises(LiveResponseError, match=f"{failed_participant} GPT Live connection failed to start") as caught:
        await runner.run()

    assert caught.value.failure_stage == f"{failed_participant}_connection"
    assert caller.closed is True
    assert assistant.closed is True


@pytest.mark.asyncio
async def test_dual_gpt_live_caller_opening_request_failures_have_a_distinct_stage() -> None:
    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    controls = SimulatorControlTools()
    caller = OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200)
    assistant = OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200)

    async def reject_opening(_text: str) -> None:
        raise RuntimeError("opening context rejected")

    caller.trigger_opening = reject_opening  # type: ignore[method-assign]
    runner = DualGptLiveRunner(
        scenario,
        caller=caller,
        assistant=assistant,
        caller_tools=controls,
        application_tools=application,
        real_time=False,
        offline=True,
    )

    with pytest.raises(LiveResponseError, match="Caller opening request failed") as caught:
        await runner.run()

    assert caught.value.failure_stage == "caller_opening"


@pytest.mark.asyncio
async def test_dual_gpt_live_caller_opening_times_out_without_speech(monkeypatch: pytest.MonkeyPatch) -> None:
    from run_harness.simulation import gpt_live_runner

    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    controls = SimulatorControlTools()
    caller = OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200)
    assistant = OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200)

    async def remain_silent(_text: str) -> None:
        return None

    caller.trigger_opening = remain_silent  # type: ignore[method-assign]
    monkeypatch.setattr(gpt_live_runner, "CALLER_OPENING_TIMEOUT_SECONDS", 0)
    runner = DualGptLiveRunner(
        scenario,
        caller=caller,
        assistant=assistant,
        caller_tools=controls,
        application_tools=application,
        real_time=False,
        offline=True,
    )

    with pytest.raises(LiveResponseError, match="Caller opening timed out") as caught:
        await runner.run()

    assert caught.value.failure_stage == "caller_opening"


@pytest.mark.asyncio
@pytest.mark.parametrize("failed_participant", ["caller", "assistant"])
async def test_dual_gpt_live_audio_stream_failures_identify_the_failed_participant(failed_participant: str) -> None:
    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    controls = SimulatorControlTools()
    caller = OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200)
    assistant = OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200)

    async def reject_audio(_pcm: bytes) -> None:
        raise RuntimeError("socket disconnected")

    participant: Any = caller if failed_participant == "caller" else assistant
    participant.send_audio = reject_audio
    runner = DualGptLiveRunner(
        scenario,
        caller=caller,
        assistant=assistant,
        caller_tools=controls,
        application_tools=application,
        real_time=False,
        offline=True,
    )

    with pytest.raises(LiveResponseError, match=f"{failed_participant} GPT Live audio stream failed") as caught:
        await runner.run()

    assert caught.value.failure_stage == f"{failed_participant}_connection"


@pytest.mark.asyncio
@pytest.mark.parametrize("closed_participant", ["caller", "assistant"])
async def test_dual_gpt_live_unexpected_session_close_identifies_the_closed_participant(
    closed_participant: str,
) -> None:
    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    controls = SimulatorControlTools()
    runner = DualGptLiveRunner(
        scenario,
        caller=OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200),
        assistant=OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200),
        caller_tools=controls,
        application_tools=application,
        real_time=False,
        offline=True,
    )
    await runner.events.put((closed_participant, {"type": "session.closed"}))

    await runner._drain_events()

    assert runner.failure is not None
    assert runner.failure.failure_stage == f"{closed_participant}_connection"
    assert "closed before the conversation completed" in str(runner.failure)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("target", "terminal_type", "close_terminal", "reason"),
    [
        ("responses", "response.completed", False, None),
        ("responses", "response.failed", False, "caller_backend_failed"),
        ("responses", "response.incomplete", False, "caller_backend_failed"),
        ("responses", None, False, "caller_backend_pending"),
        ("responses", "response.completed", True, "caller_backend_pending"),
        ("client", None, False, "unsupported_caller_delegation"),
    ],
)
async def test_managed_caller_validity_retains_diagnostics_and_excludes_backend_failures(
    tmp_path: Path,
    target: str,
    terminal_type: str | None,
    close_terminal: bool,
    reason: str | None,
) -> None:
    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    controls = SimulatorControlTools()
    caller = OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200)
    runner = DualGptLiveRunner(
        scenario,
        caller=caller,
        assistant=OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200),
        caller_tools=controls,
        application_tools=application,
        real_time=False,
        offline=True,
        max_duration_s=30,
        simulator_backend_model="gpt-5.6-sol",
        simulator_backend_reasoning_effort="medium",
        save_conversations=tmp_path / "audio",
    )
    await runner.events.put(
        (
            "caller",
            {
                "type": "session.delegation.created",
                "delegation": {"id": "caller-handoff", "target": target, "response_id": "caller-response"},
            },
        )
    )
    if target == "responses":
        await runner.events.put(("caller", {"type": "response.created", "response": {"id": "caller-response"}}))
    if close_terminal:
        close_caller = caller.close

        async def finish_backend_during_close() -> None:
            await caller.events.put({"type": terminal_type, "response": {"id": "caller-response"}})
            await close_caller()

        caller.close = finish_backend_during_close  # type: ignore[method-assign]
    elif terminal_type:
        await runner.events.put(("caller", {"type": terminal_type, "response": {"id": "caller-response"}}))
    result = await runner.run()
    validity = result.run_metadata["simulator_validity"]
    item = build_result_item(
        result_row(scenario, result, offline=True), run_dir=tmp_path, scenario_id_key="scenario_id"
    )

    assert validity["status"] == ("valid" if reason is None else "invalid")
    assert validity["target_metrics_eligible"] is (reason is None)
    assert validity["reason"] == reason
    assert validity["unexpected_delegation_count"] == (1 if target == "client" else 0)
    assert item["status"] == ("passed" if reason is None else "infrastructure_error")
    if reason:
        assert item["error"]["stage"] == "caller_simulation"
        assert reason in item["error"]["message"]
    if reason == "caller_backend_pending":
        assert result.termination_reason == "duration_limit"
    if close_terminal:
        assert runner._caller_work_state.active is False
    assert result.run_metadata["simulator_backend_model"] == "gpt-5.6-sol"
    assert result.run_metadata["simulator_backend_reasoning_effort"] == "medium"
    assert result.task_metrics["requirements_satisfied"] is True
    assert application.snapshot()["reservation_created"] is True
    assert await asyncio.to_thread(Path(result.artifacts["audio"]).is_file)
    saved = json.loads(await asyncio.to_thread(Path(result.artifacts["result"]).read_text))
    assert saved["run_metadata"]["simulator_validity"] == validity
    assert "Maya" in saved["transcript"]


@pytest.mark.asyncio
@pytest.mark.parametrize("event_copies", [1, 2])
async def test_unsupported_caller_delegation_keeps_artifacts_but_cannot_count_as_a_target_pass(
    tmp_path: Path,
    event_copies: int,
) -> None:
    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    controls = SimulatorControlTools()
    runner = DualGptLiveRunner(
        scenario,
        caller=OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200),
        assistant=OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200),
        caller_tools=controls,
        application_tools=application,
        real_time=False,
        offline=True,
        save_conversations=tmp_path / "audio",
    )
    for _ in range(event_copies):
        await runner.events.put(
            ("caller", {"type": "session.delegation.created", "delegation": {"id": "unsupported", "target": "client"}})
        )
    result = await runner.run()
    validity = result.run_metadata["simulator_validity"]
    assert validity["status"] == "invalid"
    assert validity["unexpected_delegation_count"] == 1
    assert validity["reason"] == "unsupported_caller_delegation"
    # Keep real task evidence, but do not count an invalid simulator as a target
    # pass or failure. Existing report consumers already exclude this status.
    item = build_result_item(
        result_row(scenario, result, offline=True), run_dir=tmp_path, scenario_id_key="scenario_id"
    )
    assert item["status"] == "infrastructure_error"
    assert item["error"]["stage"] == "caller_simulation"
    assert item["validity"] == validity
    assert item["metrics"]["task"]["task_completed"] is True
    assert await asyncio.to_thread(Path(result.artifacts["audio"]).is_file)
    saved = json.loads(await asyncio.to_thread(Path(result.artifacts["result"]).read_text))
    assert saved["run_metadata"]["simulator_validity"] == validity


def test_gpt_live_caller_prompt_requests_brief_overlapping_backchannels() -> None:
    prompt = caller_frontend_instructions(restaurant_booking())

    assert "assistant speech longer than two seconds" in prompt
    assert '"Mm-hmm," "Right," or "Okay,"' in prompt
    assert "occasionally overlap" in prompt
    assert "immediately yield" in prompt
    assert "Avoid interrupting questions" in prompt


@pytest.mark.asyncio
async def test_heard_input_turn_is_not_projected_as_participant_output(tmp_path: Path) -> None:
    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    controls = SimulatorControlTools()
    caller = OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200)
    assistant = OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200)
    runner = DualGptLiveRunner(
        scenario,
        caller=caller,
        assistant=assistant,
        caller_tools=controls,
        application_tools=application,
        real_time=False,
        save_conversations=tmp_path / "audio",
        offline=True,
    )
    await runner.events.put(
        (
            "assistant",
            {
                "type": "session.input_transcript.delta",
                "start_ms": 0,
                "end_ms": 200,
                "delta": "heard caller input",
            },
        )
    )

    await runner._drain_events()

    assert not runner.timeline.transcript_projection.pending("assistant")


def test_dual_gpt_live_preserves_provider_timestamps_when_projecting_delegated_events() -> None:
    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    controls = SimulatorControlTools()
    runner = DualGptLiveRunner(
        scenario,
        caller=OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200),
        assistant=OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200),
        caller_tools=controls,
        application_tools=application,
        real_time=False,
        offline=True,
    )
    runner.input_ms = 1_400

    runner._project_assistant_event(
        {"type": "session.delegation.created", "offset_ms": 1_100, "delegation": {"target": "responses"}}
    )
    runner._project_assistant_event({"type": "tool.called", "name": "check_availability", "call_id": "call-1"})

    assert [(event.event_type, event.timestamp_ms) for event in runner.timeline.agent_events] == [
        ("session.delegation.created", 1_100),
        ("tool.called", 1_400),
    ]


@pytest.mark.asyncio
async def test_turn_projects_at_its_audio_boundary_even_with_future_buffering(tmp_path: Path) -> None:
    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    controls = SimulatorControlTools()
    runner = DualGptLiveRunner(
        scenario,
        caller=OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200),
        assistant=OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200),
        caller_tools=controls,
        application_tools=application,
        real_time=False,
        save_conversations=tmp_path / "audio",
        offline=True,
    )
    pcm = b"\x01\x00\x02\x00"
    await runner.events.put(("caller", {"type": "session.output_audio.delta", "delta": base64.b64encode(pcm).decode()}))
    await runner.events.put(
        (
            "caller",
            {
                "type": "session.output_transcript.delta",
                "start_ms": 5000,
                "end_ms": 5200,
                "delta": "caller output",
            },
        )
    )
    await runner._drain_events()

    runner._project_completed_turns("caller")
    assert runner.timeline.user_utterances == []

    runner._pop_audio("caller", len(pcm))
    runner.timeline.add_audio("user", 0, 200, True)
    runner.input_ms = 1000
    runner._project_completed_turns("caller")
    assert [item.text for item in runner.timeline.user_utterances] == ["caller output"]


@pytest.mark.asyncio
async def test_dual_gpt_live_relay_preserves_each_participants_real_provider_timestamp_gaps(tmp_path: Path) -> None:
    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    controls = SimulatorControlTools()
    runner = DualGptLiveRunner(
        scenario,
        caller=OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200),
        assistant=OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200),
        caller_tools=controls,
        application_tools=application,
        real_time=False,
        offline=True,
    )
    caller_first = array("h", [1_100] * 2_400).tobytes()
    caller_second = array("h", [2_200] * 2_400).tobytes()
    assistant_first = array("h", [3_300] * 2_400).tobytes()
    assistant_second = array("h", [4_400] * 2_400).tobytes()
    for label, start_ms, pcm in (
        ("caller", 160, caller_first),
        ("assistant", 5_660, assistant_first),
        ("caller", 460, caller_second),
        ("assistant", 5_960, assistant_second),
    ):
        await runner.events.put(
            (
                label,
                {
                    "type": "session.output_audio.delta",
                    "start_ms": start_ms,
                    "end_ms": start_ms + 100,
                    "delta": base64.b64encode(pcm).decode(),
                },
            )
        )

    await runner._drain_events()

    assert runner.audio["caller"] == caller_first + bytes(9_600) + caller_second
    assert runner.audio["assistant"] == assistant_first + bytes(9_600) + assistant_second
    assert runner.received_audio_bytes == {"caller": 19_200, "assistant": 19_200}


@pytest.mark.asyncio
async def test_dual_gpt_live_turn_waits_for_gap_inclusive_relay_boundary(tmp_path: Path) -> None:
    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    controls = SimulatorControlTools()
    runner = DualGptLiveRunner(
        scenario,
        caller=OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200),
        assistant=OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200),
        caller_tools=controls,
        application_tools=application,
        real_time=False,
        offline=True,
    )
    first = array("h", [1_100] * 2_400).tobytes()
    second = array("h", [2_200] * 2_400).tobytes()
    for start_ms, pcm in ((160, first), (460, second)):
        await runner.events.put(
            (
                "caller",
                {
                    "type": "session.output_audio.delta",
                    "start_ms": start_ms,
                    "end_ms": start_ms + 100,
                    "delta": base64.b64encode(pcm).decode(),
                },
            )
        )
    await runner.events.put(
        (
            "caller",
            {"type": "session.output_transcript.delta", "start_ms": 5000, "end_ms": 5400, "delta": "caller output"},
        )
    )

    await runner._drain_events()
    runner._pop_audio("caller", len(first))
    runner._project_completed_turns("caller")
    assert runner.timeline.user_utterances == []
    runner._pop_audio("caller", 9_600)
    runner._project_completed_turns("caller")
    assert runner.timeline.user_utterances == []
    runner._pop_audio("caller", len(second))
    runner.timeline.add_audio("user", 0, 100, True)
    runner.timeline.add_audio("user", 300, 400, True)
    runner.input_ms = 1000
    runner._project_completed_turns("caller")

    assert [item.text for item in runner.timeline.user_utterances] == ["caller output"]


@pytest.mark.asyncio
async def test_dual_gpt_live_does_not_duplicate_already_relayed_silence_after_duplicate_frame() -> None:
    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    controls = SimulatorControlTools()
    runner = DualGptLiveRunner(
        scenario,
        caller=OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200),
        assistant=OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200),
        caller_tools=controls,
        application_tools=application,
        real_time=False,
        offline=True,
    )
    first = array("h", [1_100] * 2_400).tobytes()
    second = array("h", [2_200] * 2_400).tobytes()

    async def queue_frame(start_ms: int, pcm: bytes) -> None:
        await runner.events.put(
            (
                "caller",
                {
                    "type": "session.output_audio.delta",
                    "start_ms": start_ms,
                    "end_ms": start_ms + 100,
                    "delta": base64.b64encode(pcm).decode(),
                },
            )
        )
        await runner._drain_events()

    await queue_frame(0, first)
    assert runner._pop_audio("caller", 9_600) == first + bytes(4_800)
    await queue_frame(0, first)
    await queue_frame(300, second)

    assert runner.audio["caller"] == bytes(4_800) + second
    assert runner.received_audio_bytes["caller"] == 14_400


def test_verified_outcome_plus_natural_closing_is_a_lifecycle_signal(tmp_path: Path) -> None:
    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    for index, expected in enumerate(scenario.expected.tools.required, start=1):
        application.execute(expected.name, expected.arguments, call_id=f"test-{index}")
    controls = SimulatorControlTools()
    runner = DualGptLiveRunner(
        scenario,
        caller=OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200),
        assistant=OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200),
        caller_tools=controls,
        application_tools=application,
        real_time=False,
        save_conversations=tmp_path / "audio",
        offline=True,
    )
    runner.timeline.add_user_utterance(1_000, 1_500, "Perfect, thank you. Goodbye.")

    assert runner._verified_outcome() is True
    assert runner._caller_closed() is True


def test_dual_gpt_live_classifies_overlapping_acknowledgements_and_interruptions(tmp_path: Path) -> None:
    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    controls = SimulatorControlTools()
    runner = DualGptLiveRunner(
        scenario,
        caller=OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200),
        assistant=OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200),
        caller_tools=controls,
        application_tools=application,
        real_time=False,
        save_conversations=tmp_path / "audio",
        offline=True,
    )
    runner.caller_actions["OPENING"] = 1
    runner.timeline.add_audio("assistant", 1_000, 2_000, True)

    assert runner._caller_action("Mm-hmm.", 1_200, 1_500) == "BACKCHANNEL"
    assert runner._caller_action("Actually, make it eight.", 1_200, 1_800) == "INTERRUPT"
    assert runner._caller_action("Right.", 2_200, 2_500) == "SPEAK"


@pytest.mark.asyncio
async def test_offline_dual_gpt_live_relay_completes_booking_and_derives_metrics_post_hoc(tmp_path: Path) -> None:
    scenario = restaurant_booking()
    resources = assistant_resources()
    facts = resources.load_facts()
    application = resources.create_executor(scenario.application.initial_state, facts)
    controls = SimulatorControlTools()
    caller = OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200)
    assistant = OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200)
    event_path = tmp_path / "events.jsonl"

    result = await DualGptLiveRunner(
        scenario,
        caller=caller,
        assistant=assistant,
        caller_tools=controls,
        application_tools=application,
        tick_ms=200,
        max_duration_s=30,
        real_time=False,
        save_conversations=tmp_path / "audio",
        event_log_path=event_path,
        debug_artifacts=True,
        offline=True,
        caller_voice="cedar",
        agent_voice="marin",
    ).run()

    assert result.task_status == "passed"
    assert result.task_metrics["task_completed"] is True
    assert application.snapshot()["reservation_created"] is True
    assert controls.finished is True
    assert result.interaction_metrics["response_rate"] == 1.0
    assert result.run_metadata["metric_derivation"] == "post_hoc_audio_and_events"
    assert result.run_metadata["caller_voice"] == "cedar"
    assert result.run_metadata["agent_voice"] == "marin"
    assert result.artifacts is not None
    audio_exists, ticks_exist, event_text = await asyncio.gather(
        asyncio.to_thread(Path(result.artifacts["audio"]).exists),
        asyncio.to_thread(Path(result.artifacts["ticks"]).exists),
        asyncio.to_thread(event_path.read_text, encoding="utf-8"),
    )
    assert audio_exists
    assert ticks_exist
    records = [json.loads(line) for line in event_text.splitlines()]
    assert any(record["type"] == "dual_gpt_live.tick" for record in records)
    assert not any(record["type"].startswith("simulator.floor") for record in records)


@pytest.mark.asyncio
async def test_dual_gpt_live_captures_final_assistant_usage_without_counting_caller(tmp_path: Path) -> None:
    scenario = restaurant_booking()
    resources = assistant_resources()
    application = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    controls = SimulatorControlTools()
    caller = OfflineCallerParticipant(scenario, controls, sample_rate=24_000, tick_ms=200)
    assistant = OfflineRestaurantParticipant(scenario, application, sample_rate=24_000, tick_ms=200)

    async def close_caller() -> None:
        caller.closed = True
        await caller.events.put({"type": "session.closed", "usage": {"seconds": 99.0}})

    async def close_assistant() -> None:
        assistant.closed = True
        await assistant.events.put({"type": "session.usage.updated", "usage": {"seconds": 9.0}})
        await assistant.events.put({"type": "session.closed", "usage": {"seconds": 90.0}})

    caller.close = close_caller  # type: ignore[method-assign]
    assistant.close = close_assistant  # type: ignore[method-assign]
    event_path = tmp_path / "usage-events.jsonl"
    runner = DualGptLiveRunner(
        scenario,
        caller=caller,
        assistant=assistant,
        caller_tools=controls,
        application_tools=application,
        tick_ms=200,
        max_duration_s=30,
        real_time=False,
        event_log_path=event_path,
        offline=True,
        simulator_backend_model="gpt-5.6-sol",
    )
    for event in (
        {
            "type": "session.delegation.created",
            "delegation": {"id": "caller-handoff", "target": "responses", "response_id": "caller-response"},
        },
        {"type": "response.created", "response": {"id": "caller-response"}},
        {
            "type": "response.completed",
            "response": {"id": "caller-response", "usage": {"input_tokens": 666, "output_tokens": 333}},
        },
    ):
        await runner.events.put(("caller", event))
    result = await runner.run()
    tokens = _token_counts(result)

    assert tokens["frontend_audio_duration_ms"] == 90_000
    assert tokens.get("frontend_total_tokens") is None
    assert tokens.get("frontend_input_tokens") is None
    assert tokens.get("frontend_output_tokens") is None
    assert tokens["backend_total_tokens"] == 72  # Two target responses at 24 input + 12 output tokens each.
    assert result.delegation_count == 1
    assert result.efficiency_metrics["unique_tool_invocation_count"] == len(scenario.expected.tools.required)
    assert any(usage.get("source") == "caller_gpt_live" and usage.get("input_tokens") == 666 for usage in result.usage)
    assert not any(
        event["response_id"] == "caller-response" for event in result.run_metadata["delegation_lifecycle_events"]
    )
    records = [json.loads(line) for line in event_path.read_text(encoding="utf-8").splitlines()]
    shutdowns = [record for record in records if record.get("type") == "session.closed"]
    assert {record["source"] for record in shutdowns} == {"caller_gpt_live", "assistant_gpt_live"}
