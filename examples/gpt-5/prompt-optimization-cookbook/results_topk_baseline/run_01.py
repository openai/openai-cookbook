import re
import heapq

def compute_top_k(text: str, k: int):
    # Tokenize: lowercase, ASCII [a-z0-9]+; others are separators
    if not text or k <= 0:
        return []
    s = text.lower()
    pattern = re.compile(r'[a-z0-9]+', re.ASCII)

    counts = {}
    get = counts.get
    for m in pattern.finditer(s):
        t = m.group(0)
        counts[t] = get(t, 0) + 1

    n = min(k, len(counts))
    if n <= 0:
        return []
    # Sort by count desc, then token asc
    return heapq.nsmallest(n, counts.items(), key=lambda it: (-it[1], it[0]))

def _to_int(v):
    try:
        return int(v)
    except Exception:
        return 0

# Use provided globals; expose only top_k
_text = globals().get('text', '')
_k = _to_int(globals().get('k', 0))
top_k = compute_top_k(_text, _k)

__all__ = ['top_k']