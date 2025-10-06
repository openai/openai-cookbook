import re
import heapq

def _compute_top_k(text, k):
    # Tokens: ASCII [A-Za-z0-9]+, lowercased; others are separators.
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    try:
        k = int(k)
    except Exception:
        k = 0
    if k <= 0 or not text:
        return []

    counts = {}
    # Iterate matches without lowercasing the entire text to keep memory low.
    pattern = re.compile(r'[A-Za-z0-9]+', flags=re.ASCII)
    for m in pattern.finditer(text):
        tok = m.group(0).lower()
        counts[tok] = counts.get(tok, 0) + 1

    if not counts:
        return []

    n_unique = len(counts)
    kk = k if k < n_unique else n_unique
    if kk == 0:
        return []

    # Use a heap to avoid sorting the entire map when k << unique tokens.
    # Key: (-count, token) gives count desc, then token asc.
    top = heapq.nsmallest(kk, counts.items(), key=lambda it: (-it[1], it[0]))
    return top

# Expect globals 'text' and 'k'; define top_k for inspection.
top_k = _compute_top_k(globals().get('text', ''), globals().get('k', 0))