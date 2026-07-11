import heapq
from typing import Iterator, List, Tuple

def _iter_tokens(s: str) -> Iterator[str]:
    # Stream tokens: lowercase ASCII [a-z0-9]+; others are separators
    buf = []
    append = buf.append
    for ch in s:
        lo = ch.lower()
        if ('a' <= lo <= 'z') or ('0' <= ch <= '9'):
            append(lo)
        elif buf:
            yield ''.join(buf)
            buf.clear()
    if buf:
        yield ''.join(buf)

def _top_k_tokens(text: str, k: int) -> List[Tuple[str, int]]:
    # Count in one pass
    counts = {}
    for tok in _iter_tokens(text):
        counts[tok] = counts.get(tok, 0) + 1

    # Handle edge cases
    try:
        kk = int(k)
    except Exception:
        kk = 0
    if kk <= 0 or not counts:
        return []

    # Select Top-K sorted by count desc, then token asc
    kk = min(kk, len(counts))
    return heapq.nsmallest(kk, counts.items(), key=lambda item: (-item[1], item[0]))

# Compute using provided globals `text` and `k`
top_k = _top_k_tokens(globals().get('text', ''), globals().get('k', 0))