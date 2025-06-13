import os
import sys
import math
import types
import pytest

# Add path to examples/utils
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "examples", "utils"))

# ---------------------------------------------------------------------------
# Provide lightweight stubs for external dependencies so that the utilities
# can be imported without the real packages installed. Only the minimal
# functionality needed for the tested functions is implemented.
# ---------------------------------------------------------------------------

# Minimal numpy stub
np_stub = types.ModuleType("numpy")

def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _norm(v):
    return math.sqrt(sum(x * x for x in v))


def _argsort(seq):
    return sorted(range(len(seq)), key=lambda i: seq[i])


np_stub.dot = _dot
np_stub.array = lambda x: x
np_stub.argsort = _argsort
np_stub.linalg = types.SimpleNamespace(norm=_norm)
np_stub.ndarray = list
np_stub.isscalar = lambda x: not isinstance(x, (list, tuple))
np_stub.asarray = lambda x: list(x)
sys.modules.setdefault("numpy", np_stub)

# Minimal scipy.spatial.distance stub
scipy_stub = types.ModuleType("scipy")
spatial_stub = types.ModuleType("spatial")
distance_stub = types.ModuleType("distance")


def _cosine(a, b):
    return 1 - _dot(a, b) / (_norm(a) * _norm(b))


def _cityblock(a, b):
    return sum(abs(x - y) for x, y in zip(a, b))


def _euclidean(a, b):
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _chebyshev(a, b):
    return max(abs(x - y) for x, y in zip(a, b))


distance_stub.cosine = _cosine
distance_stub.cityblock = _cityblock
distance_stub.euclidean = _euclidean
distance_stub.chebyshev = _chebyshev
spatial_stub.distance = distance_stub
scipy_stub.spatial = spatial_stub
sys.modules.setdefault("scipy", scipy_stub)
sys.modules.setdefault("scipy.spatial", spatial_stub)
sys.modules.setdefault("scipy.spatial.distance", distance_stub)

# Other unused imports in embeddings_utils
sys.modules.setdefault("matplotlib", types.ModuleType("matplotlib"))
sys.modules.setdefault(
    "matplotlib.pyplot", types.ModuleType("matplotlib.pyplot")
)
sys.modules.setdefault("plotly", types.ModuleType("plotly"))
sys.modules.setdefault("plotly.express", types.ModuleType("plotly.express"))
sys.modules.setdefault("sklearn", types.ModuleType("sklearn"))
sklearn_decomp = types.ModuleType("sklearn.decomposition")
sklearn_manifold = types.ModuleType("sklearn.manifold")
sklearn_metrics = types.ModuleType("sklearn.metrics")

class _Dummy:
    def __init__(self, *a, **k):
        pass

    def fit_transform(self, X):
        return X


sklearn_decomp.PCA = _Dummy
sklearn_manifold.TSNE = _Dummy
sklearn_metrics.average_precision_score = lambda *a, **k: 0
sklearn_metrics.precision_recall_curve = lambda *a, **k: ([0], [0], [0])

sys.modules.setdefault("sklearn.decomposition", sklearn_decomp)
sys.modules.setdefault("sklearn.manifold", sklearn_manifold)
sys.modules.setdefault("sklearn.metrics", sklearn_metrics)

openai_stub = types.ModuleType("openai")
openai_stub.OpenAI = type("OpenAI", (), {"__init__": lambda self, *a, **k: None})
sys.modules.setdefault("openai", openai_stub)
sys.modules.setdefault("pandas", types.ModuleType("pandas"))

from embeddings_utils import (
    cosine_similarity,
    distances_from_embeddings,
    indices_of_nearest_neighbors_from_distances,
)


def test_cosine_similarity_basic():
    a = [1, 0]
    b = [1, 0]
    c = [0, 1]
    d = [1, 1]

    assert math.isclose(cosine_similarity(a, b), 1.0, rel_tol=1e-6)
    assert math.isclose(cosine_similarity(a, c), 0.0, rel_tol=1e-6)
    expected = 1 / math.sqrt(2)
    assert math.isclose(cosine_similarity(a, d), expected, rel_tol=1e-6)


def test_distances_from_embeddings_cosine():
    query = [1.0, 0.0]
    embeddings = [[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]]
    dists = distances_from_embeddings(query, embeddings, distance_metric="cosine")
    expected = [0.0, 1.0, 1 - 1 / math.sqrt(2)]
    assert all(
        math.isclose(d, e, rel_tol=1e-6) for d, e in zip(dists, expected)
    )


def test_indices_of_nearest_neighbors_from_distances():
    distances = [0.5, 0.2, 0.9]
    indices = indices_of_nearest_neighbors_from_distances(distances)
    assert list(indices) == [1, 0, 2]


