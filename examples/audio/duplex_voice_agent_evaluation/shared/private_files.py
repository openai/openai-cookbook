"""Owner-only artifact creation without changing the process-wide umask."""

from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Any


def private_directory(path: Path, *, exist_ok: bool = True) -> Path:
    """Create missing directories privately; leave existing parent permissions alone."""
    if not path.parent.exists():
        private_directory(path.parent)
    path.mkdir(mode=0o700, exist_ok=exist_ok)
    return path


def private_open(path: Path, mode: str = "w", *, encoding: str | None = "utf-8") -> Any:
    """Open a regular, singly linked output with owner-only permissions before writing."""
    if mode not in {"w", "a", "x", "wb", "ab", "xb"}:
        raise ValueError("private_open supports only artifact write/append/create modes")
    private_directory(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    if mode.startswith("x"):
        flags |= os.O_EXCL
    if mode.startswith("a"):
        flags |= os.O_APPEND
    fd = os.open(path, flags, 0o600)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("Artifact output must be a regular, singly linked file")
        os.fchmod(fd, 0o600)
        if mode.startswith("w"):
            os.ftruncate(fd, 0)
        stream = os.fdopen(fd, mode, encoding=None if "b" in mode else encoding)
    except BaseException:
        os.close(fd)
        raise
    return stream


def private_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    with private_open(path, encoding=encoding) as output:
        output.write(text)
