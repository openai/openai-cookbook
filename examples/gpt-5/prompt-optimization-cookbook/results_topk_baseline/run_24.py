from typing import List, Tuple, Dict

def compute_top_k(s: str, k: int) -> List[Tuple[str, int]]:
    # Tokenize: lowercase letters, digits; others are separators
    counts: Dict[str, int] = {}
    buf: List[str] = []

    append = buf.append
    get = counts.get

    for c in s:
        oc = ord(c)
        if 48 <= oc <= 57:  # '0'-'9'
            append(c)
        elif 65 <= oc <= 90:  # 'A'-'Z' -> to lowercase
            append(chr(oc + 32))
        elif 97 <= oc <= 122:  # 'a'-'z'
            append(c)
        else:
            if buf:
                tok = ''.join(buf)
                counts[tok] = (get(tok) or 0) + 1
                buf.clear()
    if buf:
        tok = ''.join(buf)
        counts[tok] = (get(tok) or 0) + 1

    if k <= 0 or not counts:
        return []

    items = counts.items()
    items_sorted = sorted(items, key=lambda it: (-it[1], it[0]))
    return items_sorted[:min(k, len(items_sorted))]

# Produce the required global `top_k` using provided globals `text` and `k`
try:
    _text = text  # provided externally
    _k = k        # provided externally
except NameError:
    top_k: List[Tuple[str, int]] = []
else:
    top_k = compute_top_k(_text, _k)