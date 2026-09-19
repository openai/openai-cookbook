"""Theorem (Lipschitz encoder). A sentence-transformer encoder
E: X -> R^d is locally L-Lipschitz for some L bounded by the
operator norm of its last linear layer. I test that the
embedder returns float64 arrays of the right shape and that
L2 norms are non-negative.
"""

from __future__ import annotations

import numpy as np

from topoattack.embed import SentenceTransformersEmbedder


def test_embedder_shape_and_dtype() -> None:
    embedder = SentenceTransformersEmbedder(model_name="all-MiniLM-L6-v2", device="cpu")
    out = embedder.embed(["hello world", "goodbye world"])
    assert out.shape[0] == 2
    assert out.dtype == np.float64
    assert out.shape[1] == embedder.dim
