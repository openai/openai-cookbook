import sys

def _iter_tokens(s: str):
    # Stream tokenizer: ASCII [a-z0-9]+, lowercase; others are separators.
    buf = []
    append = buf.append
    join = ''.join
    for ch in s:
        c = ch.lower()
        if ('a' <= c <= 'z') or ('0' <= c <= '9'):
            append(c)
        else:
            if buf:
                yield join(buf)
                buf.clear()
    if buf:
        yield join(buf)

def _top_k_tokens(s: str, k: int):
    if k <= 0:
        return []
    counts = {}
    get = counts.get
    for tok in _iter_tokens(s):
        counts[tok] = get(tok, 0) + 1
    if not counts:
        return []
    # Sort by count desc, then token asc
    items = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return items[: min(k, len(items))]

# Expect globals: text (str) and k (int)
try:
    _text = text  # provided by caller
    _k = int(k)
except Exception:
    # If globals not provided, expose empty result for safety.
    top_k = []
else:
    top_k = _top_k_tokens(_text, _k)