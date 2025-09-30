from heapq import nsmallest

def _count_tokens(s: str):
    # One-pass ASCII [a-z0-9]+ tokenizer; letters lowercased, others are separators.
    counts = {}
    buf = []
    append = buf.append
    for ch in s:
        o = ord(ch)
        if 48 <= o <= 57:  # '0'-'9'
            append(ch)
        elif 65 <= o <= 90:  # 'A'-'Z' -> lower
            append(chr(o + 32))
        elif 97 <= o <= 122:  # 'a'-'z'
            append(ch)
        else:
            if buf:
                tok = ''.join(buf)
                counts[tok] = counts.get(tok, 0) + 1
                buf.clear()
    if buf:
        tok = ''.join(buf)
        counts[tok] = counts.get(tok, 0) + 1
    return counts

def compute_top_k(text, k):
    s = text if isinstance(text, str) else str(text)
    try:
        k = int(k)
    except Exception:
        k = 0
    counts = _count_tokens(s)
    if k <= 0 or not counts:
        return []
    n = min(k, len(counts))
    # Sort by count desc, then token asc using key (-count, token)
    return nsmallest(n, counts.items(), key=lambda kv: (-kv[1], kv[0]))

try:
    top_k = compute_top_k(text, k)
except NameError:
    # If globals not provided, expose empty result.
    top_k = []