"""Offline checks for the security notebook's comparison-table labels.

Run with: python -m unittest discover -s examples/agents_sdk/tests
The metadata fixtures are not scanned or used as evidence; only the display cell runs.
"""

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

EXAMPLE_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXAMPLE_DIR))
import security_review_helpers as helpers


class RepositoryLabelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        notebook = json.loads((EXAMPLE_DIR / "security_scanners_with_agents_sdk.ipynb").read_text(encoding="utf-8"))
        cell = next(cell for cell in notebook["cells"] if cell["id"] == "security-swarm-24")
        cls.display_code = compile("".join(cell["source"]), "<comparison-display>", "exec")

    def render_comparison(self, repository):
        snapshot = None
        if repository is not None:
            manifest = helpers.TargetManifest(
                target_id="fixture", repository=repository, release="fixture", commit="1" * 40,
                approved_files=(helpers.ApprovedFile(path="app.py", sha256="0" * 64),),
            )
            snapshot = helpers.SourceSnapshot(
                root=EXAMPLE_DIR, target_id=manifest.target_id, source_url=manifest.repository,
                source_revision=manifest.commit, snapshot_digest="2" * 64,
                files=(helpers.SourceFile(path="app.py", sha256="0" * 64,
                                          size_bytes=0, production_source=True),),
            )
        bundle = helpers.ReviewBundle(
            status="partial" if snapshot else "not_authorized", target_id="fixture",
            snapshot=snapshot, selected_scanners=("semgrep", "bandit") if snapshot else (),
        )
        captured = []
        with patch.object(helpers, "display", captured.append):
            exec(self.display_code, {
                "target_reviews": {"fixture": bundle}, "show_table": helpers.show_table,
                "result_rows": helpers.result_rows, "show_review_details": helpers.show_review_details,
            })
        self.assertEqual(len(captured), 1)
        return captured[0].data

    def test_repository_name_without_trailing_slash(self):
        markdown = self.render_comparison("https://github.com/OWASP/crAPI")
        self.assertTrue(markdown.startswith("**crAPI / semgrep, bandit**\n"))
        self.assertIn('aria-label="crAPI / semgrep, bandit review results"', markdown)

    def test_accepted_trailing_slash_preserves_title_and_accessible_label(self):
        plain = self.render_comparison("https://github.com/OWASP/crAPI")
        trailing = self.render_comparison("https://github.com/OWASP/crAPI/")
        self.assertEqual(trailing, plain)

    def test_missing_snapshot_uses_target_identifier(self):
        markdown = self.render_comparison(None)
        self.assertTrue(markdown.startswith("**fixture / none**\n"))
        self.assertIn('aria-label="fixture / none review results"', markdown)


if __name__ == "__main__":
    unittest.main()
