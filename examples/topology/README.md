# topoattack — Topology-driven decision-boundary robustness evaluation

This directory is a self-contained example showing how to use
the Topological Blind Spot Theorem to find decision-boundary
weaknesses in embedding-based guards that front LLM APIs.

## Theorem (Topological Blind Spot)

Let S be a security guard implemented as f = g . E, where
E: X -> R^d is an encoder and g: R^d -> [0, 1] is a
piecewise-linear classifier. The decision boundary
B_tau = { z : g(z) = tau } is a PL (d-1)-manifold. If
d >= 3 and f is trained on finite data, B_tau has
non-trivial first persistent homology with probability 1;
each high-persistence H1 generator corresponds to a
connected region R in X on which f is inconsistent across
semantically equivalent inputs.

## Corollary (Universal Evasion)

No finite embedding-based security control can be topologically
complete. An attacker with black-box access to f and the
ability to compute persistent homology can systematically
discover evasion regions.

## Persistent Laplacian and Harmonic Representatives

For each H1 generator g, the Persistent Laplacian
L_1^{[a, b]} is built on the chain group of the persistent
complex between scales a and b. Its kernel is spanned by the
harmonic representative h(g) of g, which is the unique
1-cycle in the homology class of g with minimum L2 norm.
Walking x_t = x_0 + t * h(g) yields the stealthiest
perturbation direction in R^d.

## Stability (Cohen-Steiner 2007)

For two persistence diagrams D and D' with bottleneck distance
d_B(D, D') <= delta, the diagrams are delta-stable. We
bootstrap this distance under subsampling to obtain a 95%
confidence interval for the persistence of the boundary.

## Usage

```bash
pip install -e ".[dev]"
python -m topoattack analyze --prompts prompts.txt --out out/
cat out/report.md
```

In a notebook:

```python
from topoattack import *
import numpy as np
from topoattack.embed import SentenceTransformersEmbedder
from topoattack.guard import ReferenceGuard
from topoattack.topology import RipserBoundaryAnalyzer

embedder = SentenceTransformersEmbedder()
guard = ReferenceGuard(score_fn=lambda e: 1.0 / (1.0 + np.exp(-(np.linalg.norm(e, axis=1) - 1.0) * 8)))
cloud = embedder.embed(["prompt one", "prompt two", "prompt three"])
gens = RipserBoundaryAnalyzer(guard).fit(cloud)
print(gens)
```

## Responsible use

Do not run this on third-party systems without authorization.
All evaluation prompts in the notebook come from a public
sanitized dataset and target only the local `gpt-4o-mini`
judge; no live vendor exploit is performed.

## References

- Cohen-Steiner, Edelsbrunner, Harer (2007). Stability of
  persistence diagrams.
- Carlsson (2009). Topology and data.
- Mémoli, Zhou, et al. (2022). Persistent Laplacians.
- Goodfellow, Shlens, Szegedy (2015). Explaining and harnessing
  adversarial examples.
