"""Independent semantic completion decisions must never control live conversation turns."""

from __future__ import annotations

import asyncio
import base64
import json
from functools import cached_property
from types import SimpleNamespace
from typing import Any

import pytest

from assistants.resources import assistant_resources
from assistants.runtime import RemoteToolObserver
from run_harness.evaluate import DEFAULT_DATA_JSON, load_run_scenarios, parse_args
from run_harness.simulation.gpt_live_participants import (
    OfflineCallerParticipant,
    OfflineRestaurantParticipant,
    SimulatorControlTools,
)
from run_harness.simulation.gpt_live_runner import DualGptLiveRunner
from run_harness.simulation.semantic_completion import SemanticCompletionDecision, SemanticCompletionObserver
from shared.metrics.interaction import build_ticks, compute_interaction_metrics
from shared.observability.timeline import Turn


class FakeResponses:
    def __init__(
        self,
        decision: SemanticCompletionDecision | None,
        *,
        error: Exception | None = None,
        delay_seconds: float = 0,
    ) -> None:
        self.decision = decision
        self.error = error
        self.delay_seconds = delay_seconds
        self.calls: list[dict[str, Any]] = []

    async def parse(self, **kwargs: Any) -> SimpleNamespace:
        self.calls.append(kwargs)
        if self.delay_seconds:
            await asyncio.sleep(self.delay_seconds)
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            output_parsed=self.decision,
            usage=SimpleNamespace(model_dump=lambda *, exclude_none: {"input_tokens": 80, "output_tokens": 18}),
        )


def scenario(identifier: str = "restaurant_booking_complete"):
    return load_run_scenarios(DEFAULT_DATA_JSON, scenario_id=identifier)[0]


def observer_for(
    decision: SemanticCompletionDecision | None,
    *,
    error: Exception | None = None,
    delay_seconds: float = 0,
    timeout_seconds: float = 1,
) -> tuple[SemanticCompletionObserver, FakeResponses]:
    responses = FakeResponses(decision, error=error, delay_seconds=delay_seconds)
    observer = SemanticCompletionObserver(
        SimpleNamespace(responses=responses),  # type: ignore[arg-type]
        model="completion-test-model",
        timeout_seconds=timeout_seconds,
    )
    return observer, responses


def make_runner(identifier: str = "restaurant_booking_complete", *, observer: SemanticCompletionObserver | None = None):
    selected = scenario(identifier)
    resources = assistant_resources()
    application = resources.create_executor(selected.application.initial_state, resources.load_facts())
    controls = SimulatorControlTools()
    return DualGptLiveRunner(
        selected,
        caller=OfflineCallerParticipant(selected, controls, sample_rate=24_000, tick_ms=200),
        assistant=OfflineRestaurantParticipant(selected, application, sample_rate=24_000, tick_ms=200),
        caller_tools=controls,
        application_tools=application,
        real_time=False,
        offline=True,
        completion_observer=observer,
    )


def add_conversation(runner: DualGptLiveRunner, closing: str) -> None:
    opening = runner.scenario.input.text
    runner.timeline.add_turn(Turn("user", 0, 500, opening, "caller-opening"))
    runner.timeline.add_user_utterance(0, 500, opening, source="caller_gpt_live", action="OPENING")
    runner.caller_actions["OPENING"] += 1
    runner.timeline.add_turn(Turn("assistant", 600, 1_100, "Your request is complete.", "assistant-answer"))
    runner.timeline.add_turn(Turn("user", 1_200, 1_600, closing, "caller-closing"))
    runner.timeline.add_user_utterance(1_200, 1_600, closing, source="caller_gpt_live", action="SPEAK")
    runner.caller_actions["SPEAK"] += 1
    runner.input_ms = 1_600


@pytest.mark.asyncio
async def test_semantic_observer_prewarms_responses_without_sending_a_request() -> None:
    expected = SemanticCompletionDecision(should_drain=False, outcome="unresolved", reason="Still waiting.")

    class LazyClient:
        def __init__(self) -> None:
            self.initializations = 0

        @cached_property
        def responses(self) -> FakeResponses:
            self.initializations += 1
            return FakeResponses(expected)

    client = LazyClient()
    observer = SemanticCompletionObserver(client, model="completion-test-model")  # type: ignore[arg-type]

    assert client.initializations == 1
    assert client.responses.calls == []

    selected = scenario()
    for _ in range(2):
        decision = await observer.assess(
            selected,
            turns=[],
            initial_state={},
            observed_state={},
            state_verified=False,
            tool_executions=[],
            assistant_work_pending=False,
        )
        assert decision == expected

    assert client.initializations == 1
    assert len(client.responses.calls) == 2


@pytest.mark.asyncio
async def test_semantic_observer_receives_grounded_evidence_without_assistant_grading_answers() -> None:
    selected = scenario()
    expected = SemanticCompletionDecision(
        should_drain=True,
        outcome="resolved",
        reason="The verified booking is confirmed and the caller has no further questions.",
    )
    observer, responses = observer_for(expected)

    decision = await observer.assess(
        selected,
        turns=[
            Turn("assistant", 0, 300, "Your reservation is confirmed."),
            Turn("user", 400, 700, "Das war alles, wunderbar."),
        ],
        initial_state={},
        observed_state={"reservation_created": True},
        state_verified=True,
        tool_executions=[{"name": "create_reservation", "status": "completed", "output": {"ok": True}}],
        assistant_work_pending=False,
    )

    request = responses.calls[0]
    payload = json.loads(request["input"][1]["content"])
    assert decision == expected
    assert request["model"] == "completion-test-model"
    assert request["store"] is False
    assert request["text_format"] is SemanticCompletionDecision
    assert payload["caller_goal"] == selected.simulation_goal
    assert payload["expected_state_verified"] is True
    assert payload["conversation"][-1]["text"] == "Das war alles, wunderbar."
    assert selected.expected.answer not in request["input"][1]["content"]
    assert observer.usage == [{"input_tokens": 80, "output_tokens": 18}]
    assert observer.assessments[0]["outcome"] == "resolved"


@pytest.mark.asyncio
async def test_semantic_observer_times_out_without_blocking_indefinitely() -> None:
    observer, _ = observer_for(
        SemanticCompletionDecision(should_drain=False, outcome="unresolved", reason="Still waiting."),
        delay_seconds=0.1,
        timeout_seconds=0.01,
    )

    with pytest.raises(TimeoutError, match="observer timed out"):
        await observer.assess(
            scenario(),
            turns=[],
            initial_state={},
            observed_state={},
            state_verified=False,
            tool_executions=[],
            assistant_work_pending=False,
        )


@pytest.mark.asyncio
async def test_semantic_observer_rejects_a_missing_structured_decision() -> None:
    observer, _ = observer_for(None)

    with pytest.raises(RuntimeError, match="no structured decision"):
        await observer.assess(
            scenario(),
            turns=[],
            initial_state={},
            observed_state={},
            state_verified=False,
            tool_executions=[],
            assistant_work_pending=False,
        )


@pytest.mark.asyncio
async def test_semantic_drain_recognizes_finality_without_english_goodbye_keywords() -> None:
    observer, _ = observer_for(
        SemanticCompletionDecision(should_drain=True, outcome="resolved", reason="The caller is completely satisfied.")
    )
    runner = make_runner(observer=observer)
    for index, required in enumerate(runner.scenario.expected.tools.required):
        runner.application_tools.execute(required.name, required.arguments, call_id=f"tool-{index}")
    add_conversation(runner, "Perfekt, das war alles.")

    assert runner._caller_closed() is False
    assert runner._advance_semantic_completion() is None
    await asyncio.sleep(0)
    decision = runner._advance_semantic_completion()

    assert decision is not None
    assert decision.should_drain is True
    # A session-level completion decision does not independently classify this
    # utterance as non-requesting, even if its drain eventually succeeds.
    assert runner.timeline.user_utterances[-1].action == "SPEAK"
    assert "STOP" not in runner.caller_actions


@pytest.mark.asyncio
async def test_semantic_success_cannot_bypass_missing_expected_application_state() -> None:
    observer, _ = observer_for(
        SemanticCompletionDecision(should_drain=True, outcome="resolved", reason="The caller appears satisfied.")
    )
    runner = make_runner(observer=observer)
    add_conversation(runner, "That is everything I needed.")

    assert runner._advance_semantic_completion() is None
    await asyncio.sleep(0)

    assert runner._advance_semantic_completion() is None
    assert runner._verified_outcome() is False
    assert runner.caller_actions["SPEAK"] == 1
    assert "STOP" not in runner.caller_actions


@pytest.mark.asyncio
async def test_semantic_observer_supports_terminal_refusals_with_unchanged_state() -> None:
    observer, _ = observer_for(
        SemanticCompletionDecision(
            should_drain=True,
            outcome="refused",
            reason="The unauthorized request was refused and the caller accepted the decision.",
        )
    )
    runner = make_runner("restaurant_cancel_unauthorized", observer=observer)
    add_conversation(runner, "Verstanden, das war's.")

    assert runner._verified_outcome() is True
    assert runner._advance_semantic_completion() is None
    await asyncio.sleep(0)
    decision = runner._advance_semantic_completion()

    assert decision is not None
    assert decision.outcome == "refused"
    assert "STOP" not in runner.caller_actions


@pytest.mark.asyncio
async def test_semantic_observer_failure_activates_the_existing_deterministic_fallback() -> None:
    observer, _ = observer_for(None, error=RuntimeError("observer unavailable"))
    runner = make_runner(observer=observer)
    add_conversation(runner, "Thanks, goodbye.")

    assert runner._advance_semantic_completion() is None
    await asyncio.sleep(0)

    assert runner._advance_semantic_completion() is None
    assert "observer unavailable" in runner._completion_fallback_reason


def test_assistant_drain_waits_for_a_quiet_audio_tail_and_outstanding_work() -> None:
    runner = make_runner()
    runner.input_ms = 3_200
    runner.timeline.last_assistant_speech_ms = 2_800
    runner.timeline.add_turn(Turn("assistant", 2_000, 2_800, "The answer is complete.", "final-answer"))

    assert runner._assistant_drain_complete(1_500) is False
    runner.input_ms = 3_400
    assert runner._assistant_drain_complete(1_500) is True
    runner.audio["assistant"].extend(bytes(960))
    assert runner._assistant_drain_complete(1_500) is True
    runner.audio["assistant"].extend((1_200).to_bytes(2, byteorder="little", signed=True) * 480)
    assert runner._assistant_drain_complete(1_500) is False


def test_semantic_drain_is_enabled_by_default_and_can_be_configured() -> None:
    defaults = parse_args([])
    disabled = parse_args(["--no-semantic-drain"])
    custom = parse_args(["--completion-model", "observer-model", "--completion-timeout-seconds", "3.5"])

    assert defaults.semantic_drain is True
    assert defaults.completion_model == "gpt-5.6-terra"
    assert defaults.completion_timeout_seconds == 8.0
    assert disabled.semantic_drain is False
    assert custom.completion_model == "observer-model"
    assert custom.completion_timeout_seconds == 3.5


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["assistant_turn", "application_state", "tool_execution", "pending_work"])
async def test_semantic_completion_rechecks_changed_evidence_without_a_new_caller_turn(change: str) -> None:
    observer, responses = observer_for(
        SemanticCompletionDecision(should_drain=False, outcome="unresolved", reason="Still waiting.")
    )
    runner = make_runner(observer=observer)
    observed = RemoteToolObserver(initial_state=runner.initial_application_state, facts={})
    runner.application_tools = observed
    add_conversation(runner, "I'll wait for the result.")
    runner._advance_semantic_completion()
    await asyncio.sleep(0)
    runner._advance_semantic_completion()

    if change == "assistant_turn":
        runner.timeline.add_turn(Turn("assistant", 1_800, 2_000, "The booking is now confirmed.", "final-answer"))
    elif change == "application_state":
        observed.observe({"application_state": {"reservation_created": True}})
    elif change == "tool_execution":
        observed.observe(
            {"tool_execution": {"call_id": "booking", "name": "create_reservation", "status": "completed"}}
        )
    else:
        runner.timeline.delegation_active = True
    runner.input_ms = 2_200
    runner._advance_semantic_completion()
    await asyncio.sleep(0)

    assert len(responses.calls) == 2
    first, latest = (json.loads(call["input"][1]["content"]) for call in responses.calls)
    assert first != latest
    assert len(runner.timeline.user_utterances) == 2


@pytest.mark.asyncio
async def test_pending_work_completion_and_final_answer_can_resolve_without_another_caller_turn() -> None:
    observer, responses = observer_for(
        SemanticCompletionDecision(should_drain=False, outcome="unresolved", reason="The booking is still pending.")
    )
    runner = make_runner(observer=observer)
    add_conversation(runner, "That is all I need once the booking is confirmed.")
    runner.timeline.delegation_active = True
    runner._advance_semantic_completion()
    await asyncio.sleep(0)
    assert runner._advance_semantic_completion() is None

    for index, required in enumerate(runner.scenario.expected.tools.required):
        runner.application_tools.execute(required.name, required.arguments, call_id=f"tool-{index}")
    runner.timeline.delegation_active = False
    runner.timeline.add_turn(Turn("assistant", 1_800, 2_200, "Your reservation is confirmed.", "final-answer"))
    runner.input_ms = 2_200
    responses.decision = SemanticCompletionDecision(
        should_drain=True, outcome="resolved", reason="The work is complete."
    )
    runner._advance_semantic_completion()
    await asyncio.sleep(0)

    decision = runner._advance_semantic_completion()
    assert decision is not None and decision.outcome == "resolved"
    assert len(responses.calls) == 2
    assert runner._verified_outcome()


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_source", ["semantic", "finish_tool"])
async def test_caller_backend_work_blocks_completion_until_its_response_finishes(finish_source: str) -> None:
    observer, responses = observer_for(
        SemanticCompletionDecision(should_drain=True, outcome="refused", reason="The caller accepted the refusal.")
    )
    runner = make_runner("restaurant_cancel_unauthorized", observer=observer if finish_source == "semantic" else None)
    runner.simulator_backend_model = "gpt-5.6-sol"
    add_conversation(runner, "That is all, thanks.")
    if finish_source == "finish_tool":
        runner.caller_tools.execute("finish_conversation", {}, call_id="finished")
    await runner.events.put(
        (
            "caller",
            {"type": "session.delegation.created", "delegation": {"target": "responses", "response_id": "caller-work"}},
        )
    )
    await runner._drain_events()

    assert runner._advance_completion_lifecycle() is False
    await asyncio.sleep(0)
    runner.input_ms = 5_000
    assert runner._advance_completion_lifecycle() is False
    assert runner.completion_signal == ""
    assert responses.calls == []

    await runner.events.put(("caller", {"type": "response.completed", "response": {"id": "caller-work"}}))
    await runner._drain_events()
    assert runner._advance_completion_lifecycle() is False
    await asyncio.sleep(0)
    assert runner._advance_completion_lifecycle() is False
    assert runner.completion_signal
    runner.input_ms += 1_600
    assert runner._advance_completion_lifecycle() is True


@pytest.mark.asyncio
@pytest.mark.parametrize("decision_accepted", [False, True])
async def test_new_caller_backend_work_invalidates_inflight_or_accepted_completion(decision_accepted: bool) -> None:
    observer, responses = observer_for(
        SemanticCompletionDecision(should_drain=True, outcome="refused", reason="The caller accepted the refusal.")
    )
    runner = make_runner("restaurant_cancel_unauthorized", observer=observer)
    runner.simulator_backend_model = "gpt-5.6-sol"
    add_conversation(runner, "That is all, thanks.")
    runner._advance_completion_lifecycle()
    await asyncio.sleep(0)
    if decision_accepted:
        runner._advance_completion_lifecycle()
        assert runner.completion_signal

    runner.input_ms = 2_000
    await runner.events.put(("caller", {"type": "response.created", "response": {"id": "caller-followup"}}))
    await runner._drain_events()
    assert runner._advance_completion_lifecycle() is False
    assert runner.completion_signal == ""

    runner.input_ms = 2_400
    await runner.events.put(("caller", {"type": "response.completed", "response": {"id": "caller-followup"}}))
    await runner._drain_events()
    runner._advance_completion_lifecycle()
    await asyncio.sleep(0)
    runner._advance_completion_lifecycle()
    assert len(responses.calls) == 2
    # Backend work alone changed; recheck even though the spoken turns are identical.
    assert responses.calls[0]["input"] == responses.calls[1]["input"]
    runner.input_ms = 3_300
    assert runner._advance_completion_lifecycle() is False
    runner.input_ms = 4_000
    assert runner._advance_completion_lifecycle() is True


@pytest.mark.asyncio
@pytest.mark.parametrize("should_drain", [False, True])
async def test_semantic_completion_discards_stale_decisions_and_assesses_the_new_revision(should_drain: bool) -> None:
    observer, responses = observer_for(
        SemanticCompletionDecision(
            should_drain=should_drain,
            outcome="refused" if should_drain else "unresolved",
            reason="Decision for the older conversation.",
        )
    )
    runner = make_runner("restaurant_cancel_unauthorized", observer=observer)
    add_conversation(runner, "I understand.")
    runner._advance_semantic_completion()
    runner.timeline.add_turn(Turn("assistant", 1_800, 2_000, "Do you want help with anything else?", "follow-up"))
    runner.input_ms = 2_200
    await asyncio.sleep(0)

    assert runner._advance_semantic_completion() is None
    assert "STOP" not in runner.caller_actions
    await asyncio.sleep(0)
    assert len(responses.calls) == 2


@pytest.mark.asyncio
async def test_unchanged_completion_evidence_is_rate_limited_but_has_an_idle_recheck() -> None:
    observer, responses = observer_for(
        SemanticCompletionDecision(should_drain=False, outcome="unresolved", reason="The caller may continue.")
    )
    runner = make_runner(observer=observer)
    add_conversation(runner, "I'll wait.")
    runner._advance_semantic_completion()
    await asyncio.sleep(0)
    for now_ms in range(1_600, 2_001, 20):
        runner.input_ms = now_ms
        runner._advance_semantic_completion()
        await asyncio.sleep(0)
    assert len(responses.calls) == 1

    runner.input_ms = 6_600
    runner._advance_semantic_completion()
    await asyncio.sleep(0)
    assert len(responses.calls) == 2
    for _ in range(20):
        runner._advance_semantic_completion()
        await asyncio.sleep(0)
    assert len(responses.calls) == 2


@pytest.mark.parametrize("new_evidence", ["speech", "buffered_audio", "pending_transcript", "completed_transcript"])
def test_drain_cannot_finish_over_new_or_unprojected_caller_activity(new_evidence: str) -> None:
    runner = make_runner()
    runner.input_ms = 3_400
    runner.timeline.last_assistant_speech_ms = 2_800
    runner.timeline.add_turn(Turn("assistant", 2_000, 2_800, "The answer is complete.", "final-answer"))
    if new_evidence == "speech":
        runner.timeline.add_audio("user", 3_300, 3_400, True)
    elif new_evidence == "buffered_audio":
        runner.audio["caller"].extend((1_200).to_bytes(2, byteorder="little", signed=True) * 480)
    elif new_evidence == "pending_transcript":
        runner.timeline.transcript_projection.record(
            "user",
            {
                "type": "session.output_transcript.delta",
                "delta": "Actually, change it.",
                "start_ms": 5000,
                "end_ms": 5200,
            },
            received_ms=runner.input_ms,
        )
    else:
        runner.timeline.add_user_utterance(3_000, 3_200, "Actually, change it.", action="SPEAK")

    assert runner._assistant_drain_complete(1_500) is False


def test_late_captioned_audio_revises_run_evidence_without_counting_another_action() -> None:
    runner = make_runner("restaurant_cancel_unauthorized")
    for text, start, received in [
        (" Okay,", 38800, 39660),
        (" thanks", 39000, 40180),
        (" anyway.", 39400, 40380),
        (" Bye.", 40000, 40860),
    ]:
        runner.timeline.transcript_projection.record(
            "user", {"delta": text, "start_ms": start, "end_ms": start + 200}, received_ms=received
        )
    runner.timeline.add_audio("user", 39980, 41260, True)
    runner.input_ms = 42000
    runner._project_completed_turns("caller")
    original = runner.timeline.latest_turn("user")
    original_revision, _ = runner._completion_evidence()
    assert original is not None and runner._caller_evidence_current()

    runner.timeline.add_audio("user", 42160, 42380, True)
    runner.input_ms = 42600
    runner._project_completed_turns("caller")
    assert not runner._caller_evidence_current()
    runner.input_ms = 44000
    runner._project_completed_turns("caller")
    revised = runner.timeline.latest_turn("user")
    assert revised is not None and revised.turn_id == original.turn_id and revised.end_ms == 42380
    assert len(runner.timeline.user_utterances) == 1
    assert sum(runner.caller_actions.values()) == 1
    revision, _ = runner._completion_evidence()
    assert revision > original_revision and runner._caller_evidence_current()

    runner._project_completed_turns("caller")
    assert runner._completion_evidence()[0] == revision
    # A subsequent utterance without a caption must not inherit the goodbye.
    runner.timeline.add_audio("user", 45000, 45400, True)
    runner.input_ms = 46000
    runner._project_completed_turns("caller")
    assert runner.timeline.latest_turn("user") == revised
    assert not runner._caller_evidence_current()


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_source", ["semantic", "finish_tool"])
@pytest.mark.parametrize("speaker", ["caller", "assistant"])
@pytest.mark.parametrize("transcript_arrives", [True, False])
async def test_new_speech_revokes_drain_until_its_late_transcript_is_assessed(
    finish_source: str, speaker: str, transcript_arrives: bool
) -> None:
    observer, responses = observer_for(
        SemanticCompletionDecision(should_drain=True, outcome="refused", reason="The caller accepted the refusal.")
    )
    runner = make_runner("restaurant_cancel_unauthorized", observer=observer)
    runner.max_duration_s = 5
    add_conversation(runner, "That is all, thanks.")
    pcm = (1_200).to_bytes(2, byteorder="little", signed=True) * 4_800
    runner.audio["caller"].extend(pcm)
    runner.received_audio_bytes["caller"] = len(pcm)
    runner.timeline.transcript_projection.record(
        "user",
        {
            "type": "session.output_transcript.delta",
            "start_ms": 10_000,
            "end_ms": 10_200,
            "delta": "That is all, thanks.",
        },
        received_ms=runner.input_ms,
        boundary=len(pcm),
    )
    if finish_source == "finish_tool":
        runner.caller_tools.execute("finish_conversation", {}, call_id="initial-finish")
    injected = False
    frames_since_correction = 0
    participant = runner.caller if speaker == "caller" else runner.assistant
    correction = "Actually, I need more help." if speaker == "caller" else "Actually, I cannot complete this request."

    async def quiet_send(_pcm: bytes) -> None:
        return None

    async def no_new_opening(_text: str) -> None:
        return None

    async def correct_during_drain(_pcm: bytes) -> None:
        nonlocal injected, frames_since_correction
        if runner.completion_signal and not injected:
            injected = True
            responses.decision = SemanticCompletionDecision(
                should_drain=False, outcome="unresolved", reason="The conversation now contains an unresolved request."
            )
            await participant.events.put(  # type: ignore[attr-defined]
                {"type": "session.output_audio.delta", "delta": base64.b64encode(pcm).decode()}
            )
        elif injected:
            frames_since_correction += 1
            if frames_since_correction == 8 and transcript_arrives:
                await participant.events.put(  # type: ignore[attr-defined]
                    {
                        "type": "session.output_transcript.delta",
                        "event_id": "correction",
                        "start_ms": 20_000,
                        "end_ms": 20_200,
                        "delta": correction,
                    }
                )

    runner.assistant.send_audio = quiet_send  # type: ignore[method-assign]
    runner.caller.send_audio = quiet_send  # type: ignore[method-assign]
    participant.send_audio = correct_during_drain  # type: ignore[method-assign]
    runner.caller.trigger_opening = no_new_opening  # type: ignore[method-assign]

    result = await runner.run()

    assert injected
    assert result.termination_reason == "duration_limit"
    assert "STOP" not in runner.caller_actions
    if transcript_arrives:
        assert runner.timeline.latest_turn("user" if speaker == "caller" else "assistant").transcript == correction
        assert len(responses.calls) >= 2
    else:
        assert not any(turn.transcript == correction for turn in runner.timeline.turns)
    if finish_source == "finish_tool":
        assert runner.caller_tools.finished


@pytest.mark.asyncio
@pytest.mark.parametrize("participant", ["caller", "assistant"])
async def test_a_drain_signal_does_not_hide_a_participant_disconnect(participant: str) -> None:
    runner = make_runner()
    runner.completion_signal = "semantic_conversation_resolved"
    await runner.events.put((participant, {"type": "session.closed"}))

    await runner._drain_events()

    assert runner.failure is not None
    assert runner.failure.failure_stage == f"{participant}_connection"


@pytest.mark.asyncio
async def test_unpaced_live_observer_retries_still_use_wall_time(monkeypatch: pytest.MonkeyPatch) -> None:
    observer, responses = observer_for(
        SemanticCompletionDecision(should_drain=False, outcome="unresolved", reason="The caller may continue.")
    )
    runner = make_runner(observer=observer)
    runner.offline = False
    runner.real_time = False
    add_conversation(runner, "I'll wait.")
    wall_seconds = [1_000.0]
    monkeypatch.setattr("run_harness.simulation.gpt_live_runner.time.monotonic", lambda: wall_seconds[0])
    runner._advance_semantic_completion()
    await asyncio.sleep(0)
    runner._advance_semantic_completion()

    # Fast-forwarding PCM must not turn a 5-second retry into repeated immediate
    # API requests. Only explicitly offline fixtures have a simulation clock.
    runner.input_ms = 1_000_000
    runner._advance_semantic_completion()
    await asyncio.sleep(0)
    assert len(responses.calls) == 1

    wall_seconds[0] += 5.0
    runner._advance_semantic_completion()
    await asyncio.sleep(0)
    assert len(responses.calls) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("finish_source", ["semantic", "finish_tool"])
@pytest.mark.parametrize(("final_answer_ms", "missed", "response_rate"), [(1_200, 0, 1.0), (6_400, 1, 0.5)])
async def test_session_completion_does_not_remove_the_final_response_opportunity(
    finish_source: str, final_answer_ms: int, missed: int, response_rate: float
) -> None:
    observer, _ = observer_for(
        SemanticCompletionDecision(should_drain=True, outcome="resolved", reason="Both requests are complete.")
    )
    runner = make_runner(observer=observer if finish_source == "semantic" else None)
    for index, required in enumerate(runner.scenario.expected.tools.required):
        runner.application_tools.execute(required.name, required.arguments, call_id=f"tool-{index}")
    for index, (start, end, text) in enumerate(
        [(0, 200, "Is a table available?"), (800, 1_000, "Please book that table.")]
    ):
        runner.timeline.add_audio("user", start, end, True)
        runner.timeline.add_turn(Turn("user", start, end, text, f"caller-{index}"))
        runner.timeline.add_user_utterance(start, end, text, source="caller_gpt_live", action="SPEAK")
        runner.caller_actions["SPEAK"] += 1
    for index, (start, end, text) in enumerate(
        [
            (400, 600, "A table is available."),
            (final_answer_ms, final_answer_ms + 200, "Your reservation is confirmed."),
        ]
    ):
        runner.timeline.add_audio("assistant", start, end, True)
        runner.timeline.add_turn(Turn("assistant", start, end, text, f"assistant-{index}"))
    if finish_source == "finish_tool":
        runner.caller_tools.execute("finish_conversation", {}, call_id="finished")
    runner.input_ms = final_answer_ms + 400
    assert runner._advance_completion_lifecycle() is False
    await asyncio.sleep(0)
    assert runner._advance_completion_lifecycle() is False
    runner.input_ms += 1_600
    assert runner._advance_completion_lifecycle() is True

    ticks = build_ticks(runner.timeline, 200, 24_000, duration_ms=runner.input_ms)
    metrics = compute_interaction_metrics(ticks, tick_ms=200, timeline=runner.timeline, response_deadline_ms=5_000)

    # Finality describes the session, not whether its last utterance was a request.
    # A late answer must keep its missed deadline even after successful task completion.
    assert metrics["counts"]["response_total"] == 2
    assert metrics["counts"]["no_response_count"] == missed
    assert metrics["response_rate"] == response_rate
    assert runner.timeline.user_utterances[-1].action == "SPEAK"
