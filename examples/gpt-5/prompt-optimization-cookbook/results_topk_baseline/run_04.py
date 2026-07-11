import re
import heapq

def compute_top_k(s: str, k_value: int):
    # Count tokens: ASCII [A-Za-z0-9]+, case-insensitive, stored lowercase
    counts = {}
    for m in re.finditer(r'[A-Za-z0-9]+', s):
        tok = m.group(0).lower()
        counts[tok] = counts.get(tok, 0) + 1

    n = max(0, int(k_value))
    if n == 0 or not counts:
        return []

    # Sort by count desc, then token asc using a key tuple
    key = lambda item: (-item[1], item[0])
    # Use nsmallest with the composite key to avoid sorting the whole list when k << unique
    top_items = heapq.nsmallest(n, counts.items(), key=key)
    # Ensure exact order (nsmallest returns sorted by key already)
    return [(tok, cnt) for tok, cnt in top_items]

# Expect globals: text (str), k (int)
top_k = compute_top_k(text, k)