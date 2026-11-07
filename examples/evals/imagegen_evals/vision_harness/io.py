from __future__ import annotations

import base64
from pathlib import Path

_MIME_BY_SUFFIX = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def image_to_data_url(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix not in _MIME_BY_SUFFIX:
        raise ValueError(f"Unsupported image extension: {suffix or '<none>'}")
    mime = _MIME_BY_SUFFIX[suffix]
    b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{b64}"
