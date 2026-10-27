"""Check installed Promptfoo grading/export using offline echo fixtures."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from routing_eval import ROOT, build_config, config_matches, notebook_definitions, result_rows


class PromptfooCliTests(unittest.TestCase):
    def test_offline_cli_grading_and_export(self):
        node = shutil.which("node")
        entrypoint = ROOT / "node_modules/promptfoo/dist/src/entrypoint.js"
        if not node or not entrypoint.exists():
            self.skipTest("Install pinned Promptfoo and put Node.js on PATH for CLI checks")
        scope = notebook_definitions()
        config = build_config(scope["offline_cases"], scope["QUESTION"], scope["MODEL"])
        config["description"] = "OFFLINE invented fixtures: not model-performance evidence"
        config["providers"] = ["echo"]
        config["prompts"] = ["{{fixture}}"]
        for test in config["tests"]:
            test["vars"]["fixture"] = json.dumps(scope["fixture_response"](
                test["vars"]["case_id"]))
        with tempfile.TemporaryDirectory(prefix="decisions-offline-cli-") as temporary:
            directory = Path(temporary)
            path = directory / "config.json"
            path.write_text(json.dumps(config))
            result_path = directory / "results.json"
            environment = os.environ.copy()
            environment.pop("OPENAI_API_KEY", None)
            environment.update({
                "PROMPTFOO_DISABLE_TELEMETRY": "1",
                "PROMPTFOO_DISABLE_UPDATE": "1",
                "PROMPTFOO_CONFIG_DIR": str(directory / "local"),
            })
            completed = subprocess.run([
                node, str(entrypoint), "eval", "-c", str(path), "--no-cache",
                "--max-concurrency", "1", "-o", str(result_path),
            ], env=environment, cwd=directory, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
            self.assertIn(completed.returncode, (0, 100), completed.stdout)
            export = json.loads(result_path.read_text())
            rows = result_rows(export, config, scope)
            held_out = [r for r in rows if r["split"] == "test"]
            self.assertEqual(scope["evaluate"](held_out, 0.8)["misroutes"], 1)
            results = export["results"]["results"]
            expected_correct = sum(r["predicted"] == r["expected"] for r in rows)
            self.assertEqual(sum(bool(r["success"]) for r in results), expected_correct)
            self.assertTrue(config_matches(export["config"], config))


if __name__ == "__main__":
    unittest.main()
