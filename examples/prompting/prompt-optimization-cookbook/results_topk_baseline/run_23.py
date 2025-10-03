import heapq

def _iter_tokens_ascii_lower(s):
    # Stream tokens: ASCII [a-z0-9]+, lowercase letters; non-matching chars are separators.
    buf = []
    append = buf.append
    for ch in s:
        o = ord(ch)
        if 65 <= o <= 90:           # 'A'-'Z' -> lower
            append(chr(o + 32))
        elif 97 <= o <= 122 or 48 <= o <= 57:  # 'a'-'z' or '0'-'9'
            append(ch)
        else:
            if buf:
                yield ''.join(buf)
                buf.clear()
    if buf:
        yield ''.join(buf)

def _top_k_tokens(s, k):
    if not s or k <= 0:
        return []
    counts = {}
    for tok in _iter_tokens_ascii_lower(s):
        counts[tok] = counts.get(tok, 0) + 1
    if not counts:
        return []
    m = k if k < len(counts) else len(counts)
    # Sort by count desc, then token asc -> key (-count, token); nsmallest returns sorted ascending by key.
    return heapq.nsmallest(m, counts.items(), key=lambda it: (-it[1], it[0]))

# Use provided globals `text` and `k`; fall back to empty values if missing.
try:
    _text, _k = text, k
except NameError:
    _text, _k = "", 0

try:
    _k = int(_k)
except Exception:
    _k = 0

top_k = _top_k_tokens(_text, _k)