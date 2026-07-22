"""Shared pytest fixtures: deterministic synthetic point clouds and guards."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import pytest
from numpy.typing import NDArray


@pytest.fixture
def rng() -> np.random.Generator:
    return np.random.default_rng(seed=1729)


@pytest.fixture
def circle_cloud(rng: np.random.Generator) -> NDArray[np.float64]:
    n = 64
    t = rng.uniform(0.0, 2.0 * np.pi, size=n)
    r = 1.0 + 0.05 * rng.standard_normal(size=n)
    x = r * np.cos(t)
    y = r * np.sin(t)
    z = 0.1 * rng.standard_normal(size=n)
    return np.column_stack([x, y, z]).astype(np.float64)


@pytest.fixture
def ring_score_function() -> Callable[[NDArray[np.float64]], NDArray[np.float64]]:
    def score(emb: NDArray[np.float64]) -> NDArray[np.float64]:
        radial = np.linalg.norm(emb[:, :2], axis=1)
        result: NDArray[np.float64] = 1.0 / (1.0 + np.exp(-(radial - 1.0) * 8.0))
        return result

    return score
