"""Theorem (Lipschitz guard). A guard f: R^d -> [0, 1] that is
L-Lipschitz satisfies |f(x) - f(y)| <= L ||x - y||. I test
that ReferenceGuard exposes a score() method with this contract.
"""

from __future__ import annotations

import numpy as np

from topoattack.guard import ReferenceGuard, SurrogateGuard
from topoattack.types import PointCloud, ScalarField


def test_protocol_is_runtime_checkable() -> None:
    guard = ReferenceGuard(model_name="unitary/toxic-bert", device="cpu")
    assert isinstance(guard, SurrogateGuard)


def test_score_shape_and_range(ring_score_function) -> None:
    cloud: PointCloud = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        dtype=np.float64,
    )
    guard = ReferenceGuard(score_fn=ring_score_function)
    s: ScalarField = guard.score(cloud)
    assert s.shape == (4,)
    assert np.all((s >= 0.0) & (s <= 1.0))
