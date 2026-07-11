from heapq import nsmallest

def _count_tokens_ascii(text: str):
    # One-pass ASCII [a-z0-9]+ tokenizer (lowercasing A-Z); others are separators.
    counts = {}
    buf = []
    append = buf.append
    get = counts.get
    def commit():
        if buf:
            tok = ''.join(buf)
            counts[tok] = get(tok, 0) + 1
            buf.clear()

    for ch in text:
        o = ord(ch)
        if 65 <= o <= 90:          # 'A'-'Z' -> lower
            append(chr(o + 32))
        elif 97 <= o <= 122:       # 'a'-'z'
            append(ch)
        elif 48 <= o <= 57:        # '0'-'9'
            append(ch)
        else:
            commit()
    commit()
    return counts

def _top_k_from_counts(counts, k: int):
    if k <= 0 or not counts:
        return []
    # Sort by count desc, then token asc using nsmallest with key (-count, token)
    return nsmallest(k, counts.items(), key=lambda kv: (-kv[1], kv[0]))

# Expect globals: text (str) and k (int) to be provided by the environment.
# Produce the required global `top_k`.
top_k = _top_k_from_counts(_count_tokens_ascii(text), k)