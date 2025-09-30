from collections import defaultdict

def _iter_tokens_ascii_lower(s: str):
    # Yield lowercase ASCII [a-z0-9]+ tokens, treating everything else as separators.
    buf = []
    append = buf.append
    for ch in s:
        # Fast ASCII classification with manual lowercasing for A-Z
        if 'A' <= ch <= 'Z':
            append(chr(ord(ch) + 32))  # to lowercase
        elif 'a' <= ch <= 'z' or '0' <= ch <= '9':
            append(ch)
        else:
            if buf:
                yield ''.join(buf)
                buf.clear()
    if buf:
        yield ''.join(buf)

def _top_k_tokens(text: str, k: int):
    if not isinstance(text, str) or not isinstance(k, int) or k <= 0:
        return []
    counts = defaultdict(int)
    for tok in _iter_tokens_ascii_lower(text):
        counts[tok] += 1
    if not counts:
        return []
    # Sort by count desc, then token asc
    items = sorted(counts.items(), key=lambda it: (-it[1], it[0]))
    return items[:k]

# Expect globals `text` and `k` to be provided by the environment.
try:
    top_k = _top_k_tokens(text, k)  # type: ignore[name-defined]
except NameError:
    top_k = []