import re
import heapq

# Compute Top-K most frequent ASCII [a-z0-9]+ tokens (case-insensitive).
def _iter_tokens(s):
    # Stream tokens; match ASCII letters/digits, case-insensitive, then lowercase per token
    for m in re.finditer(r'[a-z0-9]+', s, flags=re.ASCII | re.IGNORECASE):
        yield m.group(0).lower()

def _top_k_tokens(text, k):
    if not isinstance(text, str) or not isinstance(k, int) or k <= 0:
        return []
    counts = {}
    for tok in _iter_tokens(text):
        counts[tok] = counts.get(tok, 0) + 1
    if not counts:
        return []
    kk = min(k, len(counts))
    # Get k items sorted by count desc, then token asc
    return heapq.nsmallest(kk, counts.items(), key=lambda item: (-item[1], item[0]))

# Produce the required global `top_k` using provided globals `text` and `k`.
try:
    top_k = _top_k_tokens(text, k)
except NameError:
    # If globals are missing, expose an empty result.
    top_k = []