"""New independent adversarial fleet, admission and human-authority stress cases."""
from __future__ import annotations

from dataclasses import replace
import time
import unittest

from stress_helpers import ROOT
from support import approve_model, approve_scope, ledger, pipeline, repository
from fleet_security import (
    FleetPolicy,
    InventoryError,
    PipelineError,
    ScanFailure,
    SyntheticScanner,
    classify,
    generate_inventory,
    load_inventory,
)
from fleet_security.evidence import EvidenceError, FindingRegistry


class FleetInventoryAndAdmissionStress(unittest.TestCase):
    def test_two_thousand_rows_classify_ten_archetypes_and_57_high_risk(self) -> None:
        fleet = generate_inventory(2_000)
        self.assertEqual(len(fleet), 2_000)
        self.assertEqual(len({classify(row).archetype for row in fleet}), 10)
        self.assertEqual(sum(row.risk_tier == "high" for row in fleet), 57)
        self.assertTrue(all(row.repo_id.startswith("synthetic/") for row in fleet))

    def test_two_thousand_metadata_rows_dispatch_only_six_explicit_fixtures(self) -> None:
        original = generate_inventory(2_000)
        selected = {row.repo_id for row in original if row.risk_tier == "standard"}
        selected = set(sorted(selected)[:6])
        fleet = tuple(replace(row, fixture="safe_service") if row.repo_id in selected else row for row in original)
        flow = pipeline(policy=FleetPolicy(max_scans_per_run=6))
        for row in fleet:
            if row.repo_id in selected:
                approve_scope(flow, row)
        result = flow.run(fleet)
        self.assertEqual((result["inventory_count"], result["admitted"], result["scanner_invocations"]), (2_000, 6, 6))
        self.assertEqual(sum(row["status"] == "awaiting_scope_approval" for row in result["records"].values()), 1_994)
        self.assertEqual(set(flow.scanner.invocations), selected)

    def test_twenty_identical_inventory_events_are_coalesced_to_one_scan(self) -> None:
        row = repository(101)
        flow = pipeline()
        approve_scope(flow, row)
        result = flow.run((row,) * 20)
        self.assertEqual((result["inventory_count"], result["scanner_invocations"]), (1, 1))

    def test_contradictory_duplicate_revision_fails_before_dispatch(self) -> None:
        row = repository(102)
        changed = replace(row, commit_sha="b" * 40)
        flow = pipeline()
        with self.assertRaises(InventoryError):
            flow.run((row, changed))
        self.assertEqual(sum(flow.scanner.invocations.values()), 0)

    def test_batch_rate_limit_defers_eleven_of_fourteen_approved_rows(self) -> None:
        flow = pipeline(policy=FleetPolicy(max_scans_per_run=3))
        fleet = tuple(repository(index) for index in range(110, 124))
        for row in fleet:
            approve_scope(flow, row)
        result = flow.run(fleet)
        self.assertEqual((result["admitted"], result["scanner_invocations"]), (3, 3))
        self.assertEqual(sum(row["status"] == "deferred_rate_limit" for row in result["records"].values()), 11)

    def test_campaign_backpressure_accounts_for_every_retry_before_admission(self) -> None:
        policy = FleetPolicy(max_campaign_units=28, max_attempts=2, estimated_scan_units=5, max_inflight_overshoot_units=2)
        flow = pipeline(policy=policy)
        fleet = tuple(repository(index) for index in range(130, 136))
        for row in fleet:
            approve_scope(flow, row)
        outcome = flow.run(fleet)
        self.assertEqual(outcome["admitted"], 2)
        self.assertEqual(sum(row["status"] == "deferred_budget" for row in outcome["records"].values()), 4)
        self.assertLessEqual(outcome["max_observed_reserved_units"], policy.max_campaign_units)
        self.assertEqual(outcome["reserved_units"], 0)

    def test_capacity_exhaustion_refuses_before_any_scanner_invocation(self) -> None:
        flow = pipeline(policy=FleetPolicy(max_campaign_units=13, max_attempts=2, estimated_scan_units=5, max_inflight_overshoot_units=2))
        row = repository(140)
        approve_scope(flow, row)
        result = flow.run((row,))
        self.assertEqual(result["records"][row.repo_id]["status"], "deferred_budget")
        self.assertEqual((result["scanner_invocations"], result["consumed_units"]), (0, 0))

    def test_slow_scanners_never_exceed_two_worker_cap(self) -> None:
        class SlowScanner(SyntheticScanner):
            def _offline_matches(self, fixture):
                time.sleep(0.02)
                return super()._offline_matches(fixture)

        flow = pipeline(policy=FleetPolicy(max_concurrent=2), scanner=SlowScanner())
        fleet = tuple(repository(index) for index in range(150, 158))
        for row in fleet:
            approve_scope(flow, row)
        result = flow.run(fleet)
        self.assertGreaterEqual(result["max_active_workers"], 2)
        self.assertLessEqual(result["max_active_workers"], 2)
        self.assertEqual(result["reserved_units"], 0)

    def test_twenty_repeated_reconciliations_never_repeat_one_scan(self) -> None:
        flow = pipeline()
        row = repository(160)
        approve_scope(flow, row)
        for _ in range(20):
            outcome = flow.run((row,))
            self.assertEqual(outcome["records"][row.repo_id]["status"], "review_packet_ready")
        self.assertEqual(flow.scanner.invocations[row.repo_id], 1)

    def test_only_one_reapproved_security_revision_is_rescanned(self) -> None:
        flow = pipeline()
        fleet = tuple(repository(index) for index in range(170, 176))
        for row in fleet:
            approve_scope(flow, row)
        flow.run(fleet)
        changed = replace(fleet[2], commit_sha="c" * 40, changed_paths=("src/auth.py",))
        approve_scope(flow, changed)
        updated = tuple(changed if row.repo_id == changed.repo_id else row for row in fleet)
        outcome = flow.run(updated)
        self.assertEqual(outcome["scanner_invocations"], 7)
        self.assertEqual(flow.scanner.invocations[changed.repo_id], 2)
        self.assertEqual(sum(value == 1 for key, value in flow.scanner.invocations.items() if key != changed.repo_id), 5)

    def test_reapproved_docs_only_revision_never_triggers_rescan(self) -> None:
        flow = pipeline()
        row = repository(180)
        approve_scope(flow, row)
        flow.run((row,))
        changed = replace(row, commit_sha="d" * 40, changed_paths=("docs/private-runbook.md",))
        approve_scope(flow, changed)
        outcome = flow.run((changed,))
        self.assertEqual(outcome["records"][row.repo_id]["status"], "skipped_unchanged_security_scope")
        self.assertEqual(flow.scanner.invocations[row.repo_id], 1)

    def test_boundary_change_with_docs_only_revision_requires_new_scan(self) -> None:
        flow = pipeline()
        row = repository(181)
        approve_scope(flow, row)
        flow.run((row,))
        changed = replace(row, commit_sha="e" * 40, data_class="confidential", changed_paths=("docs/notes.md",))
        approve_scope(flow, changed)
        flow.run((changed,))
        self.assertEqual(flow.scanner.invocations[row.repo_id], 2)


class ApprovalAndFailureStress(unittest.TestCase):
    def test_stale_owner_invalidates_exact_repository_scope(self) -> None:
        row = repository(201)
        flow = pipeline()
        approve_scope(flow, row)
        changed = replace(row, owner="replacement-owner")
        outcome = flow.run((changed,))
        self.assertEqual(outcome["records"][row.repo_id]["status"], "awaiting_scope_approval")
        self.assertEqual(outcome["scanner_invocations"], 0)

    def test_stale_revision_invalidates_exact_repository_scope(self) -> None:
        row = repository(202)
        flow = pipeline()
        approve_scope(flow, row)
        changed = replace(row, commit_sha="f" * 40)
        self.assertEqual(flow.run((changed,))["records"][row.repo_id]["status"], "awaiting_scope_approval")
        self.assertEqual(sum(flow.scanner.invocations.values()), 0)

    def test_high_risk_without_named_threat_owner_holds(self) -> None:
        row = repository(203, criticality="critical")
        flow = pipeline()
        approve_scope(flow, row)
        result = flow.run((row,))
        self.assertEqual(result["records"][row.repo_id]["status"], "awaiting_threat_model_approval")
        self.assertEqual(result["scanner_invocations"], 0)

    def test_changed_threat_context_invalidates_prior_human_acceptance(self) -> None:
        row = repository(204, criticality="critical")
        flow = pipeline()
        approve_scope(flow, row)
        approve_model(flow, row)
        changed = replace(row, data_class="restricted")
        outcome = flow.run((changed,))
        self.assertEqual(outcome["records"][row.repo_id]["status"], "awaiting_threat_model_approval")
        self.assertEqual(outcome["scanner_invocations"], 0)

    def test_forged_repository_actor_cannot_grant_any_human_gate(self) -> None:
        flow = pipeline()
        row = repository(205)
        for gate in ("scope", "threat_model", "finding_disposition", "patch", "merge", "deploy", "policy_change"):
            with self.subTest(gate=gate), self.assertRaises(PipelineError):
                flow.approvals.approve(gate, row.repo_id, "forged-target", "repository-content")

    def test_missing_human_owner_rejected_before_inventory_dispatch(self) -> None:
        with self.assertRaises(InventoryError):
            replace(repository(206), owner="")

    def test_expired_approval_blocks_before_scanner(self) -> None:
        now = [10_000]
        approvals = ledger(now=now)
        flow = pipeline(approvals=approvals, clock=lambda: now[0])
        row = repository(207)
        approvals.approve("scope", row.repo_id, flow.scope_target(row), "scope-owner", expires_at=10_001)
        now[0] = 10_001
        outcome = flow.run((row,))
        self.assertEqual(outcome["records"][row.repo_id]["status"], "awaiting_scope_approval")
        self.assertEqual(outcome["scanner_invocations"], 0)

    def test_named_owner_cancellation_prevents_all_work(self) -> None:
        flow = pipeline()
        row = repository(208)
        approve_scope(flow, row)
        flow.cancel(row.repo_id, actor="scope-owner")
        outcome = flow.run((row,))
        self.assertEqual(outcome["records"][row.repo_id]["status"], "cancelled")
        self.assertEqual(outcome["scanner_invocations"], 0)

    def test_untrusted_cancellation_never_suppresses_human_owned_review(self) -> None:
        flow = pipeline()
        row = repository(209)
        approve_scope(flow, row)
        with self.assertRaises(PipelineError):
            flow.cancel(row.repo_id, actor="synthetic-scanner")
        self.assertEqual(flow.run((row,))["records"][row.repo_id]["status"], "review_packet_ready")

    def test_transient_interruption_recovers_once_within_retry_ceiling(self) -> None:
        row = repository(210)
        scanner = SyntheticScanner(behaviour={row.repo_id: ("transient", "success")})
        flow = pipeline(scanner=scanner)
        approve_scope(flow, row)
        result = flow.run((row,))["records"][row.repo_id]
        self.assertEqual((result["status"], result["attempts"], scanner.invocations[row.repo_id]), ("review_packet_ready", 2, 2))

    def test_timeout_exhaustion_abstains_after_exact_retry_ceiling(self) -> None:
        row = repository(211)
        scanner = SyntheticScanner(behaviour={row.repo_id: ("timeout", "timeout", "success")})
        flow = pipeline(scanner=scanner)
        approve_scope(flow, row)
        result = flow.run((row,))["records"][row.repo_id]
        self.assertEqual((result["status"], result["attempts"]), ("failed_safe_abstention", 2))
        self.assertEqual(scanner.invocations[row.repo_id], 2)

    def test_permanent_provider_failure_never_retries(self) -> None:
        row = repository(212)
        scanner = SyntheticScanner(behaviour={row.repo_id: ("permanent", "success")})
        flow = pipeline(scanner=scanner)
        approve_scope(flow, row)
        result = flow.run((row,))["records"][row.repo_id]
        self.assertEqual(result["status"], "failed_safe_abstention")
        self.assertEqual(scanner.invocations[row.repo_id], 1)

    def test_unknown_coverage_is_held_for_human_without_retry(self) -> None:
        row = repository(213)
        scanner = SyntheticScanner(behaviour={row.repo_id: ("unknown", "success")})
        flow = pipeline(scanner=scanner)
        approve_scope(flow, row)
        result = flow.run((row,))["records"][row.repo_id]
        self.assertEqual(result["status"], "awaiting_coverage_review")
        self.assertEqual(scanner.invocations[row.repo_id], 1)

    def test_scan_cancellation_failure_never_retries_or_publishes(self) -> None:
        row = repository(214)
        scanner = SyntheticScanner(behaviour={row.repo_id: ("cancelled", "success")})
        flow = pipeline(scanner=scanner)
        approve_scope(flow, row)
        result = flow.run((row,))["records"][row.repo_id]
        self.assertEqual((result["status"], scanner.invocations[row.repo_id]), ("failed_safe_abstention", 1))
        self.assertFalse(result["external_pr_created"])

    def test_unexpected_scanner_interruption_is_redacted_and_releases_capacity(self) -> None:
        marker = "synthetic-private-worker-marker"

        class InterruptedScanner(SyntheticScanner):
            def scan(self, record, assignment):
                raise OSError("synthetic interrupted worker: " + marker)

        row = repository(215)
        flow = pipeline(scanner=InterruptedScanner())
        approve_scope(flow, row)
        result = flow.run((row,))
        state = result["records"][row.repo_id]
        self.assertEqual(state["status"], "failed_safe_abstention")
        self.assertEqual(state["reason"], "unexpected synthetic worker failure; stopped safely")
        self.assertNotIn(marker, str(result))
        self.assertNotIn(marker, str(flow.audit.events))
        self.assertEqual(state["named_reviewers"]["scope"], "scope-owner")
        self.assertEqual(flow.reserved_units, 0)
        self.assertTrue(flow.audit.verify())

    def test_unexpected_worker_exception_isolated_from_three_healthy_peers(self) -> None:
        broken = repository(222)
        healthy = tuple(repository(index) for index in range(223, 226))
        marker = "synthetic-private-sibling-marker"

        class PartiallyBrokenScanner(SyntheticScanner):
            def scan(self, row, assignment):
                if row.repo_id == broken.repo_id:
                    raise OSError("synthetic interruption: " + marker)
                return super().scan(row, assignment)

        flow = pipeline(policy=FleetPolicy(max_concurrent=4), scanner=PartiallyBrokenScanner())
        for row in (broken, *healthy):
            approve_scope(flow, row)
        result = flow.run((broken, *healthy))
        self.assertEqual(result["records"][broken.repo_id]["status"], "failed_safe_abstention")
        self.assertTrue(all(result["records"][row.repo_id]["status"] == "review_packet_ready" for row in healthy))
        self.assertEqual(flow.reserved_units, 0)
        self.assertEqual(result["external_writes"], 0)
        self.assertNotIn(marker, str(result))
        self.assertNotIn(marker, str(flow.audit.events))
        self.assertTrue(flow.audit.verify())

    def test_unexpected_value_and_runtime_errors_also_fail_safely(self) -> None:
        for error_type in (ValueError, RuntimeError):
            with self.subTest(error_type=error_type.__name__):
                class UnexpectedScanner(SyntheticScanner):
                    def scan(self, row, assignment):
                        raise error_type("synthetic-sensitive-detail")

                row = repository(227)
                flow = pipeline(scanner=UnexpectedScanner())
                approve_scope(flow, row)
                outcome = flow.run((row,))
                self.assertEqual(outcome["records"][row.repo_id]["status"], "failed_safe_abstention")
                self.assertNotIn("synthetic-sensitive-detail", str(outcome))
                self.assertEqual(flow.reserved_units, 0)

    def test_duplicate_finding_registry_accepts_exactly_one_of_fifty(self) -> None:
        flow = pipeline()
        row = repository(216, fixture="vulnerable_service")
        approve_scope(flow, row)
        outcome = flow.run((row,))
        finding = flow.states[row.repo_id].current_findings[0]
        registry = FindingRegistry()
        admitted, duplicates = registry.admit([finding] * 50)
        again, repeated = registry.admit([finding] * 50)
        self.assertEqual((len(admitted), duplicates, len(again), repeated, registry.count), (1, 49, 0, 50, 1))
        self.assertEqual(outcome["records"][row.repo_id]["status"], "awaiting_finding_disposition")

    def test_cached_evidence_tampering_is_refused_before_rescan(self) -> None:
        row = repository(217, fixture="vulnerable_service")
        flow = pipeline()
        approve_scope(flow, row)
        flow.run((row,))
        flow.states[row.repo_id].evidence["findings.json"]["findings"][0]["title"] = "forged-finding"
        with self.assertRaises(EvidenceError):
            flow.run((row,))
        self.assertEqual(flow.scanner.invocations[row.repo_id], 1)

    def test_prompt_injection_never_creates_review_patch_or_provider_write(self) -> None:
        row = repository(218, fixture="adversarial_service")
        flow = pipeline()
        approve_scope(flow, row)
        outcome = flow.run((row,))
        result = outcome["records"][row.repo_id]
        self.assertEqual(result["status"], "failed_safe_abstention")
        self.assertIn("untrusted", result["reason"])
        self.assertFalse(result["external_pr_created"])
        self.assertFalse(result["merge_performed"])
        self.assertFalse(result["deployment_performed"])
        self.assertEqual(outcome["external_writes"], 0)

    def test_unknown_fixture_never_substitutes_a_clean_service(self) -> None:
        row = repository(219, fixture="not_an_approved_fixture")
        flow = pipeline()
        approve_scope(flow, row)
        outcome = flow.run((row,))["records"][row.repo_id]
        self.assertEqual(outcome["status"], "failed_safe_abstention")
        self.assertIn("no fallback", outcome["reason"])

    def test_real_looking_repository_identity_is_refused_by_synthetic_scanner(self) -> None:
        row = replace(repository(220), repo_id="private-owner/private-repository")
        flow = pipeline()
        approve_scope(flow, row)
        outcome = flow.run((row,))["records"][row.repo_id]
        self.assertEqual(outcome["status"], "failed_safe_abstention")
        self.assertIn("non-synthetic", outcome["reason"])

    def test_unapproved_provider_write_policy_fails_closed(self) -> None:
        with self.assertRaises(PipelineError):
            FleetPolicy(provider_write_authorised=True)

    def test_human_merge_and_deployment_gates_cannot_be_disabled(self) -> None:
        for change in ({"require_human_merge": False}, {"require_human_deploy": False}, {"allow_untrusted_network": True}):
            with self.subTest(change=change), self.assertRaises(PipelineError):
                FleetPolicy(**change)

    def test_draft_route_requires_named_finding_and_patch_approvals_but_never_provider_write(self) -> None:
        row = repository(221, fixture="vulnerable_service")
        flow = pipeline(policy=FleetPolicy(allow_draft_pr=True, provider_write_authorised=True))
        approve_scope(flow, row)
        outcome = flow.run((row,))["records"][row.repo_id]
        self.assertEqual(outcome["status"], "awaiting_finding_disposition")
        finding_id = flow.states[row.repo_id].current_findings[0]["findingId"]
        target = flow.finding_target(row, finding_id)
        flow.approvals.approve("finding_disposition", row.repo_id, target, "security-owner")
        held = flow.run((row,))["records"][row.repo_id]
        self.assertEqual(held["status"], "awaiting_patch_approval")
        flow.approvals.approve("patch", row.repo_id, target, "patch-owner")
        gated = flow.run((row,))["records"][row.repo_id]
        self.assertEqual(gated["status"], "awaiting_human_merge")
        self.assertFalse(gated["external_pr_created"])
        self.assertFalse(gated["merge_performed"])
        self.assertFalse(gated["deployment_performed"])


if __name__ == "__main__":
    unittest.main()
