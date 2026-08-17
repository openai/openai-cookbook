"""Theorem (multi-parameter persistence). For a 2-parameter
filtration indexed by (score, prompt_length) in R^2, the
invariant bigraded module decomposes as a direct sum of
indecomposables. The rank function rank(t1, t2) is the
number of components alive at grade (t1, t2). I test that
rank is monotone non-increasing in each argument and that
the surface is well-defined.
"""

from __future__ import annotations

import numpy as np

from topoattack.multi_param import rank_function


def test_rank_is_monotone() -> None:
    cloud = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.5, 0.5, 0.0]], dtype=np.float64)
    scores = np.array([0.1, 0.5, 0.9], dtype=np.float64)
    lengths = np.array([3.0, 5.0, 7.0], dtype=np.float64)
    r1 = rank_function(cloud, scores, lengths, t_score=0.3, t_length=4.0)
    r2 = rank_function(cloud, scores, lengths, t_score=0.6, t_length=4.0)
    assert r1 >= r2


def test_rank_count_in_range() -> None:
    cloud = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], dtype=np.float64)
    scores = np.array([0.2, 0.8], dtype=np.float64)
    lengths = np.array([2.0, 6.0], dtype=np.float64)
    r = rank_function(cloud, scores, lengths, t_score=0.5, t_length=5.0)
    assert 0 <= r <= cloud.shape[0]
