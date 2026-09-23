"""Independent regression cases for documentation-only scheduling shortcuts."""
from dataclasses import asdict, replace
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from fleet_security import ApprovalLedger, FleetPipeline, FleetPolicy, Repository, SyntheticScanner, ThreatCatalogue
from fleet_security.evidence import EvidenceError
from fleet_security.inventory import classify, stable_digest


class SchedulingValidity(unittest.TestCase):
    def test_security_documentation_is_not_a_docs_only_shortcut(self):
        for path in ("docs/security.md", "docs/threat_model.md", "docs/architecture.md", "security/guide.md"):
            with self.subTest(path=path):
                self.assertTrue(FleetPipeline._security_relevant(path))

    def setUp(self):
        self.record = Repository(
            repo_id="synthetic/flint-scheduling", commit_sha="a" * 40, owner="fixture-owner",
            language="python", framework="fastapi", topology="container", data_class="internal",
            exposure="private", authentication="service_identity", dependencies=("synthetic-library",),
            controls=("audit_logging",), changed_paths=("src/service.py",), fixture="safe_service",
        )
        self.approvals = ApprovalLedger({"scope_authorizer": {"scope-owner"}, "policy_owner": {"policy-owner"}})
        self.flow = FleetPipeline(policy=FleetPolicy(), approvals=self.approvals)
        self.approve(self.record)

    def approve(self, record):
        self.approvals.approve("scope", record.repo_id, self.flow.scope_target(record), "scope-owner")

    def docs_revision(self):
        revision = replace(self.record, commit_sha="b" * 40, changed_paths=("docs/guide.md",))
        self.approve(revision)
        return revision

    def test_unchanged_context_documentation_baseline_may_skip(self):
        self.flow.run((self.record,))
        result = self.flow.run((self.docs_revision(),))
        self.assertEqual(result["records"][self.record.repo_id]["status"], "skipped_unchanged_security_scope")
        self.assertEqual(result["scanner_invocations"], 1)

    def test_organisation_context_drift_must_not_be_skipped_for_docs_revision(self):
        self.flow.run((self.record,))
        self.flow.catalogue = replace(self.flow.catalogue, version="synthetic-org-v2")
        result = self.flow.run((self.docs_revision(),))
        self.assertEqual(result["scanner_invocations"], 2)

    def test_archetype_context_drift_must_not_be_skipped_for_docs_revision(self):
        self.flow.run((self.record,))
        self.flow.catalogue = replace(self.flow.catalogue, archetype_overrides={
            classify(self.record).archetype: ("synthetic_new_security_boundary",),
        })
        result = self.flow.run((self.docs_revision(),))
        self.assertEqual(result["scanner_invocations"], 2)

    def test_scanner_version_drift_must_not_be_skipped_for_docs_revision(self):
        self.flow.run((self.record,))
        policy = replace(self.flow.policy, scanner_version="synthetic-security-adapter/2.0")
        self.approvals.approve("policy_change", "fleet", stable_digest(asdict(policy)), "policy-owner")
        self.flow.apply_policy(policy, actor="policy-owner")
        result = self.flow.run((self.docs_revision(),))
        self.assertEqual(result["scanner_invocations"], 2)

    def test_policy_version_drift_must_not_be_skipped_for_docs_revision(self):
        self.flow.run((self.record,))
        policy = replace(self.flow.policy, policy_version="synthetic-policy-v2")
        self.approvals.approve("policy_change", "fleet", stable_digest(asdict(policy)), "policy-owner")
        self.flow.apply_policy(policy, actor="policy-owner")
        result = self.flow.run((self.docs_revision(),))
        self.assertEqual(result["scanner_invocations"], 2)

    def test_failed_predecessor_is_not_clean_unchanged_evidence(self):
        self.flow.scanner = SyntheticScanner(behaviour={self.record.repo_id: ("permanent", "success")})
        first = self.flow.run((self.record,))
        self.assertEqual(first["records"][self.record.repo_id]["status"], "failed_safe_abstention")
        result = self.flow.run((self.docs_revision(),))
        self.assertEqual(result["scanner_invocations"], 2)

    def test_tampered_predecessor_cannot_use_documentation_shortcut(self):
        self.flow.run((self.record,))
        self.flow.states[self.record.repo_id].evidence["report.md"] += "synthetic tamper"
        revision = self.docs_revision()
        try:
            result = self.flow.run((revision,))
        except EvidenceError:
            return
        self.assertNotEqual(result["records"][self.record.repo_id]["status"], "skipped_unchanged_security_scope")

    def test_documentation_shortcut_does_not_erase_known_unresolved_findings(self):
        self.record = replace(self.record, fixture="vulnerable_service")
        self.approve(self.record)
        first = self.flow.run((self.record,))
        prior = first["records"][self.record.repo_id]
        self.assertEqual(prior["status"], "awaiting_finding_disposition")
        result = self.flow.run((self.docs_revision(),))
        current = result["records"][self.record.repo_id]
        self.assertEqual(current["current_findings"], prior["current_findings"])
        self.assertEqual(current["route"], "review_packet")


if __name__ == "__main__":
    unittest.main(verbosity=2)
