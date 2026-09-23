import re, heapq
from collections import Counter
from typing import List, Tuple, Iterable

# ASCII token pattern; case-insensitive matching; tokens are lowered individually
_TOKEN = re.compile(r"[a-z0-9]+", flags=re.ASCII | re.IGNORECASE)

def _tokens(s: str) -> Iterable[str]:
    for m in _TOKEN.finditer(s):
        yield m.group(0).lower()

def top_k_tokens(text: str, k: int) -> List[Tuple[str, int]]:
    if k <= 0:
        return []
    cnt = Counter(_tokens(text))
    u = len(cnt)
    if u == 0:
        return []
    key = lambda kv: (-kv[1], kv[0])  # sort by count desc, then token asc
    if k >= u:
        return sorted(cnt.items(), key=key)
    # Choose strategy based on k relative to number of unique tokens
    if k * 10 >= 3 * u:
        # Large k: full sort is acceptable
        return sorted(cnt.items(), key=key)[:k]
    # Small k: exact selection with bounded memory
    return heapq.nsmallest(k, cnt.items(), key=key)

# Compute from provided globals when available; demo only if missing and running as main
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

# Complexity: counting O(N tokens) time, O(U) space; selection O(U log k) via heap for small k or O(U log U) for large k; extra memory beyond counts is O(k).