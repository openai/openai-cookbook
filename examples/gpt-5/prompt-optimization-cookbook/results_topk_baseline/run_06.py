import heapq
from typing import Dict, List, Tuple

def _compute_counts(s: str) -> Dict[str, int]:
    # Single pass ASCII [a-z0-9]+ tokenizer with inline lowercasing
    counts: Dict[str, int] = {}
    buf: List[str] = []
    append = buf.append
    for ch in s:
        o = ord(ch)
        if 48 <= o <= 57:  # '0'-'9'
            append(ch)
        elif 65 <= o <= 90:  # 'A'-'Z' -> to lower
            append(chr(o + 32))
        elif 97 <= o <= 122:  # 'a'-'z'
            append(ch)
        else:
            if buf:
                tok = "".join(buf)
                counts[tok] = counts.get(tok, 0) + 1
                buf.clear()
    if buf:
        tok = "".join(buf)
        counts[tok] = counts.get(tok, 0) + 1
    return counts

def compute_top_k(text: str, k: int) -> List[Tuple[str, int]]:
    if not isinstance(text, str) or not isinstance(k, int) or k <= 0:
        return []
    counts = _compute_counts(text)
    if not counts:
        return []
    n = min(k, len(counts))
    # Top-K by count desc, then token asc
    return heapq.nsmallest(n, counts.items(), key=lambda kv: (-kv[1], kv[0]))

# Fetch provided globals; fall back to empty if absent
try:
    _text = text  # type: ignore[name-defined]
except NameError:
    _text = ""
try:
    _k = k  # type: ignore[name-defined]
except NameError:
    _k = 0

# Expose result as requested
top_k: List[Tuple[str, int]] = compute_top_k(_text, _k)