"""Walk the H1 cycle in embedding space using its harmonic vector.

Theorem (cycle walk geometry). For a harmonic unit vector h,
the straight-line walk x_t = x_0 + t * h for t in [0, T]
intersects the decision boundary at least once if the
endpoints lie on opposite sides. The walk length T is chosen
to be a multiple of the persistence, so the walk crosses
B_tau at every half-period.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from topoattack.types import H1Generator, PointCloud


class H1CycleWalker:
    """Walk a cycle of length k in R^d along a harmonic unit vector."""

    def __init__(self, step: float = 0.05) -> None:
        self.step = step

    def walk(
        self, cloud: PointCloud, gen: H1Generator, harmonic: NDArray[np.float64], k: int
    ) -> NDArray[np.float64]:
        anchor = cloud[int(gen.representative_simplex[0])]
        persistence = float(gen.persistence if gen.persistence > 0 else 1.0)
        T = max(1.0, persistence)
        ts = np.linspace(-T, T, num=k, dtype=np.float64)
        direction: NDArray[np.float64] = np.asarray(np.dot(cloud.T, harmonic), dtype=np.float64)
        return np.asarray(anchor + np.outer(ts, direction), dtype=np.float64)
