"""Read-only package resources and writable defaults for source and wheel use."""

from __future__ import annotations

import os
import sys
import tomllib
from importlib.resources import files
from pathlib import Path

PACKAGES = ("assistants", "crawl_harness", "walk_harness", "run_harness", "shared")
PHASES = ("crawl", "walk", "run")


def package_path(package: str, *parts: str) -> Path:
    """Locate assets in a normal filesystem installation (including editable installs)."""
    resource = files(package).joinpath(*parts)
    if not isinstance(resource, Path):
        raise RuntimeError("Install gpt-live-evals normally; direct ZIP imports are not supported")
    return resource.resolve()


def source_checkout_root() -> Path | None:
    root = Path(__file__).resolve().parents[1]
    manifest = root / "pyproject.toml"
    if manifest.is_file():
        with manifest.open("rb") as stream:
            if tomllib.load(stream).get("project", {}).get("name") == "gpt-live-evals":
                return root
    return None


def default_results_dir(phase: str) -> Path:
    if phase not in PHASES:
        raise ValueError(f"Unknown evaluation phase: {phase}")
    root = source_checkout_root()
    return root / f"{phase}_harness" / "results" if root else Path.cwd() / "results" / phase


def default_audio_cache_dir() -> Path:
    root = source_checkout_root()
    if root:
        return root / "crawl_harness" / ".audio_cache"
    override = os.getenv("XDG_CACHE_HOME", "")
    if override and Path(override).is_absolute():
        cache = Path(override)
    elif sys.platform == "darwin":
        cache = Path.home() / "Library" / "Caches"
    elif sys.platform == "win32":
        cache = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        cache = Path.home() / ".cache"
    return cache / "gpt-live-evals" / "crawl-audio"


def is_installed_package_path(path: Path) -> bool:
    if source_checkout_root() is not None:
        return False
    resolved = path.expanduser().resolve()
    return any(resolved.is_relative_to(package_path(package)) for package in PACKAGES)


def require_external_output(path: Path) -> Path:
    """Do not write evaluation artifacts into this distribution's installed packages."""
    resolved = path.expanduser().resolve()
    if is_installed_package_path(resolved):
        raise ValueError(f"Output must be outside installed gpt-live-evals packages: {resolved}")
    return resolved
