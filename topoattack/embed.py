"""Encoder interface and SentenceTransformers reference implementation.

Theorem (encoder pullback). If E: X -> R^d is L-Lipschitz, then
for any ball B_r(c) in R^d, the preimage E^{-1}(B_r(c)) has
diameter at least r / L in X. This gives the input-space
diameter of an evasion region.
"""

from __future__ import annotations

from typing import Any, Protocol, TypeAlias, runtime_checkable

import numpy as np
from numpy.typing import NDArray

TextBatch: TypeAlias = list[str]


@runtime_checkable
class Embedder(Protocol):
    """Protocol for text encoders. E: X -> R^d, L-Lipschitz."""

    @property
    def dim(self) -> int:
        """Embedding dimension d."""

    def embed(self, texts: TextBatch) -> NDArray[np.float64]:
        """Map a list of strings to an (n, d) float64 array."""


class SentenceTransformersEmbedder:
    """Sentence-Transformers based embedder. Default MiniLM (d=384)."""

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", device: str = "cpu") -> None:
        self.model_name = model_name
        self.device = device
        self._model: Any = None
        self._dim: int | None = None

    def _load(self) -> None:
        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name, device=self.device)
        self._dim = int(self._model.get_embedding_dimension())

    @property
    def dim(self) -> int:
        if self._dim is None:
            self._load()
        assert self._dim is not None
        return self._dim

    def embed(self, texts: TextBatch) -> NDArray[np.float64]:
        if self._model is None:
            self._load()
        assert self._model is not None
        vecs = self._model.encode(
            list(texts),
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        out: NDArray[np.float64] = vecs.astype(np.float64)
        return out
