import re
import heapq
from collections import Counter
from typing import Iterable, List, Tuple

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
    key = lambda kv: (-kv[1], kv[0])  # count desc, token asc
    if k >= u:
        return sorted(cnt.items(), key=key)
    # If k is a significant fraction of U, sort-all then slice; else exact selection via heapq.nsmallest
    if 10 * k >= 3 * u:  # k >= 0.3 * U
        return sorted(cnt.items(), key=key)[:k]
    return heapq.nsmallest(k, cnt.items(), key=key)

# Use provided globals when present; otherwise run a small demo only under __main__
try:
    text  # type: ignore[name-defined]
    k     # type: ignore[name-defined]
except NameError:
    if __name__ == "__main__":
        demo_text = "A a b b b c1 C1 c1 -- d! d? e"
        demo_k = 3
        top_k = top_k_tokens(demo_text, demo_k)
        print(top_k)
else:
    top_k = top_k_tokens(text, k)  # type: ignore[name-defined]

# Complexity: counting O(N tokens); selection O(U log k) via heap/selection or O(U log U) when sorting; extra space O(U) counts + O(k) selection.