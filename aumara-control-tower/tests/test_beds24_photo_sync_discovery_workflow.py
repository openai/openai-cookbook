from __future__ import annotations

import pathlib
import unittest


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]


class Beds24PhotoSyncDiscoveryWorkflowTests(unittest.TestCase):
    def test_only_secret_name_validation_is_fatal(self) -> None:
        workflow = (
            REPOSITORY_ROOT
            / ".github"
            / "workflows"
            / "beds24-photo-sync-discovery.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("receipt['status']='AMBIGUOUS_MATCH'", workflow)
        self.assertIn("receipt['status']='MISSING_MATCH'", workflow)
        self.assertIn("exit_code=2", workflow)
        self.assertIn("receipt['status']='TOKEN_EXCHANGE_FAILED'", workflow)
        self.assertIn(
            "'LIVE_CONTENT_READ_OK' if 200 <= status < 300 else "
            "'LIVE_CONTENT_READ_FAILED'",
            workflow,
        )
        self.assertNotIn("exit_code=3", workflow)
