import re
import heapq

# Compile once for speed; ASCII-only tokens
_TOKEN_RE = re.compile(r'[A-Za-z0-9]+')

def _compute_top_k(src_text: str, k: int):
    # k <= 0 yields empty result
    if not isinstance(k, int) or k <= 0:
        return []

    counts = {}
    # One pass: iterate matches without building an intermediate list
    for m in _TOKEN_RE.finditer(src_text):
        tok = m.group(0).lower()  # lowercase per token
        counts[tok] = counts.get(tok, 0) + 1

    if not counts:
        return []

    top_n = k if k < len(counts) else len(counts)
    # Sort by count desc, then token asc using a key on (-count, token)
    return heapq.nsmallest(top_n, counts.items(), key=lambda kv: (-kv[1], kv[0]))

# Expose the requested global result
top_k = _compute_top_k(text, k)