"""Expose the legacy hyphenated Control Tower scripts as Python modules."""

from pathlib import Path


_LEGACY_SCRIPTS = (
    Path(__file__).resolve().parents[2] / "aumara-control-tower" / "scripts"
)
if _LEGACY_SCRIPTS.is_dir():
    __path__.append(str(_LEGACY_SCRIPTS))
