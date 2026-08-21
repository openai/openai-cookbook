from __future__ import annotations

import pathlib
import unittest


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]


class Beds24PhotoSyncDiscoveryWorkflowTests(unittest.TestCase):
    def test_only_secret_name_discovery_errors_hard_fail(self) -> None:
        workflow = (
            REPOSITORY_ROOT
            / ".github"
            / "workflows"
            / "beds24-photo-sync-discovery.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("receipt['status']='AMBIGUOUS_MATCH'", workflow)
        self.assertIn("receipt['status']='MISSING_MATCH'", workflow)
        self.assertEqual(workflow.count("exit_code=2"), 2)
        self.assertNotIn("exit_code=3", workflow)


if __name__ == "__main__":
    unittest.main()
