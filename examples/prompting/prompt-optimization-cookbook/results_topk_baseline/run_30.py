import re
from collections import Counter

def compute_top_k(text: str, k: int):
    # Tokens: ASCII [A-Za-z0-9]+, lowercased; other chars are separators
    if not isinstance(text, str) or not isinstance(k, int) or k <= 0:
        return []
    counter = Counter()
    pattern = re.compile(r'[A-Za-z0-9]+')
    for m in pattern.finditer(text):
        counter[m.group(0).lower()] += 1
    if not counter:
        return []
    items = sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))
    return items[:min(k, len(items))]

# Exposed result
top_k = compute_top_k(text, k)