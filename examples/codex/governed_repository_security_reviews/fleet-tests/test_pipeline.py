from __future__ import annotations

import hashlib
import time
import unittest
from dataclasses import asdict, replace

from support import approve_model, approve_scope, ledger, pipeline, repository
from fleet_security import FleetPolicy, PipelineError, ScanFailure, SyntheticScanner, generate_inventory
from fleet_security.inventory import stable_digest


class PipelineAdmissionTests(unittest.TestCase):
    def test_unapproved_scope_never_invokes_scanner(self) -> None:
        flow = pipeline()
        record = repository()
        result = flow.run((record,))
        self.assertEqual(result["records"][record.repo_id]["status"], "awaiting_scope_approval")
        self.assertEqual((result["scanner_invocations"], result["consumed_units"]), (0, 0))

    def test_scope_approval_is_bound_to_exact_revision_and_current_named_owner(self) -> None:
        flow = pipeline()
        original = repository()
        approve_scope(flow, original)
        revised = replace(original, commit_sha="b" * 40)
        reassigned = replace(original, owner="replacement-owner")
        for record in (revised, reassigned):
            with self.subTest(record=record.repo_id):
                outcome = flow.run((record,))
                self.assertEqual(outcome["records"][record.repo_id]["status"], "awaiting_scope_approval")
        self.assertEqual(sum(flow.scanner.invocations.values()), 0)

    def test_high_risk_model_requires_human_acceptance_before_scanner_launch(self) -> None:
        flow = pipeline()
        record = repository(criticality="critical")
        approve_scope(flow, record)
        result = flow.run((record,))
        self.assertEqual(result["records"][record.repo_id]["status"], "awaiting_threat_model_approval")
        self.assertEqual(result["scanner_invocations"], 0)
        approve_model(flow, record)
        self.assertEqual(flow.run((record,))["records"][record.repo_id]["status"], "review_packet_ready")

    def test_stale_model_approval_does_not_cover_changed_threat_context(self) -> None:
        flow = pipeline()
        record = repository(criticality="critical")
        approve_scope(flow, record)
        approve_model(flow, record)
        changed = replace(record, data_class="restricted")
        result = flow.run((changed,))
        self.assertEqual(result["records"][record.repo_id]["status"], "awaiting_threat_model_approval")
        self.assertEqual(result["scanner_invocations"], 0)

    def test_unknown_actor_cannot_grant_scope_model_disposition_or_patch(self) -> None:
        flow = pipeline()
        record = repository()
        for gate in ("scope", "threat_model", "finding_disposition", "patch", "policy_change"):
            with self.subTest(gate=gate), self.assertRaises(PipelineError):
                flow.approvals.approve(gate, record.repo_id, "trusted-target", "synthetic-scanner")

    def test_expired_scope_approval_blocks_before_scan(self) -> None:
        now = [100]
        approvals = ledger(now=now)
        flow = pipeline(approvals=approvals, clock=lambda: now[0])
        record = repository()
        approvals.approve("scope", record.repo_id, flow.scope_target(record), "scope-owner", expires_at=101)
        now[0] = 101
        result = flow.run((record,))
        self.assertEqual(result["records"][record.repo_id]["status"], "awaiting_scope_approval")
        self.assertEqual(result["scanner_invocations"], 0)

    def test_cancellation_prevents_any_adapter_invocation(self) -> None:
        flow = pipeline()
        record = repository()
        approve_scope(flow, record)
        flow.cancel(record.repo_id, actor="scope-owner")
        result = flow.run((record,))
        self.assertEqual(result["records"][record.repo_id]["status"], "cancelled")
        self.assertEqual(result["scanner_invocations"], 0)

    def test_scanner_or_untrusted_actor_cannot_cancel_an_authorised_campaign(self) -> None:
        flow = pipeline()
        record = repository()
        approve_scope(flow, record)
        with self.assertRaises(PipelineError):
            flow.cancel(record.repo_id, actor="synthetic-scanner")
        self.assertEqual(flow.run((record,))["records"][record.repo_id]["status"], "review_packet_ready")

    def test_merge_deploy_network_or_unapproved_provider_policy_cannot_be_relaxed(self) -> None:
        for change in (
            {"require_human_merge": False},
            {"require_human_deploy": False},
            {"allow_untrusted_network": True},
            {"provider_write_authorised": True},
        ):
            with self.subTest(change=change), self.assertRaises(PipelineError):
                FleetPolicy(**change)

    def test_policy_change_requires_named_owner_and_exact_policy_digest(self) -> None:
        flow = pipeline()
        updated = FleetPolicy(policy_version="synthetic-policy-v2")
        with self.assertRaises(PipelineError):
            flow.apply_policy(updated, actor="policy-owner")
        target = stable_digest(asdict(updated))
        flow.approvals.approve("policy_change", "fleet", target, "policy-owner")
        flow.apply_policy(updated, actor="policy-owner")
        self.assertEqual(flow.policy.policy_version, "synthetic-policy-v2")


class PipelineSchedulingTests(unittest.TestCase):
    def test_identical_revision_context_and_policy_reuses_verified_evidence(self) -> None:
        flow = pipeline()
        record = repository()
        approve_scope(flow, record)
        first = flow.run((record,))
        second = flow.run((record,))
        self.assertEqual((first["scanner_invocations"], second["scanner_invocations"]), (1, 1))
        self.assertEqual(second["records"][record.repo_id]["status"], "review_packet_ready")

    def test_docs_only_change_is_not_rescanned_after_explicit_new_revision_approval(self) -> None:
        flow = pipeline()
        original = repository()
        approve_scope(flow, original)
        flow.run((original,))
        updated = replace(original, commit_sha="d" * 40, changed_paths=("docs/guide.md",))
        approve_scope(flow, updated)
        outcome = flow.run((updated,))
        self.assertEqual(outcome["records"][updated.repo_id]["status"], "skipped_unchanged_security_scope")
        self.assertEqual(outcome["scanner_invocations"], 1)

    def test_readme_agents_and_security_code_changes_remain_security_relevant(self) -> None:
        for path in ("README.md", "AGENTS.md", "src/service.py", "infra/main.tf", "package-lock.json"):
            flow = pipeline()
            original = repository()
            approve_scope(flow, original)
            flow.run((original,))
            updated = replace(original, commit_sha="e" * 40, changed_paths=(path,))
            approve_scope(flow, updated)
            outcome = flow.run((updated,))
            with self.subTest(path=path):
                self.assertEqual(outcome["scanner_invocations"], 2)

    def test_boundary_change_rescans_even_when_only_documentation_changed(self) -> None:
        flow = pipeline()
        original = repository()
        approve_scope(flow, original)
        flow.run((original,))
        changed = replace(original, data_class="confidential", commit_sha="f" * 40, changed_paths=("docs/guide.md",))
        approve_scope(flow, changed)
        outcome = flow.run((changed,))
        self.assertEqual(outcome["scanner_invocations"], 2)

    def test_rate_limit_defers_excess_repositories_without_invoking_them(self) -> None:
        flow = pipeline(policy=FleetPolicy(max_scans_per_run=2))
        fleet = tuple(repository(index) for index in range(1, 5))
        for record in fleet:
            approve_scope(flow, record)
        result = flow.run(fleet)
        self.assertEqual((result["admitted"], result["scanner_invocations"]), (2, 2))
        self.assertEqual(sum(value["status"] == "deferred_rate_limit" for value in result["records"].values()), 2)

    def test_hard_campaign_budget_reserves_all_retries_and_inflight_overshoot(self) -> None:
        policy = FleetPolicy(max_campaign_units=20, estimated_scan_units=5, max_inflight_overshoot_units=2, max_attempts=2)
        flow = pipeline(policy=policy)
        fleet = (repository(1), repository(2))
        for record in fleet:
            approve_scope(flow, record)
        result = flow.run(fleet)
        self.assertEqual(result["admitted"], 1)
        self.assertEqual(sum(value["status"] == "deferred_budget" for value in result["records"].values()), 1)
        self.assertLessEqual(result["max_observed_reserved_units"], policy.max_campaign_units)
        self.assertEqual(result["reserved_units"], 0)

    def test_estimated_overshoot_that_would_exceed_budget_is_never_admitted(self) -> None:
        flow = pipeline(policy=FleetPolicy(max_campaign_units=10, estimated_scan_units=5,
                                            max_inflight_overshoot_units=3, max_attempts=2))
        record = repository()
        approve_scope(flow, record)
        outcome = flow.run((record,))
        self.assertEqual(outcome["records"][record.repo_id]["status"], "deferred_budget")
        self.assertEqual(outcome["scanner_invocations"], 0)

    def test_worker_concurrency_never_exceeds_trusted_cap(self) -> None:
        class SlowScanner(SyntheticScanner):
            def _offline_matches(self, fixture):
                time.sleep(0.015)
                return super()._offline_matches(fixture)

        flow = pipeline(scanner=SlowScanner(), policy=FleetPolicy(max_concurrent=3))
        fleet = tuple(repository(index) for index in range(1, 9))
        for record in fleet:
            approve_scope(flow, record)
        outcome = flow.run(fleet)
        self.assertGreaterEqual(outcome["max_active_workers"], 2)
        self.assertLessEqual(outcome["max_active_workers"], 3)
        self.assertEqual(outcome["reserved_units"], 0)

    def test_inventory_2000_rows_is_classified_but_only_approved_sample_is_executed(self) -> None:
        fleet = generate_inventory(2_000)
        flow = pipeline(policy=FleetPolicy(max_scans_per_run=10))
        approved = tuple(record for record in fleet if record.risk_tier == "standard")[:10]
        for record in approved:
            approve_scope(flow, record)
        outcome = flow.run(fleet)
        self.assertEqual(outcome["inventory_count"], 2_000)
        self.assertEqual((outcome["admitted"], outcome["scanner_invocations"]), (10, 10))


class PipelineFailureTests(unittest.TestCase):
    def outcome(self, behaviours: tuple[str, ...]) -> tuple[dict[str, object], SyntheticScanner]:
        record = repository()
        scanner = SyntheticScanner(behaviour={record.repo_id: behaviours})
        flow = pipeline(scanner=scanner)
        approve_scope(flow, record)
        return flow.run((record,))["records"][record.repo_id], scanner

    def test_transient_failure_is_retried_once_then_succeeds(self) -> None:
        result, scanner = self.outcome(("transient", "success"))
        self.assertEqual(result["status"], "review_packet_ready")
        self.assertEqual((result["attempts"], sum(scanner.invocations.values())), (2, 2))

    def test_timeout_retries_with_hard_attempt_limit_then_abstains(self) -> None:
        result, scanner = self.outcome(("timeout", "timeout"))
        self.assertEqual(result["status"], "failed_safe_abstention")
        self.assertEqual((result["attempts"], sum(scanner.invocations.values())), (2, 2))

    def test_permanent_access_failure_is_not_retried(self) -> None:
        result, scanner = self.outcome(("permanent", "success"))
        self.assertEqual(result["status"], "failed_safe_abstention")
        self.assertEqual(sum(scanner.invocations.values()), 1)

    def test_partial_and_unknown_coverage_escalate_without_retry(self) -> None:
        for behaviour in ("partial", "unknown"):
            with self.subTest(behaviour=behaviour):
                result, scanner = self.outcome((behaviour, "success"))
                self.assertEqual(result["status"], "awaiting_coverage_review")
                self.assertEqual(sum(scanner.invocations.values()), 1)

    def test_returned_partial_coverage_is_never_accepted_as_complete(self) -> None:
        class PartialScanner(SyntheticScanner):
            def scan(self, record, assignment):
                result = super().scan(record, assignment)
                result["coverage.json"]["completeness"] = "partial"
                return result

        flow = pipeline(scanner=PartialScanner())
        record = repository()
        approve_scope(flow, record)
        result = flow.run((record,))["records"][record.repo_id]
        self.assertEqual(result["status"], "awaiting_coverage_review")
        self.assertEqual(result["attempts"], 1)

    def test_unknown_fixture_fails_closed_without_external_fallback(self) -> None:
        flow = pipeline()
        record = repository(fixture="missing-fixture")
        approve_scope(flow, record)
        outcome = flow.run((record,))
        self.assertEqual(outcome["records"][record.repo_id]["status"], "failed_safe_abstention")
        self.assertEqual(outcome["scanner_invocations"], 1)

    def test_repository_prompt_injection_stops_before_any_reviewable_outcome(self) -> None:
        flow = pipeline()
        record = repository(fixture="adversarial_service")
        approve_scope(flow, record)
        outcome = flow.run((record,))["records"][record.repo_id]
        self.assertEqual(outcome["status"], "failed_safe_abstention")
        self.assertIn("untrusted repository", outcome["reason"])
        self.assertFalse(outcome["external_pr_created"])


class HumanReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.record = repository(fixture="vulnerable_service")
        self.flow = pipeline()
        approve_scope(self.flow, self.record)

    def _first_finding(self, flow=None, record=None) -> str:
        current = flow or self.flow
        target = record or self.record
        return current.states[target.repo_id].current_findings[0]["findingId"]

    def _approve_disposition(self, flow, record, finding) -> None:
        flow.approvals.approve("finding_disposition", record.repo_id,
                               flow.finding_target(record, finding), "security-owner")

    def _approve_patch(self, flow, record, finding) -> None:
        flow.approvals.approve("patch", record.repo_id, flow.finding_target(record, finding), "patch-owner")

    def test_consequential_finding_waits_for_named_security_disposition(self) -> None:
        first = self.flow.run((self.record,))["records"][self.record.repo_id]
        self.assertEqual(first["status"], "awaiting_finding_disposition")
        self.assertEqual((first["current_findings"], first["fresh_findings"]), (1, 1))
        self._approve_disposition(self.flow, self.record, self._first_finding())
        second = self.flow.run((self.record,))["records"][self.record.repo_id]
        self.assertEqual(second["status"], "review_packet_ready")
        self.assertEqual(second["named_reviewers"]["security"], "security-owner")
        self.assertEqual(sum(self.flow.scanner.invocations.values()), 1)

    def test_default_policy_never_creates_draft_pull_request(self) -> None:
        self.flow.run((self.record,))
        self._approve_disposition(self.flow, self.record, self._first_finding())
        result = self.flow.run((self.record,))["records"][self.record.repo_id]
        self.assertEqual(result["route"], "review_packet")
        self.assertFalse(result["external_pr_created"])

    def test_draft_route_requires_provider_policy_and_exact_human_patch_approval(self) -> None:
        flow = pipeline(policy=FleetPolicy(allow_draft_pr=True, provider_write_authorised=True))
        approve_scope(flow, self.record)
        first = flow.run((self.record,))["records"][self.record.repo_id]
        self.assertEqual(first["status"], "awaiting_finding_disposition")
        finding = self._first_finding(flow)
        self._approve_disposition(flow, self.record, finding)
        pending = flow.run((self.record,))["records"][self.record.repo_id]
        self.assertEqual(pending["status"], "awaiting_patch_approval")
        self._approve_patch(flow, self.record, finding)
        ready = flow.run((self.record,))["records"][self.record.repo_id]
        self.assertEqual((ready["route"], ready["status"]), ("draft_pr_artifact_only", "awaiting_human_merge"))
        self.assertFalse(ready["external_pr_created"])
        self.assertFalse(ready["merge_performed"])
        self.assertFalse(ready["deployment_performed"])

    def test_policy_without_provider_authorisation_remains_review_packet_only(self) -> None:
        flow = pipeline(policy=FleetPolicy(allow_draft_pr=True, provider_write_authorised=False))
        approve_scope(flow, self.record)
        flow.run((self.record,))
        self._approve_disposition(flow, self.record, self._first_finding(flow))
        result = flow.run((self.record,))["records"][self.record.repo_id]
        self.assertEqual((result["route"], result["status"]), ("review_packet", "review_packet_ready"))

    def test_duplicate_persistent_finding_never_bypasses_new_revision_disposition(self) -> None:
        self.flow.run((self.record,))
        finding = self._first_finding()
        self._approve_disposition(self.flow, self.record, finding)
        self.flow.run((self.record,))
        revised = replace(self.record, commit_sha=hashlib.sha1(b"next-synthetic-revision").hexdigest())
        approve_scope(self.flow, revised)
        result = self.flow.run((revised,))["records"][revised.repo_id]
        self.assertEqual((result["current_findings"], result["fresh_findings"], result["duplicates"]), (1, 0, 1))
        self.assertEqual(result["status"], "awaiting_finding_disposition")
        self.assertNotEqual(self.flow.finding_target(self.record, finding), self.flow.finding_target(revised, finding))

    def test_stale_patch_approval_is_not_reused_after_context_or_revision_change(self) -> None:
        flow = pipeline(policy=FleetPolicy(allow_draft_pr=True, provider_write_authorised=True))
        approve_scope(flow, self.record)
        flow.run((self.record,))
        finding = self._first_finding(flow)
        self._approve_disposition(flow, self.record, finding)
        self._approve_patch(flow, self.record, finding)
        flow.run((self.record,))
        revised = replace(self.record, commit_sha="c" * 40)
        approve_scope(flow, revised)
        flow.run((revised,))
        self._approve_disposition(flow, revised, finding)
        result = flow.run((revised,))["records"][revised.repo_id]
        self.assertEqual(result["status"], "awaiting_patch_approval")

    def test_exception_requires_trusted_owner_exact_evidence_and_future_expiry(self) -> None:
        now = [100]
        flow = pipeline(approvals=ledger(now=now), clock=lambda: now[0])
        approve_scope(flow, self.record)
        flow.run((self.record,))
        finding = self._first_finding(flow)
        target = flow.finding_target(self.record, finding)
        with self.assertRaises(PipelineError):
            flow.approvals.approve_exception(self.record.repo_id, target, "synthetic-scanner", expires_at=200)
        flow.approvals.approve_exception(self.record.repo_id, target, "exception-owner", expires_at=200)
        accepted = flow.run((self.record,))["records"][self.record.repo_id]
        self.assertEqual((accepted["status"], accepted["named_reviewers"]["exception"]),
                         ("review_packet_ready", "exception-owner"))
        now[0] = 201
        expired = flow.run((self.record,))["records"][self.record.repo_id]
        self.assertEqual(expired["status"], "awaiting_finding_disposition")

    def test_multiple_findings_are_deduplicated_but_each_current_identity_requires_review(self) -> None:
        record = repository(fixture="multiple_findings")
        flow = pipeline()
        approve_scope(flow, record)
        first = flow.run((record,))["records"][record.repo_id]
        self.assertEqual((first["current_findings"], first["fresh_findings"], first["duplicates"]), (4, 3, 1))
        for finding in flow.states[record.repo_id].current_findings:
            self._approve_disposition(flow, record, finding["findingId"])
        ready = flow.run((record,))["records"][record.repo_id]
        self.assertEqual(ready["status"], "review_packet_ready")

    def test_every_receipt_truthfully_denies_external_write_merge_and_deploy(self) -> None:
        result = self.flow.run((self.record,))
        receipt = result["records"][self.record.repo_id]
        self.assertFalse(result["product_execution"])
        self.assertEqual(result["external_writes"], 0)
        self.assertFalse(receipt["external_pr_created"])
        self.assertFalse(receipt["merge_performed"])
        self.assertFalse(receipt["deployment_performed"])


if __name__ == "__main__":
    unittest.main()
