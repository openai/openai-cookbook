from heapq import nsmallest

def _count_tokens(s):
    # Scan once, building ASCII [a-z0-9]+ tokens in lowercase.
    counts = {}
    buf = []  # token buffer
    append = buf.append  # local for speed
    get = counts.get
    for ch in s:
        o = ord(ch)
        if 48 <= o <= 57:          # '0'-'9'
            append(ch)
        elif 65 <= o <= 90:        # 'A'-'Z' -> lower
            append(chr(o + 32))
        elif 97 <= o <= 122:       # 'a'-'z'
            append(ch)
        else:
            if buf:
                tok = "".join(buf)
                counts[tok] = get(tok, 0) + 1
                buf.clear()
    if buf:
        tok = "".join(buf)
        counts[tok] = get(tok, 0) + 1
        buf.clear()
    return counts

def _select_top_k(counts, k):
    # Sort by count desc, then token asc; pick up to k unique tokens.
    if not counts or k <= 0:
        return []
    n = min(k, len(counts))
    items = counts.items()
    # nsmallest with key (-count, token) gives desired order
    top = nsmallest(n, items, key=lambda kv: (-kv[1], kv[0]))
    return list(top)

# Expect globals: text (str), k (int)
# Build top_k as required: list of (token, count) tuples.
top_k = _select_top_k(_count_tokens(text), int(k))