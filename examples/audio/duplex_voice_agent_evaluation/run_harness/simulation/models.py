"""RUN settings; portable task contracts live in shared."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from assistants.config import ReasoningEffort, assistant_default_tools, assistant_env, assistant_prompt
from shared.audio.effects import AudioRealism
from shared.environment import load_environment
from shared.metrics.interaction import DEFAULT_RESPONSE_DEADLINE_MS
from shared.scenarios import AudioCondition, ExpectedToolCall, Persona, Scenario

DEFAULT_SIMULATOR_BACKEND_MODEL = "gpt-5.6-luna"
DEFAULT_SIMULATOR_BACKEND_REASONING_EFFORT: ReasoningEffort = "low"


class Settings(BaseModel):
    """Run configuration, independent of a reusable scenario or agent provider."""

    @model_validator(mode="before")
    @classmethod
    def load_local_environment(cls, value: Any) -> Any:
        load_environment()
        return value

    completion_model: str = Field(
        default_factory=lambda: os.getenv("OPENAI_COMPLETION_MODEL", "gpt-5.6-terra").strip() or "gpt-5.6-terra"
    )
    semantic_drain: bool = True
    completion_timeout_seconds: float = Field(default=8.0, gt=0, le=60)
    agent_instructions: str = Field(default_factory=lambda: assistant_prompt("frontend"))
    agent_endpoint: str = Field(default_factory=lambda: assistant_env("OPENAI_LIVE_ENDPOINT"))
    agent_model: str = Field(default_factory=lambda: assistant_env("OPENAI_LIVE_MODEL"))
    agent_voice: str = Field(default_factory=lambda: assistant_env("OPENAI_LIVE_VOICE"))
    backend_model: str = Field(default_factory=lambda: assistant_env("OPENAI_LIVE_BACKEND_MODEL"))
    simulator_backend_model: str = Field(default=DEFAULT_SIMULATOR_BACKEND_MODEL, min_length=1)
    simulator_backend_reasoning_effort: ReasoningEffort = DEFAULT_SIMULATOR_BACKEND_REASONING_EFFORT
    assistant_mode: Literal["responses", "client"] = Field(
        default_factory=lambda: os.getenv("OPENAI_ASSISTANT_MODE", "responses").strip() or "responses",
        validate_default=True,
    )
    assistant_endpoint: str = Field(default_factory=lambda: os.getenv("OPENAI_CLIENT_ASSISTANT_ENDPOINT", "").strip())
    backend_instructions: str = Field(
        default_factory=lambda settings: assistant_prompt("backend", assistant_mode=settings["assistant_mode"])
    )
    delegation_tools: list[dict[str, Any]] = Field(
        default_factory=lambda settings: assistant_default_tools(assistant_mode=settings["assistant_mode"])
    )
    tick_ms: int = Field(default=200, ge=20, le=1_000)
    response_deadline_ms: int = Field(default=DEFAULT_RESPONSE_DEADLINE_MS, gt=0)
    sample_rate: int = 24_000
    speech_rms_threshold: float = Field(default=220, ge=0)
    final_audio_quiet_ms: int = Field(default=600, ge=0, le=10_000)
    max_duration_s: float = Field(default=90, gt=0, le=600)
    seed: int = 7
    condition: AudioCondition = "clean"
    audio_realism: AudioRealism = Field(default_factory=AudioRealism)
    listen: bool = False
    verbose: bool = False
    debug_artifacts: bool = False
    save_conversations: Path | None = None
    event_log_path: Path | None = None
    assistant_opening_prompt: str | None = None


__all__ = [
    "AudioRealism",
    "ExpectedToolCall",
    "Persona",
    "Scenario",
    "Settings",
]
