"""Exercise notebook path discovery against real Git filename quoting."""

import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "check_notebooks.py"
SPEC = importlib.util.spec_from_file_location("check_notebooks", SCRIPT)
check_notebooks = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(check_notebooks)


class ChangedNotebookPathsTest(unittest.TestCase):
    def test_changed_notebook_paths_are_not_git_quoted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
            subprocess.run(
                ["git", "-C", str(root), "config", "core.quotePath", "true"],
                check=True,
            )
            empty_tree = subprocess.check_output(
                ["git", "-C", str(root), "hash-object", "-w", "-t", "tree", "--stdin"],
                input="",
                text=True,
            ).strip()
            paths = [
                Path("examples/plain/notebook.ipynb"),
                Path("examples/多语言/notebook.ipynb"),
                Path("examples/space topic/notebook.ipynb"),
            ]
            for path in paths:
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("invalid notebook JSON", encoding="utf-8")
            subprocess.run(["git", "-C", str(root), "add", "examples"], check=True)

            previous_directory = Path.cwd()
            try:
                os.chdir(root)
                changed = check_notebooks.get_changed_notebooks(empty_tree)
                self.assertCountEqual(changed, paths)
                self.assertTrue(all(path.exists() for path in changed))
            finally:
                os.chdir(previous_directory)

    def test_no_changed_notebooks_returns_empty_list(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
            empty_tree = subprocess.check_output(
                ["git", "-C", str(root), "hash-object", "-w", "-t", "tree", "--stdin"],
                input="",
                text=True,
            ).strip()
            previous_directory = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(check_notebooks.get_changed_notebooks(empty_tree), [])
            finally:
                os.chdir(previous_directory)


if __name__ == "__main__":
    unittest.main()
