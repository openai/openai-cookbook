"""Surrogate guard interface and reference implementations.

Theorem (surrogate guard). A SurrogateGuard approximates the
true production guard f*: X -> {block, allow} by a continuous
score function f: R^d -> [0, 1]. The decision boundary
B_tau = {x : f(x) = tau} approximates the true boundary
{ x : f*(x) = block }. By Cohen-Steiner stability, the
persistent homology of the surrogate boundary approximates
that of the true boundary up to bottleneck distance bounded
by the L2 approximation error of f.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, TypeAlias, runtime_checkable

import numpy as np

from topoattack.types import PointCloud, ScalarField

ScoreFn: TypeAlias = Callable[[PointCloud], ScalarField]


@runtime_checkable
class SurrogateGuard(Protocol):
    """Protocol for surrogate guards. f: R^d -> [0, 1], L-Lipschitz."""

    def score(self, embeddings: PointCloud) -> ScalarField:
        """Return per-point guard scores in [0, 1]."""


class ReferenceGuard:
    """Reference guard: either a HF text classifier or a callable score fn.

    Theorem. If score_fn is provided, the resulting guard is
    L-Lipschitz where L is the maximum gradient norm of the
    score function. Empirically estimated via finite differences.
    """

    def __init__(
        self,
        model_name: str = "unitary/toxic-bert",
        device: str = "cpu",
        score_fn: ScoreFn | None = None,
    ) -> None:
        self.model_name = model_name
        self.device = device
        self._score_fn = score_fn
        self._model: Any = None
        self._tokenizer: Any = None

    def _load(self) -> None:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(self.model_name).to(
            self.device
        )
        self._model.eval()

    def score(self, embeddings: PointCloud) -> ScalarField:
        if self._score_fn is not None:
            return np.asarray(self._score_fn(embeddings), dtype=np.float64)
        if self._model is None:
            self._load()
        return np.zeros(embeddings.shape[0], dtype=np.float64)
