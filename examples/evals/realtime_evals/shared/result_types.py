"""Structured dataclasses for crawl, walk, and run harness outputs."""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


def _coerce_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _coerce_optional_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _coerce_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _coerce_optional_path(value: Any) -> Path | None:
    text = _coerce_str(value).strip()
    if not text:
        return None
    return Path(text)


def _parse_tool_calls(value: Any) -> list["ToolCallRecord"]:
    raw_tool_calls: list[Any]
    if isinstance(value, str):
        if not value.strip():
            raw_tool_calls = []
        else:
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                raw_tool_calls = []
            else:
                raw_tool_calls = parsed if isinstance(parsed, list) else []
    elif isinstance(value, list):
        raw_tool_calls = value
    else:
        raw_tool_calls = []

    tool_calls: list[ToolCallRecord] = []
    for raw_tool_call in raw_tool_calls:
        if isinstance(raw_tool_call, Mapping):
            tool_calls.append(ToolCallRecord.from_mapping(raw_tool_call))
    return tool_calls


@dataclass(slots=True)
class ToolCallRecord:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    raw_arguments: str = ""
    call_id: str = ""

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ToolCallRecord":
        raw_arguments = _coerce_str(data.get("raw_arguments", ""))
        arguments_value = data.get("arguments", {})
        arguments = arguments_value if isinstance(arguments_value, dict) else {}
        return cls(
            name=_coerce_str(data.get("name", "")),
            arguments=arguments,
            raw_arguments=raw_arguments,
            call_id=_coerce_str(data.get("call_id", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "raw_arguments": self.raw_arguments,
            "call_id": self.call_id,
        }


@dataclass(slots=True)
class ToolOutputRecord:
    call_id: str = ""
    name: str = ""
    arguments: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ToolOutputRecord":
        arguments_value = data.get("arguments", {})
        output_value = data.get("output", {})
        return cls(
            call_id=_coerce_str(data.get("call_id", "")),
            name=_coerce_str(data.get("name", "")),
            arguments=arguments_value if isinstance(arguments_value, dict) else {},
            output=output_value if isinstance(output_value, dict) else {},
        )

    @classmethod
    def from_tool_call(
        cls, tool_call: ToolCallRecord, output: Mapping[str, Any]
    ) -> "ToolOutputRecord":
        return cls(
            call_id=tool_call.call_id,
            name=tool_call.name,
            arguments=tool_call.arguments,
            output=dict(output),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "name": self.name,
            "arguments": self.arguments,
            "output": self.output,
        }


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
        return int(
            self.tool_call_correctness == 1 and self.tool_call_arg_correctness == 1
        )

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any]) -> "ToolCallGrade":
        return cls(
            pred_tool_call=_coerce_str(data.get("pred_tool_call", "")),
            pred_tool_call_arg=_coerce_str(data.get("pred_tool_call_arg", "")),
            tool_call_correctness=int(data.get("tool_call_correctness", 0)),
            tool_call_arg_correctness=int(data.get("tool_call_arg_correctness", 0)),
        )


@dataclass(slots=True, frozen=True)
class ResultArtifactPaths:
    input_audio_path: Path
    event_log_path: Path
    output_audio_path: Path | None = None


@dataclass(slots=True, frozen=True)
class ResultLatencies:
    first_audio_ms: float | None = None
    first_text_ms: float | None = None
    response_done_ms: float | None = None


@dataclass(slots=True, frozen=True)
class OutputTokenUsage:
    output_tokens: int | None = None
    output_audio_tokens: int | None = None
    output_text_tokens: int | None = None


@dataclass(slots=True, frozen=True)
class EvalErrorInfo:
    status: str = "ok"
    failure_stage: str = ""
    error_type: str = ""
    error_message: str = ""


@dataclass(slots=True)
class CrawlEvalResult:
    example_id: str
    user_text: str
    expected_tool_call: ExpectedToolCall
    assistant_text: str
    tool_calls: list[ToolCallRecord]
    tool_call_grade: ToolCallGrade
    artifact_paths: ResultArtifactPaths
    latencies: ResultLatencies
    output_tokens: OutputTokenUsage
    error_info: EvalErrorInfo = EvalErrorInfo()

    @classmethod
    def from_csv_row(cls, row: Mapping[str, Any]) -> "CrawlEvalResult":
        input_audio_path = _coerce_optional_path(row.get("input_audio_path", ""))
        event_log_path = _coerce_optional_path(row.get("event_log_path", ""))
        if input_audio_path is None or event_log_path is None:
            raise ValueError(
                "Crawl eval results require input_audio_path and event_log_path."
            )

        return cls(
            example_id=_coerce_str(row.get("example_id", "")),
            user_text=_coerce_str(row.get("user_text", "")),
            expected_tool_call=ExpectedToolCall(
                name=_coerce_str(row.get("gt_tool_call", "")),
                arguments_json=_coerce_str(row.get("gt_tool_call_arg", "")),
            ),
            assistant_text=_coerce_str(row.get("assistant_text", "")),
            tool_calls=_parse_tool_calls(row.get("tool_calls", "[]")),
            tool_call_grade=ToolCallGrade(
                pred_tool_call=_coerce_str(row.get("pred_tool_call", "")),
                pred_tool_call_arg=_coerce_str(row.get("pred_tool_call_arg", "")),
                tool_call_correctness=int(row.get("tool_call_correctness", 0)),
                tool_call_arg_correctness=int(row.get("tool_call_arg_correctness", 0)),
            ),
            artifact_paths=ResultArtifactPaths(
                input_audio_path=input_audio_path,
                event_log_path=event_log_path,
                output_audio_path=_coerce_optional_path(
                    row.get("output_audio_path", "")
                ),
            ),
            latencies=ResultLatencies(
                first_audio_ms=_coerce_optional_float(
                    row.get("latency_first_audio_ms")
                ),
                first_text_ms=_coerce_optional_float(row.get("latency_first_text_ms")),
                response_done_ms=_coerce_optional_float(
                    row.get("latency_response_done_ms")
                ),
            ),
            output_tokens=OutputTokenUsage(
                output_tokens=_coerce_optional_int(row.get("output_tokens")),
                output_audio_tokens=_coerce_optional_int(
                    row.get("output_audio_tokens")
                ),
                output_text_tokens=_coerce_optional_int(row.get("output_text_tokens")),
            ),
            error_info=EvalErrorInfo(
                status=_coerce_str(row.get("status", "ok")) or "ok",
                failure_stage=_coerce_str(row.get("failure_stage", "")),
                error_type=_coerce_str(row.get("error_type", "")),
                error_message=_coerce_str(row.get("error_message", "")),
            ),
        )

    def _tool_grade_csv_fields(
        self,
        *,
        include_tool_call_columns: bool,
        include_tool_call_arg_columns: bool,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {}
        if include_tool_call_columns:
            row["gt_tool_call"] = self.expected_tool_call.name
            row["pred_tool_call"] = self.tool_call_grade.pred_tool_call
            row["tool_call_correctness"] = self.tool_call_grade.tool_call_correctness
        if include_tool_call_arg_columns:
            row["gt_tool_call_arg"] = self.expected_tool_call.arguments_json
            row["pred_tool_call_arg"] = self.tool_call_grade.pred_tool_call_arg
            row["tool_call_arg_correctness"] = (
                self.tool_call_grade.tool_call_arg_correctness
            )
        if include_tool_call_columns and include_tool_call_arg_columns:
            row["grade"] = self.tool_call_grade.grade
        return row

    def to_csv_row(
        self,
        *,
        include_tool_call_columns: bool = True,
        include_tool_call_arg_columns: bool = True,
    ) -> dict[str, Any]:
        row = {
            "example_id": self.example_id,
            "user_text": self.user_text,
            "input_audio_path": str(self.artifact_paths.input_audio_path),
            "assistant_text": self.assistant_text,
            "output_audio_path": (
                str(self.artifact_paths.output_audio_path)
                if self.artifact_paths.output_audio_path is not None
                else ""
            ),
            "event_log_path": str(self.artifact_paths.event_log_path),
            "tool_calls": json.dumps(
                [tool_call.to_dict() for tool_call in self.tool_calls]
            ),
            "latency_first_audio_ms": self.latencies.first_audio_ms,
            "latency_first_text_ms": self.latencies.first_text_ms,
            "latency_response_done_ms": self.latencies.response_done_ms,
            "output_tokens": self.output_tokens.output_tokens,
            "output_audio_tokens": self.output_tokens.output_audio_tokens,
            "output_text_tokens": self.output_tokens.output_text_tokens,
            "status": self.error_info.status,
            "failure_stage": self.error_info.failure_stage,
            "error_type": self.error_info.error_type,
            "error_message": self.error_info.error_message,
        }
        row.update(
            self._tool_grade_csv_fields(
                include_tool_call_columns=include_tool_call_columns,
                include_tool_call_arg_columns=include_tool_call_arg_columns,
            )
        )
        return row


@dataclass(slots=True)
class WalkEvalResult:
    example_id: str
    user_text: str
    expected_tool_call: ExpectedToolCall
    assistant_text: str
    tool_calls: list[ToolCallRecord]
    tool_call_grade: ToolCallGrade
    audio_path: Path
    event_log_path: Path
    output_audio_path: Path | None
    latencies: ResultLatencies
    output_tokens: OutputTokenUsage
    error_info: EvalErrorInfo = EvalErrorInfo()

    def _tool_grade_csv_fields(
        self,
        *,
        include_tool_call_columns: bool,
        include_tool_call_arg_columns: bool,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {}
        if include_tool_call_columns:
            row["gt_tool_call"] = self.expected_tool_call.name
            row["pred_tool_call"] = self.tool_call_grade.pred_tool_call
            row["tool_call_correctness"] = self.tool_call_grade.tool_call_correctness
        if include_tool_call_arg_columns:
            row["gt_tool_call_arg"] = self.expected_tool_call.arguments_json
            row["pred_tool_call_arg"] = self.tool_call_grade.pred_tool_call_arg
            row["tool_call_arg_correctness"] = (
                self.tool_call_grade.tool_call_arg_correctness
            )
        if include_tool_call_columns and include_tool_call_arg_columns:
            row["grade"] = self.tool_call_grade.grade
        return row

    def to_csv_row(
        self,
        *,
        include_tool_call_columns: bool = True,
        include_tool_call_arg_columns: bool = True,
    ) -> dict[str, Any]:
        row = {
            "example_id": self.example_id,
            "user_text": self.user_text,
            "audio_path": str(self.audio_path),
            "assistant_text": self.assistant_text,
            "output_audio_path": (
                str(self.output_audio_path)
                if self.output_audio_path is not None
                else ""
            ),
            "event_log_path": str(self.event_log_path),
            "tool_calls": json.dumps(
                [tool_call.to_dict() for tool_call in self.tool_calls]
            ),
            "latency_first_audio_ms": self.latencies.first_audio_ms,
            "latency_first_text_ms": self.latencies.first_text_ms,
            "latency_response_done_ms": self.latencies.response_done_ms,
            "output_tokens": self.output_tokens.output_tokens,
            "output_audio_tokens": self.output_tokens.output_audio_tokens,
            "output_text_tokens": self.output_tokens.output_text_tokens,
            "status": self.error_info.status,
            "failure_stage": self.error_info.failure_stage,
            "error_type": self.error_info.error_type,
            "error_message": self.error_info.error_message,
        }
        row.update(
            self._tool_grade_csv_fields(
                include_tool_call_columns=include_tool_call_columns,
                include_tool_call_arg_columns=include_tool_call_arg_columns,
            )
        )
        return row


@dataclass(slots=True, frozen=True)
class NumericMetricSummary:
    avg: float | None = None
    p50: float | None = None
    p95: float | None = None
    p99: float | None = None

    @classmethod
    def from_flat_summary(
        cls, summary: Mapping[str, Any], prefix: str
    ) -> "NumericMetricSummary | None":
        metric = cls(
            avg=_coerce_optional_float(summary.get(f"{prefix}_avg")),
            p50=_coerce_optional_float(summary.get(f"{prefix}_p50")),
            p95=_coerce_optional_float(summary.get(f"{prefix}_p95")),
            p99=_coerce_optional_float(summary.get(f"{prefix}_p99")),
        )
        if all(
            value is None for value in (metric.avg, metric.p50, metric.p95, metric.p99)
        ):
            return None
        return metric

    def to_flat_summary(self, prefix: str) -> dict[str, float]:
        data: dict[str, float] = {}
        if self.avg is not None:
            data[f"{prefix}_avg"] = self.avg
        if self.p50 is not None:
            data[f"{prefix}_p50"] = self.p50
        if self.p95 is not None:
            data[f"{prefix}_p95"] = self.p95
        if self.p99 is not None:
            data[f"{prefix}_p99"] = self.p99
        return data


@dataclass(slots=True, frozen=True)
class CrawlEvalRunConfig:
    run_name: str
    model: str
    tts_model: str
    voice: str
    chunk_ms: int
    sample_rate_hz: int
    input_audio_format: str
    output_audio_format: str
    real_time: bool
    data_csv: Path
    system_prompt_file: Path
    tools_file: Path

    def to_flat_summary(self) -> dict[str, Any]:
        return {
            "run_name": self.run_name,
            "model": self.model,
            "tts_model": self.tts_model,
            "voice": self.voice,
            "chunk_ms": self.chunk_ms,
            "sample_rate_hz": self.sample_rate_hz,
            "input_audio_format": self.input_audio_format,
            "output_audio_format": self.output_audio_format,
            "real_time": self.real_time,
            "data_csv": str(self.data_csv),
            "system_prompt_file": str(self.system_prompt_file),
            "tools_file": str(self.tools_file),
        }


@dataclass(slots=True, frozen=True)
class CrawlEvalRunSummary:
    total_examples: int
    failed_examples: int
    grade_mean: float
    config: CrawlEvalRunConfig
    tool_call_correctness_mean: float | None = None
    tool_call_arg_correctness_mean: float | None = None
    latency_first_audio_ms: NumericMetricSummary | None = None
    latency_first_text_ms: NumericMetricSummary | None = None
    latency_response_done_ms: NumericMetricSummary | None = None
    output_tokens: NumericMetricSummary | None = None
    output_audio_tokens: NumericMetricSummary | None = None
    output_text_tokens: NumericMetricSummary | None = None

    @classmethod
    def from_flat_summary(
        cls, summary: Mapping[str, Any], config: CrawlEvalRunConfig
    ) -> "CrawlEvalRunSummary":
        return cls(
            total_examples=int(summary.get("total_examples", 0)),
            failed_examples=int(summary.get("failed_examples", 0)),
            grade_mean=float(summary.get("grade_mean", 0.0)),
            config=config,
            tool_call_correctness_mean=_coerce_optional_float(
                summary.get("tool_call_correctness_mean")
            ),
            tool_call_arg_correctness_mean=_coerce_optional_float(
                summary.get("tool_call_arg_correctness_mean")
            ),
            latency_first_audio_ms=NumericMetricSummary.from_flat_summary(
                summary, "latency_first_audio_ms"
            ),
            latency_first_text_ms=NumericMetricSummary.from_flat_summary(
                summary, "latency_first_text_ms"
            ),
            latency_response_done_ms=NumericMetricSummary.from_flat_summary(
                summary, "latency_response_done_ms"
            ),
            output_tokens=NumericMetricSummary.from_flat_summary(
                summary, "output_tokens"
            ),
            output_audio_tokens=NumericMetricSummary.from_flat_summary(
                summary, "output_audio_tokens"
            ),
            output_text_tokens=NumericMetricSummary.from_flat_summary(
                summary, "output_text_tokens"
            ),
        )

    def to_flat_summary(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "total_examples": self.total_examples,
            "failed_examples": self.failed_examples,
            "grade_mean": self.grade_mean,
        }
        if self.tool_call_correctness_mean is not None:
            summary["tool_call_correctness_mean"] = self.tool_call_correctness_mean
        if self.tool_call_arg_correctness_mean is not None:
            summary["tool_call_arg_correctness_mean"] = (
                self.tool_call_arg_correctness_mean
            )

        metric_fields = {
            "latency_first_audio_ms": self.latency_first_audio_ms,
            "latency_first_text_ms": self.latency_first_text_ms,
            "latency_response_done_ms": self.latency_response_done_ms,
            "output_tokens": self.output_tokens,
            "output_audio_tokens": self.output_audio_tokens,
            "output_text_tokens": self.output_text_tokens,
        }
        for prefix, metric in metric_fields.items():
            if metric is not None:
                summary.update(metric.to_flat_summary(prefix))

        summary.update(self.config.to_flat_summary())
        return summary


@dataclass(slots=True, frozen=True)
class WalkEvalRunConfig:
    run_name: str
    model: str
    voice: str
    chunk_ms: int
    sample_rate_hz: int
    input_audio_format: str
    output_audio_format: str
    output_sample_rate_hz: int
    real_time: bool
    data_csv: Path
    system_prompt_file: Path
    tools_file: Path

    def to_flat_summary(self) -> dict[str, Any]:
        return {
            "run_name": self.run_name,
            "model": self.model,
            "voice": self.voice,
            "chunk_ms": self.chunk_ms,
            "sample_rate_hz": self.sample_rate_hz,
            "input_audio_format": self.input_audio_format,
            "output_audio_format": self.output_audio_format,
            "output_sample_rate_hz": self.output_sample_rate_hz,
            "real_time": self.real_time,
            "data_csv": str(self.data_csv),
            "system_prompt_file": str(self.system_prompt_file),
            "tools_file": str(self.tools_file),
        }


@dataclass(slots=True, frozen=True)
class WalkEvalRunSummary:
    total_examples: int
    failed_examples: int
    grade_mean: float
    config: WalkEvalRunConfig
    tool_call_correctness_mean: float | None = None
    tool_call_arg_correctness_mean: float | None = None
    latency_first_audio_ms: NumericMetricSummary | None = None
    latency_first_text_ms: NumericMetricSummary | None = None
    latency_response_done_ms: NumericMetricSummary | None = None
    output_tokens: NumericMetricSummary | None = None
    output_audio_tokens: NumericMetricSummary | None = None
    output_text_tokens: NumericMetricSummary | None = None

    @classmethod
    def from_flat_summary(
        cls, summary: Mapping[str, Any], config: WalkEvalRunConfig
    ) -> "WalkEvalRunSummary":
        return cls(
            total_examples=int(summary.get("total_examples", 0)),
            failed_examples=int(summary.get("failed_examples", 0)),
            grade_mean=float(summary.get("grade_mean", 0.0)),
            config=config,
            tool_call_correctness_mean=_coerce_optional_float(
                summary.get("tool_call_correctness_mean")
            ),
            tool_call_arg_correctness_mean=_coerce_optional_float(
                summary.get("tool_call_arg_correctness_mean")
            ),
            latency_first_audio_ms=NumericMetricSummary.from_flat_summary(
                summary, "latency_first_audio_ms"
            ),
            latency_first_text_ms=NumericMetricSummary.from_flat_summary(
                summary, "latency_first_text_ms"
            ),
            latency_response_done_ms=NumericMetricSummary.from_flat_summary(
                summary, "latency_response_done_ms"
            ),
            output_tokens=NumericMetricSummary.from_flat_summary(
                summary, "output_tokens"
            ),
            output_audio_tokens=NumericMetricSummary.from_flat_summary(
                summary, "output_audio_tokens"
            ),
            output_text_tokens=NumericMetricSummary.from_flat_summary(
                summary, "output_text_tokens"
            ),
        )

    def to_flat_summary(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "total_examples": self.total_examples,
            "failed_examples": self.failed_examples,
            "grade_mean": self.grade_mean,
        }
        if self.tool_call_correctness_mean is not None:
            summary["tool_call_correctness_mean"] = self.tool_call_correctness_mean
        if self.tool_call_arg_correctness_mean is not None:
            summary["tool_call_arg_correctness_mean"] = (
                self.tool_call_arg_correctness_mean
            )
        for prefix, metric in {
            "latency_first_audio_ms": self.latency_first_audio_ms,
            "latency_first_text_ms": self.latency_first_text_ms,
            "latency_response_done_ms": self.latency_response_done_ms,
            "output_tokens": self.output_tokens,
            "output_audio_tokens": self.output_audio_tokens,
            "output_text_tokens": self.output_text_tokens,
        }.items():
            if metric is not None:
                summary.update(metric.to_flat_summary(prefix))
        summary.update(self.config.to_flat_summary())
        return summary


@dataclass(slots=True, frozen=True)
class RunTurnArtifactPaths:
    user_audio_path: Path
    assistant_audio_path: Path
    event_log_path: Path


@dataclass(slots=True)
class RunTurnResult:
    simulation_id: str
    assistant_model: str
    simulator_model: str
    turn_index: int
    user_text: str
    assistant_text: str
    expected_tool_call: ExpectedToolCall
    tool_calls: list[ToolCallRecord]
    tool_outputs: list[ToolOutputRecord]
    tool_call_grade: ToolCallGrade
    artifact_paths: RunTurnArtifactPaths
    latencies: ResultLatencies
    output_tokens: OutputTokenUsage
    error_info: EvalErrorInfo = EvalErrorInfo()
    extra_grades: dict[str, int] = field(default_factory=dict)
    extra_rationales: dict[str, str] = field(default_factory=dict)

    def set_grader_result(self, grader_id: str, grade: int, rationale: str) -> None:
        self.extra_grades[grader_id] = grade
        self.extra_rationales[grader_id] = rationale

    def _tool_grade_csv_fields(
        self,
        *,
        include_tool_call_columns: bool,
        include_tool_call_arg_columns: bool,
    ) -> dict[str, Any]:
        row: dict[str, Any] = {}
        if include_tool_call_columns:
            row["gt_tool_call"] = self.expected_tool_call.name
            row["pred_tool_call"] = self.tool_call_grade.pred_tool_call
            row["tool_call_correctness"] = self.tool_call_grade.tool_call_correctness
        if include_tool_call_arg_columns:
            row["gt_tool_call_arg"] = self.expected_tool_call.arguments_json
            row["pred_tool_call_arg"] = self.tool_call_grade.pred_tool_call_arg
            row["tool_call_arg_correctness"] = (
                self.tool_call_grade.tool_call_arg_correctness
            )
        return row

    def to_csv_row(
        self,
        *,
        include_tool_call_columns: bool = True,
        include_tool_call_arg_columns: bool = True,
    ) -> dict[str, Any]:
        row = {
            "simulation_id": self.simulation_id,
            "assistant_model": self.assistant_model,
            "simulator_model": self.simulator_model,
            "turn_index": self.turn_index,
            "user_text": self.user_text,
            "assistant_text": self.assistant_text,
            "tool_calls": json.dumps(
                [tool_call.to_dict() for tool_call in self.tool_calls]
            ),
            "tool_outputs": json.dumps(
                [tool_output.to_dict() for tool_output in self.tool_outputs]
            ),
            "user_audio_path": str(self.artifact_paths.user_audio_path),
            "assistant_audio_path": str(self.artifact_paths.assistant_audio_path),
            "event_log_path": str(self.artifact_paths.event_log_path),
            "latency_first_audio_ms": self.latencies.first_audio_ms,
            "latency_first_text_ms": self.latencies.first_text_ms,
            "latency_response_done_ms": self.latencies.response_done_ms,
            "output_tokens": self.output_tokens.output_tokens,
            "output_audio_tokens": self.output_tokens.output_audio_tokens,
            "output_text_tokens": self.output_tokens.output_text_tokens,
            "status": self.error_info.status,
            "failure_stage": self.error_info.failure_stage,
            "error_type": self.error_info.error_type,
            "error_message": self.error_info.error_message,
        }
        row.update(
            self._tool_grade_csv_fields(
                include_tool_call_columns=include_tool_call_columns,
                include_tool_call_arg_columns=include_tool_call_arg_columns,
            )
        )
        for grader_id, grade in self.extra_grades.items():
            row[f"{grader_id}_grade"] = grade
            row[f"{grader_id}_rationale"] = self.extra_rationales.get(grader_id, "")
        return row


@dataclass(slots=True)
class RunSimulationResult:
    rows: list[RunTurnResult]
    turn_grade_requests: list[dict[str, Any]]
    trace_grade_requests: list[dict[str, Any]]
    simulation_id: str
    include_tool_call_columns: bool = False
    include_tool_call_arg_columns: bool = False


@dataclass(slots=True, frozen=True)
class RunEvalRunConfig:
    run_name: str
    assistant_model_default: str
    simulator_model_default: str
    input_audio_format: str
    output_audio_format: str
    chunk_ms: int
    sample_rate_hz: int
    real_time: bool
    data_csv: Path

    def to_flat_summary(self) -> dict[str, Any]:
        return {
            "run_name": self.run_name,
            "assistant_model_default": self.assistant_model_default,
            "simulator_model_default": self.simulator_model_default,
            "input_audio_format": self.input_audio_format,
            "output_audio_format": self.output_audio_format,
            "chunk_ms": self.chunk_ms,
            "sample_rate_hz": self.sample_rate_hz,
            "real_time": self.real_time,
            "data_csv": str(self.data_csv),
        }


@dataclass(slots=True, frozen=True)
class RunEvalRunSummary:
    total_rows: int
    failed_simulations: int
    grade_means: dict[str, float]
    config: RunEvalRunConfig
    latency_first_audio_ms: NumericMetricSummary | None = None
    latency_first_text_ms: NumericMetricSummary | None = None
    latency_response_done_ms: NumericMetricSummary | None = None
    output_tokens: NumericMetricSummary | None = None
    output_audio_tokens: NumericMetricSummary | None = None
    output_text_tokens: NumericMetricSummary | None = None

    @classmethod
    def from_flat_summary(
        cls, summary: Mapping[str, Any], config: RunEvalRunConfig
    ) -> "RunEvalRunSummary":
        grade_means: dict[str, float] = {}
        overall_grade_mean = _coerce_optional_float(summary.get("grade_mean"))
        if overall_grade_mean is not None:
            grade_means["grade_mean"] = overall_grade_mean
        grade_means.update(
            {
                key: float(value)
                for key, value in summary.items()
                if key.endswith("_grade_mean") and value not in (None, "")
            }
        )
        return cls(
            total_rows=int(summary.get("total_rows", 0)),
            failed_simulations=int(summary.get("failed_simulations", 0)),
            grade_means=grade_means,
            config=config,
            latency_first_audio_ms=NumericMetricSummary.from_flat_summary(
                summary, "latency_first_audio_ms"
            ),
            latency_first_text_ms=NumericMetricSummary.from_flat_summary(
                summary, "latency_first_text_ms"
            ),
            latency_response_done_ms=NumericMetricSummary.from_flat_summary(
                summary, "latency_response_done_ms"
            ),
            output_tokens=NumericMetricSummary.from_flat_summary(
                summary, "output_tokens"
            ),
            output_audio_tokens=NumericMetricSummary.from_flat_summary(
                summary, "output_audio_tokens"
            ),
            output_text_tokens=NumericMetricSummary.from_flat_summary(
                summary, "output_text_tokens"
            ),
        )

    def to_flat_summary(self) -> dict[str, Any]:
        summary: dict[str, Any] = {
            "total_rows": self.total_rows,
            "failed_simulations": self.failed_simulations,
        }
        summary.update(self.grade_means)
        for prefix, metric in {
            "latency_first_audio_ms": self.latency_first_audio_ms,
            "latency_first_text_ms": self.latency_first_text_ms,
            "latency_response_done_ms": self.latency_response_done_ms,
            "output_tokens": self.output_tokens,
            "output_audio_tokens": self.output_audio_tokens,
            "output_text_tokens": self.output_text_tokens,
        }.items():
            if metric is not None:
                summary.update(metric.to_flat_summary(prefix))
        summary.update(self.config.to_flat_summary())
        return summary
