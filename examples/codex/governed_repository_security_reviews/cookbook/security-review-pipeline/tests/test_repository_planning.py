"""Adversarial regressions for non-executing real-repository metadata plans."""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
SOURCE = next(
    source for source in (ROOT / "src", *sorted(ROOT.glob("*/src")))
    if (source / "fleet_security" / "planning.py").is_file()
)
if str(SOURCE) not in sys.path:
    sys.path.insert(0, str(SOURCE))

from fleet_security.inventory import InventoryError, Repository
from fleet_security.pipeline import PipelineError
from fleet_security.planning import prepare_repository_review
from fleet_security.recipe import RecipeConfiguration
from fleet_security.threats import ThreatCatalogue


EXAMPLES = ROOT / "cookbook" / "security-review-pipeline"


class RepositoryPlanningTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="metadata-only-planning-test-")
        self.addCleanup(self.temporary.cleanup)
        self.workspace = Path(self.temporary.name)
        self.configuration = self.workspace / "configuration.json"
        self.inventory = self.workspace / "inventory.json"
        self.approvals = self.workspace / "approvals.json"
        self.configuration.write_bytes((EXAMPLES / "config.example.json").read_bytes())
        self.inventory.write_bytes((EXAMPLES / "inventory.real.example.json").read_bytes())
        self.approvals.write_bytes((EXAMPLES / "approvals.real.example.json").read_bytes())

    def plan(self) -> dict:
        return prepare_repository_review(
            configuration_path=self.configuration,
            inventory_path=self.inventory,
            approvals_path=self.approvals,
        )

    def edit_inventory(self, update) -> None:
        document = json.loads(self.inventory.read_text(encoding="utf-8"))
        update(document)
        self.inventory.write_text(json.dumps(document), encoding="utf-8")

    def edit_approvals(self, update) -> None:
        document = json.loads(self.approvals.read_text(encoding="utf-8"))
        update(document)
        self.approvals.write_text(json.dumps(document), encoding="utf-8")

    def test_default_metadata_example_never_inspects_code_or_creates_findings(self) -> None:
        before = {item.name for item in self.workspace.iterdir()}
        with mock.patch.object(socket, "create_connection", side_effect=AssertionError("network used")):
            with mock.patch.object(subprocess, "run", side_effect=AssertionError("scanner executed")):
                receipt = self.plan()
        self.assertEqual(receipt["mode"], "planning_only")
        self.assertEqual(receipt["decision_states"], {
            "awaiting_scope_approval": 1,
            "awaiting_threat_model_acceptance": 1,
            "planned_not_executed": 1,
        })
        self.assertEqual(receipt["scanned_repositories"], 0)
        self.assertEqual(receipt["scan_receipts"], 0)
        self.assertIsNone(receipt["finding_count"])
        self.assertEqual(receipt["review_packets_created"], 0)
        self.assertFalse(receipt["customer_repository_accessed"])
        self.assertFalse(receipt["product_scan_executed"])
        self.assertEqual(receipt["paid_api_calls"], 0)
        self.assertEqual(receipt["external_writes"], 0)
        self.assertEqual(before, {item.name for item in self.workspace.iterdir()})

    def test_only_exact_scope_authorised_standard_repository_enters_inert_campaign(self) -> None:
        receipt = self.plan()
        self.assertEqual(len(receipt["campaigns"]), 1)
        campaign = receipt["campaigns"][0]
        self.assertEqual(campaign["repository_count"], 1)
        self.assertIn("https://git.example.invalid/example-company/payments-api.git", {
            row["repository"] for row in campaign["rows"]
        })
        self.assertFalse(campaign["command_executed"])
        self.assertFalse(campaign["campaign_files_written"])
        self.assertFalse(campaign["native_campaign_has_hard_cost_flag"])

    def test_high_risk_requires_exact_named_threat_context_acceptance(self) -> None:
        configuration = RecipeConfiguration.from_file(self.configuration)
        raw = next(row for row in json.loads(self.inventory.read_text())["repositories"]
                   if row["repo_id"] == "example-company/edge-auth")
        row = {key: value for key, value in raw.items() if key != "repository_url"}
        for key in ("dependencies", "controls", "changed_paths"):
            row[key] = tuple(row[key])
        repository = Repository(**row)
        catalogue = ThreatCatalogue(
            organisation_controls=configuration.organisation_controls,
            version=configuration.organisation_model_version,
        )
        context = catalogue.assign(repository).effective_model_hash
        self.edit_approvals(lambda document: document["approvals"].append({
            "gate": "threat_model", "repository_id": repository.repo_id,
            "revision": repository.commit_sha, "context_sha256": context,
            "actor": "threat-owner",
        }))
        receipt = self.plan()
        result = next(row for row in receipt["repositories"] if row["repository_id"] == repository.repo_id)
        self.assertEqual(result["status"], "planned_not_executed")
        self.assertEqual(result["named_human_reviewers"]["threat_model"], "threat-owner")
        self.assertEqual(receipt["scanned_repositories"], 0)

    def test_embedded_url_credentials_are_rejected_without_execution(self) -> None:
        self.edit_inventory(lambda doc: doc["repositories"][0].update(
            repository_url="https://secret-user:secret-pass@git.example.invalid/example-company/payments-api.git"
        ))
        with self.assertRaisesRegex(PipelineError, "embedded credentials|HTTPS"):
            self.plan()

    def test_localhost_and_private_addresses_are_rejected(self) -> None:
        for host in ("localhost", "127.0.0.1", "169.254.169.254", "10.1.2.3"):
            with self.subTest(host=host):
                self.edit_inventory(lambda doc, host=host: doc["repositories"][0].update(
                    repository_url=f"https://{host}/example-company/payments-api.git"
                ))
                with self.assertRaisesRegex(PipelineError, "localhost|internal address"):
                    self.plan()

    def test_provider_url_must_match_exact_trusted_repository_identity(self) -> None:
        self.edit_inventory(lambda doc: doc["repositories"][0].update(
            repository_url="https://git.example.invalid/example-company/unrelated-clean-service.git"
        ))
        with self.assertRaisesRegex(PipelineError, "exact trusted repository identity"):
            self.plan()

    def test_encoded_provider_path_is_rejected(self) -> None:
        self.edit_inventory(lambda doc: doc["repositories"][0].update(
            repository_url="https://git.example.invalid/example-company/payments%2dapi.git"
        ))
        with self.assertRaisesRegex(PipelineError, "encoded|ambiguous"):
            self.plan()

    def test_repository_revision_must_be_full_immutable_sha(self) -> None:
        self.edit_inventory(lambda doc: doc["repositories"][0].update(commit_sha="main"))
        with self.assertRaisesRegex(InventoryError, "revision|SHA"):
            self.plan()

    def test_real_metadata_cannot_select_a_synthetic_clean_fixture(self) -> None:
        self.edit_inventory(lambda doc: doc["repositories"][0].update(fixture="safe_service"))
        with self.assertRaisesRegex(PipelineError, "synthetic fixture"):
            self.plan()

    def test_scope_owner_mismatch_invalidates_the_whole_plan(self) -> None:
        self.edit_approvals(lambda doc: doc["approvals"][0].update(service_owner="different-owner"))
        with self.assertRaisesRegex(PipelineError, "named service owner"):
            self.plan()

    def test_untrusted_human_actor_cannot_grant_scope(self) -> None:
        self.edit_approvals(lambda doc: doc["approvals"][0].update(actor="untrusted-actor"))
        with self.assertRaisesRegex(PipelineError, "not authorised"):
            self.plan()

    def test_unsupported_provider_write_approval_is_rejected(self) -> None:
        self.edit_approvals(lambda doc: doc["approvals"][0].update(grant_provider_write=True))
        with self.assertRaisesRegex(PipelineError, "unsupported authority"):
            self.plan()

    def test_model_approval_false_blocks_execution_even_for_authorised_metadata(self) -> None:
        receipt = self.plan()
        self.assertFalse(receipt["model_execution_approved"])
        self.assertIn("named_model_and_spending_owner_approval_required", receipt["execution_blockers"])
        self.assertIn("native_product_execution_not_authorised", receipt["execution_blockers"])

    def test_no_scope_approval_yields_hold_without_campaign(self) -> None:
        self.edit_approvals(lambda doc: doc.update(approvals=[]))
        receipt = self.plan()
        self.assertEqual(receipt["decision_states"], {"awaiting_scope_approval": 3})
        self.assertEqual(receipt["campaigns"], [])


if __name__ == "__main__":
    unittest.main()
