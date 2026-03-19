from __future__ import annotations

import shutil
from pathlib import Path

from .benchmark import DEFAULT_HARNESS_DIR
from .github_cache import DEFAULT_CACHE_ROOT, cache_dir_for
from .types import JSONDict


def reset_app_state(
    *,
    cache_key: str,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    harness_dir: Path = DEFAULT_HARNESS_DIR,
) -> JSONDict:
    cache_dir = cache_dir_for(cache_root, cache_key)
    results_dir = harness_dir / "results"

    removed_cache = False
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
        removed_cache = True

    removed_run_dirs: list[str] = []
    if results_dir.exists():
        for child in sorted(results_dir.iterdir()):
            if child.name == ".gitkeep":
                continue
            if child.is_dir():
                shutil.rmtree(child)
                removed_run_dirs.append(child.name)
                continue
            child.unlink()
            removed_run_dirs.append(child.name)

    return {
        "cache_key": cache_key,
        "cache_dir": str(cache_dir),
        "cache_removed": removed_cache,
        "results_dir": str(results_dir),
        "removed_run_artifacts": removed_run_dirs,
    }
