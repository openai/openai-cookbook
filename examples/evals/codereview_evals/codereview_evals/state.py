from __future__ import annotations

import shutil
from pathlib import Path

from .github_cache import DEFAULT_CACHE_ROOT, cache_dir_for
from .paths import HARNESS_DIRS, PREPARED_ROOT
from .types import JSONDict


def reset_app_state(
    *,
    cache_key: str,
    cache_root: Path = DEFAULT_CACHE_ROOT,
    prepared_root: Path = PREPARED_ROOT,
) -> JSONDict:
    cache_dir = cache_dir_for(cache_root, cache_key)
    prepared_dir = prepared_root / cache_key

    removed_cache = False
    if cache_dir.exists():
        shutil.rmtree(cache_dir)
        removed_cache = True

    removed_prepared = False
    if prepared_dir.exists():
        shutil.rmtree(prepared_dir)
        removed_prepared = True

    removed_run_artifacts: dict[str, list[str]] = {}
    for harness_dir in HARNESS_DIRS.values():
        results_dir = harness_dir / "results"
        removed: list[str] = []
        if results_dir.exists():
            for child in sorted(results_dir.iterdir()):
                if child.name == ".gitkeep":
                    continue
                if child.is_dir():
                    shutil.rmtree(child)
                else:
                    child.unlink()
                removed.append(child.name)
        results_dir.mkdir(parents=True, exist_ok=True)
        gitkeep = results_dir / ".gitkeep"
        if not gitkeep.exists():
            gitkeep.write_text("", encoding="utf-8")
        removed_run_artifacts[harness_dir.name] = removed

    return {
        "cache_key": cache_key,
        "cache_dir": str(cache_dir),
        "cache_removed": removed_cache,
        "prepared_dir": str(prepared_dir),
        "prepared_removed": removed_prepared,
        "removed_run_artifacts": removed_run_artifacts,
    }
