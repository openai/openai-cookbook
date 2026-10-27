from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from support import ROOT, approve_scope, pipeline, repository
from fleet_security import SyntheticScanner


LAB_SOURCE = str(ROOT.parent / "src")
if LAB_SOURCE not in sys.path:
    sys.path.insert(0, LAB_SOURCE)

from field_autonomy.sandbox import ContainerConfiguration, ContainerExecutor, ContainerRuntime, scrubbed_environment


class IsolationPolicyTests(unittest.TestCase):
    def test_host_chosen_container_command_has_no_shell_and_denies_network_privileges(self) -> None:
        with tempfile.TemporaryDirectory(prefix="synthetic-fleet-mounts-") as temporary:
            root = Path(temporary)
            source, tests, scratch = (root / name for name in ("source", "tests", "scratch"))
            for directory in (source, tests, scratch):
                directory.mkdir()
            command = ContainerExecutor(source, tests, scratch, ContainerConfiguration()).command(
                ["python3", "-I", "-c", "print('synthetic')"], "fleet-policy-proof",
            )
            self.assertEqual(command[command.index("--network") + 1], "none")
            self.assertEqual(command[command.index("--user") + 1], "65532:65532")
            self.assertEqual(command[command.index("--cap-drop") + 1], "ALL")
            self.assertEqual(command[command.index("--security-opt") + 1], "no-new-privileges")
            self.assertIn("--read-only", command)
            self.assertEqual(command[command.index("--pull") + 1], "never")
            self.assertIsInstance(command, list)
            self.assertNotIn("/bin/sh", command)

    def test_scrubbed_host_environment_excludes_api_cloud_and_github_credentials(self) -> None:
        values = {
            "OPENAI_API_KEY": "synthetic-api-secret",
            "CODEX_API_KEY": "synthetic-codex-secret",
            "GITHUB_TOKEN": "synthetic-github-secret",
            "GH_TOKEN": "synthetic-gh-secret",
            "AWS_SECRET_ACCESS_KEY": "synthetic-cloud-secret",
            "OPENAI_WEBHOOK_SECRET": "synthetic-webhook-secret",
        }
        with patch.dict(os.environ, values):
            cleaned = scrubbed_environment()
        self.assertTrue(all(name not in cleaned for name in values))
        self.assertTrue(all(value not in cleaned.values() for value in values.values()))

    def test_untrusted_symbolic_source_path_fails_closed(self) -> None:
        fixtures = ROOT / "fixtures"
        with tempfile.TemporaryDirectory(prefix="synthetic-link-", dir=fixtures) as temporary:
            fixture = Path(temporary)
            (fixture / "src").mkdir()
            (fixture / "tests").mkdir()
            (fixture / "src" / "outside.py").symlink_to(ROOT / "src" / "fleet_security" / "scanner.py")
            flow = pipeline()
            record = repository(fixture=fixture.name)
            approve_scope(flow, record)
            outcome = flow.run((record,))["records"][record.repo_id]
            self.assertEqual(outcome["status"], "failed_safe_abstention")
            self.assertIn("symbolic", outcome["reason"])

    def test_hidden_environment_and_credential_files_are_never_inspected(self) -> None:
        fixtures = ROOT / "fixtures"
        for forbidden in (".env", ".env.local", "credentials.json", "id_rsa"):
            with self.subTest(forbidden=forbidden):
                with tempfile.TemporaryDirectory(prefix="synthetic-hidden-", dir=fixtures) as temporary:
                    fixture = Path(temporary)
                    (fixture / "src").mkdir()
                    (fixture / "tests").mkdir()
                    (fixture / "src" / forbidden).write_text("synthetic-private-material", encoding="utf-8")
                    flow = pipeline()
                    record = repository(fixture=fixture.name)
                    approve_scope(flow, record)
                    outcome = flow.run((record,))["records"][record.repo_id]
                    self.assertEqual(outcome["status"], "failed_safe_abstention")
                    self.assertIn("hidden secret", outcome["reason"])

    def test_missing_daemon_refuses_without_falling_back_to_host_execution(self) -> None:
        record = repository()
        flow = pipeline(scanner=SyntheticScanner(isolated=True))
        approve_scope(flow, record)
        with patch.object(ContainerRuntime, "_validate_daemon_and_image", side_effect=__import__(
            "field_autonomy.policy", fromlist=["PolicyViolation"],
        ).PolicyViolation("synthetic daemon unavailable")):
            outcome = flow.run((record,))["records"][record.repo_id]
        self.assertEqual(outcome["status"], "failed_safe_abstention")
        self.assertIn("no local fallback", outcome["reason"])


@unittest.skipUnless(os.environ.get("RUN_FLEET_DOCKER") == "1", "genuine fleet Docker proof requires RUN_FLEET_DOCKER=1")
class GenuineFleetDockerTests(unittest.TestCase):
    def test_real_synthetic_finding_scan_enforces_every_container_trust_boundary(self) -> None:
        scanner = SyntheticScanner(isolated=True)
        flow = pipeline(scanner=scanner)
        record = repository(fixture="vulnerable_service")
        approve_scope(flow, record)
        injected = {
            "OPENAI_API_KEY": "synthetic-do-not-forward",
            "CODEX_API_KEY": "synthetic-do-not-forward",
            "GITHUB_TOKEN": "synthetic-do-not-forward",
            "AWS_SECRET_ACCESS_KEY": "synthetic-do-not-forward",
        }
        with patch.dict(os.environ, injected):
            result = flow.run((record,))["records"][record.repo_id]
        self.assertEqual(result["status"], "awaiting_finding_disposition")
        self.assertEqual(result["current_findings"], 1)
        receipt = scanner.isolation_receipts[0]
        self.assertEqual(receipt["uid"], 65532)
        self.assertTrue(receipt["networkBlocked"])
        self.assertTrue(receipt["rootReadOnly"])
        self.assertEqual(receipt["mountChecks"], {
            "source": "read_only", "protectedTests": "read_only", "scratch": "writable",
        })
        self.assertEqual(int(receipt["effectiveCapabilities"], 16), 0)
        self.assertEqual(receipt["noNewPrivileges"], "1")
        self.assertTrue(all(value is False for value in receipt["hiddenPathPresence"].values()))
        self.assertTrue(all(value is False for value in receipt["credentialPresence"].values()))

    def test_real_restricted_safe_fixture_stops_at_human_review(self) -> None:
        flow = pipeline(scanner=SyntheticScanner(isolated=True))
        record = repository()
        approve_scope(flow, record)
        outcome = flow.run((record,))
        self.assertEqual(outcome["records"][record.repo_id]["status"], "review_packet_ready")
        self.assertEqual(outcome["external_writes"], 0)

    def test_real_restricted_prompt_injection_abstains(self) -> None:
        flow = pipeline(scanner=SyntheticScanner(isolated=True))
        record = repository(fixture="adversarial_service")
        approve_scope(flow, record)
        outcome = flow.run((record,))["records"][record.repo_id]
        self.assertEqual(outcome["status"], "failed_safe_abstention")
        self.assertFalse(outcome["external_pr_created"])

    def test_real_timeout_forces_container_cleanup_without_fallback(self) -> None:
        fixture = ROOT / "fixtures" / "safe_service"
        runtime = ContainerRuntime()
        with runtime.open(fixture, "synthetic-timeout") as workspace:
            executor = workspace.executor
            self.assertIsNotNone(executor)
            with self.assertRaises(subprocess.TimeoutExpired):
                executor.run(["python3", "-I", "-c", "import time; time.sleep(5)"], timeout=0.25)
            self.assertTrue(executor.container_names)
            name = executor.container_names[-1]
            inspected = subprocess.run(
                ["docker", "container", "inspect", name],
                capture_output=True,
                check=False,
                shell=False,
                timeout=8,
                text=True,
                env=scrubbed_environment(),
            )
            self.assertNotEqual(inspected.returncode, 0)


if __name__ == "__main__":
    unittest.main()
