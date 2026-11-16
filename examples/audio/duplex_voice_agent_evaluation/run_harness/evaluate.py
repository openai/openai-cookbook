"""Cookbook-style, full-duplex GPT Live multi-turn RUN evaluation harness."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

from assistants.config import (
    LiveAgentSettings,
    render_authorized_context,
)
from assistants.resources import AssistantResources, assistant_resources
from run_harness.graders import apply_procedure_grade, apply_semantic_completion, grade_procedure, judge_result
from run_harness.observability import append_grading_trace, build_observability
from run_harness.scenarios import load_run_dataset
from run_harness.simulation.gpt_live import run_gpt_live_conversation
from run_harness.simulation.models import (
    DEFAULT_SIMULATOR_BACKEND_MODEL,
    DEFAULT_SIMULATOR_BACKEND_REASONING_EFFORT,
    Scenario,
    Settings,
)
from run_harness.simulation.semantic_completion import SemanticCompletionObserver
from shared.artifacts import artifact_path, create_run_directory, scenario_audio_directory, validate_artifact_id
from shared.audio.effects import add_audio_realism_arguments, audio_realism_from_args
from shared.config import load_harness_config
from shared.grading.outcomes import compact_assessment
from shared.grading.scoring import EvalResult
from shared.metrics.interaction import DEFAULT_RESPONSE_DEADLINE_MS, METRICS_VERSION
from shared.metrics.reporting import build_metric_row
from shared.metrics.tokens import TokenUsage, aggregate_backend_usage
from shared.paths import default_results_dir, package_path, require_external_output
from shared.private_files import private_directory
from shared.reporting.compat import is_live_frontend_usage
from shared.reporting.results import build_results_report, build_timestamped_run_name, write_json

HARNESS_DIR = package_path("run_harness")
DEFAULT_CONFIG_PATH = HARNESS_DIR / "config.toml"
DEFAULT_DATA_JSON = HARNESS_DIR / "data" / "scenarios.json"
DEFAULT_SYSTEM_PROMPT_PATH = package_path("assistants") / "frontend" / "prompts" / "voice.txt"
DEFAULT_BACKEND_PROMPT_PATH = package_path("assistants") / "responses" / "prompts" / "backend.txt"
DEFAULT_ASSISTANT_OPENING_PROMPT_PATH = package_path("assistants") / "frontend" / "prompts" / "assistant_first.txt"


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Expose the same small, file-oriented workflow as the CRAWL harness."""
    config = load_harness_config(argv, DEFAULT_CONFIG_PATH)
    assistant = LiveAgentSettings()
    parser = argparse.ArgumentParser(description="Run GPT Live full-duplex, multi-turn simulated conversations.")
    parser.add_argument("--config", type=Path, default=config.path)
    parser.add_argument("--data", type=Path, default=config.path_for("dataset", "path", DEFAULT_DATA_JSON))
    parser.add_argument(
        "--results-dir", type=Path, default=config.path_for("execution", "results_dir", default_results_dir("run"))
    )
    parser.add_argument("--run-name", default="", help="Optional label; a UTC timestamp is always appended.")
    parser.add_argument(
        "--scenario",
        "--example",
        dest="scenario",
        default="all",
        help="Run one scenario ID or all multi-turn scenarios.",
    )
    add_audio_realism_arguments(parser, condition_default=config.get("simulation", "condition", "clean"))
    parser.add_argument("--model", default=assistant.model)
    parser.add_argument("--backend-model", default=assistant.backend_model)
    parser.add_argument(
        "--assistant",
        choices=("responses", "client"),
        default=os.getenv("OPENAI_ASSISTANT_MODE", "").strip()
        or config.get("assistant", "mode", assistant.assistant_mode),
        help="Choose the independent OpenAI-managed or application-managed target agent.",
    )
    parser.add_argument(
        "--assistant-endpoint",
        default=os.getenv("OPENAI_CLIENT_ASSISTANT_ENDPOINT", "").strip()
        or config.get("assistant", "endpoint", assistant.client_endpoint),
        help="Optional separately deployed client-managed agent WebSocket endpoint.",
    )
    parser.add_argument("--endpoint", default=assistant.endpoint)
    parser.add_argument("--voice", default=assistant.voice)
    parser.add_argument(
        "--completion-model",
        default=os.getenv("OPENAI_COMPLETION_MODEL", "").strip()
        or config.get("simulation", "completion_model", "gpt-5.6-terra"),
        help="Independent text model that recognizes when a GPT Live conversation should drain.",
    )
    parser.add_argument(
        "--semantic-drain",
        action=argparse.BooleanOptionalAction,
        default=config.get("simulation", "semantic_drain", True),
        help="Observe GPT Live conversation completion semantically without controlling either participant.",
    )
    parser.add_argument(
        "--completion-timeout-seconds",
        type=float,
        default=config.get("simulation", "completion_timeout_seconds", 8.0),
        help="Maximum time for one asynchronous semantic completion decision.",
    )
    parser.add_argument("--simulator-model", default=assistant.model, help="GPT Live model for the simulated caller.")
    parser.add_argument(
        "--simulator-voice", default="", help="GPT Live caller voice; defaults to the scenario persona."
    )
    parser.set_defaults(
        simulator_backend_model=config.get("simulation", "simulator_backend_model", DEFAULT_SIMULATOR_BACKEND_MODEL),
        simulator_backend_reasoning_effort=config.get(
            "simulation", "simulator_backend_reasoning_effort", DEFAULT_SIMULATOR_BACKEND_REASONING_EFFORT
        ),
    )
    parser.add_argument("--judge-model", default=os.getenv("OPENAI_EVAL_JUDGE_MODEL", "gpt-5.6-terra"))
    parser.add_argument("--judge-reasoning-effort", default=os.getenv("OPENAI_EVAL_JUDGE_REASONING_EFFORT", "medium"))
    parser.add_argument("--judge-repetitions", type=int, default=config.get("grading", "repetitions", 1))
    parser.add_argument(
        "--judge", action=argparse.BooleanOptionalAction, default=config.get("grading", "enabled", True)
    )
    parser.add_argument("--tick-ms", type=int, default=config.get("simulation", "tick_ms", 200))
    parser.add_argument(
        "--response-deadline-ms",
        type=int,
        default=config.get("simulation", "response_deadline_ms", DEFAULT_RESPONSE_DEADLINE_MS),
        help="Deadline for first post-request audio; a scoring policy, not a model SLA (default: 5000 ms).",
    )
    parser.add_argument("--drain-ms", type=int, default=config.get("simulation", "drain_ms", 1_500))
    parser.add_argument(
        "--max-duration-seconds",
        type=float,
        default=config.get("simulation", "max_duration_seconds", 90.0),
    )
    parser.add_argument("--max-examples", type=int, default=config.get("execution", "max_examples", 0))
    parser.add_argument(
        "--concurrency",
        type=int,
        default=config.get("execution", "concurrency", 1),
        help="Maximum independent conversation sessions (1–8; default: 1).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=config.get("execution", "verbose", False),
        help="Print protocol events and per-scenario details (default: disabled).",
    )
    parser.add_argument("--seed", type=int, default=config.get("simulation", "seed", 7))
    parser.add_argument("--listen", action="store_true", help="Monitor caller and agent in live stereo.")
    parser.add_argument(
        "--assistant-opening-prompt",
        type=Path,
        default=None,
        help="Prompt file that makes the evaluated agent speak before the caller in RUN.",
    )
    parser.add_argument("--debug-artifacts", action="store_true", help="Also save tick and turn JSONL artifacts.")
    parser.add_argument(
        "--visualize",
        action="store_true",
        help="Save detailed conversation traces and generate a standalone interactive viewer.",
    )
    parser.add_argument("--offline", action="store_true", help="Run a deterministic fixture without API calls.")
    args = parser.parse_args(argv)
    if args.visualize:
        args.debug_artifacts = True
    return args


def _read_prompt(path: Path) -> str:
    value = path.read_text(encoding="utf-8").strip()
    if not value:
        raise ValueError(f"Prompt file is empty: {path}")
    return value


def _read_assistant_opening_prompt(path: Path | None) -> str | None:
    """Load an optional opening instruction verbatim while validating it before artifact creation."""
    if path is None:
        return None
    try:
        value = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Unable to read assistant opening prompt: {path}") from exc
    if not value.strip():
        raise ValueError(f"Assistant opening prompt file is empty: {path}")
    return value


def load_run_scenarios(path: Path, *, scenario_id: str = "all", max_examples: int = 0) -> list[Scenario]:
    """Validate and select only explicitly interactive, persona-backed scenarios."""
    if max_examples < 0:
        raise ValueError("--max-examples must be zero or greater")
    dataset = load_run_dataset(path)
    scenarios = [item for item in dataset.scenarios if item.interaction_mode == "multi_turn"]
    if scenario_id != "all":
        scenarios = [item for item in scenarios if item.id == scenario_id]
        if not scenarios:
            raise ValueError(f"Unknown multi-turn scenario: {scenario_id}")
    if not scenarios:
        raise ValueError(f"No multi-turn scenarios found in {path}")
    if any(item.simulation_parameters is None for item in scenarios):
        raise ValueError("Every RUN scenario must define simulation_parameters and a caller persona")
    return scenarios[:max_examples] if max_examples else scenarios


def _validate_distinct_gpt_live_voices(
    scenarios: Sequence[Scenario], *, agent_voice: str, simulator_voice: str
) -> None:
    normalized_agent_voice = agent_voice.strip().casefold()
    collisions = [
        scenario.id
        for scenario in scenarios
        if (simulator_voice or scenario.persona.voice).strip().casefold() == normalized_agent_voice
    ]
    if collisions:
        joined = ", ".join(collisions)
        raise ValueError(f"GPT Live caller and agent voices must differ; voice {agent_voice!r} collides for: {joined}")


def _load_tools(path: Path) -> list[dict[str, Any]]:
    parsed = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(parsed, list) or not parsed:
        raise ValueError(f"Application tools must be a nonempty JSON list: {path}")
    seen: set[str] = set()
    tools: list[dict[str, Any]] = []
    for item in parsed:
        if not isinstance(item, dict) or item.get("type") != "function":
            raise ValueError("RUN application tools must be function definitions")
        name = item.get("name")
        if not isinstance(name, str) or not name.strip() or name in seen:
            raise ValueError("RUN application tools must have unique, nonempty names")
        seen.add(name)
        tools.append(item)
    return tools


def _procedure_status(result: EvalResult, kind: str) -> str:
    procedure = result.task_metrics.get("procedure")
    if not isinstance(procedure, dict):
        return "not_applicable"
    steps = [step for step in procedure.get("steps", []) if isinstance(step, dict) and step.get("kind") == kind]
    if not steps:
        return "not_applicable"
    if kind == "state":
        return "passed" if result.task_metrics.get("outcome_state_satisfied") else "failed"
    return "passed" if all(step.get("status") == "passed" for step in steps) else "failed"


def _golden(scenario: Scenario) -> dict[str, Any]:
    delegations = scenario.expected.golden_path.delegations
    if delegations is None:
        raise ValueError("RUN scenarios must define expected.golden_path.delegations")
    return {
        "total_turns": scenario.expected.golden_path.turns,
        "delegations": delegations,
        "delegation_policy": scenario.expected.delegation,
        "tool_calls": [
            {"name": tool.name, "count": 1, "arguments": tool.arguments} for tool in scenario.expected.tools.required
        ],
    }


def _token_counts(result: EvalResult) -> dict[str, Any]:
    """Report final cumulative Live usage and independently attributed backend work."""
    totals: dict[str, Any] = {}

    def add(prefix: str, usage: dict[str, Any]) -> None:
        parsed = TokenUsage.from_mapping(usage, text_only=prefix == "backend")
        if prefix == "frontend" and parsed.audio_duration_ms is not None:
            totals["frontend_audio_duration_ms"] = parsed.audio_duration_ms
        if prefix == "backend" and parsed.backend_model_usage:
            totals["backend_model_usage"] = list(parsed.backend_model_usage)
        fields = {
            "total_tokens": parsed.total_tokens,
            "input_tokens": parsed.input_tokens,
            "cached_input_tokens": parsed.cached_input_tokens,
            "cache_write_input_tokens": parsed.cache_write_input_tokens,
            "input_audio_tokens": parsed.input_audio_tokens,
            "input_text_tokens": parsed.input_text_tokens,
            "input_image_tokens": parsed.input_image_tokens,
            "output_tokens": parsed.output_tokens,
            "cached_output_tokens": parsed.cached_output_tokens,
            "output_audio_tokens": parsed.output_audio_tokens,
            "output_text_tokens": parsed.output_text_tokens,
            "output_image_tokens": parsed.output_image_tokens,
            "output_reasoning_tokens": parsed.output_reasoning_tokens,
        }
        for field, value in fields.items():
            if value is not None:
                key = f"{prefix}_{field}"
                totals[key] = int(value)

    session_snapshots = [
        usage for usage in result.usage if isinstance(usage, dict) and is_live_frontend_usage(usage.get("source"))
    ]
    latest_session = session_snapshots[-1] if session_snapshots else None
    if latest_session is not None:
        add("frontend", latest_session)
    grouped_backend = latest_session.get("backend_model_usage") if latest_session is not None else None
    if isinstance(grouped_backend, list) and grouped_backend:
        add("backend", aggregate_backend_usage(grouped_backend))
    else:
        responses = [
            usage
            for usage in result.usage
            if isinstance(usage, dict) and usage.get("source") in {"delegated_response", "delegated_responses"}
        ]
        if responses:
            add("backend", aggregate_backend_usage(responses))
    return totals


def result_row(scenario: Scenario, result: EvalResult, *, offline: bool) -> dict[str, Any]:
    """Report the shared task, observed-audio, and agent-token metrics."""
    golden = _golden(scenario)
    artifacts = result.artifacts or {}
    tokens = _token_counts(result)
    metrics = build_metric_row(
        task=result.task_metrics,
        efficiency=result.efficiency_metrics,
        interaction=result.interaction_metrics,
        golden=golden,
        usage=tokens,
    )
    assessment = result.task_metrics.get("outcome_assessment", {})
    validity = (result.run_metadata or {}).get("simulator_validity", {})
    invalid_simulator = validity.get("status") == "invalid"
    return {
        "scenario_id": scenario.id,
        "scenario_title": scenario.title,
        "status": "infrastructure_error" if invalid_simulator else result.task_status,
        "validity": validity,
        "execution_mode": "offline_fixture" if offline else "live",
        "semantic_evaluation_status": ("not_assessed" if offline or result.rubric_metrics is None else "assessed"),
        "semantic_dimension_scores": {
            dimension: float(grade["score"])
            for dimension, grade in (result.rubric_metrics or {}).items()
            if isinstance(grade, dict)
            and isinstance(grade.get("score"), int | float)
            and not isinstance(grade.get("score"), bool)
        },
        "assessment": compact_assessment(assessment),
        "observability": (result.run_metadata or {}).get("observability", {}),
        **metrics,
        **tokens,
        "sop_id": result.task_metrics.get("sop_id", ""),
        "sop_status": ("passed" if result.task_metrics.get("sop_passed") else "failed")
        if "sop_passed" in result.task_metrics
        else "not_applicable",
        "tool_sequence_status": _procedure_status(result, "tool"),
        "clarification_status": _procedure_status(result, "clarification"),
        "correction_status": _procedure_status(result, "correction"),
        "authorization_status": _procedure_status(result, "authorization"),
        "final_state_status": _procedure_status(result, "state"),
        "grounded_confirmation_status": _procedure_status(result, "grounded_confirmation"),
        "refusal_status": _procedure_status(result, "refusal"),
        "delegation_count": result.delegation_count,
        "audio_condition": result.audio_condition,
        "agent_model": (result.run_metadata or {}).get("agent_model", ""),
        "backend_model": (result.run_metadata or {}).get("delegation_backend_model", ""),
        "termination_reason": result.termination_reason,
        "conversation_audio_path": artifacts.get("audio", ""),
        "conversation_transcript_path": artifacts.get("transcript", ""),
        "event_log_path": artifacts.get("events", ""),
        "result_path": artifacts.get("result", ""),
        "failure_stage": "caller_simulation" if invalid_simulator else "",
        "error_message": (
            f"Caller simulation is invalid ({validity.get('reason', 'unknown')}); target metrics are diagnostic only."
            if invalid_simulator
            else ""
        ),
    }


def failed_row(scenario: Scenario, exc: Exception, *, offline: bool, args: argparse.Namespace) -> dict[str, Any]:
    """Exclude infrastructure and judge failures from target-model grading."""
    golden = _golden(scenario)
    return {
        "scenario_id": scenario.id,
        "scenario_title": scenario.title,
        "status": "infrastructure_error",
        "execution_mode": "offline_fixture" if offline else "live",
        "semantic_evaluation_status": "not_assessed",
        "task_completed": False,
        "turns": f"0/{golden['total_turns']}",
        "tool_calls": f"0/{len(golden['tool_calls'])}",
        "audio_condition": args.condition,
        "agent_model": args.model,
        "backend_model": args.backend_model,
        "failure_stage": getattr(exc, "failure_stage", "run_or_judge"),
        "error_message": str(exc),
    }


def _settings(
    args: argparse.Namespace,
    scenario: Scenario,
    run_dir: Path,
    *,
    resources: AssistantResources | None = None,
    tools: list[dict[str, Any]] | None = None,
    facts: dict[str, Any] | None = None,
    assistant_opening_prompt: str | None = None,
) -> Settings:
    resources = resources or assistant_resources(assistant_mode=args.assistant)
    agent_instructions = _read_prompt(resources.system_prompt_file)
    backend_instructions = _read_prompt(resources.backend_system_prompt_file)
    if facts is not None:
        initial_state = scenario.application.initial_state
        agent_instructions = render_authorized_context(
            agent_instructions,
            facts=facts or {},
            initial_state=initial_state,
            conversation_context=scenario.input.context.summary if scenario.input.context is not None else "",
        )
        backend_instructions = render_authorized_context(
            backend_instructions,
            facts=facts or {},
            initial_state=initial_state,
            conversation_context=scenario.input.context.summary if scenario.input.context is not None else "",
        )
    return Settings(
        completion_model=args.completion_model,
        semantic_drain=args.semantic_drain,
        completion_timeout_seconds=args.completion_timeout_seconds,
        agent_endpoint=args.endpoint,
        agent_model=args.model,
        agent_voice=args.voice,
        backend_model=args.backend_model,
        simulator_backend_model=args.simulator_backend_model,
        simulator_backend_reasoning_effort=args.simulator_backend_reasoning_effort,
        assistant_mode=args.assistant,
        assistant_endpoint=args.assistant_endpoint,
        agent_instructions=agent_instructions,
        backend_instructions=backend_instructions,
        delegation_tools=tools if tools is not None else [],
        tick_ms=args.tick_ms,
        response_deadline_ms=args.response_deadline_ms,
        max_duration_s=args.max_duration_seconds,
        seed=args.seed,
        condition=args.condition,
        audio_realism=audio_realism_from_args(args),
        listen=args.listen,
        verbose=args.verbose,
        debug_artifacts=args.debug_artifacts,
        save_conversations=scenario_audio_directory(artifact_path(run_dir, "audio"), scenario.id),
        event_log_path=artifact_path(run_dir, "events", f"{validate_artifact_id(scenario.id)}.jsonl"),
        assistant_opening_prompt=assistant_opening_prompt,
    )


def _validate_run_args(args: argparse.Namespace) -> None:
    """Reject invalid execution/scoring policy before allocating run artifacts."""
    if args.judge_repetitions < 1:
        raise ValueError("--judge-repetitions must be at least 1")
    if not 1 <= args.concurrency <= 8:
        raise ValueError("--concurrency must be between 1 and 8")
    if args.completion_timeout_seconds <= 0:
        raise ValueError("--completion-timeout-seconds must be positive")
    if args.response_deadline_ms <= 0:
        raise ValueError("--response-deadline-ms must be positive")
    if args.listen and args.concurrency != 1:
        raise ValueError("--listen requires --concurrency 1 so independent conversations are not mixed")


async def run_evals(args: argparse.Namespace | None = None) -> Path:
    """Execute one independent, continuously paced duplex session per scenario."""
    args = args or parse_args()
    _validate_run_args(args)
    assistant_opening_prompt = _read_assistant_opening_prompt(args.assistant_opening_prompt)
    if not args.offline and not os.getenv("OPENAI_API_KEY", "").strip():
        raise ValueError("OPENAI_API_KEY is required; use --offline to verify without API access")
    scenarios = load_run_scenarios(args.data, scenario_id=args.scenario, max_examples=args.max_examples)
    if not args.offline:
        _validate_distinct_gpt_live_voices(
            scenarios,
            agent_voice=args.voice,
            simulator_voice=args.simulator_voice,
        )
    run_name = build_timestamped_run_name(phase="run", offline=args.offline, label=args.run_name)
    run_dir = create_run_directory(require_external_output(args.results_dir), run_name)
    transcripts_dir = run_dir / "transcripts"
    private_directory(transcripts_dir)
    rows: list[dict[str, Any]] = []
    resources = assistant_resources(assistant_mode=args.assistant)
    tools = _load_tools(resources.tools_file)
    facts = resources.load_facts()
    judge_client = AsyncOpenAI() if args.judge and not args.offline else None
    completion_client = (
        judge_client or AsyncOpenAI(timeout=max(args.completion_timeout_seconds + 2, 10), max_retries=1)
        if args.semantic_drain and not args.offline
        else None
    )
    semaphore = asyncio.Semaphore(args.concurrency)

    async def run_one(index: int, scenario: Scenario) -> tuple[int, dict[str, Any]]:
        async with semaphore:
            if args.verbose:
                print(f"\n[{index}/{len(scenarios)}] {scenario.id}: {scenario.title}", flush=True)
            try:
                executor = resources.create_executor(
                    scenario.application.initial_state,
                    facts,
                    remote=args.assistant == "client" and bool(args.assistant_endpoint) and not args.offline,
                )
                settings = _settings(
                    args,
                    scenario,
                    run_dir,
                    resources=resources,
                    tools=tools,
                    facts=facts,
                    assistant_opening_prompt=assistant_opening_prompt,
                )
                result = await run_gpt_live_conversation(
                    scenario,
                    settings,
                    tool_executor=executor,
                    offline=args.offline,
                    simulator_model=args.simulator_model,
                    simulator_voice=args.simulator_voice,
                    drain_ms=args.drain_ms,
                    completion_observer=(
                        SemanticCompletionObserver(
                            completion_client,
                            model=settings.completion_model,
                            timeout_seconds=settings.completion_timeout_seconds,
                        )
                        if completion_client is not None
                        else None
                    ),
                )
                procedure = grade_procedure(
                    scenario,
                    result,
                    initial_state=scenario.application.initial_state,
                    final_state=executor.snapshot(),
                    executions=executor.executions,
                )
                apply_procedure_grade(result, procedure)
                # A simulator failure is not a target-model grade.
                # Keep deterministic state/artifacts, but skip paid semantic
                # judging and exclude the attempt from valid pass/fail counts.
                if (
                    judge_client is not None
                    and (result.run_metadata or {}).get("simulator_validity", {}).get("status") != "invalid"
                ):
                    result.rubric_metrics = await judge_result(
                        scenario,
                        result,
                        model=args.judge_model,
                        reasoning_effort=args.judge_reasoning_effort,
                        repetitions=args.judge_repetitions,
                        golden=_golden(scenario),
                        client=judge_client,
                    )
                    apply_semantic_completion(result, result.rubric_metrics)
                if result.run_metadata is not None:
                    result.run_metadata["observability"] = build_observability(scenario, result)
                append_grading_trace(result)
                if result.artifacts is not None:
                    write_json(
                        artifact_path(settings.save_conversations, "conversation.result.json"), result.model_dump()
                    )
                write_json(
                    artifact_path(transcripts_dir, f"{validate_artifact_id(scenario.id)}.json"), result.model_dump()
                )
                return index, result_row(scenario, result, offline=args.offline)
            except Exception as exc:  # noqa: BLE001 - isolate one session or grader failure.
                if args.verbose:
                    print(f"  [{scenario.id}] infrastructure failure: {type(exc).__name__}: {exc}", flush=True)
                return index, failed_row(scenario, exc, offline=args.offline, args=args)

    try:
        completed = await asyncio.gather(
            *(run_one(index, scenario) for index, scenario in enumerate(scenarios, start=1))
        )
        rows = [row for _, row in sorted(completed, key=lambda item: item[0])]
    finally:
        if completion_client is not None and completion_client is not judge_client:
            await completion_client.close()
        if judge_client is not None:
            await judge_client.close()

    report = build_results_report(
        module="run",
        run_name=run_name,
        execution_mode="offline_fixture" if args.offline else "live",
        interaction="multi_turn",
        dataset=args.data,
        configuration={
            "model": args.model,
            "backend_model": args.backend_model,
            "assistant_mode": args.assistant,
            "assistant_endpoint": args.assistant_endpoint if args.assistant == "client" else None,
            "voice": args.voice,
            "first_speaker": "assistant" if assistant_opening_prompt is not None else "caller",
            "simulator_model": args.simulator_model,
            "simulator_voice": args.simulator_voice or None,
            "simulator_backend_model": args.simulator_backend_model if not args.offline else None,
            "simulator_backend_reasoning_effort": args.simulator_backend_reasoning_effort if not args.offline else None,
            "semantic_drain": args.semantic_drain and not args.offline,
            "completion_model": args.completion_model,
            "completion_timeout_seconds": args.completion_timeout_seconds,
            "concurrency": args.concurrency,
            "audio_condition": args.condition,
            "audio_realism": audio_realism_from_args(args).model_dump(mode="json", exclude_none=True),
            "tick_ms": args.tick_ms,
            "metrics_version": METRICS_VERSION,
            "response_deadline_ms": args.response_deadline_ms,
            "seed": args.seed,
        },
        rows=rows,
        run_dir=run_dir,
        scenario_id_key="scenario_id",
        title_key="scenario_title",
    )
    write_json(run_dir / "results.json", report)
    summary = report["summary"]
    print(
        f"\nCompleted {summary['total'] - summary['infrastructure_errors']}/{summary['total']} valid conversations; "
        f"{summary['passed']} passed; {summary['failed']} failed; "
        f"{summary['infrastructure_errors']} infrastructure failures.",
        flush=True,
    )
    print(f"Results: {run_dir}", flush=True)
    if getattr(args, "visualize", False):
        try:
            from run_harness.visualization.export_viewer import export_viewer

            viewer_path = export_viewer(run_dir / "results.json")
        except Exception as exc:  # noqa: BLE001 - optional presentation cannot invalidate a completed evaluation.
            print(f"Viewer unavailable: {exc}", flush=True)
        else:
            print(f"Viewer: {viewer_path}", flush=True)
    return run_dir


def main(argv: Sequence[str] | None = None) -> None:
    asyncio.run(run_evals(parse_args(argv)))


if __name__ == "__main__":
    main()
