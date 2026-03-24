from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from codereview_evals.state import reset_app_state


class StateTests(unittest.TestCase):
    def test_reset_app_state_clears_cache_prepared_and_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            cache_root = root / "cache"
            prepared_root = root / "prepared"
            cache_dir = cache_root / "openai_codex"
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / "manifest.json").write_text("{}", encoding="utf-8")

            prepared_dir = prepared_root / "openai_codex" / "level_1"
            prepared_dir.mkdir(parents=True, exist_ok=True)
            (prepared_dir / "benchmark.jsonl").write_text("", encoding="utf-8")

            from codereview_evals.paths import HARNESS_DIRS

            for harness_dir in HARNESS_DIRS.values():
                results_dir = harness_dir / "results"
                results_dir.mkdir(parents=True, exist_ok=True)
                (results_dir / "temp-run").mkdir(exist_ok=True)
                (results_dir / ".gitkeep").write_text("", encoding="utf-8")

            summary = reset_app_state(
                cache_key="openai_codex",
                cache_root=cache_root,
                prepared_root=prepared_root,
            )

            self.assertTrue(summary["cache_removed"])
            self.assertTrue(summary["prepared_removed"])
            self.assertFalse(cache_dir.exists())
            self.assertFalse((prepared_root / "openai_codex").exists())


if __name__ == "__main__":
    unittest.main()
