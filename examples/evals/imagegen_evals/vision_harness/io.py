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
    mime = _MIME_BY_SUFFIX.get(path.suffix.lower(), "image/png")
    b64 = base64.b64encode(path.read_bytes()).decode("utf-8")
    return f"data:{mime};base64,{b64}"
