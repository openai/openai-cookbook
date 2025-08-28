import re
import heapq
from collections import Counter
from typing import Iterable, List, Tuple

_TOKEN = re.compile(r"[a-z0-9]+", flags=re.ASCII | re.IGNORECASE)

def _tokens(s: str) -> Iterable[str]:
    for m in _TOKEN.finditer(s):
        yield m.group(0).lower()

def _revlex_tuple(t: str) -> Tuple[int, ...]:
    # For reverse-lex ordering using a min-heap: larger original token -> smaller tuple
    return tuple(-ord(c) for c in t)

def top_k_tokens(text: str, k: int) -> List[Tuple[str, int]]:
    if k <= 0:
        return []
    cnt = Counter(_tokens(text))
    u = len(cnt)
    if u == 0:
        return []
    k_eff = k if k < u else u
    key = lambda kv: (-kv[1], kv[0])

    # If selecting a large fraction, sort all; otherwise use a bounded heap of size k
    if 10 * k_eff >= 3 * u:
        return sorted(cnt.items(), key=key)[:k_eff]

    # Bounded heap where root is the current "worst" (lowest count, then lexicographically largest)
    heap: List[Tuple[Tuple[int, Tuple[int, ...]], str, int]] = []
    for tok, c in cnt.items():
        rk = (c, _revlex_tuple(tok))
        if len(heap) < k_eff:
            heapq.heappush(heap, (rk, tok, c))
        else:
            if rk > heap[0][0]:
                heapq.heapreplace(heap, (rk, tok, c))
    result = [(tok, c) for _, tok, c in heap]
    result.sort(key=lambda kv: (-kv[1], kv[0]))
    return result

# Use provided globals when available; demo guarded otherwise
try:
    text; k  # type: ignore[name-defined]
except NameError:
    if __name__ == "__main__":
        demo_text = "A a b b b c1 C1 c1 -- d! d? e"
        demo_k = 3
        top_k = top_k_tokens(demo_text, demo_k)
        print(top_k)
else:
    top_k = top_k_tokens(text, k)  # type: ignore[name-defined]

# Complexity: counting O(N tokens); selection O(U log k) with heap or O(U log U) when sorting; extra space O(U + k)