import re
from collections import Counter
from heapq import nsmallest

def _compute_top_k(text: str, k: int):
    # Tokens: ASCII [a-z0-9]+ after lowercasing
    pat = re.compile(r'[A-Za-z0-9]+', flags=re.ASCII)
    freq = Counter()
    for m in pat.finditer(text):
        freq[m.group(0).lower()] += 1

    items = list(freq.items())
    if not items:
        return []

    t = max(0, min(int(k), len(items)))
    if t == 0:
        return []

    key = lambda it: (-it[1], it[0])  # count desc, token asc
    if t < len(items):
        return nsmallest(t, items, key=key)
    return sorted(items, key=key)

try:
    top_k = _compute_top_k(text, k)
except NameError:
    # If text or k are not defined, expose an empty result.
    top_k = []