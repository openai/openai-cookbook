from collections import Counter
import heapq

def _iter_tokens(s):
    # Stream tokens: lowercase ASCII [a-z0-9]+; others are separators
    buf = []
    append = buf.append
    for ch in s:
        c = ch.lower()
        if ('a' <= c <= 'z') or ('0' <= c <= '9'):
            append(c)
        elif buf:
            yield ''.join(buf)
            buf.clear()
    if buf:
        yield ''.join(buf)

def _compute_top_k(s, k):
    if not isinstance(k, int) or k <= 0:
        return []
    counts = Counter()
    for tok in _iter_tokens(s):
        counts[tok] += 1
    # Sort by count desc, then token asc
    return heapq.nsmallest(k, counts.items(), key=lambda kv: (-kv[1], kv[0]))

# Use provided globals; fall back to safe defaults if missing
try:
    _text = text
except NameError:
    _text = ""
try:
    _k = k
except NameError:
    _k = 0

top_k = _compute_top_k(_text, _k)