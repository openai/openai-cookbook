import heapq

# Produces top_k: list[(token, count)] from globals `text` (str) and `k` (int).
# Tokenization: lowercase ASCII [a-z0-9]+, others are separators.
# Sorting: count desc, then token asc. Length = min(k, unique tokens).

def _iter_ascii_tokens(s):
    buf = []
    append = buf.append
    for ch in s:
        o = ord(ch)
        if 65 <= o <= 90:        # 'A'-'Z' -> lowercase
            append(chr(o | 32))
        elif 97 <= o <= 122 or 48 <= o <= 57:  # 'a'-'z' or '0'-'9'
            append(ch)
        else:
            if buf:
                yield ''.join(buf)
                buf.clear()
    if buf:
        yield ''.join(buf)

def _top_k_tokens(s, k):
    try:
        kk = int(k)
    except Exception:
        kk = 0
    if kk <= 0:
        return []

    counts = {}
    get = counts.get
    for tok in _iter_ascii_tokens(s):
        counts[tok] = get(tok, 0) + 1

    if not counts:
        return []

    kk = min(kk, len(counts))
    # nsmallest with key (-count, token) gives count desc, token asc and returns sorted.
    return heapq.nsmallest(kk, counts.items(), key=lambda it: (-it[1], it[0]))

# Build top_k from provided globals `text` and `k`.
try:
    top_k = _top_k_tokens(text, k)
except NameError:
    # If globals are missing, expose an empty result.
    top_k = []