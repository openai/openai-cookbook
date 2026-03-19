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
    def test_reset_app_state_clears_cache_and_generated_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            cache_root = root / "data" / "cache" / "github"
            cache_dir = cache_root / "openai_codex"
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / "manifest.json").write_text("{}", encoding="utf-8")

            harness_dir = root / "1_benchmark_harness"
            results_dir = harness_dir / "results"
            run_dir = results_dir / "run-123"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "results.json").write_text("[]", encoding="utf-8")
            (results_dir / ".gitkeep").write_text("", encoding="utf-8")

            summary = reset_app_state(
                cache_key="openai_codex",
                cache_root=cache_root,
                harness_dir=harness_dir,
            )

            self.assertTrue(summary["cache_removed"])
            self.assertEqual(summary["removed_run_artifacts"], ["run-123"])
            self.assertFalse(cache_dir.exists())
            self.assertFalse(run_dir.exists())
            self.assertTrue((results_dir / ".gitkeep").exists())


if __name__ == "__main__":
    unittest.main()
