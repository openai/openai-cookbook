"""Topoattack: topology-driven adversarial-prompt evaluation.

Theorem (Topological Blind Spot).
Let S be a security guard implemented as f = g . E, where
E: X -> R^d is an encoder and g: R^d -> [0,1] is a piecewise-linear
classifier (e.g. a ReLU network). The decision boundary
B_tau = {z in R^d : g(z) = tau} is a PL (d-1)-manifold. If
d >= 3 and f is trained on finite data, B_tau has non-trivial
first persistent homology with probability 1; each high-persistence
H1 generator corresponds to a connected region R in X on which
f is inconsistent across semantically equivalent inputs.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
