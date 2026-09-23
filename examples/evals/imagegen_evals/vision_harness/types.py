from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional

TaskType = Literal["image_generation", "image_editing"]
ScoreValue = bool | int | float | str


@dataclass(frozen=True)
class ImageInputs:
    """Editing inputs: one or more reference images + optional mask."""

    image_paths: list[Path]
    mask_path: Optional[Path] = None


@dataclass(frozen=True)
class TestCase:
    """A single evaluable example."""

    id: str
    task_type: TaskType
    prompt: str
    criteria: str
    image_inputs: Optional[ImageInputs] = None


@dataclass(frozen=True)
class ModelRun:
    """One model configuration to evaluate (useful for sweeps)."""

    label: str
    task_type: TaskType
    params: dict[str, Any]  # e.g. {"model": "...", "quality": "...", ...}


@dataclass(frozen=True)
class Artifact:
    """A saved artifact from a run (usually an image)."""

    kind: Literal["image"]
    path: Path
    mime: str = "image/png"


@dataclass
class ModelResponse:
    """Normalized output from any runner."""

    artifacts: list[Artifact] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)  # optional debug payload


@dataclass(frozen=True)
class Score:
    key: str
    value: ScoreValue
    reason: str = ""
    tags: Optional[list[str]] = None
