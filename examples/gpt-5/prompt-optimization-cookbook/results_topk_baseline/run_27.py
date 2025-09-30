from collections import Counter
import heapq

# Expects globals: text (str) and k (int). Produces: top_k = [(token, count), ...]

def _count_tokens(s: str) -> Counter:
    # Single-pass ASCII tokenizer: [a-z0-9]+, lowercased; others are separators
    counts = Counter()
    buf = []
    for ch in s:
        o = ord(ch)
        if 48 <= o <= 57:          # '0'-'9'
            buf.append(ch)
        elif 65 <= o <= 90:        # 'A'-'Z' -> lower
            buf.append(chr(o + 32))
        elif 97 <= o <= 122:       # 'a'-'z'
            buf.append(ch)
        else:
            if buf:
                tok = ''.join(buf)
                counts[tok] += 1
                buf.clear()
    if buf:
        tok = ''.join(buf)
        counts[tok] += 1
    return counts

# Read provided globals safely
try:
    _text = text
except NameError:
    _text = ""

try:
    _k = int(k)
except Exception:
    _k = 0
if _k < 0:
    _k = 0

_counts = _count_tokens(_text)

# Top-K by count desc, then token asc
if _counts and _k:
    top_k = heapq.nsmallest(_k, _counts.items(), key=lambda kv: (-kv[1], kv[0]))
else:
    top_k = []