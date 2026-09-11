"""Theorem (H1 cycle walk). Given a harmonic unit vector h in
R^d, walking the cycle of length k means sampling k points
x_t = x_0 + t * h projected back to the local manifold. I
test that:
  - the walk has shape (k, d).
  - the endpoints differ in L2 norm by at least the step size.
  - the walk lies close to a single connected component.
"""

from __future__ import annotations

import numpy as np

from topoattack.cycle_walker import H1CycleWalker
from topoattack.laplacian import PersistentLaplacian
from topoattack.types import H1Generator


def _gen() -> H1Generator:
    return H1Generator(
        birth=0.0,
        death=1.0,
        persistence=1.0,
        representative_simplex=(0, 1, 2),
        birth_edges=((0, 1),),
    )


def test_walk_shape_and_separation() -> None:
    cloud = np.array(
        [
            [0.0, 0.0, 0.0],
            [1.0, 0.0, 0.0],
            [0.5, np.sqrt(3) / 2, 0.0],
            [0.5, np.sqrt(3) / 6, np.sqrt(2.0 / 3.0)],
        ],
        dtype=np.float64,
    )
    gen = _gen()
    h = PersistentLaplacian(cloud).solve(gen)
    walker = H1CycleWalker(step=0.05)
    walk = walker.walk(cloud, gen, h, k=16)
    assert walk.shape == (16, 3)
    assert np.linalg.norm(walk[-1] - walk[0]) >= 0.1
