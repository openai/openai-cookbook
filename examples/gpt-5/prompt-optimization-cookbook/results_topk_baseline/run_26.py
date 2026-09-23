from heapq import nsmallest

def _counts_from_text(s: str):
    # One-pass ASCII tokenizer: [a-z0-9]+ after lowercasing A-Z only
    counts = {}
    buf = []
    append = buf.append
    clear = buf.clear
    get = counts.get
    for ch in s:
        oc = ord(ch)
        if 48 <= oc <= 57:          # 0-9
            append(ch)
        elif 65 <= oc <= 90:        # A-Z -> a-z
            append(chr(oc + 32))
        elif 97 <= oc <= 122:       # a-z
            append(ch)
        else:
            if buf:
                tok = ''.join(buf)
                counts[tok] = get(tok, 0) + 1
                clear()
    if buf:
        tok = ''.join(buf)
        counts[tok] = get(tok, 0) + 1
    return counts

def _top_k_from_counts(counts, k: int):
    if k <= 0 or not counts:
        return []
    # Sort by count desc, then token asc; do k-selection to avoid full sort
    return list(nsmallest(k, counts.items(), key=lambda it: (-it[1], it[0])))

# Use provided globals `text` (str) and `k` (int)
try:
    _text = text
    _k = k
except NameError:
    _text = ""
    _k = 0

try:
    _k = int(_k)
except Exception:
    _k = 0
if _k < 0:
    _k = 0

top_k = _top_k_from_counts(_counts_from_text(_text), _k)