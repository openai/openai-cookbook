import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_registry  # noqa: E402

GITHUB_DIR = Path(__file__).resolve().parents[2]


def entry(path: str, slug: str, **extra) -> dict:
    return {"title": slug, "path": path, "slug": slug, "tags": [], "authors": [], **extra}


class CheckRegistryEntriesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in ("a.md", "b.md"):
            (self.root / name).write_text("x")

    def test_valid_entries_have_no_errors(self):
        entries = [entry("a.md", "a"), entry("b.md", "b", redirects=["old-b"])]
        self.assertEqual(check_registry.check_registry_entries(entries, self.root), [])

    def test_missing_file_is_reported(self):
        errors = check_registry.check_registry_entries([entry("gone.md", "gone")], self.root)
        self.assertEqual(errors, ["registry.yaml: gone.md: file does not exist in the repo"])

    def test_duplicate_path_and_slug_are_reported(self):
        entries = [entry("a.md", "same"), entry("a.md", "same")]
        errors = check_registry.check_registry_entries(entries, self.root)
        self.assertIn("registry.yaml: a.md: path is listed more than once", errors)
        self.assertIn("registry.yaml: same: slug is used more than once", errors)

    def test_redirect_collisions_are_reported(self):
        entries = [
            entry("a.md", "a", redirects=["dup", "b"]),
            entry("b.md", "b", redirects=["dup"]),
        ]
        errors = check_registry.check_registry_entries(entries, self.root)
        self.assertIn("registry.yaml: dup: redirect is used more than once", errors)
        self.assertIn("registry.yaml: b: redirect matches an existing slug", errors)


    def test_paths_outside_repo_or_empty_are_reported(self):
        entries = [entry("../outside.md", "x"), entry("", "y"), entry("./a.md", "z")]
        (self.root.parent / "outside.md").write_text("x")
        self.addCleanup((self.root.parent / "outside.md").unlink)
        errors = check_registry.check_registry_entries(entries, self.root)
        self.assertIn("registry.yaml: ../outside.md: file does not exist in the repo", errors)
        self.assertIn("registry.yaml: : file does not exist in the repo", errors)
        self.assertEqual(len(errors), 2)

    def test_equivalent_paths_count_as_duplicates(self):
        entries = [entry("a.md", "x"), entry("./a.md", "y")]
        errors = check_registry.check_registry_entries(entries, self.root)
        self.assertEqual(errors, ["registry.yaml: a.md: path is listed more than once"])


class ValidateSchemaTest(unittest.TestCase):
    def test_missing_required_field_is_reported(self):
        errors = check_registry.validate_schema(
            [{"title": "t"}], GITHUB_DIR / "registry_schema.json", "registry.yaml"
        )
        self.assertTrue(any("'path' is a required property" in e for e in errors))

    def test_invalid_date_is_reported(self):
        data = [{**entry("a.md", "a"), "date": "not-a-date"}]
        errors = check_registry.validate_schema(
            data, GITHUB_DIR / "registry_schema.json", "registry.yaml"
        )
        self.assertTrue(any("not-a-date" in e for e in errors))

    def test_invalid_author_uri_is_reported(self):
        data = {"x": {"name": "n", "website": "not a uri", "avatar": "https://a.example/b.png"}}
        errors = check_registry.validate_schema(
            data, GITHUB_DIR / "authors_schema.json", "authors.yaml"
        )
        self.assertTrue(any("not a uri" in e for e in errors))


if __name__ == "__main__":
    unittest.main()