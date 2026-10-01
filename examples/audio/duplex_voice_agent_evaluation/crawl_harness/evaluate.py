"""Cookbook-shaped, single-turn GPT Live CRAWL evaluation runner."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI, OpenAI

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
from crawl_harness.audio_cache import CallerAudioCache
from crawl_harness.graders import (
    DEFAULT_JUDGE_MODEL,
    DEFAULT_JUDGE_REASONING_EFFORT,
    apply_semantic_grades,
    expected_tool_fields,
    grade_crawl_example,
    judge_semantic_dimensions,
    unassessed_semantic_dimensions,
)
from shared.artifacts import artifact_path, create_run_directory, scenario_audio_directory, validate_artifact_id
from shared.audio.conversation import ConversationRecorder, LiveMonitor
from shared.audio.pcm import tone_for_text, write_mono_wav
from shared.config import load_harness_config
from shared.metrics.evidence import evidence_scores
from shared.metrics.interaction import build_ticks, compute_interaction_metrics, compute_turn_interaction_metrics
from shared.metrics.tokens import TokenUsage, aggregate_backend_usage
from shared.observability.timeline import Timeline
from shared.observability.trace import record_event
from shared.paths import default_audio_cache_dir, default_results_dir, package_path, require_external_output
from shared.private_files import private_open
from shared.reporting.results import build_results_report, build_timestamped_run_name, ensure_dir, write_json
from shared.reporting.schema import SCHEMA_VERSION
from shared.scenarios import Scenario, load_scenario_dataset
from shared.single_turn.console import SingleTurnConsoleEventLog as CrawlConsoleEventLog
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
    CrawlEvalResult,
    CrawlEvalRunConfig,
    EvalErrorInfo,
    ExpectedToolCall,
    ResultArtifactPaths,
    ResultLatencies,
    ToolCallGrade,
    ToolCallRecord,
)

HARNESS_DIR = package_path("crawl_harness")
DEFAULT_CONFIG_PATH = HARNESS_DIR / "config.toml"
ASSISTANTS_DIR = package_path("assistants")
DEFAULT_DATA_JSON = HARNESS_DIR / "data" / "scenarios.json"
RESTAURANT_SYSTEM_PROMPT_PATH = ASSISTANTS_DIR / "frontend" / "prompts" / "voice.txt"
RESTAURANT_BACKEND_SYSTEM_PROMPT_PATH = ASSISTANTS_DIR / "responses" / "prompts" / "backend.txt"
RESTAURANT_TOOLS_PATH = ASSISTANTS_DIR / "responses" / "tools" / "definitions.json"
RESTAURANT_FACTS_PATH = ASSISTANTS_DIR / "responses" / "tools" / "restaurant_facts.json"
DEFAULT_SYSTEM_PROMPT_PATH = RESTAURANT_SYSTEM_PROMPT_PATH
DEFAULT_BACKEND_SYSTEM_PROMPT_PATH = RESTAURANT_BACKEND_SYSTEM_PROMPT_PATH
DEFAULT_TOOLS_PATH = RESTAURANT_TOOLS_PATH
DEFAULT_TTS_MODEL = "gpt-4o-mini-tts"
DEFAULT_CHUNK_MS = 20
DEFAULT_SAMPLE_RATE_HZ = 24_000
DEFAULT_INPUT_AUDIO_FORMAT = "pcm16"
DEFAULT_OUTPUT_AUDIO_FORMAT = "pcm16"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    config = load_harness_config(argv, DEFAULT_CONFIG_PATH)
    assistant = LiveAgentSettings()
    parser = argparse.ArgumentParser(
        description="Run cookbook-compatible GPT Live synthetic single-turn CRAWL evaluations."
    )
    parser.add_argument("--config", type=Path, default=config.path)
    parser.add_argument("--data", type=Path, default=config.path_for("dataset", "path", DEFAULT_DATA_JSON))
    parser.add_argument(
        "--results-dir", type=Path, default=config.path_for("execution", "results_dir", default_results_dir("crawl"))
    )
    parser.add_argument(
        "--audio-cache-dir",
        type=Path,
        default=config.path_for("audio", "cache_dir", default_audio_cache_dir()),
        help="Writable cache for synthetic caller audio.",
    )
    parser.add_argument(
        "--run-name",
        type=str,
        default="",
        help="Optional readable run label; a UTC timestamp is always appended.",
    )
    parser.add_argument("--model", type=str, default=assistant.model)
    parser.add_argument("--backend-model", type=str, default=assistant.backend_model)
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
    parser.add_argument("--endpoint", type=str, default=assistant.endpoint)
    parser.add_argument(
        "--response-timeout-seconds",
        type=float,
        default=config.get("execution", "response_timeout_seconds", DEFAULT_RESPONSE_TIMEOUT_SECONDS),
    )
    parser.add_argument("--judge-model", type=str, default=os.getenv("OPENAI_EVAL_JUDGE_MODEL", DEFAULT_JUDGE_MODEL))
    parser.add_argument(
        "--judge-reasoning-effort",
        type=str,
        default=os.getenv("OPENAI_EVAL_JUDGE_REASONING_EFFORT", DEFAULT_JUDGE_REASONING_EFFORT),
    )
    parser.add_argument("--voice", type=str, default=assistant.voice)
    parser.add_argument("--tts-model", type=str, default=os.getenv("OPENAI_TTS_MODEL", DEFAULT_TTS_MODEL))
    parser.add_argument(
        "--refresh-audio",
        action="store_true",
        help="Regenerate cached synthetic caller recordings before evaluating.",
    )
    parser.add_argument("--chunk-ms", type=int, default=config.get("audio", "chunk_ms", DEFAULT_CHUNK_MS))
    parser.add_argument(
        "--sample-rate-hz", type=int, default=config.get("audio", "sample_rate_hz", DEFAULT_SAMPLE_RATE_HZ)
    )
    parser.add_argument("--input-audio-format", type=str, default=DEFAULT_INPUT_AUDIO_FORMAT)
    parser.add_argument("--output-audio-format", type=str, default=DEFAULT_OUTPUT_AUDIO_FORMAT)
    parser.add_argument(
        "--real-time",
        action=argparse.BooleanOptionalAction,
        default=config.get("audio", "real_time", True),
        help="Pace synthetic caller audio in real time (default: enabled).",
    )
    parser.add_argument(
        "--max-examples",
        type=int,
        default=config.get("execution", "max_examples", 0),
        help="Limit the dataset for a quick smoke test.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=config.get("execution", "concurrency", 1),
        help="Maximum independent evaluation sessions to run in parallel (1–8; default: 1).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=config.get("execution", "verbose", False),
        help="Print protocol events and per-scenario results (default: disabled).",
    )
    parser.add_argument(
        "--example",
        "--scenario",
        dest="example",
        default="all",
        help="Run one dataset example ID, such as restaurant_003, or all examples.",
    )
    parser.add_argument(
        "--listen",
        action="store_true",
        help="Play caller audio on the left and the GPT Live assistant on the right while evaluating.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Verify the complete artifact and delegation pipeline with an explicitly labeled local protocol fixture.",
    )
    return parser.parse_args(argv)


def load_system_prompt(path: Path) -> str:
    prompt = path.read_text(encoding="utf-8").strip()
    if not prompt:
        raise ValueError(f"System prompt is empty: {path}")
    return prompt


def load_tools(path: Path) -> list[dict[str, Any]]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list) or not parsed:
        raise ValueError("Application tools must be a nonempty JSON list")
    tools: list[dict[str, Any]] = []
    names: set[str] = set()
    for item in parsed:
        if not isinstance(item, dict) or item.get("type") != "function":
            raise ValueError("CRAWL application tools must be function definitions")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError("Application tools must have unique, nonempty names")
        names.add(name)
        tools.append(item)
    return tools


def load_dataset(path: Path) -> list[Scenario]:
    """Load portable single-turn scenarios without a phase-specific data format."""

    examples = [scenario for scenario in load_scenario_dataset(path).scenarios if scenario.interaction == "single_turn"]
    if not examples:
        raise ValueError("The CRAWL dataset does not contain any single-turn scenarios")
    return examples


def _render_authorized_context(prompt: str, scenario: Scenario, facts: dict[str, Any]) -> str:
    """Render authorized application context without evaluator-only expectations."""
    return render_authorized_context(
        prompt,
        facts=facts,
        initial_state=scenario.application.initial_state,
        conversation_context=scenario.input.context.summary if scenario.input.context is not None else "",
    )


def write_pcm16_wav(path: Path, pcm: bytes, sample_rate_hz: int) -> Path:
    if not pcm or len(pcm) % 2:
        raise ValueError("WAV artifacts require nonempty, even-length PCM16 audio")
    return write_mono_wav(path, pcm, sample_rate_hz)


def tts_to_pcm_bytes(client: OpenAI, text: str, model: str, voice: str) -> bytes:
    with client.audio.speech.with_streaming_response.create(
        model=model,
        voice=voice,
        input=text,
        response_format="pcm",
    ) as response:
        return b"".join(response.iter_bytes())


def build_error_info(exc: Exception, default_stage: str) -> EvalErrorInfo:
    stage = str(getattr(exc, "failure_stage", default_stage))
    return EvalErrorInfo(
        status="failed",
        failure_stage=stage,
        error_type=type(exc).__name__,
        error_message=str(exc),
    )


def build_failed_result(
    scenario: Scenario,
    run_audio_dir: Path,
    run_events_dir: Path,
    run_transcript_dir: Path,
    error_info: EvalErrorInfo,
) -> CrawlEvalResult:
    example_id = validate_artifact_id(scenario.id)
    expected_name, expected_arguments = expected_tool_fields(scenario)
    audio_dir = scenario_audio_directory(run_audio_dir, example_id)
    output_audio = audio_dir / "output.wav"
    conversation_audio = audio_dir / "conversation.wav"
    conversation_transcript = audio_dir / "conversation.transcript.txt"
    transcript_path = artifact_path(run_transcript_dir, f"{example_id}.json")
    return CrawlEvalResult(
        example_id=example_id,
        user_text=scenario.input.text,
        expected_tool_call=ExpectedToolCall(expected_name, expected_arguments),
        expected_tool_calls=[
            ExpectedToolCall(tool.name, json.dumps(tool.arguments, ensure_ascii=False, sort_keys=True))
            for tool in scenario.expected.tools.required
        ],
        assistant_text="",
        tool_calls=[],
        tool_call_grade=ToolCallGrade(),
        artifact_paths=ResultArtifactPaths(
            input_audio_path=audio_dir / "input.wav",
            event_log_path=artifact_path(run_events_dir, f"{example_id}.jsonl"),
            output_audio_path=output_audio if output_audio.is_file() else None,
            transcript_path=transcript_path if transcript_path.is_file() else None,
            conversation_audio_path=conversation_audio if conversation_audio.is_file() else None,
            conversation_transcript_path=conversation_transcript if conversation_transcript.is_file() else None,
        ),
        latencies=ResultLatencies(),
        error_info=error_info,
        scenario_type=scenario.scenario_type,
        context_mode=scenario.context_mode,
        expected_delegation=scenario.expected.requires_delegation,
        delegation_policy=scenario.expected.delegation,
        initial_state=scenario.application.initial_state,
        expected_final_state=scenario.expected.state,
        expected_response=scenario.expected.answer,
    )


@dataclass(frozen=True, slots=True)
class _PreparedInput:
    """CRAWL-owned input and checked output destinations."""

    example_id: str
    user_text: str
    input_pcm: bytes
    audio_dir: Path
    input_path: Path
    events_path: Path
    transcript_path: Path
    user_audio_ms: int


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
    config: CrawlEvalRunConfig,
    run_audio_dir: Path,
    run_events_dir: Path,
    run_transcript_dir: Path,
    tts_client: OpenAI | None,
    audio_cache: CallerAudioCache | None,
) -> _PreparedInput:
    """Synthesize/cache caller audio and reserve CRAWL artifacts."""
    example_id = validate_artifact_id(scenario.id)
    user_text = scenario.input.text
    audio_dir = ensure_dir(scenario_audio_directory(run_audio_dir, example_id))
    input_path = audio_dir / "input.wav"
    events_path = artifact_path(run_events_dir, f"{example_id}.jsonl")
    transcript_path = artifact_path(run_transcript_dir, f"{example_id}.json")
    if config.offline:
        input_pcm = tone_for_text(user_text, config.sample_rate_hz)
    else:
        if tts_client is None:
            raise LiveResponseError("A TTS client is required for live evaluation", failure_stage="audio_synthesis")
        if audio_cache is None:
            input_pcm = await asyncio.to_thread(tts_to_pcm_bytes, tts_client, user_text, config.tts_model, config.voice)
        else:
            cached = await asyncio.to_thread(
                audio_cache.load_or_create,
                example_id,
                text=user_text,
                model=config.tts_model,
                voice=config.voice,
                sample_rate_hz=config.sample_rate_hz,
                synthesize=lambda: tts_to_pcm_bytes(tts_client, user_text, config.tts_model, config.voice),
            )
            input_pcm = cached.pcm
            if config.verbose:
                print(f"  AUDIO      {'reused' if cached.reused else 'generated'} {cached.path}", flush=True)
    write_pcm16_wav(input_path, input_pcm, config.sample_rate_hz)
    user_audio_ms = len(input_pcm) * 1_000 // (config.sample_rate_hz * 2)
    return _PreparedInput(
        example_id, user_text, input_pcm, audio_dir, input_path, events_path, transcript_path, user_audio_ms
    )


async def _run_session(
    *,
    scenario: Scenario,
    prepared: _PreparedInput,
    config: CrawlEvalRunConfig,
    resources: AssistantResources,
    facts: dict[str, Any],
    system_prompt: str,
    backend_system_prompt: str,
    tools: list[dict[str, Any]],
    audio_monitor: LiveMonitor | None,
) -> _SessionEvidence:
    """Own this harness's assistant setup, concurrent streaming, and teardown."""
    initial_state = scenario.application.initial_state
    example_id = prepared.example_id
    user_text = prepared.user_text
    input_pcm = prepared.input_pcm
    events_path = prepared.events_path
    user_audio_ms = prepared.user_audio_ms
    application_tools = resources.create_executor(
        initial_state,
        facts,
        remote=config.assistant_mode == "client" and bool(config.assistant_endpoint) and not config.offline,
    )
    offline_behavior = (
        resources.create_offline_behavior(
            conversation_context=scenario.conversation_context,
            initial_state=initial_state,
            facts=facts,
        )
        if config.offline
        else None
    )
    timeline = Timeline()
    recorder = ConversationRecorder(config.sample_rate_hz)
    timeline.add_user_utterance(0, user_audio_ms, user_text, source="crawl.synthetic")
    assistant_settings = LiveAgentSettings(
        endpoint=config.endpoint,
        model=config.model,
        voice=config.voice,
        backend_model=config.backend_model,
        assistant_mode=config.assistant_mode,
        client_endpoint=config.assistant_endpoint,
    )
    authorized_instructions = _render_authorized_context(system_prompt, scenario, facts)
    authorized_backend_instructions = _render_authorized_context(backend_system_prompt, scenario, facts)
    initial_items = build_initial_items(scenario.input.context.history) if scenario.input.context is not None else None
    session = build_assistant_session(
        assistant_settings,
        instructions=authorized_instructions,
        backend_instructions=authorized_backend_instructions,
        tools=tools,
        initial_items=initial_items,
    )
    api_key = os.getenv("OPENAI_API_KEY", "")

    with private_open(events_path) as persisted_event_log:
        console_trace = CrawlConsoleEventLog(persisted_event_log, chunk_ms=config.chunk_ms) if config.verbose else None
        event_log = console_trace if console_trace is not None else persisted_event_log
        trace_started_at = asyncio.get_running_loop().time()
        event_index_state = {"value": 0}
        async with open_live_connection(
            endpoint=config.endpoint,
            model=config.model,
            api_key=api_key,
            timeout_seconds=config.response_timeout_seconds,
            offline=config.offline,
            example_id=example_id,
            user_text=user_text,
            input_audio_length=len(input_pcm),
            sample_rate_hz=config.sample_rate_hz,
            offline_behavior=offline_behavior,
        ) as connection:
            await connection.send_json(session)
            record_event(
                event_log,
                session,
                started_at=trace_started_at,
                event_index_state=event_index_state,
                source="live_frontend",
                direction="client_to_server",
            )
            session_started = await wait_for_session_started(
                connection,
                event_log,
                timeout_seconds=config.response_timeout_seconds,
                started_at=trace_started_at,
                event_index_state=event_index_state,
            )
            assistant_connection: AssistantConnection | None = None
            if config.assistant_mode == "client" and not config.offline:
                assistant_connection = await bind_client_delegation(
                    connection,
                    config=assistant_settings,
                    instructions=authorized_backend_instructions,
                    tools=tools,
                    executor=application_tools,
                    api_key=api_key,
                    initial_items=initial_items,
                )
            else:
                assistant_connection = await bind_responses_delegation(connection, executor=application_tools)
            connection = assistant_connection
            response: dict[str, Any] | None = None
            caller_audio_completion = CallerAudioCompletion()
            audio_sender: asyncio.Task[None] | None = None
            response_receiver: asyncio.Task[dict[str, Any]] | None = None
            try:
                audio_sender = asyncio.create_task(
                    stream_audio_to_connection(
                        connection,
                        input_pcm,
                        config.chunk_ms,
                        config.sample_rate_hz,
                        config.real_time,
                        log_file=event_log,
                        started_at=trace_started_at,
                        event_index_state=event_index_state,
                        timeline=timeline,
                        recorder=recorder,
                        audio_monitor=audio_monitor,
                        caller_audio_completion=caller_audio_completion,
                    ),
                    name=f"crawl-caller-audio-{example_id}",
                )
                response_receiver = asyncio.create_task(
                    collect_live_response(
                        connection,
                        event_log,
                        chunk_ms=config.chunk_ms,
                        sample_rate_hz=config.sample_rate_hz,
                        timeout_seconds=config.response_timeout_seconds,
                        trace_started_at=trace_started_at,
                        event_index_state=event_index_state,
                        tool_observer=application_tools,
                        timeline=timeline,
                        recorder=recorder,
                        audio_monitor=audio_monitor,
                        tool_source="assistant_application",
                        caller_audio_completion=caller_audio_completion,
                    ),
                    name=f"crawl-live-receiver-{example_id}",
                )
                _, response = await asyncio.gather(audio_sender, response_receiver)
            finally:
                try:
                    pending = [
                        task for task in (audio_sender, response_receiver) if task is not None and not task.done()
                    ]
                    for task in pending:
                        task.cancel()
                    if pending:
                        await asyncio.gather(*pending, return_exceptions=True)
                    if recorder.user or recorder.assistant:
                        recorder.save(prepared.audio_dir / "conversation.wav", timeline.evaluation_transcript())
                    frontend_usage = await close_live_session(
                        connection,
                        event_log,
                        trace_started_at=trace_started_at,
                        event_index_state=event_index_state,
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
            raise LiveResponseError(
                "Live audio playback did not finish before the timeout", failure_stage="audio_playback"
            )

    if response is None:
        raise LiveResponseError("GPT Live did not produce a response", failure_stage="response_collection")
    output_pcm = response["output_audio_bytes"]
    if not output_pcm:
        raise LiveResponseError("GPT Live completed without assistant audio", failure_stage="output_audio")
    return _SessionEvidence(response, frontend_usage, session_started, timeline, recorder, trace_started_at)


async def _grade_and_write_result(
    *,
    scenario: Scenario,
    prepared: _PreparedInput,
    evidence: _SessionEvidence,
    config: CrawlEvalRunConfig,
    facts: dict[str, Any],
    judge_client: AsyncOpenAI | None,
) -> CrawlEvalResult:
    """Grade this phase's evidence and write its transcript and result contract."""
    initial_state = scenario.application.initial_state
    example_id = prepared.example_id
    user_text = prepared.user_text
    audio_dir = prepared.audio_dir
    input_path = prepared.input_path
    events_path = prepared.events_path
    transcript_path = prepared.transcript_path
    user_audio_ms = prepared.user_audio_ms
    response = evidence.response
    frontend_usage = evidence.frontend_usage
    session_started = evidence.session_started
    timeline = evidence.timeline
    recorder = evidence.recorder
    trace_started_at = evidence.started_at
    output_pcm = response["output_audio_bytes"]
    output_path = write_pcm16_wav(audio_dir / "output.wav", output_pcm, config.sample_rate_hz)
    conversation_path, conversation_transcript_path = recorder.save(
        audio_dir / "conversation.wav", timeline.evaluation_transcript()
    )
    raw_calls = response["tool_calls"]
    tool_calls = [ToolCallRecord.from_mapping(item) for item in raw_calls]
    ticks = build_ticks(
        timeline,
        config.chunk_ms,
        config.sample_rate_hz,
        duration_ms=user_audio_ms,
        user_track=recorder.user,
        assistant_track=recorder.assistant,
    )
    interaction_metrics = compute_interaction_metrics(ticks, tick_ms=config.chunk_ms, timeline=timeline)
    turn_metrics = compute_turn_interaction_metrics(ticks, timeline)
    grades = grade_crawl_example(
        scenario,
        tool_calls,
        timeline,
        interaction_metrics=interaction_metrics,
        turn_metrics=turn_metrics,
        user_audio_ms=user_audio_ms,
        run_name=config.run_name,
        tts_model=config.tts_model,
        offline=config.offline,
        tool_executions=response["tool_executions"],
        final_state=response["final_state"],
        initial_state=initial_state,
        delegations=response["delegations"],
        post_tool_assistant_text=response["post_tool_assistant_text"],
    )
    source_result = grades.source_result
    delegations = response["delegations"]
    semantic_grades: dict[str, Any] = {}
    judge_usage_events: list[dict[str, Any]] = []
    if config.offline:
        semantic_grades = {
            dimension: grade.to_dict() for dimension, grade in unassessed_semantic_dimensions(scenario).items()
        }
    else:
        if judge_client is None:
            raise LiveResponseError("An independent semantic judge is required", failure_stage="semantic_judge")
        if config.verbose:
            print("  JUDGE      assessing semantic dimensions...", flush=True)
        assessed, judge_usage_events = await judge_semantic_dimensions(
            scenario,
            assistant_text=response["assistant_turn_transcript"] or response["assistant_text"],
            delegations=delegations,
            backend_messages=response["backend_messages"],
            tool_executions=response["tool_executions"],
            final_state=response["final_state"],
            facts=facts,
            client=judge_client,
            model=config.judge_model,
            reasoning_effort=config.judge_reasoning_effort,
        )
        semantic_grades = {dimension: grade.to_dict() for dimension, grade in assessed.items()}
    rubric_metrics = apply_semantic_grades(source_result, semantic_grades)
    if rubric_metrics is not None:
        grades.evidence_metrics.update(
            evidence_scores(
                source_result.task_metrics,
                source_result.efficiency_metrics,
                {
                    "tool_calls": [{"count": 1} for _ in scenario.expected.tools.required],
                    "total_turns": 2,
                },
            )
        )
    deterministic_grades = {dimension: grade.to_dict() for dimension, grade in grades.dimension_grades.items()}
    observability = build_single_turn_observability(
        scenario,
        source_result,
        audio_source="synthetic",
        deterministic_grades=deterministic_grades,
        semantic_grades=semantic_grades,
    )
    assessment = result_assessment(source_result)
    append_single_turn_grading_trace(
        events_path,
        scenario=scenario,
        result=source_result,
        deterministic_grades=deterministic_grades,
        semantic_grades=semantic_grades,
        started_at=trace_started_at,
    )
    first_delegation = delegations[0] if delegations else {}
    started_session = session_started.get("session", {})
    transcript = {
        "schema_version": SCHEMA_VERSION,
        "example_id": example_id,
        "session_id": started_session.get("id") if isinstance(started_session, dict) else None,
        "mode": "offline_fixture" if config.offline else "live",
        "scenario_type": scenario.scenario_type,
        "context_mode": scenario.context_mode,
        "conversation_context": scenario.conversation_context,
        "initial_state": initial_state,
        "conversation_audio_path": str(conversation_path),
        "conversation_transcript_path": str(conversation_transcript_path),
        "input_reference": user_text,
        "input_projected": response["input_transcript"],
        "input_fragments": response["input_fragments"],
        "assistant_projected": response["assistant_text"],
        "assistant_turn_transcript": response["assistant_turn_transcript"],
        "assistant_fragments": response["assistant_fragments"],
        "post_tool_assistant_fragments": response["post_tool_assistant_fragments"],
        "post_tool_assistant_text": response["post_tool_assistant_text"],
        "backend_messages": response["backend_messages"],
        "backend_text": response["backend_text"],
        "backend_usage_events": response["backend_usage_events"],
        "audio_timeline": {
            "projected_user_turn_end_ms": response["projected_user_turn_end_ms"],
            "first_assistant_speech_offset_ms": response["first_assistant_speech_offset_ms"],
            "first_assistant_text_offset_ms": response["first_assistant_text_offset_ms"],
        },
        "turns": response["turns"],
        "delegations": delegations,
        "expected_delegation": scenario.expected.delegation,
        "expected_tool_calls": [tool.model_dump() for tool in scenario.expected.tools.required],
        "tool_calls": [call.to_dict() for call in tool_calls],
        "tool_executions": response["tool_executions"],
        "final_state": response["final_state"],
        "evaluation_transcript": timeline.evaluation_transcript(),
        "agent_events": [event.model_dump() for event in timeline.agent_events],
        "timeline_usage": timeline.usage,
        "task_metrics": source_result.task_metrics,
        "interaction_metrics": interaction_metrics,
        "turn_metrics": source_result.turn_metrics,
        "efficiency_metrics": source_result.efficiency_metrics,
        "evidence_metrics": grades.evidence_metrics,
        "rubric_metrics": rubric_metrics,
        "dimension_grades": deterministic_grades,
        "semantic_grades": semantic_grades,
        "judge_usage_events": judge_usage_events,
        "assessment": assessment,
        "observability": observability,
    }
    write_json(transcript_path, transcript)

    return CrawlEvalResult(
        example_id=example_id,
        user_text=user_text,
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
        task_metrics=source_result.task_metrics,
        interaction_metrics=interaction_metrics,
        efficiency_metrics=source_result.efficiency_metrics,
        evidence_metrics=grades.evidence_metrics,
        scenario_type=scenario.scenario_type,
        context_mode=scenario.context_mode,
        expected_delegation=scenario.expected.requires_delegation,
        delegation_policy=scenario.expected.delegation,
        initial_state=initial_state,
        expected_final_state=scenario.expected.state,
        expected_response=scenario.expected.answer,
        dimension_grades=deterministic_grades,
        semantic_grades=semantic_grades,
        rubric_metrics=rubric_metrics,
        judge_usage_events=judge_usage_events,
        assessment=assessment,
        observability=observability,
    )


async def run_single_eval(
    *,
    tts_client: OpenAI | None,
    scenario: Scenario,
    system_prompt: str,
    backend_system_prompt: str,
    tools: list[dict[str, Any]],
    run_audio_dir: Path,
    run_events_dir: Path,
    run_transcript_dir: Path,
    config: CrawlEvalRunConfig,
    resources: AssistantResources | None = None,
    business_facts: dict[str, Any] | None = None,
    judge_client: AsyncOpenAI | None = None,
    audio_monitor: LiveMonitor | None = None,
    audio_cache: CallerAudioCache | None = None,
) -> CrawlEvalResult:
    """Prepare, run, and grade one independently owned CRAWL evaluation."""
    resources = resources or assistant_resources(assistant_mode=config.assistant_mode)
    facts = business_facts if business_facts is not None else resources.load_facts()
    prepared = await _prepare_input(
        scenario=scenario,
        config=config,
        run_audio_dir=run_audio_dir,
        run_events_dir=run_events_dir,
        run_transcript_dir=run_transcript_dir,
        tts_client=tts_client,
        audio_cache=audio_cache,
    )
    evidence = await _run_session(
        scenario=scenario,
        prepared=prepared,
        config=config,
        resources=resources,
        facts=facts,
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
        facts=facts,
        judge_client=judge_client,
    )


def format_example_result(result: CrawlEvalResult) -> str:
    """Render the actual conversation, executed tools, grades, and audio timing."""

    semantic_failed = any(grade.get("status") == "failed" for grade in result.semantic_grades.values())
    task_completed = bool(result.task_metrics.get("task_completed", result.tool_call_grade.grade))
    if result.error_info.status != "ok":
        status = "ERROR"
    elif task_completed and result.tool_call_grade.grade and not semantic_failed:
        status = "PASS"
    else:
        status = "FAIL"

    assistant_text = result.assistant_turn_transcript or result.assistant_text or "[no assistant response]"
    lines = [f"  USER       {result.user_text}", f"  ASSISTANT  {assistant_text}"]

    if result.tool_executions:
        for execution in result.tool_executions:
            arguments = json.dumps(
                execution.get("arguments", {}), ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            lines.append(f"  TOOL       {execution.get('name', 'unknown')} {arguments} [{execution.get('status')}]")
    elif result.tool_calls:
        for call in result.tool_calls:
            arguments = json.dumps(call.arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            lines.append(f"  TOOL       {call.name} {arguments} [requested]")
    else:
        lines.append("  TOOL       none")

    metric_row = result.to_result_row()
    metrics = [status]
    for label, key in (("tool", "tool_accuracy"), ("response_rate", "response_rate")):
        value = metric_row.get(key)
        if isinstance(value, int | float) and not isinstance(value, bool):
            metrics.append(f"{label}={value:.2f}")
    metrics.append(f"tools={metric_row['tool_calls']}")
    response_latency = metric_row.get("response_latency_ms")
    if isinstance(response_latency, int | float) and not isinstance(response_latency, bool):
        metrics.append(f"response={response_latency:g}ms")
    lines.append(f"  RESULT     {' | '.join(metrics)}")

    deterministic = [
        f"{name}={grade['status']}"
        for name, grade in result.dimension_grades.items()
        if grade.get("status") in {"passed", "failed"}
    ]
    if deterministic:
        lines.append(f"  CHECKS     {' | '.join(deterministic)}")

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


def _config_from_args(args: argparse.Namespace, run_name: str, resources: AssistantResources) -> CrawlEvalRunConfig:
    return CrawlEvalRunConfig(
        run_name=run_name,
        model=args.model,
        backend_model=args.backend_model,
        endpoint=args.endpoint,
        response_timeout_seconds=args.response_timeout_seconds,
        tts_model=args.tts_model,
        voice=args.voice,
        chunk_ms=args.chunk_ms,
        sample_rate_hz=args.sample_rate_hz,
        input_audio_format=args.input_audio_format,
        output_audio_format=args.output_audio_format,
        real_time=args.real_time,
        data=args.data.resolve(),
        system_prompt_file=resources.system_prompt_file.resolve(),
        backend_system_prompt_file=resources.backend_system_prompt_file.resolve(),
        tools_file=resources.tools_file.resolve(),
        config_file=args.config.resolve(),
        offline=args.offline,
        facts_file=resources.facts_file.resolve(),
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
    validate_audio_config(args.sample_rate_hz, args.input_audio_format, args.output_audio_format)
    if args.response_timeout_seconds <= 0:
        raise ValueError("Response timeout must be greater than zero")
    if args.chunk_ms <= 0:
        raise ValueError("Audio chunk duration must be greater than zero")
    if args.max_examples < 0:
        raise ValueError("Maximum examples cannot be negative")
    if not 1 <= args.concurrency <= 8:
        raise ValueError("--concurrency must be between 1 and 8")
    if args.listen and args.concurrency != 1:
        raise ValueError("--listen requires --concurrency 1 so independent conversations are not mixed")
    if not args.judge_model.strip():
        raise ValueError("Judge model must be a nonempty model name")
    if not args.judge_reasoning_effort.strip():
        raise ValueError("Judge reasoning effort must be nonempty")
    if not args.offline and not os.getenv("OPENAI_API_KEY", "").strip():
        raise ValueError("OPENAI_API_KEY is required; use --offline to verify artifacts without API access")


async def run_evals(args: argparse.Namespace | None = None) -> Path:
    if args is None:
        args = parse_args()
    _validate_run_args(args)

    examples = load_dataset(args.data)
    if args.example != "all":
        examples = [scenario for scenario in examples if scenario.id == args.example]
        if not examples:
            raise ValueError(f"Unknown CRAWL example: {args.example}")
    resources = assistant_resources(assistant_mode=args.assistant)
    facts = resources.load_facts()
    if args.max_examples:
        examples = examples[: args.max_examples]
    system_prompt = load_system_prompt(resources.system_prompt_file)
    backend_system_prompt = load_system_prompt(resources.backend_system_prompt_file)
    tools = load_tools(resources.tools_file)
    run_name = build_timestamped_run_name(phase="crawl", offline=args.offline, label=args.run_name)
    config = _config_from_args(args, run_name, resources)
    run_dir = create_run_directory(require_external_output(args.results_dir), run_name)
    run_audio_dir = ensure_dir(run_dir / "audio")
    run_events_dir = ensure_dir(run_dir / "events")
    run_transcript_dir = ensure_dir(run_dir / "transcripts")
    tts_client = None if args.offline else OpenAI()
    audio_cache = None if args.offline else CallerAudioCache(args.audio_cache_dir, refresh=args.refresh_audio)
    judge_client = AsyncOpenAI() if not args.offline else None
    audio_monitor = LiveMonitor(config.sample_rate_hz) if config.listen else None
    semaphore = asyncio.Semaphore(config.concurrency)
    console_lock = asyncio.Lock()
    label = "offline fixture" if args.offline else "GPT Live"
    if config.verbose:
        print(
            f"Running {label} CRAWL: {len(examples)} examples (concurrency={config.concurrency}) -> {run_dir}",
            flush=True,
        )

    async def run_one(index: int, scenario: Scenario) -> tuple[int, CrawlEvalResult]:
        async with semaphore:
            prefix = f"[{index}/{len(examples)}] {scenario.id}"
            if config.verbose:
                print(f"{prefix}{' started' if config.concurrency > 1 else ''}", flush=True)
            try:
                result = await run_single_eval(
                    tts_client=tts_client,
                    scenario=scenario,
                    system_prompt=system_prompt,
                    backend_system_prompt=backend_system_prompt,
                    tools=tools,
                    run_audio_dir=run_audio_dir,
                    run_events_dir=run_events_dir,
                    run_transcript_dir=run_transcript_dir,
                    config=config,
                    resources=resources,
                    business_facts=facts,
                    judge_client=judge_client,
                    audio_monitor=audio_monitor,
                    audio_cache=audio_cache,
                )
            except Exception as exc:  # noqa: BLE001 - retain one explicit infrastructure-failure row.
                error = build_error_info(exc, "example_execution")
                result = build_failed_result(scenario, run_audio_dir, run_events_dir, run_transcript_dir, error)
            if config.verbose:
                async with console_lock:
                    if config.concurrency > 1:
                        print(prefix, flush=True)
                    print(format_example_result(result), flush=True)
            return index, result

    try:
        if audio_monitor is not None:
            audio_monitor.start()
            if config.verbose:
                print("Listening in stereo: caller=left, GPT Live=right.", flush=True)
        completed = await asyncio.gather(
            *(run_one(index, scenario) for index, scenario in enumerate(examples, start=1))
        )
        results = [result for _, result in sorted(completed, key=lambda item: item[0])]
    finally:
        if audio_monitor is not None:
            try:
                await asyncio.to_thread(audio_monitor.wait_until_drained, config.response_timeout_seconds)
            finally:
                audio_monitor.close()
        if judge_client is not None:
            await judge_client.close()

    rows = [item.to_result_row() for item in results]
    report = build_results_report(
        module="crawl",
        run_name=run_name,
        execution_mode="offline_fixture" if config.offline else "live",
        interaction="single_turn",
        dataset=config.data,
        configuration={
            "audio_source": "synthetic",
            "model": config.model,
            "backend_model": config.backend_model,
            "assistant_mode": config.assistant_mode,
            "assistant_endpoint": config.assistant_endpoint if config.assistant_mode == "client" else None,
            "voice": config.voice,
            "tts_model": config.tts_model,
            "audio_cache_dir": str(args.audio_cache_dir),
            "refresh_audio": args.refresh_audio,
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
        f"Completed {summary['total'] - summary['infrastructure_errors']}/{summary['total']} valid examples; "
        f"{summary['passed']} passed; {summary['failed']} failed; "
        f"{summary['infrastructure_errors']} infrastructure failures.",
        flush=True,
    )
    print(f"Results: {run_dir}", flush=True)
    return run_dir


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    asyncio.run(run_evals(args))


if __name__ == "__main__":
    main()
