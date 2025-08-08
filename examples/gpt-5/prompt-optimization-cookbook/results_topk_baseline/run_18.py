import re
from heapq import nsmallest

# Token generator: ASCII [a-z0-9]+, lowercased, streaming via re.finditer
def _iter_tokens_ascii_lower(s: str):
    for m in re.finditer(r'[A-Za-z0-9]+', s):
        yield m.group(0).lower()

def _compute_top_k(s: str, k: int):
    if not s or k <= 0:
        return []
    counts = {}
    for tok in _iter_tokens_ascii_lower(s):
        counts[tok] = counts.get(tok, 0) + 1
    if not counts:
        return []
    kk = k if k < len(counts) else len(counts)
    # Select and sort by count desc, then token asc
    return [(t, c) for t, c in nsmallest(kk, counts.items(), key=lambda it: (-it[1], it[0]))]

# Expose result as a convenient global
top_k = _compute_top_k(text, k)