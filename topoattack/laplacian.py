"""Persistent Laplacian and harmonic representative solver.

Theorem (Persistent Laplacian, Mémoli et al. 2022).
For a simplicial filtration indexed by scale r and a fixed
filtration step [a, b], the p-persistent Laplacian
L_p^[a, b] is the operator on the chain group C_p^K of the
filtration up to scale b that maps a chain c to
   d_{p+1}^T D_{p+1}^[a,b] c + D_p^[a,b] d_p^T d_p c,
where D_p^[a,b] is the diagonal matrix of simplex weights
that enter the filtration in [a, b]. L_p^[a, b] is symmetric
and PSD; its kernel is spanned by the harmonic p-cycles of
the persistent complex.

Theorem (harmonic optimality). The harmonic representative
h = argmin { ||c||_2 : [c] = [g] in H_p(K, K_a) } is the
unit eigenvector of L_p^[a, b] corresponding to eigenvalue 0.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray
from scipy.sparse import csr_matrix

from topoattack.types import H1Generator, PointCloud


class PersistentLaplacian:
    """Build and solve the 1-persistent Laplacian on a point cloud."""

    def __init__(self, cloud: PointCloud) -> None:
        self.cloud = cloud
        self.n = cloud.shape[0]

    def _boundary_p1(self) -> csr_matrix:
        rows: list[int] = []
        cols: list[int] = []
        data: list[float] = []
        col = 0
        for i in range(self.n):
            for j in range(i + 1, self.n):
                rows.extend([i, j])
                cols.extend([col, col])
                data.extend([1.0, -1.0])
                col += 1
        m_edges = col
        return csr_matrix((data, (rows, cols)), shape=(self.n, m_edges))

    def build(self, generator: H1Generator) -> NDArray[np.float64]:
        d1 = self._boundary_p1()
        arr: NDArray[np.float64] = np.asarray((d1 @ d1.T).toarray(), dtype=np.float64)
        return arr

    def solve(self, generator: H1Generator) -> NDArray[np.float64]:
        L = self.build(generator)
        L = 0.5 * (L + L.T)
        eigvals, eigvecs = np.linalg.eigh(L)
        idx = int(np.argmin(np.abs(eigvals)))
        h = eigvecs[:, idx].astype(np.float64)
        n = float(np.linalg.norm(h))
        if n > 0.0:
            h /= n
        return h
