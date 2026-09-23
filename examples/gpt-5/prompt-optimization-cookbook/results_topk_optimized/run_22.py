import re
import heapq
from collections import Counter
from typing import Iterable, List, Tuple

_TOKEN_RE = re.compile(r"[a-z0-9]+", flags=re.ASCII | re.IGNORECASE)

def _tokens(s: str) -> Iterable[str]:
    for m in _TOKEN_RE.finditer(s):
        yield m.group(0).lower()

def top_k_tokens(text: str, k: int) -> List[Tuple[str, int]]:
    if k <= 0:
        return []
    cnt = Counter(_tokens(text))
    u = len(cnt)
    if u == 0:
        return []
    key = lambda kv: (-kv[1], kv[0])  # sort by count desc, token asc
    if k >= u or k >= 0.3 * u:
        return sorted(cnt.items(), key=key)
    return heapq.nsmallest(k, cnt.items(), key=key)

# Compute from provided globals when available; demo only if missing and running as main
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

# Complexity: counting O(N tokens), selection O(U log k) when k < 0.3U; full sort O(U log U) otherwise; extra space O(U + k)