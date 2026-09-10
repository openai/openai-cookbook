"""Replay recorded single-turn WAV files against the shared GPT Live assistant."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from assistants.client.transport import bind_client_delegation
from assistants.config import (
    LiveAgentSettings,
    build_assistant_session,
    build_initial_items,
    render_authorized_context,
)
from assistants.errors import LiveResponseError
from assistants.frontend.connection import AssistantConnection
from assistants.frontend.transport import DEFAULT_RESPONSE_TIMEOUT_SECONDS, validate_audio_config
from assistants.resources import AssistantResources, assistant_resources
from assistants.responses.delegation import bind_responses_delegation
from shared.artifacts import artifact_path, create_run_directory, scenario_audio_directory, validate_artifact_id
from shared.audio.conversation import ConversationRecorder, LiveMonitor
from shared.audio.pcm import read_mono_wav, write_mono_wav
from shared.config import load_harness_config
from shared.metrics.evidence import evidence_scores
from shared.metrics.interaction import build_ticks, compute_interaction_metrics, compute_turn_interaction_metrics
from shared.metrics.tokens import TokenUsage, aggregate_backend_usage
from shared.observability.timeline import Timeline
from shared.observability.trace import record_event
from shared.paths import default_results_dir, package_path, require_external_output
from shared.private_files import private_open
from shared.reporting.results import build_results_report, build_timestamped_run_name, ensure_dir, write_json
from shared.reporting.schema import SCHEMA_VERSION
from shared.scenarios import Recording, Scenario, load_scenario_dataset, resolve_recording_path
from shared.single_turn.console import SingleTurnConsoleEventLog
from shared.single_turn.observability import (
    append_single_turn_grading_trace,
    build_single_turn_observability,
    result_assessment,
)
from shared.single_turn.runtime import (
    CallerAudioCompletion,
    close_live_session,
    collect_live_response,
    open_live_connection,
    stream_audio_to_connection,
    wait_for_session_started,
)
from shared.single_turn.types import (
    EvalErrorInfo,
    ExpectedToolCall,
    ResultArtifactPaths,
    ResultLatencies,
    SingleTurnEvalResult,
    SingleTurnEvalRunConfig,
    ToolCallGrade,
    ToolCallRecord,
)
from walk_harness.graders import (
    DEFAULT_JUDGE_MODEL,
    DEFAULT_JUDGE_REASONING_EFFORT,
    apply_semantic_grades,
    expected_tool_fields,
    grade_walk_example,
    judge_semantic_dimensions,
    unassessed_semantic_dimensions,
)

HARNESS_DIR = package_path("walk_harness")
DEFAULT_CONFIG_PATH = HARNESS_DIR / "config.toml"
DEFAULT_DATA_JSON = HARNESS_DIR / "data" / "scenarios.json"
DEFAULT_CHUNK_MS = 20
DEFAULT_SAMPLE_RATE_HZ = 24_000


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Keep recorded-audio replay as small and familiar as the CRAWL CLI."""
    config = load_harness_config(argv, DEFAULT_CONFIG_PATH)
    assistant = LiveAgentSettings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=config.path)
    parser.add_argument("--data", type=Path, default=config.path_for("dataset", "path", DEFAULT_DATA_JSON))
    parser.add_argument(
        "--results-dir", type=Path, default=config.path_for("execution", "results_dir", default_results_dir("walk"))
    )
    parser.add_argument("--run-name", default="")
    parser.add_argument(
        "--example",
        "--scenario",
        dest="example",
        default="all",
        help="Run one recorded scenario or all examples.",
    )
    parser.add_argument("--max-examples", type=int, default=config.get("execution", "max_examples", 0))
    parser.add_argument(
        "--concurrency",
        type=int,
        default=config.get("execution", "concurrency", 1),
        help="Independent recorded sessions; 1–8.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=config.get("execution", "verbose", False),
        help="Print protocol events and per-scenario results (default: disabled).",
    )
    parser.add_argument("--model", default=assistant.model)
    parser.add_argument("--backend-model", default=assistant.backend_model)
    parser.add_argument(
        "--assistant",
        choices=("responses", "client"),
        default=os.getenv("OPENAI_ASSISTANT_MODE", "").strip()
        or config.get("assistant", "mode", assistant.assistant_mode),
        help="Choose the independent OpenAI-managed or application-managed target assistant.",
    )
    parser.add_argument(
        "--assistant-endpoint",
        default=os.getenv("OPENAI_CLIENT_ASSISTANT_ENDPOINT", "").strip()
        or config.get("assistant", "endpoint", assistant.client_endpoint),
        help="Optional separately deployed client-assistant WebSocket endpoint.",
    )
    parser.add_argument("--endpoint", default=assistant.endpoint)
    parser.add_argument("--voice", default=assistant.voice)
    parser.add_argument("--judge-model", default=os.getenv("OPENAI_EVAL_JUDGE_MODEL", DEFAULT_JUDGE_MODEL))
    parser.add_argument(
        "--judge-reasoning-effort",
        default=os.getenv("OPENAI_EVAL_JUDGE_REASONING_EFFORT", DEFAULT_JUDGE_REASONING_EFFORT),
    )
    parser.add_argument(
        "--response-timeout-seconds",
        type=float,
        default=config.get("execution", "response_timeout_seconds", DEFAULT_RESPONSE_TIMEOUT_SECONDS),
    )
    parser.add_argument("--chunk-ms", type=int, default=config.get("audio", "chunk_ms", DEFAULT_CHUNK_MS))
    parser.add_argument(
        "--sample-rate-hz",
        type=int,
        default=config.get("audio", "sample_rate_hz", DEFAULT_SAMPLE_RATE_HZ),
    )
    parser.add_argument(
        "--real-time",
        action=argparse.BooleanOptionalAction,
        default=config.get("audio", "real_time", True),
        help="Replay the actual WAV at its original real-time cadence.",
    )
    parser.add_argument("--listen", action="store_true", help="Monitor recording and assistant in live stereo.")
    parser.add_argument("--offline", action="store_true", help="Verify replay without model or judge requests.")
    return parser.parse_args(argv)


def load_dataset(path: Path) -> list[Scenario]:
    """Validate single-turn scenarios and their explicitly attached WAV recordings."""

    scenarios = [
        scenario
        for scenario in load_scenario_dataset(path).scenarios
        if scenario.interaction == "single_turn" and scenario.input.recordings
    ]
    if not scenarios:
        raise ValueError("The recorded-audio dataset does not contain any single-turn scenarios with recordings")
    for scenario in scenarios:
        if len(scenario.input.recordings) != 1:
            raise ValueError(f"Recorded scenario {scenario.id} requires exactly one attached WAV recording")
        recording = resolve_recording_path(path, scenario.input.recordings[0])
        if recording.suffix.lower() != ".wav" or not recording.is_file():
            raise ValueError(f"Recorded scenario {scenario.id} requires an existing .wav file: {recording}")
        scenario.input.recordings[0].path = recording
    return scenarios


def read_recorded_pcm(path: Path, *, sample_rate_hz: int = DEFAULT_SAMPLE_RATE_HZ) -> bytes:
    """Read the exact mono PCM frames that will be sent to GPT Live."""
    return read_mono_wav(path, sample_rate_hz=sample_rate_hz)


def _read_prompt(path: Path) -> str:
    prompt = path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"Assistant prompt is empty: {path}")
    return prompt


def _load_tools(path: Path) -> list[dict[str, Any]]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("Application tools must be a nonempty JSON list")
    names: set[str] = set()
    for tool in parsed:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            raise ValueError("Application tools must be function definitions")
        name = tool.get("name")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("Application tools must have unique, nonempty names")
        names.add(name)
    return parsed


def _authorized_prompt(prompt: str, scenario: Scenario, facts: dict[str, Any]) -> str:
    return render_authorized_context(
        prompt,
        facts=facts,
        initial_state=scenario.application.initial_state,
        conversation_context=scenario.input.context.summary if scenario.input.context is not None else "",
    )


@dataclass(frozen=True, slots=True)
class _PreparedInput:
    """WALK-owned input and checked output destinations."""

    example_id: str
    reference: str
    input_pcm: bytes
    audio_dir: Path
    input_path: Path
    events_path: Path
    transcript_path: Path
    user_audio_ms: int
    recording: Recording
    source_path: Path


@dataclass(frozen=True, slots=True)
class _SessionEvidence:
    """Completed session evidence; no open transport is passed to grading."""

    response: dict[str, Any]
    frontend_usage: dict[str, Any]
    session_started: dict[str, Any]
    timeline: Timeline
    recorder: ConversationRecorder
    started_at: float


async def _prepare_input(
    *,
    scenario: Scenario,
    config: SingleTurnEvalRunConfig,
    run_audio_dir: Path,
    run_events_dir: Path,
    run_transcript_dir: Path,
) -> _PreparedInput:
    """Validate and copy the recorded WAV without synthesizing caller audio."""
    example_id = validate_artifact_id(scenario.id)
    reference = scenario.input.text
    recording = scenario.input.recordings[0]
    source_path = recording.path
    input_pcm = await asyncio.to_thread(read_recorded_pcm, source_path, sample_rate_hz=config.sample_rate_hz)
    audio_dir = ensure_dir(scenario_audio_directory(run_audio_dir, example_id))
    input_path = write_mono_wav(audio_dir / "input.wav", input_pcm, config.sample_rate_hz)
    events_path = artifact_path(run_events_dir, f"{example_id}.jsonl")
    transcript_path = artifact_path(run_transcript_dir, f"{example_id}.json")
    user_audio_ms = len(input_pcm) * 1_000 // (config.sample_rate_hz * 2)
    return _PreparedInput(
        example_id,
        reference,
        input_pcm,
        audio_dir,
        input_path,
        events_path,
        transcript_path,
        user_audio_ms,
        recording,
        source_path,
    )


async def _run_session(
    *,
    scenario: Scenario,
    prepared: _PreparedInput,
    config: SingleTurnEvalRunConfig,
    resources: AssistantResources,
    business_facts: dict[str, Any],
    system_prompt: str,
    backend_system_prompt: str,
    tools: list[dict[str, Any]],
    audio_monitor: LiveMonitor | None,
) -> _SessionEvidence:
    """Own this harness's assistant setup, concurrent streaming, and teardown."""
    initial_state = scenario.application.initial_state
    example_id = prepared.example_id
    reference = prepared.reference
    input_pcm = prepared.input_pcm
    events_path = prepared.events_path
    user_audio_ms = prepared.user_audio_ms
    application_tools = resources.create_executor(
        initial_state,
        business_facts,
        remote=config.assistant_mode == "client" and bool(config.assistant_endpoint) and not config.offline,
    )
    offline_behavior = (
        resources.create_offline_behavior(
            conversation_context=scenario.conversation_context,
            initial_state=initial_state,
            facts=business_facts,
        )
        if config.offline
        else None
    )
    timeline = Timeline()
    recorder = ConversationRecorder(config.sample_rate_hz)
    timeline.add_user_utterance(0, user_audio_ms, reference, source="walk.recorded_reference")
    assistant = LiveAgentSettings(
        endpoint=config.endpoint,
        model=config.model,
        voice=config.voice,
        backend_model=config.backend_model,
        assistant_mode=config.assistant_mode,
        client_endpoint=config.assistant_endpoint,
    )
    authorized_instructions = _authorized_prompt(system_prompt, scenario, business_facts)
    authorized_backend_instructions = _authorized_prompt(backend_system_prompt, scenario, business_facts)
    initial_items = build_initial_items(scenario.input.context.history) if scenario.input.context is not None else None
    session = build_assistant_session(
        assistant,
        instructions=authorized_instructions,
        backend_instructions=authorized_backend_instructions,
        tools=tools,
        initial_items=initial_items,
    )

    with private_open(events_path) as persisted_event_log:
        console_trace = (
            SingleTurnConsoleEventLog(persisted_event_log, chunk_ms=config.chunk_ms) if config.verbose else None
        )
        event_log = console_trace if console_trace is not None else persisted_event_log
        started_at = asyncio.get_running_loop().time()
        event_index = {"value": 0}
        async with open_live_connection(
            endpoint=config.endpoint,
            model=config.model,
            api_key=os.getenv("OPENAI_API_KEY", ""),
            timeout_seconds=config.response_timeout_seconds,
            offline=config.offline,
            example_id=example_id,
            user_text=reference if config.offline else "",
            input_audio_length=len(input_pcm),
            sample_rate_hz=config.sample_rate_hz,
            offline_behavior=offline_behavior,
        ) as connection:
            await connection.send_json(session)
            record_event(
                event_log,
                session,
                started_at=started_at,
                event_index_state=event_index,
                source="live_frontend",
                direction="client_to_server",
            )
            session_started = await wait_for_session_started(
                connection,
                event_log,
                timeout_seconds=config.response_timeout_seconds,
                started_at=started_at,
                event_index_state=event_index,
            )
            assistant_connection: AssistantConnection | None = None
            if config.assistant_mode == "client" and not config.offline:
                assistant_connection = await bind_client_delegation(
                    connection,
                    config=assistant,
                    instructions=authorized_backend_instructions,
                    tools=tools,
                    executor=application_tools,
                    api_key=os.getenv("OPENAI_API_KEY", ""),
                    initial_items=initial_items,
                )
            else:
                assistant_connection = await bind_responses_delegation(connection, executor=application_tools)
            connection = assistant_connection
            response: dict[str, Any] | None = None
            audio_sender: asyncio.Task[None] | None = None
            response_receiver: asyncio.Task[dict[str, Any]] | None = None
            completion = CallerAudioCompletion()
            try:
                audio_sender = asyncio.create_task(
                    stream_audio_to_connection(
                        connection,
                        input_pcm,
                        config.chunk_ms,
                        config.sample_rate_hz,
                        config.real_time,
                        log_file=event_log,
                        started_at=started_at,
                        event_index_state=event_index,
                        timeline=timeline,
                        recorder=recorder,
                        audio_monitor=audio_monitor,
                        caller_audio_completion=completion,
                    ),
                    name=f"walk-recorded-audio-{example_id}",
                )
                response_receiver = asyncio.create_task(
                    collect_live_response(
                        connection,
                        event_log,
                        chunk_ms=config.chunk_ms,
                        sample_rate_hz=config.sample_rate_hz,
                        timeout_seconds=config.response_timeout_seconds,
                        trace_started_at=started_at,
                        event_index_state=event_index,
                        tool_observer=application_tools,
                        timeline=timeline,
                        recorder=recorder,
                        audio_monitor=audio_monitor,
                        tool_source="assistant_application",
                        caller_audio_completion=completion,
                    ),
                    name=f"walk-live-receiver-{example_id}",
                )
                _, response = await asyncio.gather(audio_sender, response_receiver)
            finally:
                try:
                    pending = [task for task in (audio_sender, response_receiver) if task and not task.done()]
                    for task in pending:
                        task.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                    if recorder.user or recorder.assistant:
                        recorder.save(prepared.audio_dir / "conversation.wav", timeline.evaluation_transcript())
                    frontend_usage = await close_live_session(
                        connection,
                        event_log,
                        trace_started_at=started_at,
                        event_index_state=event_index,
                        timeline=timeline,
                    )
                finally:
                    if assistant_connection is not None:
                        await assistant_connection.close()
                    if console_trace is not None:
                        console_trace.finish()

    if audio_monitor is not None:
        drained = await asyncio.to_thread(audio_monitor.wait_until_drained, config.response_timeout_seconds)
        if not drained:
            raise LiveResponseError("Recorded audio playback did not finish before timeout", failure_stage="playback")
    if response is None:
        raise LiveResponseError("GPT Live did not produce a response", failure_stage="response_collection")
    output_pcm = response["output_audio_bytes"]
    if not output_pcm:
        raise LiveResponseError("GPT Live completed without assistant audio", failure_stage="output_audio")

    return _SessionEvidence(response, frontend_usage, session_started, timeline, recorder, started_at)


async def _grade_and_write_result(
    *,
    scenario: Scenario,
    prepared: _PreparedInput,
    evidence: _SessionEvidence,
    config: SingleTurnEvalRunConfig,
    business_facts: dict[str, Any],
    judge_client: AsyncOpenAI | None,
) -> SingleTurnEvalResult:
    """Grade this phase's evidence and write its transcript and result contract."""
    initial_state = scenario.application.initial_state
    example_id = prepared.example_id
    reference = prepared.reference
    audio_dir = prepared.audio_dir
    input_path = prepared.input_path
    events_path = prepared.events_path
    transcript_path = prepared.transcript_path
    user_audio_ms = prepared.user_audio_ms
    recording = prepared.recording
    source_path = prepared.source_path
    response = evidence.response
    frontend_usage = evidence.frontend_usage
    session_started = evidence.session_started
    timeline = evidence.timeline
    recorder = evidence.recorder
    started_at = evidence.started_at
    output_pcm = response["output_audio_bytes"]
    output_path = write_mono_wav(audio_dir / "output.wav", output_pcm, config.sample_rate_hz)
    conversation_path, conversation_transcript_path = recorder.save(
        audio_dir / "conversation.wav", timeline.evaluation_transcript()
    )
    tool_calls = [ToolCallRecord.from_mapping(item) for item in response["tool_calls"]]
    ticks = build_ticks(
        timeline,
        config.chunk_ms,
        config.sample_rate_hz,
        duration_ms=user_audio_ms,
        user_track=recorder.user,
        assistant_track=recorder.assistant,
    )
    interaction = compute_interaction_metrics(ticks, tick_ms=config.chunk_ms, timeline=timeline)
    grades = grade_walk_example(
        scenario,
        tool_calls,
        timeline,
        interaction_metrics=interaction,
        turn_metrics=compute_turn_interaction_metrics(ticks, timeline),
        user_audio_ms=user_audio_ms,
        run_name=config.run_name,
        tts_model="",
        offline=config.offline,
        audio_source="recorded",
        tool_executions=response["tool_executions"],
        final_state=response["final_state"],
        initial_state=initial_state,
        delegations=response["delegations"],
        post_tool_assistant_text=response["post_tool_assistant_text"],
    )
    result = grades.source_result
    if config.offline:
        semantic_grades = {name: grade.to_dict() for name, grade in unassessed_semantic_dimensions(scenario).items()}
        judge_usage: list[dict[str, Any]] = []
    else:
        if judge_client is None:
            raise LiveResponseError("An independent semantic judge is required", failure_stage="semantic_judge")
        assessed, judge_usage = await judge_semantic_dimensions(
            scenario,
            assistant_text=response["assistant_turn_transcript"] or response["assistant_text"],
            delegations=response["delegations"],
            backend_messages=response["backend_messages"],
            tool_executions=response["tool_executions"],
            final_state=response["final_state"],
            facts=business_facts,
            client=judge_client,
            model=config.judge_model,
            reasoning_effort=config.judge_reasoning_effort,
        )
        semantic_grades = {name: grade.to_dict() for name, grade in assessed.items()}

    rubrics = apply_semantic_grades(result, semantic_grades)
    if rubrics is not None:
        grades.evidence_metrics.update(
            evidence_scores(
                result.task_metrics,
                result.efficiency_metrics,
                {
                    "total_turns": 2,
                    "tool_calls": [{"count": 1} for _ in scenario.expected.tools.required],
                },
            )
        )
    deterministic = {name: grade.to_dict() for name, grade in grades.dimension_grades.items()}
    observability = build_single_turn_observability(
        scenario,
        result,
        audio_source="recorded",
        deterministic_grades=deterministic,
        semantic_grades=semantic_grades,
    )
    assessment = result_assessment(result)
    append_single_turn_grading_trace(
        events_path,
        scenario=scenario,
        result=result,
        deterministic_grades=deterministic,
        semantic_grades=semantic_grades,
        started_at=started_at,
    )
    delegations = response["delegations"]
    first_delegation = delegations[0] if delegations else {}
    started_session = session_started.get("session", {})
    transcript = {
        "schema_version": SCHEMA_VERSION,
        "example_id": example_id,
        "session_id": started_session.get("id") if isinstance(started_session, dict) else None,
        "mode": "offline_fixture" if config.offline else "live",
        "audio_source": "recorded",
        "recording": recording.model_dump(mode="json"),
        "source_audio_path": str(source_path),
        "scenario_type": scenario.scenario_type,
        "context_mode": scenario.context_mode,
        "initial_state": initial_state,
        "conversation_audio_path": str(conversation_path),
        "conversation_transcript_path": str(conversation_transcript_path),
        "input_reference": reference,
        "input_projected": response["input_transcript"],
        "input_fragments": response["input_fragments"],
        "assistant_projected": response["assistant_text"],
        "assistant_turn_transcript": response["assistant_turn_transcript"],
        "post_tool_assistant_text": response["post_tool_assistant_text"],
        "backend_messages": response["backend_messages"],
        "backend_usage_events": response["backend_usage_events"],
        "turns": response["turns"],
        "delegations": delegations,
        "expected_delegation": scenario.expected.delegation,
        "expected_tool_calls": [tool.model_dump() for tool in scenario.expected.tools.required],
        "tool_calls": [call.to_dict() for call in tool_calls],
        "tool_executions": response["tool_executions"],
        "final_state": response["final_state"],
        "evaluation_transcript": timeline.evaluation_transcript(),
        "agent_events": [event.model_dump() for event in timeline.agent_events],
        "task_metrics": result.task_metrics,
        "interaction_metrics": interaction,
        "turn_metrics": result.turn_metrics,
        "efficiency_metrics": result.efficiency_metrics,
        "evidence_metrics": grades.evidence_metrics,
        "rubric_metrics": rubrics,
        "dimension_grades": deterministic,
        "semantic_grades": semantic_grades,
        "judge_usage_events": judge_usage,
        "assessment": assessment,
        "observability": observability,
    }
    write_json(transcript_path, transcript)
    return SingleTurnEvalResult(
        example_id=example_id,
        user_text=reference,
        expected_tool_call=ExpectedToolCall(*expected_tool_fields(scenario)),
        expected_tool_calls=[
            ExpectedToolCall(tool.name, json.dumps(tool.arguments, ensure_ascii=False, sort_keys=True))
            for tool in scenario.expected.tools.required
        ],
        assistant_text=response["assistant_text"],
        tool_calls=tool_calls,
        tool_call_grade=grades.tool_call,
        artifact_paths=ResultArtifactPaths(
            input_audio_path=input_path,
            event_log_path=events_path,
            output_audio_path=output_path,
            transcript_path=transcript_path,
            conversation_audio_path=conversation_path,
            conversation_transcript_path=conversation_transcript_path,
        ),
        latencies=ResultLatencies(
            first_audio_ms=response["first_audio_time_ms"],
            first_text_ms=response["first_text_time_ms"],
            response_done_ms=response["response_done_time_ms"],
            delegation_ms=response["delegation_time_ms"],
            first_tool_call_ms=response["first_tool_call_time_ms"],
            first_tool_completed_ms=response["first_tool_completed_time_ms"],
            backend_completed_ms=response["backend_completed_time_ms"],
        ),
        frontend_usage=TokenUsage.from_mapping(frontend_usage),
        backend_usage=TokenUsage.from_mapping(
            aggregate_backend_usage(frontend_usage["backend_model_usage"])
            if isinstance(frontend_usage.get("backend_model_usage"), list) and frontend_usage["backend_model_usage"]
            else response["backend_usage"],
            text_only=True,
        ),
        input_transcript=response["input_transcript"],
        assistant_turn_transcript=response["assistant_turn_transcript"],
        post_tool_assistant_text=response["post_tool_assistant_text"],
        backend_text=response["backend_text"],
        backend_response_count=len(response["backend_usage_events"]),
        delegation_target=str(first_delegation.get("target", "")),
        delegation_response_id=str(first_delegation.get("response_id", "")),
        delegation_item_id=str(first_delegation.get("id", "")),
        delegation_count=len(delegations),
        tool_executions=response["tool_executions"],
        final_state=response["final_state"],
        task_metrics=result.task_metrics,
        interaction_metrics=interaction,
        efficiency_metrics=result.efficiency_metrics,
        evidence_metrics=grades.evidence_metrics,
        scenario_type=scenario.scenario_type,
        context_mode=scenario.context_mode,
        expected_delegation=scenario.expected.requires_delegation,
        delegation_policy=scenario.expected.delegation,
        initial_state=initial_state,
        expected_final_state=scenario.expected.state,
        expected_response=scenario.expected.answer,
        dimension_grades=deterministic,
        semantic_grades=semantic_grades,
        rubric_metrics=rubrics,
        judge_usage_events=judge_usage,
        assessment=assessment,
        observability=observability,
    )


async def run_single_eval(
    *,
    scenario: Scenario,
    system_prompt: str,
    backend_system_prompt: str,
    tools: list[dict[str, Any]],
    run_audio_dir: Path,
    run_events_dir: Path,
    run_transcript_dir: Path,
    config: SingleTurnEvalRunConfig,
    resources: AssistantResources,
    business_facts: dict[str, Any],
    judge_client: AsyncOpenAI | None = None,
    audio_monitor: LiveMonitor | None = None,
) -> SingleTurnEvalResult:
    """Replay one WAV; transcript and expected outcome never enter the target session."""
    prepared = await _prepare_input(
        scenario=scenario,
        config=config,
        run_audio_dir=run_audio_dir,
        run_events_dir=run_events_dir,
        run_transcript_dir=run_transcript_dir,
    )
    evidence = await _run_session(
        scenario=scenario,
        prepared=prepared,
        config=config,
        resources=resources,
        business_facts=business_facts,
        system_prompt=system_prompt,
        backend_system_prompt=backend_system_prompt,
        tools=tools,
        audio_monitor=audio_monitor,
    )
    return await _grade_and_write_result(
        scenario=scenario,
        prepared=prepared,
        evidence=evidence,
        config=config,
        business_facts=business_facts,
        judge_client=judge_client,
    )


def _failed_result(
    scenario: Scenario,
    *,
    audio_dir: Path,
    events_dir: Path,
    transcripts_dir: Path,
    exc: Exception,
) -> SingleTurnEvalResult:
    example_id = validate_artifact_id(scenario.id)
    recording_dir = scenario_audio_directory(audio_dir, example_id)
    output = recording_dir / "output.wav"
    conversation = recording_dir / "conversation.wav"
    transcript = artifact_path(transcripts_dir, f"{example_id}.json")
    return SingleTurnEvalResult(
        example_id=example_id,
        user_text=scenario.input.text,
        expected_tool_call=ExpectedToolCall(*expected_tool_fields(scenario)),
        expected_tool_calls=[
            ExpectedToolCall(tool.name, json.dumps(tool.arguments, ensure_ascii=False, sort_keys=True))
            for tool in scenario.expected.tools.required
        ],
        assistant_text="",
        tool_calls=[],
        tool_call_grade=ToolCallGrade(),
        artifact_paths=ResultArtifactPaths(
            input_audio_path=recording_dir / "input.wav",
            event_log_path=artifact_path(events_dir, f"{example_id}.jsonl"),
            output_audio_path=output if output.is_file() else None,
            transcript_path=transcript if transcript.is_file() else None,
            conversation_audio_path=conversation if conversation.is_file() else None,
        ),
        latencies=ResultLatencies(),
        error_info=EvalErrorInfo(
            status="failed",
            failure_stage=str(getattr(exc, "failure_stage", "recorded_audio_replay")),
            error_type=type(exc).__name__,
            error_message=str(exc),
        ),
        delegation_policy=scenario.expected.delegation,
    )


def format_example_result(result: SingleTurnEvalResult) -> str:
    status = (
        "ERROR" if result.error_info.status != "ok" else "PASS" if result.task_metrics.get("task_completed") else "FAIL"
    )
    assistant = result.assistant_turn_transcript or result.assistant_text or "[no assistant response]"
    lines = [f"  USER       {result.user_text}", f"  ASSISTANT  {assistant}"]
    if result.tool_executions:
        for execution in result.tool_executions:
            arguments = json.dumps(execution.get("arguments", {}), ensure_ascii=False, sort_keys=True)
            lines.append(f"  TOOL       {execution.get('name', 'unknown')} {arguments} [{execution.get('status')}]")
    else:
        lines.append("  TOOL       none")
    metric_row = result.to_result_row()
    metrics = [status]
    for label, key in (("tool", "tool_accuracy"), ("response_rate", "response_rate")):
        value = metric_row.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            metrics.append(f"{label}={value:.2f}")
    metrics.append(f"tools={metric_row['tool_calls']}")
    latency = metric_row.get("response_latency_ms")
    if isinstance(latency, int | float) and not isinstance(latency, bool):
        metrics.append(f"response={latency:g}ms")
    lines.append(f"  RESULT     {' | '.join(metrics)}")
    checks = [
        f"{name}={grade['status']}"
        for name, grade in result.dimension_grades.items()
        if grade.get("status") in {"passed", "failed"}
    ]
    if checks:
        lines.append(f"  CHECKS     {' | '.join(checks)}")
    semantic = [
        f"{name}={grade['status']}"
        for name, grade in result.semantic_grades.items()
        if grade.get("status") in {"passed", "failed"}
    ]
    if semantic:
        lines.append(f"  JUDGE      {' | '.join(semantic)}")
    elif result.semantic_grades:
        lines.append("  JUDGE      not assessed (offline fixture)")
    if result.error_info.error_message:
        lines.append(f"  ERROR      {result.error_info.failure_stage}: {result.error_info.error_message}")
    return "\n".join(lines)


def _result_row(
    scenario: Scenario,
    result: SingleTurnEvalResult,
    *,
    offline: bool,
) -> dict[str, Any]:
    row = result.to_result_row()
    recording = scenario.input.recordings[0]
    row.update(
        {
            "audio_path": str(recording.path),
            "recording": recording.model_dump(mode="json"),
            "reference_transcript": scenario.input.text,
            "execution_mode": "offline_fixture" if offline else "live",
            "audio_source": "recorded",
        }
    )
    return row


def _config(
    args: argparse.Namespace,
    *,
    run_name: str,
    resources: AssistantResources,
) -> SingleTurnEvalRunConfig:
    return SingleTurnEvalRunConfig(
        run_name=run_name,
        model=args.model,
        backend_model=args.backend_model,
        endpoint=args.endpoint,
        response_timeout_seconds=args.response_timeout_seconds,
        tts_model="recorded_audio",
        voice=args.voice,
        chunk_ms=args.chunk_ms,
        sample_rate_hz=args.sample_rate_hz,
        input_audio_format="pcm16",
        output_audio_format="pcm16",
        real_time=args.real_time,
        data=args.data.resolve(),
        system_prompt_file=resources.system_prompt_file.resolve(),
        backend_system_prompt_file=resources.backend_system_prompt_file.resolve(),
        tools_file=resources.tools_file.resolve(),
        config_file=args.config.resolve(),
        offline=args.offline,
        facts_file=resources.facts_file,
        judge_model=args.judge_model,
        judge_reasoning_effort=args.judge_reasoning_effort,
        listen=args.listen,
        verbose=args.verbose,
        example=args.example,
        concurrency=args.concurrency,
        assistant_mode=args.assistant,
        assistant_endpoint=args.assistant_endpoint,
    )


def _validate_run_args(args: argparse.Namespace) -> None:
    """Validate this harness's batch policy before opening resources."""
    if args.chunk_ms <= 0:
        raise ValueError("Audio chunk duration must be greater than zero")
    if args.response_timeout_seconds <= 0:
        raise ValueError("Response timeout must be greater than zero")
    if args.max_examples < 0:
        raise ValueError("Maximum examples cannot be negative")
    if not 1 <= args.concurrency <= 8:
        raise ValueError("--concurrency must be between 1 and 8")
    if args.listen and args.concurrency != 1:
        raise ValueError("--listen requires --concurrency 1 so recordings are not mixed")
    if not args.judge_model.strip() or not args.judge_reasoning_effort.strip():
        raise ValueError("Judge model and reasoning effort must not be empty")
    if not args.offline and not os.getenv("OPENAI_API_KEY", "").strip():
        raise ValueError("OPENAI_API_KEY is required; use --offline to verify recorded replay")


async def run_evals(args: argparse.Namespace | None = None) -> Path:
    """Evaluate each recorded WAV in an isolated audio-only GPT Live session."""
    args = args or parse_args()
    _validate_run_args(args)

    examples = load_dataset(args.data)
    if args.example != "all":
        examples = [scenario for scenario in examples if scenario.id == args.example]
        if not examples:
            raise ValueError(f"Unknown WALK example: {args.example}")
    if args.max_examples:
        examples = examples[: args.max_examples]
    resources = assistant_resources(assistant_mode=args.assistant)
    run_name = build_timestamped_run_name(phase="walk", offline=args.offline, label=args.run_name)
    config = _config(args, run_name=run_name, resources=resources)
    validate_audio_config(config.sample_rate_hz, config.input_audio_format, config.output_audio_format)
    facts = resources.load_facts()
    system_prompt = _read_prompt(config.system_prompt_file)
    backend_prompt = _read_prompt(config.backend_system_prompt_file)
    tools = _load_tools(config.tools_file)
    run_dir = create_run_directory(require_external_output(args.results_dir), run_name)
    audio_dir = ensure_dir(run_dir / "audio")
    events_dir = ensure_dir(run_dir / "events")
    transcripts_dir = ensure_dir(run_dir / "transcripts")
    judge = None if config.offline else AsyncOpenAI()
    monitor = LiveMonitor(config.sample_rate_hz) if config.listen else None
    semaphore = asyncio.Semaphore(config.concurrency)
    output_lock = asyncio.Lock()
    label = "offline fixture" if config.offline else "GPT Live"
    if config.verbose:
        print(
            f"Running {label} WALK: {len(examples)} recorded examples (concurrency={config.concurrency}) -> {run_dir}",
            flush=True,
        )

    async def run_one(index: int, scenario: Scenario) -> tuple[int, dict[str, Any]]:
        async with semaphore:
            prefix = f"[{index}/{len(examples)}] {scenario.id}"
            if config.verbose:
                print(f"{prefix}{' started' if config.concurrency > 1 else ''}", flush=True)
            try:
                result = await run_single_eval(
                    scenario=scenario,
                    system_prompt=system_prompt,
                    backend_system_prompt=backend_prompt,
                    tools=tools,
                    run_audio_dir=audio_dir,
                    run_events_dir=events_dir,
                    run_transcript_dir=transcripts_dir,
                    config=config,
                    resources=resources,
                    business_facts=facts,
                    judge_client=judge,
                    audio_monitor=monitor,
                )
            except Exception as exc:  # noqa: BLE001 - preserve one infrastructure-failure row.
                result = _failed_result(
                    scenario,
                    audio_dir=audio_dir,
                    events_dir=events_dir,
                    transcripts_dir=transcripts_dir,
                    exc=exc,
                )
            if config.verbose:
                async with output_lock:
                    if config.concurrency > 1:
                        print(prefix, flush=True)
                    print(format_example_result(result), flush=True)
            return index, _result_row(scenario, result, offline=config.offline)

    try:
        if monitor is not None:
            monitor.start()
            if config.verbose:
                print("Listening in stereo: recording=left, GPT Live=right.", flush=True)
        completed = await asyncio.gather(
            *(run_one(index, scenario) for index, scenario in enumerate(examples, start=1))
        )
    finally:
        if monitor is not None:
            try:
                await asyncio.to_thread(monitor.wait_until_drained, config.response_timeout_seconds)
            finally:
                monitor.close()
        if judge is not None:
            await judge.close()

    rows = [row for _, row in sorted(completed, key=lambda item: item[0])]
    report = build_results_report(
        module="walk",
        run_name=run_name,
        execution_mode="offline_fixture" if config.offline else "live",
        interaction="single_turn",
        dataset=config.data,
        configuration={
            "audio_source": "recorded",
            "model": config.model,
            "backend_model": config.backend_model,
            "assistant_mode": config.assistant_mode,
            "assistant_endpoint": config.assistant_endpoint if config.assistant_mode == "client" else None,
            "voice": config.voice,
            "concurrency": config.concurrency,
            "sample_rate_hz": config.sample_rate_hz,
            "chunk_ms": config.chunk_ms,
            "real_time": config.real_time,
        },
        rows=rows,
        run_dir=run_dir,
        scenario_id_key="example_id",
    )
    write_json(run_dir / "results.json", report)
    summary = report["summary"]
    print(
        f"Completed {summary['total'] - summary['infrastructure_errors']}/{summary['total']} valid recordings; "
        f"{summary['passed']} passed; {summary['failed']} failed; "
        f"{summary['infrastructure_errors']} infrastructure failures.",
        flush=True,
    )
    print(f"Results: {run_dir}", flush=True)
    return run_dir


def main(argv: Sequence[str] | None = None) -> None:
    asyncio.run(run_evals(parse_args(argv)))


if __name__ == "__main__":
    main()
