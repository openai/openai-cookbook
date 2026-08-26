"""Entirely synthetic string utilities used by the autonomy evaluation suite."""

import re


def slugify(value: str) -> str:
    """Normalise ASCII punctuation while leaving the Unicode issue unresolved."""
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
