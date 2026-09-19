"""Typed models used across topoattack.

Theorem (type invariants). All n-dimensional point clouds stored in
NDArray[np.float64] of shape (n, d). All scalar fields stored in
NDArray[np.float64] of shape (n,). Persistence diagrams are lists
of (birth, death) tuples with 0 <= birth < death <= +inf.
"""

from __future__ import annotations

from typing import TypeAlias

import numpy as np
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field

PointCloud: TypeAlias = NDArray[np.float64]
ScalarField: TypeAlias = NDArray[np.float64]
PersistencePair: TypeAlias = tuple[float, float]


class H1Generator(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    birth: float = Field(ge=0.0)
    death: float = Field(ge=0.0)
    persistence: float = Field(ge=0.0)
    representative_simplex: tuple[int, ...] = Field(min_length=3)
    birth_edges: tuple[tuple[int, int], ...]


class AttackPrompt(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    base_index: int = Field(ge=0)
    step: int = Field(ge=0)
    guard_score: float = Field(ge=0.0, le=1.0)
    semantic_similarity: float = Field(ge=0.0, le=1.0)
    judge_verdict: str | None = None
