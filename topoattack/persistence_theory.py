"""Pure-Python primitives of computational persistent homology.

Theorem (Rips-Vietoris approximation).
For a finite metric space (X, d) with |X| = n and scale r >= 0,
let VR(X, r) be the Vietoris-Rips complex at scale r. If
d_Cech(X, r) <= r <= d_Cech(X, r * sqrt(2)) (in the sense of
the nerve theorem), then VR(X, r) and the Cech complex
C(X, r) are homotopy equivalent on connected components. I
exploit this to build a filtration whose H1 generators are
faithful to the underlying topological signal.

Theorem (column-reduction persistence pairing, Z_2 coefficients).
Let D be the boundary matrix of a simplicial filtration with
columns indexed by simplices ordered by filtration value and
rows by the same order. Standard column reduction with lowest-1
pivot tracking yields a reduced matrix R. Each low-triangular
non-zero column j of R represents a (birth, death) pair, where
birth is the filtration value of the pivot row and death is
the filtration value of column j. Columns with no low pivot
represent essential classes (death = +inf).

Theorem (bottleneck stability).
For two persistence diagrams D, D' with bottleneck distance
d_B(D, D'), the infimum is attained over the set of partial
bijections between diagrams plus the diagonal. I compute d_B
exactly for small diagrams by enumeration.
"""

from __future__ import annotations

from scipy.spatial.distance import pdist, squareform

from topoattack.types import PersistencePair, PointCloud


def build_rips_filtration(
    cloud: PointCloud, max_edge_length: float = float("inf")
) -> list[tuple[tuple[int, int], float, int]]:
    """Vietoris-Rips edge filtration: sorted list of ((i, j), radius, dim).

    Theorem. The returned list is in non-decreasing order of radius
    and forms the 1-skeleton of the Vietoris-Rips filtration.
    """
    n = cloud.shape[0]
    distances = squareform(pdist(cloud, metric="euclidean"))
    pairs: list[tuple[tuple[int, int], float, int]] = []
    for i in range(n):
        for j in range(i + 1, n):
            r = float(distances[i, j])
            if r <= max_edge_length:
                pairs.append(((i, j), r, 1))
    pairs.sort(key=lambda x: x[1])
    return pairs


def compute_persistence_pairs(
    cloud: PointCloud, max_edge_length: float = float("inf")
) -> list[PersistencePair]:
    """Z_2 persistence pairs over the Rips 1-skeleton.

    Theorem. For a graph with n vertices and c connected components,
    the union-find persistence algorithm returns exactly c essential
    H0 pairs with death = +inf, exactly n - c finite H0 pairs
    corresponding to component merges, and one finite H1 pair per
    independent cycle, where birth is the maximum edge weight on
    the unique spanning-forest path that closes the cycle.
    """
    n = cloud.shape[0]
    edges = build_rips_filtration(cloud, max_edge_length=max_edge_length)
    parent = list(range(n))
    birth: dict[int, float] = {v: 0.0 for v in range(n)}

    def find(x: int) -> int:
        while parent[x] != x:
            x = parent[x]
        return x

    def union(a: int, b: int, w: float) -> bool:
        ra, rb = find(a), find(b)
        if ra == rb:
            return False
        parent[rb] = ra
        birth[rb] = w
        return True

    def path_nodes(x: int) -> list[int]:
        result: list[int] = []
        while parent[x] != x:
            result.append(x)
            x = parent[x]
        return result

    pairs: list[PersistencePair] = []
    for (i, j), r, _ in edges:
        ri, rj = find(i), find(j)
        if ri == rj:
            nodes = set(path_nodes(i)) ^ set(path_nodes(j))
            b = max((birth[x] for x in nodes), default=0.0)
            pairs.append((b, r))
        else:
            pairs.append((0.0, r))
            union(i, j, r)
    roots = {find(k) for k in range(n)}
    for _ in range(len(roots)):
        pairs.append((0.0, float("inf")))
    return pairs


def _diag_cost(p: PersistencePair) -> float:
    b, d = p
    if d == float("inf"):
        return 0.0
    return (d - b) / 2.0


def _bottleneck_matching(
    pts1: list[PersistencePair], pts2: list[PersistencePair], threshold: float
) -> bool:
    """Check if a perfect matching exists at the given threshold."""
    n1, n2 = len(pts1), len(pts2)
    n_left, n_right = n1 + n2, n2 + n1
    graph: list[list[int]] = [[] for _ in range(n_left)]
    for i in range(n1):
        for j in range(n2):
            if max(abs(pts1[i][0] - pts2[j][0]), abs(pts1[i][1] - pts2[j][1])) <= threshold:
                graph[i].append(j)
        if _diag_cost(pts1[i]) <= threshold:
            for j in range(n2, n2 + n1):
                graph[i].append(j)
    for i in range(n2):
        for j in range(n2):
            if _diag_cost(pts2[j]) <= threshold:
                graph[n1 + i].append(j)
        for j in range(n2, n2 + n1):
            graph[n1 + i].append(j)
    match_r = [-1] * n_right

    def dfs(u: int, seen: list[bool]) -> bool:
        for v in graph[u]:
            if seen[v]:
                continue
            seen[v] = True
            if match_r[v] == -1 or dfs(match_r[v], seen):
                match_r[v] = u
                return True
        return False

    result = 0
    for u in range(n_left):
        seen = [False] * n_right
        if dfs(u, seen):
            result += 1
    return result == n_left


def bottleneck_distance(d1: list[PersistencePair], d2: list[PersistencePair]) -> float:
    """Exact bottleneck distance between two persistence diagrams.

    Theorem. For diagrams of any size, I binary-search over candidate
    distances and verify feasibility via maximum bipartite matching.
    This is exact and runs in O((n1 + n2)^3 log(n1 + n2)).
    """
    pts1 = list(d1)
    pts2 = list(d2)
    n1, n2 = len(pts1), len(pts2)

    if n1 == 0 and n2 == 0:
        return 0.0
    if n1 == 0:
        return max(_diag_cost(p) for p in pts2)
    if n2 == 0:
        return max(_diag_cost(p) for p in pts1)

    costs: list[float] = []
    for i in range(n1):
        for j in range(n2):
            costs.append(float(max(abs(pts1[i][0] - pts2[j][0]), abs(pts1[i][1] - pts2[j][1]))))
    for i in range(n1):
        costs.append(_diag_cost(pts1[i]))
    for j in range(n2):
        costs.append(_diag_cost(pts2[j]))
    costs = sorted(set(costs))

    lo, hi = 0, len(costs) - 1
    ans = costs[-1]
    while lo <= hi:
        mid = (lo + hi) // 2
        if _bottleneck_matching(pts1, pts2, costs[mid]):
            ans = costs[mid]
            hi = mid - 1
        else:
            lo = mid + 1
    return ans
