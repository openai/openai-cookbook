import heapq

def _iter_tokens(s):
    # Stream tokens: ASCII [a-z0-9]+, lowercase; others are separators
    buf = []
    append = buf.append
    for ch in s:
        o = ord(ch)
        if 48 <= o <= 57:          # '0'-'9'
            append(ch)
        elif 65 <= o <= 90:         # 'A'-'Z' -> to lowercase
            append(chr(o + 32))
        elif 97 <= o <= 122:        # 'a'-'z'
            append(ch)
        else:
            if buf:
                yield ''.join(buf)
                buf.clear()
    if buf:
        yield ''.join(buf)

def _compute_top_k(s, k):
    try:
        k = int(k)
    except Exception:
        k = 0
    if k <= 0 or not s:
        return []

    counts = {}
    for tok in _iter_tokens(s if isinstance(s, str) else str(s)):
        counts[tok] = counts.get(tok, 0) + 1

    if not counts:
        return []

    n_unique = len(counts)
    key = lambda kv: (-kv[1], kv[0])  # sort by count desc, token asc

    if n_unique <= k:
        return sorted(counts.items(), key=key)

    top = heapq.nsmallest(k, counts.items(), key=key)
    top.sort(key=key)
    return top

# Use provided globals `text` and `k`; fall back safely if absent.
try:
    _text = text  # type: ignore[name-defined]
except NameError:
    _text = ""
try:
    _k = k  # type: ignore[name-defined]
except NameError:
    _k = 0

# Exposed result: list of (token, count), sorted by count desc then token asc
top_k = _compute_top_k(_text, _k)