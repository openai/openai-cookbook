#!/usr/bin/env python3
import heapq
from typing import Dict, Iterable, List, Tuple

def _iter_tokens(s: str) -> Iterable[str]:
    # One-pass ASCII tokenizer with inline lowercasing
    buf: List[str] = []
    append = buf.append
    for ch in s:
        o = ord(ch)
        if 65 <= o <= 90:  # 'A'-'Z' -> lowercase
            append(chr(o + 32))
        elif 97 <= o <= 122 or 48 <= o <= 57:  # 'a'-'z' or '0'-'9'
            append(ch)
        else:
            if buf:
                yield "".join(buf)
                buf.clear()
    if buf:
        yield "".join(buf)

def compute_top_k(text: str, k: int) -> List[Tuple[str, int]]:
    if not isinstance(k, int) or k <= 0:
        return []
    counts: Dict[str, int] = {}
    get = counts.get
    for tok in _iter_tokens(text):
        counts[tok] = get(tok, 0) + 1
    if not counts:
        return []
    # Sort by count desc, then token asc, using a size-k heap
    items = counts.items()
    result = heapq.nsmallest(k, items, key=lambda kv: (-kv[1], kv[0]))
    return result

# Expected globals: text (str) and k (int)
top_k: List[Tuple[str, int]] = compute_top_k(text, k)