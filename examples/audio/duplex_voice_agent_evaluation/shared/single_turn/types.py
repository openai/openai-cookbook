"""Single-turn evaluation results and run configuration shared by CRAWL and WALK."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from shared.metrics.reporting import build_metric_row
from shared.metrics.tokens import TokenUsage


@dataclass(slots=True)
class ToolCallRecord:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_arguments: str = ""
    call_id: str = ""
    response_id: str = ""

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> ToolCallRecord:
        arguments = data.get("arguments", {})
        return cls(
            name=str(data.get("name", "")),
            arguments=arguments if isinstance(arguments, dict) else {},
            raw_arguments=str(data.get("raw_arguments", "")),
            call_id=str(data.get("call_id", "")),
            response_id=str(data.get("response_id", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        result = {
            "name": self.name,
            "arguments": self.arguments,
            "raw_arguments": self.raw_arguments,
            "call_id": self.call_id,
        }
        if self.response_id:
            result["response_id"] = self.response_id
        return result


@dataclass(slots=True, frozen=True)
class ExpectedToolCall:
    name: str = ""
    arguments_json: str = ""


@dataclass(slots=True, frozen=True)
class ToolCallGrade:
    pred_tool_call: str = ""
    pred_tool_call_arg: str = ""
    tool_call_correctness: int = 0
    tool_call_arg_correctness: int = 0

    @property
    def grade(self) -> int:
        return int(self.tool_call_correctness == 1 and self.tool_call_arg_correctness == 1)

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> ToolCallGrade:
        return cls(
            pred_tool_call=str(data.get("pred_tool_call", "")),
            pred_tool_call_arg=str(data.get("pred_tool_call_arg", "")),
            tool_call_correctness=int(data.get("tool_call_correctness", 0)),
            tool_call_arg_correctness=int(data.get("tool_call_arg_correctness", 0)),
        )


@dataclass(slots=True, frozen=True)
class ResultArtifactPaths:
    input_audio_path: Path
    event_log_path: Path
    output_audio_path: Path | None = None
    transcript_path: Path | None = None
    conversation_audio_path: Path | None = None
    conversation_transcript_path: Path | None = None


@dataclass(slots=True, frozen=True)
class ResultLatencies:
    first_audio_ms: float | None = None
    first_text_ms: float | None = None
    response_done_ms: float | None = None
    delegation_ms: float | None = None
    first_tool_call_ms: float | None = None
    first_tool_completed_ms: float | None = None
    backend_completed_ms: float | None = None


@dataclass(slots=True, frozen=True)
class EvalErrorInfo:
    status: str = "ok"
    failure_stage: str = ""
    error_type: str = ""
    error_message: str = ""


@dataclass(slots=True)
class SingleTurnEvalResult:
    example_id: str
    user_text: str
    expected_tool_call: ExpectedToolCall
    assistant_text: str
    tool_calls: list[ToolCallRecord]
    tool_call_grade: ToolCallGrade
    artifact_paths: ResultArtifactPaths
    latencies: ResultLatencies
    frontend_usage: TokenUsage = field(default_factory=TokenUsage)
    backend_usage: TokenUsage = field(default_factory=TokenUsage)
    input_transcript: str = ""
    assistant_turn_transcript: str = ""
    post_tool_assistant_text: str = ""
    backend_text: str = ""
    backend_response_count: int = 0
    delegation_target: str = ""
    delegation_response_id: str = ""
    delegation_item_id: str = ""
    delegation_count: int = 0
    tool_executions: list[dict[str, Any]] = field(default_factory=list)
    final_state: dict[str, Any] = field(default_factory=dict)
    task_metrics: dict[str, Any] = field(default_factory=dict)
    interaction_metrics: dict[str, Any] = field(default_factory=dict)
    efficiency_metrics: dict[str, Any] = field(default_factory=dict)
    evidence_metrics: dict[str, float | None] = field(default_factory=dict)
    error_info: EvalErrorInfo = field(default_factory=EvalErrorInfo)
    scenario_type: str = ""
    context_mode: str = ""
    expected_delegation: bool | None = None
    delegation_policy: str = ""
    expected_tool_calls: list[ExpectedToolCall] = field(default_factory=list)
    initial_state: dict[str, Any] = field(default_factory=dict)
    expected_final_state: dict[str, Any] = field(default_factory=dict)
    expected_response: str = ""
    dimension_grades: dict[str, dict[str, Any]] = field(default_factory=dict)
    semantic_grades: dict[str, dict[str, Any]] = field(default_factory=dict)
    rubric_metrics: dict[str, Any] | None = None
    judge_usage_events: list[dict[str, Any]] = field(default_factory=list)
    assessment: dict[str, Any] = field(default_factory=dict)
    observability: dict[str, Any] = field(default_factory=dict)

    def to_result_row(self) -> dict[str, Any]:
        """Project detailed evidence into the shared result-report fields."""
        delegation_required = (
            self.expected_delegation if self.expected_delegation is not None else bool(self.expected_tool_call.name)
        )
        expected_tools = self.expected_tool_calls or ([self.expected_tool_call] if self.expected_tool_call.name else [])
        delegation_policy = self.delegation_policy or (
            "required"
            if delegation_required
            else "forbidden"
            if self.task_metrics.get("delegation_prohibited")
            else "optional"
        )
        delegation_observed = self.delegation_count > 0
        delegation_correct = (
            delegation_policy == "optional"
            or delegation_policy == "required"
            and delegation_observed
            or delegation_policy == "forbidden"
            and not delegation_observed
        )
        observed_semantic = [
            grade for grade in self.semantic_grades.values() if grade.get("status") in {"passed", "failed"}
        ]
        expected_semantic = [
            grade for grade in self.semantic_grades.values() if grade.get("status") != "not_applicable"
        ]
        semantic_status = (
            "not_applicable"
            if not self.semantic_grades
            else "assessed"
            if expected_semantic and len(observed_semantic) == len(expected_semantic)
            else "not_assessed"
        )

        judge_latencies = [
            float(event["latency_ms"])
            for event in self.judge_usage_events
            if isinstance(event.get("latency_ms"), int | float)
        ]
        golden = {
            "total_turns": 2,
            "tool_calls": [{"count": 1} for _ in expected_tools],
            "delegations": int(delegation_policy == "required"),
            "delegation_policy": delegation_policy,
        }
        metrics = build_metric_row(
            task=self.task_metrics,
            efficiency={**self.efficiency_metrics, "delegation_count": self.delegation_count},
            interaction=self.interaction_metrics,
            golden=golden,
            evidence={key: value for key, value in self.evidence_metrics.items() if key != "delegation_accuracy"},
            usage={
                "frontend_audio_duration_ms": self.frontend_usage.audio_duration_ms,
                "frontend_total_tokens": self.frontend_usage.total_tokens,
                "frontend_input_tokens": self.frontend_usage.input_tokens,
                "frontend_input_audio_tokens": self.frontend_usage.input_audio_tokens,
                "frontend_input_text_tokens": self.frontend_usage.input_text_tokens,
                "frontend_cached_input_tokens": self.frontend_usage.cached_input_tokens,
                "frontend_cache_write_input_tokens": self.frontend_usage.cache_write_input_tokens,
                "frontend_output_tokens": self.frontend_usage.output_tokens,
                "frontend_output_audio_tokens": self.frontend_usage.output_audio_tokens,
                "frontend_output_text_tokens": self.frontend_usage.output_text_tokens,
                "backend_total_tokens": self.backend_usage.total_tokens,
                "backend_input_tokens": self.backend_usage.input_tokens,
                "backend_input_text_tokens": self.backend_usage.input_text_tokens,
                "backend_cached_input_tokens": self.backend_usage.cached_input_tokens,
                "backend_cache_write_input_tokens": self.backend_usage.cache_write_input_tokens,
                "backend_output_tokens": self.backend_usage.output_tokens,
                "backend_output_text_tokens": self.backend_usage.output_text_tokens,
                "backend_output_reasoning_tokens": self.backend_usage.output_reasoning_tokens,
            },
        )

        row: dict[str, Any] = {
            "example_id": self.example_id,
            "user_text": self.user_text,
            "assistant_text": self.assistant_text,
            "gt_tool_call": self.expected_tool_call.name,
            "gt_tool_calls": json.dumps([asdict(tool) for tool in expected_tools], ensure_ascii=False),
            "pred_tool_call": self.tool_call_grade.pred_tool_call,
            "tool_call_correctness": self.tool_call_grade.tool_call_correctness,
            "gt_tool_call_arg": self.expected_tool_call.arguments_json,
            "pred_tool_call_arg": self.tool_call_grade.pred_tool_call_arg,
            "tool_call_arg_correctness": self.tool_call_grade.tool_call_arg_correctness,
            "grade": self.tool_call_grade.grade,
            "tool_calls": metrics["tool_calls"],
            "status": self.error_info.status,
            "failure_stage": self.error_info.failure_stage,
            "error_type": self.error_info.error_type,
            "error_message": self.error_info.error_message,
            "event_log_path": str(self.artifact_paths.event_log_path),
            "input_audio_path": str(self.artifact_paths.input_audio_path),
            "output_audio_path": str(self.artifact_paths.output_audio_path or ""),
            "latency_first_audio_ms": self.latencies.first_audio_ms,
            "latency_first_text_ms": self.latencies.first_text_ms,
            "latency_response_done_ms": self.latencies.response_done_ms,
            "output_tokens": self.frontend_usage.output_tokens,
            "output_audio_tokens": self.frontend_usage.output_audio_tokens,
            "output_text_tokens": self.frontend_usage.output_text_tokens,
            "input_transcript": self.input_transcript,
            "assistant_turn_transcript": self.assistant_turn_transcript,
            "post_tool_assistant_text": self.post_tool_assistant_text,
            "backend_text": self.backend_text,
            "backend_response_count": self.backend_response_count,
            "assistant_answered_after_tool": (
                int(bool(self.post_tool_assistant_text)) if self.expected_tool_call.name else None
            ),
            "transcript_path": str(self.artifact_paths.transcript_path or ""),
            "delegation_count": self.delegation_count,
            "delegation_target": self.delegation_target,
            "delegation_item_id": self.delegation_item_id,
            "delegation_response_id": self.delegation_response_id,
            "delegation_policy": delegation_policy,
            "delegation_required": int(delegation_required),
            "delegation_observed": int(delegation_observed),
            "delegation_correctness": int(delegation_correct),
            "tool_executions": json.dumps(self.tool_executions, ensure_ascii=False),
            "tool_execution_count": len(self.tool_executions),
            "tool_execution_correctness": int(
                len(self.tool_executions) == len(expected_tools)
                and all(execution.get("status") == "completed" for execution in self.tool_executions)
                and int(self.task_metrics.get("matched_tool_call_count", len(self.tool_executions)))
                == len(expected_tools)
            ),
            "final_state": json.dumps(self.final_state, ensure_ascii=False, sort_keys=True),
            "latency_delegation_ms": self.latencies.delegation_ms,
            "latency_first_tool_call_ms": self.latencies.first_tool_call_ms,
            "latency_first_tool_completed_ms": self.latencies.first_tool_completed_ms,
            "latency_backend_completed_ms": self.latencies.backend_completed_ms,
            "frontend_audio_duration_ms": self.frontend_usage.audio_duration_ms,
            "frontend_total_tokens": self.frontend_usage.total_tokens,
            "frontend_input_tokens": self.frontend_usage.input_tokens,
            "frontend_cached_input_tokens": self.frontend_usage.cached_input_tokens,
            "frontend_cache_write_input_tokens": self.frontend_usage.cache_write_input_tokens,
            "frontend_input_audio_tokens": self.frontend_usage.input_audio_tokens,
            "frontend_input_text_tokens": self.frontend_usage.input_text_tokens,
            "frontend_input_image_tokens": self.frontend_usage.input_image_tokens,
            "frontend_output_tokens": self.frontend_usage.output_tokens,
            "frontend_cached_output_tokens": self.frontend_usage.cached_output_tokens,
            "frontend_output_audio_tokens": self.frontend_usage.output_audio_tokens,
            "frontend_output_text_tokens": self.frontend_usage.output_text_tokens,
            "frontend_output_image_tokens": self.frontend_usage.output_image_tokens,
            "frontend_output_reasoning_tokens": self.frontend_usage.output_reasoning_tokens,
            "backend_total_tokens": self.backend_usage.total_tokens,
            "backend_input_tokens": self.backend_usage.input_tokens,
            "backend_cached_input_tokens": self.backend_usage.cached_input_tokens,
            "backend_cache_write_input_tokens": self.backend_usage.cache_write_input_tokens,
            "backend_input_audio_tokens": self.backend_usage.input_audio_tokens,
            "backend_input_text_tokens": self.backend_usage.input_text_tokens,
            "backend_input_image_tokens": self.backend_usage.input_image_tokens,
            "backend_output_tokens": self.backend_usage.output_tokens,
            "backend_cached_output_tokens": self.backend_usage.cached_output_tokens,
            "backend_output_audio_tokens": self.backend_usage.output_audio_tokens,
            "backend_output_text_tokens": self.backend_usage.output_text_tokens,
            "backend_output_image_tokens": self.backend_usage.output_image_tokens,
            "backend_output_reasoning_tokens": self.backend_usage.output_reasoning_tokens,
            "backend_model_usage": list(self.backend_usage.backend_model_usage),
            "conversation_audio_path": str(self.artifact_paths.conversation_audio_path or ""),
            "conversation_transcript_path": str(self.artifact_paths.conversation_transcript_path or ""),
            **metrics,
            "requirements_satisfied": (
                int(self.task_metrics["requirements_satisfied"])
                if "requirements_satisfied" in self.task_metrics
                else None
            ),
            "tool_call_coverage": self.task_metrics.get("tool_call_coverage"),
            "tool_call_records": json.dumps([item.to_dict() for item in self.tool_calls], ensure_ascii=False),
            "scenario_type": self.scenario_type,
            "context_mode": self.context_mode,
            "initial_state": json.dumps(self.initial_state, ensure_ascii=False, sort_keys=True),
            "expected_final_state": json.dumps(self.expected_final_state, ensure_ascii=False, sort_keys=True),
            "expected_response": self.expected_response,
            "deterministic_dimension_grades": json.dumps(self.dimension_grades, ensure_ascii=False, sort_keys=True),
            "semantic_dimension_grades": json.dumps(self.semantic_grades, ensure_ascii=False, sort_keys=True),
            "semantic_evaluation_status": semantic_status,
            "semantic_dimension_scores": {
                dimension: float(grade["score"])
                for dimension, grade in self.semantic_grades.items()
                if grade.get("status") in {"passed", "failed"}
                and isinstance(grade.get("score"), int | float)
                and not isinstance(grade.get("score"), bool)
            },
            "judge_call_count": len(self.judge_usage_events),
            "judge_latency_ms": round(sum(judge_latencies), 3) if judge_latencies else None,
        }
        for dimension, grade in self.dimension_grades.items():
            row[f"{dimension}_status"] = grade.get("status")
            row[f"{dimension}_correctness"] = int(grade["passed"]) if isinstance(grade.get("passed"), bool) else None
        for dimension, grade in self.semantic_grades.items():
            row[f"{dimension}_status"] = grade.get("status")
            row[f"{dimension}_correctness"] = int(grade["passed"]) if isinstance(grade.get("passed"), bool) else None
            row[f"{dimension}_score"] = grade.get("score")
            row[f"{dimension}_rationale"] = grade.get("rationale", "")
        if self.assessment:
            row["assessment"] = self.assessment
        if self.observability:
            row["observability"] = self.observability
        return row


CrawlEvalResult = SingleTurnEvalResult


@dataclass(slots=True, frozen=True)
class SingleTurnEvalRunConfig:
    run_name: str
    model: str
    backend_model: str
    endpoint: str
    response_timeout_seconds: float
    tts_model: str
    voice: str
    chunk_ms: int
    sample_rate_hz: int
    input_audio_format: str
    output_audio_format: str
    real_time: bool
    data: Path
    system_prompt_file: Path
    backend_system_prompt_file: Path
    tools_file: Path
    config_file: Path | None = None
    offline: bool = False
    facts_file: Path | None = None
    judge_model: str = "gpt-5.6-terra"
    judge_reasoning_effort: str = "medium"
    listen: bool = False
    verbose: bool = False
    example: str = "all"
    concurrency: int = 1
    assistant_mode: str = "responses"
    assistant_endpoint: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {key: str(value) if isinstance(value, Path) else value for key, value in asdict(self).items()}


CrawlEvalRunConfig = SingleTurnEvalRunConfig
