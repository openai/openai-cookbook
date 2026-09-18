"""Independent, customer-neutral regressions for the recurring security recipe."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
SOURCE = next(path for path in (ROOT / "src", *sorted(ROOT.glob("*/src")))
              if (path / "fleet_security" / "recipe.py").is_file())
sys.path.insert(0, str(SOURCE))

from fleet_security.evidence import EvidenceError
from fleet_security.inventory import InventoryError, stable_digest
from fleet_security.pipeline import PipelineError
from fleet_security.recipe import RecipeConfiguration, RecurringSecurityRecipe, load_recipe_inventory
from fleet_security.reproduction import (
    DEMO_ATTEMPTED_REPOSITORIES, DEMO_EXPECTED_STATUSES,
    ReproductionFailure, assert_cycle_accounting,
)
from fleet_security.scanner import SyntheticScanner
from fleet_security.schema_validation import OFFICIAL_SCHEMA_NAMES, official_schema_directory


EXAMPLES = ROOT / "cookbook" / "security-review-pipeline"
EXPECTED_STATES = {
    "awaiting_finding_disposition": 2,
    "awaiting_scope_approval": 1,
    "awaiting_threat_model_approval": 1,
    "failed_safe_abstention": 1,
    "review_packet_ready": 1,
}


class RecipeCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="security-recipe-test-")
        self.root = Path(self.temporary.name)
        self.config = self.root / "configuration.json"
        self.inventory = self.root / "inventory.json"
        self.approvals = self.root / "approvals.json"
        for name, path in (("config", self.config), ("inventory", self.inventory), ("approvals", self.approvals)):
            path.write_bytes((EXAMPLES / f"{name}.example.json").read_bytes())
        self.state = self.root / "private-state"
        self.now = 1_788_000_000
        self.addCleanup(self.temporary.cleanup)

    def read(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")

    def cycle(self, *, docker: bool = False) -> dict:
        return RecurringSecurityRecipe.from_files(
            configuration_path=self.config, inventory_path=self.inventory,
            approvals_path=self.approvals, state_directory=self.state,
            docker=docker, clock=lambda: self.now,
        ).cycle()

    def repository(self, name: str) -> dict:
        return next(item for item in self.read(self.inventory)["repositories"]
                    if item["repo_id"] == f"synthetic/{name}")

    def evidence_file(self, repository: str, name: str) -> Path:
        record = self.repository(repository)
        return self.state / "evidence" / f"synthetic-{repository}" / record["commit_sha"][:12] / name

    def finding_approval_target(self, repository_id: str, finding_id: str) -> str:
        states = self.read(self.state / "state.json")["payload"]["states"]
        state = next(row for row in states if row["repository_id"] == repository_id)
        return stable_digest({
            "repository_id": state["repository_id"],
            "commit_sha": state["reviewed_revision"],
            "idempotency_key": state["idempotency_key"],
            "finding_id": finding_id,
        })


class ConfigurationTests(RecipeCase):
    def test_example_has_explicit_unapproved_model_and_all_human_owners(self) -> None:
        configuration = RecipeConfiguration.from_file(self.config)
        self.assertEqual(configuration.selected_model, "gpt-5.6-terra")
        self.assertEqual(configuration.selected_effort, "high")
        self.assertFalse(configuration.model_approved)
        self.assertEqual(len(configuration.owners), 8)

    def test_missing_named_owner_is_refused(self) -> None:
        document = self.read(self.config)
        document["owners"].pop("deploy_owner")
        self.save(self.config, document)
        with self.assertRaisesRegex(PipelineError, "every human gate"):
            RecipeConfiguration.from_file(self.config)

    def test_provider_write_authority_is_refused(self) -> None:
        document = self.read(self.config)
        document["policy"].update(allow_draft_pr=True, provider_write_authorised=True)
        self.save(self.config, document)
        with self.assertRaisesRegex(PipelineError, "never grants provider writes"):
            RecipeConfiguration.from_file(self.config)

    def test_untrusted_network_access_is_refused(self) -> None:
        document = self.read(self.config)
        document["policy"]["allow_untrusted_network"] = True
        self.save(self.config, document)
        with self.assertRaisesRegex(PipelineError, "network access"):
            RecipeConfiguration.from_file(self.config)

    def test_missing_explicit_model_selection_is_refused(self) -> None:
        document = self.read(self.config)
        document["model_selection"].pop("model")
        self.save(self.config, document)
        with self.assertRaisesRegex(PipelineError, "model, reasoning effort"):
            RecipeConfiguration.from_file(self.config)

    def test_invalid_reasoning_effort_is_refused(self) -> None:
        document = self.read(self.config)
        document["model_selection"]["effort"] = "implicit"
        self.save(self.config, document)
        with self.assertRaisesRegex(PipelineError, "reasoning effort"):
            RecipeConfiguration.from_file(self.config)

    def test_unpinned_revision_is_refused(self) -> None:
        document = self.read(self.inventory)
        document["repositories"][0]["commit_sha"] = "main"
        self.save(self.inventory, document)
        with self.assertRaisesRegex(InventoryError, "pinned"):
            load_recipe_inventory(self.inventory)

    def test_missing_service_owner_is_refused(self) -> None:
        document = self.read(self.inventory)
        document["repositories"][0]["owner"] = ""
        self.save(self.inventory, document)
        with self.assertRaisesRegex(InventoryError, "named trusted human owner"):
            load_recipe_inventory(self.inventory)


class ApprovalAndExecutionTests(RecipeCase):
    def test_first_cycle_has_expected_human_holds_and_synthetic_only_receipt(self) -> None:
        receipt = self.cycle()
        self.assertEqual(receipt["decision_states"], EXPECTED_STATES)
        self.assertEqual(receipt["scanner_invocations"], 4)
        self.assertEqual(receipt["official_schema_validated_synthetic_documents"], 9)
        self.assertEqual(receipt["inventory_count"], 6)
        self.assertFalse(receipt["live_product_execution"])
        self.assertEqual(receipt["paid_api_calls"], 0)
        self.assertEqual(receipt["external_writes"], 0)
        self.assertTrue(receipt["audit_valid"])
        self.assertLessEqual(receipt["max_active_workers"], receipt["max_concurrent_policy"])
        self.assertLessEqual(receipt["consumed_synthetic_units"], receipt["campaign_budget_synthetic_units"])
        self.assertLessEqual(receipt["max_reserved_synthetic_units"], receipt["campaign_budget_synthetic_units"])

    def test_missing_scope_stops_before_dispatch(self) -> None:
        receipt = self.cycle()
        row = receipt["records"]["synthetic/unapproved-service"]
        self.assertEqual(row["status"], "awaiting_scope_approval")
        self.assertEqual(row["attempts"], 0)

    def test_unapproved_high_risk_context_stops_before_dispatch(self) -> None:
        receipt = self.cycle()
        row = receipt["records"]["synthetic/restricted-worker"]
        self.assertEqual(row["status"], "awaiting_threat_model_approval")
        self.assertEqual(row["attempts"], 0)

    def test_untrusted_repository_content_abstains_without_credentials(self) -> None:
        receipt = self.cycle()
        row = receipt["records"]["synthetic/adversarial-docs"]
        self.assertEqual(row["status"], "failed_safe_abstention")
        self.assertIn("untrusted", row["reason"])

    def test_wrong_scope_actor_is_refused(self) -> None:
        document = self.read(self.approvals)
        document["approvals"][0]["actor"] = "repository-supplied-actor"
        self.save(self.approvals, document)
        with self.assertRaisesRegex(PipelineError, "not authorised"):
            self.cycle()

    def test_wrong_scope_owner_is_refused(self) -> None:
        document = self.read(self.approvals)
        document["approvals"][0]["service_owner"] = "wrong-owner"
        self.save(self.approvals, document)
        with self.assertRaisesRegex(PipelineError, "currently named repository owner"):
            self.cycle()

    def test_wrong_approved_revision_is_refused(self) -> None:
        document = self.read(self.approvals)
        document["approvals"][0]["revision"] = "a" * 40
        self.save(self.approvals, document)
        with self.assertRaisesRegex(PipelineError, "immutable revision"):
            self.cycle()

    def test_wrong_high_risk_context_hash_is_refused(self) -> None:
        document = self.read(self.approvals)
        next(row for row in document["approvals"] if row["gate"] == "threat_model")["context_sha256"] = "0" * 64
        self.save(self.approvals, document)
        with self.assertRaisesRegex(PipelineError, "current effective context"):
            self.cycle()

    def test_restart_reuses_clean_evidence_and_quarantines_hostile_content(self) -> None:
        first = self.cycle()
        second = self.cycle()
        self.assertEqual(first["scanner_invocations"], 4)
        self.assertEqual(second["scanner_invocations"], 0)
        self.assertEqual(second["decision_states"], first["decision_states"])
        self.assertEqual(second["quarantined_unchanged"], ["synthetic/adversarial-docs"])
        self.assertEqual(second["run_number"], 2)

    def test_signed_state_and_all_receipts_are_owner_private(self) -> None:
        self.cycle()
        self.assertEqual(stat.S_IMODE(self.state.stat().st_mode), 0o700)
        for path in self.state.rglob("*"):
            expected = 0o700 if path.is_dir() else 0o600
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), expected, str(path))

    def test_tampered_signed_checkpoint_is_refused(self) -> None:
        self.cycle()
        state_path = self.state / "state.json"
        envelope = self.read(state_path)
        envelope["payload"]["run_number"] = 50
        self.save(state_path, envelope)
        with self.assertRaisesRegex(EvidenceError, "signature"):
            self.cycle()

    def test_tampered_persisted_finding_is_refused(self) -> None:
        self.cycle()
        path = self.evidence_file("payments-api", "findings.json")
        payload = self.read(path)
        payload["findings"][0]["title"] = "forged external evidence"
        self.save(path, payload)
        with self.assertRaisesRegex(EvidenceError, "differs from its signed checkpoint"):
            self.cycle()

    def test_missing_persisted_report_is_refused(self) -> None:
        self.cycle()
        self.evidence_file("payments-api", "report.md").unlink()
        with self.assertRaisesRegex(EvidenceError, "artifact is missing"):
            self.cycle()

    def test_missing_signing_key_refuses_existing_state(self) -> None:
        self.cycle()
        (self.state / ".local-state-key").unlink()
        with self.assertRaisesRegex(EvidenceError, "original host key"):
            self.cycle()

    def test_broadened_evidence_file_permissions_are_refused(self) -> None:
        self.cycle()
        self.evidence_file("payments-api", "coverage.json").chmod(0o644)
        with self.assertRaisesRegex(EvidenceError, "not owner-private"):
            self.cycle()

    def test_named_finding_acceptance_updates_review_without_a_rescan(self) -> None:
        self.cycle()
        repository = self.repository("payments-api")
        finding = self.read(self.evidence_file("payments-api", "findings.json"))["findings"][0]
        approvals = self.read(self.approvals)
        approvals["approvals"].append({
            "gate": "finding_disposition", "repository_id": repository["repo_id"],
            "revision": repository["commit_sha"], "finding_id": finding["findingId"],
            "target_sha256": self.finding_approval_target(repository["repo_id"], finding["findingId"]),
            "expires_at": self.now + 3_600,
            "actor": "finding-owner",
        })
        self.save(self.approvals, approvals)
        receipt = self.cycle()
        self.assertEqual(receipt["records"][repository["repo_id"]]["status"], "review_packet_ready")
        self.assertEqual(receipt["scanner_invocations"], 0)
        self.assertFalse(receipt["records"][repository["repo_id"]]["external_pr_created"])

    def test_revoked_scope_prevents_cached_evidence_reuse(self) -> None:
        self.cycle()
        document = self.read(self.approvals)
        document["approvals"] = [row for row in document["approvals"]
                                  if row["repository_id"] != "synthetic/payments-api"]
        self.save(self.approvals, document)
        receipt = self.cycle()
        self.assertEqual(receipt["records"]["synthetic/payments-api"]["status"], "awaiting_scope_approval")
        self.assertEqual(receipt["scanner_invocations"], 0)

    def test_periodic_expiry_revalidates_only_approved_clean_evidence(self) -> None:
        self.cycle()
        self.now += 169 * 3_600
        receipt = self.cycle()
        self.assertEqual(receipt["scanner_invocations"], 3)
        self.assertEqual(len(receipt["revalidation_due"]), 3)
        self.assertEqual(receipt["quarantined_unchanged"], ["synthetic/adversarial-docs"])

    def test_changed_approved_revision_schedules_only_the_affected_repository(self) -> None:
        self.cycle()
        inventory = self.read(self.inventory)
        row = next(item for item in inventory["repositories"] if item["repo_id"] == "synthetic/catalog-service")
        row["commit_sha"] = "b" * 40
        self.save(self.inventory, inventory)
        approvals = self.read(self.approvals)
        next(item for item in approvals["approvals"] if item["repository_id"] == row["repo_id"])["revision"] = row["commit_sha"]
        self.save(self.approvals, approvals)
        receipt = self.cycle()
        self.assertEqual(receipt["scanner_invocations"], 1)
        self.assertEqual(receipt["records"][row["repo_id"]]["reviewed_revision"], "b" * 40)

    def test_documentation_only_revision_avoids_an_unaffected_rescan(self) -> None:
        self.cycle()
        inventory = self.read(self.inventory)
        row = next(item for item in inventory["repositories"] if item["repo_id"] == "synthetic/catalog-service")
        row["commit_sha"] = "c" * 40
        row["changed_paths"] = ["docs/operator-notes.md"]
        self.save(self.inventory, inventory)
        approvals = self.read(self.approvals)
        next(item for item in approvals["approvals"] if item["repository_id"] == row["repo_id"])["revision"] = row["commit_sha"]
        self.save(self.approvals, approvals)
        receipt = self.cycle()
        self.assertEqual(receipt["scanner_invocations"], 0)
        self.assertEqual(receipt["records"][row["repo_id"]]["status"], "skipped_unchanged_security_scope")

    def test_material_boundary_change_invalidates_only_affected_context(self) -> None:
        self.cycle()
        inventory = self.read(self.inventory)
        row = next(item for item in inventory["repositories"] if item["repo_id"] == "synthetic/catalog-service")
        row["exposure"] = "internet"
        self.save(self.inventory, inventory)
        receipt = self.cycle()
        self.assertEqual(receipt["scanner_invocations"], 1)
        self.assertEqual(receipt["records"][row["repo_id"]]["status"], "review_packet_ready")

    def test_rate_ceiling_defers_remaining_approved_scans(self) -> None:
        config = self.read(self.config)
        config["policy"]["max_scans_per_run"] = 1
        self.save(self.config, config)
        receipt = self.cycle()
        self.assertEqual(receipt["scanner_invocations"], 1)
        self.assertEqual(receipt["decision_states"]["deferred_rate_limit"], 3)

    def test_insufficient_admission_budget_prevents_all_dispatch(self) -> None:
        config = self.read(self.config)
        config["policy"]["max_campaign_units"] = 13
        self.save(self.config, config)
        receipt = self.cycle()
        self.assertEqual(receipt["scanner_invocations"], 0)
        self.assertEqual(receipt["decision_states"]["deferred_budget"], 4)

    def test_named_expiring_exception_routes_to_human_review_packet(self) -> None:
        self.cycle()
        repository = self.repository("payments-api")
        finding = self.read(self.evidence_file("payments-api", "findings.json"))["findings"][0]
        approvals = self.read(self.approvals)
        approvals["approvals"].append({
            "gate": "exception", "repository_id": repository["repo_id"],
            "revision": repository["commit_sha"], "finding_id": finding["findingId"],
            "target_sha256": self.finding_approval_target(repository["repo_id"], finding["findingId"]),
            "expires_at": self.now + 3_600, "actor": "risk-owner",
        })
        self.save(self.approvals, approvals)
        receipt = self.cycle()
        record = receipt["records"][repository["repo_id"]]
        self.assertEqual(record["status"], "review_packet_ready")
        self.assertEqual(record["named_reviewers"]["exception"], "risk-owner")
        self.assertEqual(receipt["scanner_invocations"], 0)

    def test_configuration_change_requires_named_policy_owner(self) -> None:
        self.cycle()
        config = self.read(self.config)
        config["policy"]["max_concurrent"] = 2
        self.save(self.config, config)
        with self.assertRaisesRegex(PipelineError, "policy-owner approval"):
            self.cycle()

    def test_explicit_policy_owner_approval_allows_configuration_change(self) -> None:
        self.cycle()
        config = self.read(self.config)
        config["policy"]["max_concurrent"] = 2
        self.save(self.config, config)
        approvals = self.read(self.approvals)
        approvals["approvals"].append({
            "gate": "policy_change", "repository_id": "fleet",
            "configuration_sha256": RecipeConfiguration.from_file(self.config).fingerprint,
            "expires_at": self.now + 3_600,
            "actor": "policy-owner",
        })
        self.save(self.approvals, approvals)
        receipt = self.cycle()
        self.assertEqual(receipt["run_number"], 2)
        self.assertEqual(receipt["scanner_invocations"], 0)

    def test_native_campaigns_are_pinned_explicit_and_never_executed(self) -> None:
        receipt = self.cycle()
        self.assertEqual(len(receipt["native_campaign_plans"]), 2)
        for campaign in receipt["native_campaign_plans"]:
            command = campaign["command"]
            self.assertEqual(command[:3], ["npx", "@openai/codex-security@0.1.20", "bulk-scan"])
            self.assertEqual(command.count("--knowledge-base"), 2)
            self.assertIn("--model", command)
            self.assertIn("--effort", command)
            self.assertNotIn("--max-cost", command)
            self.assertFalse(campaign["command_executed"])
            self.assertFalse(campaign["customer_model_approval_verified"])
            self.assertTrue(Path(campaign["csv_path"]).is_file())

    def test_fresh_os_processes_share_authenticated_state_without_rescanning(self) -> None:
        args = [sys.executable, str(ROOT / "scripts" / "run_security_review_cookbook.py"),
                "--config", str(self.config), "--inventory", str(self.inventory),
                "--approvals", str(self.approvals), "--state-dir", str(self.state)]
        first = json.loads(subprocess.run(args, cwd=ROOT, check=True, capture_output=True, text=True).stdout)
        second = json.loads(subprocess.run(args, cwd=ROOT, check=True, capture_output=True, text=True).stdout)
        self.assertEqual(first["scanner_invocations_per_cycle"], [4])
        self.assertEqual(second["scanner_invocations_per_cycle"], [0])
        self.assertEqual(second["latest"]["run_number"], 2)


class OfficialSchemaDiscoveryTests(RecipeCase):
    def install(self, version: str, *, complete: bool = True) -> Path:
        schemas = self.root / "cache" / version / "schemas"
        schemas.mkdir(parents=True)
        names = OFFICIAL_SCHEMA_NAMES if complete else OFFICIAL_SCHEMA_NAMES[:2]
        for name in names:
            (schemas / f"{name}.schema.json").write_text("{}")
        return schemas

    def test_newest_complete_official_plugin_is_discovered(self) -> None:
        self.install("0.1.9")
        expected = self.install("0.1.22")
        self.install("0.2.0", complete=False)
        self.assertEqual(official_schema_directory(plugin_cache=self.root / "cache"), expected.resolve())

    def test_explicit_trusted_schema_override_is_honoured(self) -> None:
        schemas = self.install("2.3.4")
        self.assertEqual(official_schema_directory(schema_root=schemas), schemas.resolve())

    def test_environment_schema_override_is_honoured(self) -> None:
        schemas = self.install("2.3.4")
        with mock.patch.dict(os.environ, {"CODEX_SECURITY_SCHEMA_ROOT": str(schemas)}):
            self.assertEqual(official_schema_directory(), schemas.resolve())

    def test_missing_contracts_fail_closed(self) -> None:
        self.install("1.0.0", complete=False)
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(EvidenceError, "official Codex Security schemas are unavailable"):
                official_schema_directory(plugin_cache=self.root / "cache")


class NotebookTests(RecipeCase):
    @staticmethod
    def notebook_path() -> Path:
        published = ROOT / "governed_repository_security_reviews.ipynb"
        return published if published.is_file() else ROOT / "cookbook" / published.name

    def test_clean_notebook_has_twelve_runnable_cells_without_saved_results(self) -> None:
        document = self.read(self.notebook_path())
        code = [item for item in document["cells"] if item["cell_type"] == "code"]
        self.assertEqual(document["nbformat"], 4)
        self.assertEqual(len(code), 12)
        self.assertTrue(all(not item["outputs"] and item["execution_count"] is None for item in code))

    def test_portable_customer_neutral_sources_exclude_private_identifiers(self) -> None:
        marker = "".join(("auto", "scout", "24"))
        paths = [self.notebook_path(),
                 ROOT / "scripts" / "run_security_review_cookbook.py",
                 ROOT / "scripts" / "build_security_review_cookbook.py",
                 *EXAMPLES.glob("*.json"), *EXAMPLES.glob("*.md")]
        for path in paths:
            content = path.read_text(encoding="utf-8").casefold()
            self.assertNotIn(marker, content, str(path))
            self.assertNotIn("/" + "users" + "/", content, str(path))
            self.assertNotIn("001" + "vu", content, str(path))


@unittest.skipUnless(os.environ.get("RUN_RECIPE_DOCKER") == "1", "genuine restricted Docker is opt-in")
class RestrictedDockerTests(RecipeCase):
    def test_restricted_docker_proves_isolation_and_restart_idempotency(self) -> None:
        first = self.cycle(docker=True)
        second = self.cycle(docker=True)
        policy = RecipeConfiguration.from_file(self.config).policy
        assert_cycle_accounting(
            first, expected_attempted_repositories=DEMO_ATTEMPTED_REPOSITORIES,
            expected_statuses=DEMO_EXPECTED_STATUSES, policy=policy,
            expected_isolation_receipts=3, context="first_cycle",
        )
        assert_cycle_accounting(
            second, expected_attempted_repositories=(),
            expected_statuses=DEMO_EXPECTED_STATUSES, policy=policy,
            expected_isolation_receipts=0, context="restart_cycle",
        )
        self.assertEqual(second["scanner_invocations"], 0)
        self.assertEqual(first["decision_states"], EXPECTED_STATES)
        self.assertEqual(first["execution_mode"], "synthetic_restricted_docker")


class RetryAccountingTests(RecipeCase):
    """Deterministic integration checks; these do not launch Docker workers."""

    def test_transient_retry_preserves_exact_jobs_and_zero_restart_work(self) -> None:
        target = "synthetic/catalog-service"
        scanner = SyntheticScanner(behaviour={target: ("transient", "success")})
        with mock.patch("fleet_security.recipe.SyntheticScanner", return_value=scanner):
            first = self.cycle()
        second = self.cycle()
        policy = RecipeConfiguration.from_file(self.config).policy
        assert_cycle_accounting(
            first, expected_attempted_repositories=DEMO_ATTEMPTED_REPOSITORIES,
            expected_statuses=DEMO_EXPECTED_STATUSES, policy=policy,
            expected_isolation_receipts=0, context="first_cycle",
        )
        self.assertEqual(first["scanner_invocations"], 5)
        self.assertEqual(first["scanner_attempts_by_repository"][target], 2)
        self.assertEqual(first["retry_attempts"], 1)
        assert_cycle_accounting(
            second, expected_attempted_repositories=(),
            expected_statuses=DEMO_EXPECTED_STATUSES, policy=policy,
            expected_isolation_receipts=0, context="restart_cycle",
        )
        self.assertEqual(second["scanner_invocations"], 0)
        self.assertEqual(second["records"][target]["attempts"], 2)

    def test_exhausted_transient_failure_cannot_pass_nominal_cycle_contract(self) -> None:
        target = "synthetic/catalog-service"
        scanner = SyntheticScanner(behaviour={target: ("timeout", "timeout")})
        with mock.patch("fleet_security.recipe.SyntheticScanner", return_value=scanner):
            receipt = self.cycle()
        self.assertEqual(receipt["records"][target]["status"], "failed_safe_abstention")
        self.assertEqual(receipt["scanner_attempts_by_repository"][target], 2)
        with self.assertRaisesRegex(ReproductionFailure, "final_repository_decisions"):
            assert_cycle_accounting(
                receipt, expected_attempted_repositories=DEMO_ATTEMPTED_REPOSITORIES,
                expected_statuses=DEMO_EXPECTED_STATUSES,
                policy=RecipeConfiguration.from_file(self.config).policy,
                expected_isolation_receipts=0, context="first_cycle",
            )


if __name__ == "__main__":
    unittest.main()
