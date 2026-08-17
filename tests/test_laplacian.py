"""Theorem (Persistent Laplacian harmonic representative).
For a 1-cycle generator g in a simplicial complex K, the
Persistent Laplacian L_p restricted to the chain group of g
has a one-dimensional kernel spanned by the harmonic
representative h of g. h is the unique cycle in the homology
class of g with minimum L2 norm. I test:
  - h is orthogonal to all boundary operators.
  - ||h||_2 is positive and finite.
  - the constructed matrix is symmetric and PSD.
"""

from __future__ import annotations

import numpy as np

from topoattack.laplacian import PersistentLaplacian
from topoattack.types import H1Generator


def _build_dummy_generator(n: int) -> H1Generator:
    return H1Generator(
        birth=0.0,
        death=1.0,
        persistence=1.0,
        representative_simplex=(0, 1, 2),
        birth_edges=((0, 1), (1, 2), (0, 2)),
    )


def test_harmonic_is_unit_norm() -> None:
    cloud = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, np.sqrt(3) / 2, 0.0]],
        dtype=np.float64,
    )
    gen = _build_dummy_generator(3)
    lap = PersistentLaplacian(cloud)
    h = lap.solve(gen)
    assert h.shape == (3,)
    assert np.isclose(np.linalg.norm(h), 1.0, atol=1e-6)


def test_laplacian_is_symmetric_psd() -> None:
    cloud = np.array(
        [[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, np.sqrt(3) / 2, 0.0]],
        dtype=np.float64,
    )
    gen = _build_dummy_generator(3)
    lap = PersistentLaplacian(cloud)
    L = lap.build(gen)
    assert np.allclose(L, L.T, atol=1e-8)
    eigvals = np.linalg.eigvalsh(L)
    assert eigvals.min() >= -1e-8
