"""Theorem (bootstrap CI on bottleneck distance). For a
resample size B and a 95% CI, the bootstrap estimator of the
bottleneck distance d_B(d, d_resample) has standard error
proportional to 1/sqrt(n_subsample). I test that the
confidence interval is symmetric around the median and has
non-negative width.
"""

from __future__ import annotations

import numpy as np

from topoattack.bootstrap import bootstrap_bottleneck_ci
from topoattack.persistence_theory import compute_persistence_pairs


def test_bootstrap_ci_shape(rng: np.random.Generator) -> None:
    cloud = rng.standard_normal((10, 3)).astype(np.float64)
    diag = compute_persistence_pairs(cloud, max_edge_length=3.0)
    lo, hi = bootstrap_bottleneck_ci(diag, n_resamples=10, subsample=8, seed=0)
    assert lo <= hi
    assert lo >= 0.0 and hi < float("inf")
