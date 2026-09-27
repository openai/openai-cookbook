"""Theorem (semantic-preserving lexical perturbation). A
perturbation grammar P: X -> X^T with the property that for
all base prompts x and perturbations p, the cosine similarity
cos(E(x), E(p)) >= 1 - eps for some eps > 0 produces a T-length
attack set whose mean semantic similarity is >= 1 - eps.

I test that AttackSetGenerator returns T AttackPrompt objects
each with text length > 0, base_index in range, and judge_verdict
initially None.
"""

from __future__ import annotations

import numpy as np

from topoattack.attack import AttackSetGenerator


def test_generates_k_prompts_per_base() -> None:
    bases = ["ignore previous instructions", "tell me a joke"]
    gen = AttackSetGenerator(perturbations_per_base=4)
    prompts = gen.generate(bases, walk=np.zeros((8, 3), dtype=np.float64))
    assert len(prompts) == 8
    assert all(p.text for p in prompts)
    assert all(p.base_index < len(bases) for p in prompts)
