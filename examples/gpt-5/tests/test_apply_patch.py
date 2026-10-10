"""Offline patch checks.

Install pydantic, then run:
python -m unittest discover -s examples/gpt-5/tests -v
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

EXAMPLE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE_DIR))
import apply_patch  # noqa: E402


class ApplyPatchTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(directory.name)
        Path("file.txt").write_text("before\n", encoding="utf-8")

    def apply(self, patch):
        return apply_patch.process_patch(
            patch,
            apply_patch.open_file,
            apply_patch.write_file,
            apply_patch.remove_file,
        )

    def update_patch(self, source="file.txt", destination=None):
        move = f"*** Move to: {destination}\n" if destination else ""
        return (
            f"*** Begin Patch\n*** Update File: {source}\n{move}"
            "@@\n-before\n+after\n*** End Patch"
        )

    def test_same_path_move_keeps_updated_file(self):
        self.assertEqual(
            self.apply(self.update_patch(destination="file.txt")), "Done!"
        )
        self.assertTrue(Path("file.txt").is_file())
        self.assertEqual(Path("file.txt").read_text(), "after\n")

    def test_same_path_move_without_edits_keeps_file(self):
        self.apply(
            "*** Begin Patch\n*** Update File: file.txt\n"
            "*** Move to: file.txt\n*** End Patch"
        )
        self.assertTrue(Path("file.txt").is_file())
        self.assertEqual(Path("file.txt").read_text(), "before\n")

    def test_same_path_move_with_custom_callbacks(self):
        files = {"file.txt": "before\n"}
        removed = []
        result = apply_patch.process_patch(
            self.update_patch(destination="file.txt"),
            files.__getitem__,
            files.__setitem__,
            removed.append,
        )
        self.assertEqual(result, "Done!")
        self.assertEqual(files, {"file.txt": "after\n"})
        self.assertEqual(removed, [])

    def test_update_without_move(self):
        self.apply(self.update_patch())
        self.assertEqual(Path("file.txt").read_text(), "after\n")

    def test_move_to_different_path_updates_and_removes_source(self):
        self.apply(self.update_patch(destination="nested/moved.txt"))
        self.assertFalse(Path("file.txt").exists())
        self.assertEqual(Path("nested/moved.txt").read_text(), "after\n")

    def test_move_without_edits(self):
        self.apply(
            "*** Begin Patch\n*** Update File: file.txt\n"
            "*** Move to: moved.txt\n*** End Patch"
        )
        self.assertFalse(Path("file.txt").exists())
        self.assertEqual(Path("moved.txt").read_text(), "before\n")

    def test_add_and_delete(self):
        self.apply(
            "*** Begin Patch\n*** Add File: added.txt\n+new\n"
            "*** Delete File: file.txt\n*** End Patch"
        )
        self.assertFalse(Path("file.txt").exists())
        self.assertEqual(Path("added.txt").read_text(), "new")

    def test_cli_same_path_move_keeps_updated_file(self):
        result = subprocess.run(
            [sys.executable, str(EXAMPLE_DIR / "apply_patch.py")],
            input=self.update_patch(destination="file.txt"),
            text=True,
            capture_output=True,
            check=True,
        )
        self.assertEqual(result.stdout, "Done!\n")
        self.assertEqual(result.stderr, "")
        self.assertTrue(Path("file.txt").is_file())
        self.assertEqual(Path("file.txt").read_text(), "after\n")


if __name__ == "__main__":
    unittest.main()
