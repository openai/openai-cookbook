import re
from typing import List, Tuple, Dict

def compute_top_k(text: str, k: int) -> List[Tuple[str, int]]:
    # Tokens are ASCII [a-z0-9]+; lowercase; others are separators.
    if not isinstance(text, str) or not isinstance(k, int) or k <= 0:
        return []

    pattern = re.compile(r'[a-z0-9]+', re.ASCII | re.IGNORECASE)
    counts: Dict[str, int] = {}
    get = counts.get

    for m in pattern.finditer(text):
        tok = m.group(0).lower()
        counts[tok] = (get(tok) or 0) + 1

    if not counts:
        return []

    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    limit = min(k, len(items))
    return items[:limit]

# Expose the result as a convenient global.
top_k: List[Tuple[str, int]] = compute_top_k(text, k)