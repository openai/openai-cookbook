"""Portable identifiers and checked destinations for dataset-derived artifacts."""

from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath

from shared.private_files import private_directory

MAX_ARTIFACT_ID_LENGTH = 100
_IDENTIFIER = re.compile(rf"[A-Za-z0-9][A-Za-z0-9._-]{{0,{MAX_ARTIFACT_ID_LENGTH - 1}}}\Z")
_RESERVED = re.compile(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)", re.IGNORECASE)


def validate_artifact_id(value: str) -> str:
    """Reject ambiguous or non-portable filenames instead of sanitizing them."""
    if not _IDENTIFIER.fullmatch(value) or value.endswith(".") or _RESERVED.match(value):
        raise ValueError(
            "artifact id must be 1-100 ASCII letters, digits, dots, underscores, or hyphens; "
            "start with a letter or digit, do not end with a dot, and avoid reserved device names"
        )
    return value


def artifact_path(root: Path, *parts: str | Path) -> Path:
    """Resolve a relative destination under a trusted root, refusing existing links.

    The root is chosen by the operator. Descendant symlinks (including links
    pointing inside the root) and multiply-linked files cannot be write targets.
    This guards imported data and pre-existing filesystem state, not concurrent
    changes by another process with write access to the same directory.
    """
    base = root.expanduser().resolve()
    candidate = base
    for part in parts:
        location = Path(part)
        if location.is_absolute() or PureWindowsPath(str(part)).drive or "\\" in str(part) or ".." in location.parts:
            raise ValueError(f"Artifact destination must be relative to {base}: {part}")
        candidate /= location
    if candidate == base:
        raise ValueError(f"Artifact destination must be below {base}")
    current = base
    for component in candidate.relative_to(base).parts:
        if (
            not component.isascii()
            or len(component) > 255
            or component.endswith((".", " "))
            or any(ord(char) < 32 or ord(char) == 127 or char in '<>:"|?*' for char in component)
            or _RESERVED.match(component)
        ):
            raise ValueError(f"Artifact destination has a non-portable filename: {component!r}")
        current /= component
        if current.is_symlink():
            raise ValueError(f"Artifact destination contains a symlink: {current}")
        if current.is_file() and current.stat().st_nlink > 1:
            raise ValueError(f"Artifact destination is a hard-linked file: {current}")
    resolved = candidate.resolve()
    if not resolved.is_relative_to(base):
        raise ValueError(f"Artifact destination escapes {base}: {candidate}")
    return candidate


def create_run_directory(results_root: Path, run_name: str) -> Path:
    """Reserve a new run; never merge with or overwrite a previous run."""
    path = artifact_path(results_root, run_name)
    private_directory(path, exist_ok=False)
    return path


def scenario_audio_directory(audio_root: Path, scenario_id: str) -> Path:
    """Check all audio/detail destinations before a scenario starts work."""
    identifier = validate_artifact_id(scenario_id)
    directory = artifact_path(audio_root, identifier)
    for name in (
        "input.wav",
        "output.wav",
        "conversation.wav",
        "conversation.transcript.txt",
        "conversation.result.json",
        "conversation.ticks.jsonl",
        "conversation.turns.jsonl",
    ):
        artifact_path(audio_root, identifier, name)
    return directory
