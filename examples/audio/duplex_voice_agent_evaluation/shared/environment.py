"""Explicit, shared environment-file discovery without parent-directory searching."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

from shared.paths import source_checkout_root


def environment_file() -> Path | None:
    explicit = os.getenv("GPT_LIVE_EVALS_ENV_FILE")
    if explicit is not None:
        if not explicit.strip():
            raise ValueError("GPT_LIVE_EVALS_ENV_FILE must name a nonempty path")
        path = Path(explicit).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f"Environment file does not exist: {path}")
        return path
    local = Path.cwd() / ".env"
    if local.is_file():
        return local
    root = source_checkout_root()
    return root / ".env" if root and (root / ".env").is_file() else None


def load_environment() -> Path | None:
    """Load one selected file; existing process/shell variables always win."""
    path = environment_file()
    if path is not None:
        load_dotenv(path, override=False)
    return path
