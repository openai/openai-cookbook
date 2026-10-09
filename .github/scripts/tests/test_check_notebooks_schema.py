import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import nbformat


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "check_notebooks.py"
spec = importlib.util.spec_from_file_location("check_notebooks", SCRIPT_PATH)
check_notebooks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_notebooks)


class NotebookSchemaTests(unittest.TestCase):
    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.directory = Path(temporary_directory.name)

    def write_notebook(self, notebook):
        path = self.directory / "example.ipynb"
        path.write_text(json.dumps(notebook), encoding="utf-8")
        return path

    def make_notebook(self):
        return nbformat.v4.new_notebook(
            cells=[nbformat.v4.new_code_cell("print('hello')")]
        )

    def validate(self, path):
        with contextlib.redirect_stdout(io.StringIO()):
            return check_notebooks.is_valid_notebook(path)

    def test_valid_notebook_is_accepted(self):
        self.assertTrue(self.validate(self.write_notebook(self.make_notebook())))

    def test_malformed_json_is_rejected(self):
        path = self.directory / "example.ipynb"
        path.write_text("not JSON", encoding="utf-8")
        self.assertFalse(self.validate(path))

    def test_readable_notebook_with_invalid_schema_is_rejected(self):
        for invalid_value in ("missing", "not an integer"):
            with self.subTest(execution_count=invalid_value):
                notebook = self.make_notebook()
                if invalid_value == "missing":
                    del notebook.cells[0]["execution_count"]
                else:
                    notebook.cells[0]["execution_count"] = invalid_value
                self.assertFalse(self.validate(self.write_notebook(notebook)))

    def test_cli_fails_for_changed_notebook_with_invalid_schema(self):
        def git(*arguments):
            return subprocess.run(
                ["git", *arguments],
                cwd=self.directory,
                capture_output=True,
                text=True,
                check=True,
            )

        git("init", "-q")
        git("config", "core.hooksPath", str(self.directory / "no-hooks"))
        git(
            "-c", "user.name=Notebook Test",
            "-c", "user.email=notebook-test@example.invalid",
            "-c", "commit.gpgsign=false",
            "commit", "--allow-empty", "-qm", "baseline",
        )
        git("update-ref", "refs/remotes/origin/main", "HEAD")
        notebook = self.make_notebook()
        del notebook.cells[0]["execution_count"]
        path = self.write_notebook(notebook)
        git("add", "--", path.name)

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH)],
            cwd=self.directory,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("example.ipynb: INVALID", result.stdout)
        self.assertIn("execution_count", result.stdout)
        self.assertIn("1 invalid notebook(s) found.", result.stdout)


if __name__ == "__main__":
    unittest.main()
