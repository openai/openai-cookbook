"""Deterministic accounting and safe failure-diagnostic checks; no Docker calls."""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
from fleet_security.pipeline import FleetPolicy
from fleet_security.recipe import RecipeConfiguration, RecurringSecurityRecipe
from fleet_security.reproduction import (
    ReproductionFailure, assert_attempt_accounting, assert_cycle_accounting,
    redact_reproduction_failure, safe_cycle_summary,
)
from fleet_security.scanner import SyntheticScanner


def script(name):
    specification = importlib.util.spec_from_file_location(
        "reproduction_test_" + name, ROOT / "scripts" / (name + ".py"),
    )
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


RUNNER = script("execute_notebook")
VERIFIER = script("verify_cookbook_example")
POLICY = FleetPolicy()
EXPECTED = {
    "synthetic/payments-api": "awaiting_finding_disposition",
    "synthetic/catalog-service": "review_packet_ready",
    "synthetic/edge-auth": "awaiting_finding_disposition",
    "synthetic/adversarial-docs": "failed_safe_abstention",
    "synthetic/unapproved-service": "awaiting_scope_approval",
    "synthetic/restricted-worker": "awaiting_threat_model_approval",
}
ATTEMPTED = (
    "synthetic/payments-api", "synthetic/catalog-service",
    "synthetic/edge-auth", "synthetic/adversarial-docs",
)
CANARY = "NONSECRET_DIAGNOSTIC_CANARY"


def nominal(*, restart=False, docker=False):
    ids = () if restart else ATTEMPTED
    receipt = {
        "records": {name: {"status": status, "attempts": 1} for name, status in EXPECTED.items()},
        "decision_states": dict(Counter(EXPECTED.values())),
        "admitted_jobs": len(ids), "attempted_repositories": len(ids),
        "scanner_invocations": len(ids), "retry_attempts": 0,
        "scanner_attempts_by_repository": {name: 1 for name in ids},
        "transient_retry_events": [], "restricted_docker_receipts": 3 if docker and ids else 0,
        "max_active_workers": min(len(ids), POLICY.max_concurrent),
        "max_concurrent_policy": POLICY.max_concurrent,
        "consumed_synthetic_units": len(ids) * POLICY.estimated_scan_units,
        "max_reserved_synthetic_units": len(ids) * POLICY.worst_case_reservation,
        "campaign_budget_synthetic_units": POLICY.max_campaign_units,
        "paid_api_calls": 0, "external_writes": 0, "live_product_execution": False,
        "automatic_pr_merge_or_deploy": False, "audit_valid": True, "durable_audit_valid": True,
        "execution_mode": "synthetic_restricted_docker" if docker else "synthetic_offline_not_sandboxed",
    }
    receipt["records"]["synthetic/adversarial-docs"]["reason"] = (
        "restricted synthetic scan abstained on untrusted repository content" if docker
        else "untrusted repository instruction requires safe abstention"
    )
    return receipt


def add_retry(receipt, name="synthetic/payments-api", reason="restricted_worker_timeout"):
    attempt = receipt["scanner_attempts_by_repository"][name]
    receipt["scanner_attempts_by_repository"][name] += 1
    receipt["scanner_invocations"] += 1
    receipt["retry_attempts"] += 1
    receipt["consumed_synthetic_units"] += POLICY.estimated_scan_units
    receipt["transient_retry_events"].append({
        "repository_id": name, "failed_attempt": attempt, "reason_code": reason,
    })


class AccountingContractTests(unittest.TestCase):
    def check(self, receipt, *, restart=False, docker=False, policy=POLICY):
        return assert_cycle_accounting(
            receipt, expected_attempted_repositories=() if restart else ATTEMPTED,
            expected_statuses=EXPECTED, policy=policy,
            expected_isolation_receipts=3 if docker and not restart else 0,
            context="restart_cycle" if restart else "first_cycle",
        )

    def rejected(self, receipt, check=None, **options):
        with self.assertRaises(ReproductionFailure) as caught:
            self.check(receipt, **options)
        if check is not None:
            self.assertEqual(caught.exception.diagnostic["check"], check)
        self.assertEqual(caught.exception.diagnostic["status"], "FAIL")
        return caught.exception

    def test_nominal_offline_and_docker_receipt_contracts_pass(self):
        for docker in (False, True):
            with self.subTest(docker=docker):
                result = self.check(nominal(docker=docker), docker=docker)
                self.assertEqual((result["scanner_invocations"], result["retry_attempts"]), (4, 0))

    def test_explicit_bounded_retry_keeps_exact_jobs_and_isolation_receipts(self):
        receipt = nominal(docker=True)
        add_retry(receipt)
        result = self.check(receipt, docker=True)
        self.assertEqual((result["attempted_repositories"], result["scanner_invocations"],
                          result["retry_attempts"], result["restricted_docker_receipts"]), (4, 5, 1, 3))

    def test_extra_raw_invocation_without_host_accounting_fails(self):
        receipt = nominal()
        receipt["scanner_invocations"] += 1
        self.rejected(receipt, "raw_attempt_accounting")

    def test_extra_accounted_attempt_without_retry_evidence_fails(self):
        receipt = nominal()
        add_retry(receipt)
        receipt["transient_retry_events"] = []
        self.rejected(receipt, "retry_event_count")

    def test_retry_beyond_per_repository_policy_ceiling_fails(self):
        receipt = nominal()
        add_retry(receipt)
        add_retry(receipt)
        self.rejected(receipt, "per_repository_attempt_ceiling")

    def test_repeated_retry_event_cannot_cover_another_attempt(self):
        receipt = nominal()
        add_retry(receipt)
        add_retry(receipt, "synthetic/catalog-service")
        receipt["transient_retry_events"][1] = deepcopy(receipt["transient_retry_events"][0])
        self.rejected(receipt, "retry_event_sequence")

    def test_retry_event_must_identify_the_exact_failed_attempt(self):
        receipt = nominal()
        add_retry(receipt)
        receipt["transient_retry_events"][0]["failed_attempt"] = 2
        self.rejected(receipt, "retry_event_sequence")

    def test_permanent_or_arbitrary_retry_reason_cannot_authorise_a_retry(self):
        receipt = nominal()
        add_retry(receipt, reason=CANARY)
        error = self.rejected(receipt, "retry_event_fields")
        self.assertNotIn(CANARY, str(error))

    def test_retry_event_cannot_hide_raw_error_text_in_an_extra_field(self):
        receipt = nominal()
        add_retry(receipt)
        receipt["transient_retry_events"][0]["error"] = CANARY
        error = self.rejected(receipt, "retry_event_shape")
        self.assertNotIn(CANARY, str(error))

    def test_same_attempt_count_for_a_different_repository_fails(self):
        receipt = nominal()
        receipt["scanner_attempts_by_repository"].pop("synthetic/catalog-service")
        receipt["scanner_attempts_by_repository"]["synthetic/unapproved-service"] = 1
        self.rejected(receipt, "exact_attempted_repository_set")

    def test_unexpected_terminal_failure_cannot_pass_expected_final_decisions(self):
        receipt = nominal()
        receipt["records"]["synthetic/catalog-service"]["status"] = "failed_safe_abstention"
        self.rejected(receipt, "final_repository_decisions")

    def test_hostile_timeout_exhaustion_is_not_an_expected_content_refusal(self):
        receipt = nominal(docker=True)
        add_retry(receipt, "synthetic/adversarial-docs")
        receipt["records"]["synthetic/adversarial-docs"]["reason"] = "restricted synthetic scan failed or timed out"
        self.rejected(receipt, "hostile_fixture_refusal", docker=True)

    def test_transient_then_actual_hostile_refusal_may_pass_with_accounted_retry(self):
        receipt = nominal(docker=True)
        add_retry(receipt, "synthetic/adversarial-docs")
        self.assertEqual(self.check(receipt, docker=True)["retry_attempts"], 1)

    def test_cached_hostile_refusal_is_checked_after_restart_too(self):
        receipt = nominal(restart=True)
        receipt["records"]["synthetic/adversarial-docs"]["reason"] = CANARY
        error = self.rejected(receipt, "hostile_fixture_refusal", restart=True)
        self.assertNotIn(CANARY, str(error))

    def test_missing_isolation_receipt_fails_even_when_attempts_match(self):
        receipt = nominal(docker=True)
        receipt["restricted_docker_receipts"] = 2
        self.rejected(receipt, "successful_isolation_receipts", docker=True)

    def test_offline_mode_cannot_claim_required_docker_receipts(self):
        receipt = nominal()
        receipt["restricted_docker_receipts"] = 3
        self.rejected(receipt, "synthetic_execution_boundary", docker=True)

    def test_wrong_aggregate_decisions_fail_even_with_correct_records(self):
        receipt = nominal()
        receipt["decision_states"]["review_packet_ready"] = 2
        self.rejected(receipt, "decision_state_counts")

    def test_restart_is_zero_new_work_despite_persisted_attempt_counts(self):
        receipt = nominal(restart=True)
        for record in receipt["records"].values():
            record["attempts"] = 2
        self.assertEqual(self.check(receipt, restart=True)["scanner_invocations"], 0)

    def test_restart_may_not_hide_a_duplicate_scan(self):
        receipt = nominal(restart=True)
        receipt["scanner_invocations"] = 1
        self.rejected(receipt, "raw_attempt_accounting", restart=True)

    def test_restart_may_not_reserve_new_campaign_work(self):
        receipt = nominal(restart=True)
        receipt["max_reserved_synthetic_units"] = 1
        self.rejected(receipt, "zero_restart_reservations", restart=True)

    def test_campaign_charge_must_account_for_every_actual_retry(self):
        receipt = nominal()
        add_retry(receipt)
        receipt["consumed_synthetic_units"] -= POLICY.estimated_scan_units
        self.rejected(receipt, "campaign_cost_accounting")

    def test_campaign_limit_cannot_be_exceeded(self):
        receipt = nominal()
        policy = FleetPolicy(max_campaign_units=19)
        receipt["campaign_budget_synthetic_units"] = policy.max_campaign_units
        receipt["max_reserved_synthetic_units"] = 0
        self.rejected(receipt, "campaign_cost_accounting", policy=policy)

    def test_excess_worker_concurrency_fails(self):
        receipt = nominal()
        receipt["max_active_workers"] = POLICY.max_concurrent + 1
        self.rejected(receipt, "worker_concurrency_budget")

    def test_boolean_or_negative_counts_do_not_equal_integer_counters(self):
        for value in (False, -1):
            with self.subTest(value=value):
                receipt = nominal()
                receipt["paid_api_calls"] = value
                self.rejected(receipt, "counter_types")

    def test_any_hosted_or_provider_execution_fails(self):
        for field, value in (("paid_api_calls", 1), ("external_writes", 1),
                             ("live_product_execution", True), ("automatic_pr_merge_or_deploy", True)):
            with self.subTest(field=field):
                receipt = nominal()
                receipt[field] = value
                self.rejected(receipt, "no_external_execution")

    def test_unverified_audit_fails(self):
        receipt = nominal()
        receipt["durable_audit_valid"] = False
        self.rejected(receipt, "authenticated_audit")

    def test_unknown_repository_and_sensitive_reason_are_redacted(self):
        receipt = nominal()
        receipt["records"][CANARY] = {"status": CANARY, "reason": CANARY}
        receipt["state_key"] = CANARY
        error = self.rejected(receipt, "exact_record_set")
        self.assertNotIn(CANARY, str(error))
        self.assertEqual(error.diagnostic["actual"]["other_record_count"], 1)

    def test_diagnostic_never_stringifies_an_untrusted_counter(self):
        class NotForDisplay:
            def __repr__(self):
                raise AssertionError("untrusted repr must not be called")
        receipt = nominal()
        receipt["scanner_invocations"] = NotForDisplay()
        self.rejected(receipt, "counter_types")

    def test_diagnostics_are_bounded_and_revalidated_at_process_boundary(self):
        receipt = nominal()
        receipt["transient_retry_events"] = [{
            "repository_id": CANARY, "reason_code": CANARY,
            "failed_attempt": 1, "error": CANARY,
        }] * 2_000
        summary = safe_cycle_summary(receipt)
        self.assertEqual(len(summary["transient_retry_events"]), 16)
        self.assertEqual(summary["retry_events_omitted"], 1_984)
        self.assertLess(len(json.dumps(summary)), 8_000)
        error = ReproductionFailure(check=CANARY, context=CANARY, receipt=receipt,
                                    expected={"attempted_repositories": CANARY, "extra": CANARY})
        error.diagnostic["extra"] = CANARY
        self.assertNotIn(CANARY, json.dumps(redact_reproduction_failure(error.diagnostic)))

    def test_reused_pipeline_raw_counter_requires_its_prior_measured_baseline(self):
        receipt = nominal(restart=True)
        receipt["scanner_invocations"] = 5
        result = assert_attempt_accounting(
            receipt, expected_attempted_repositories=(), policy=POLICY,
            scanner_invocations_before=5,
        )
        self.assertEqual(result["scanner_invocations"], 0)
        with self.assertRaises(ReproductionFailure):
            assert_attempt_accounting(receipt, expected_attempted_repositories=(), policy=POLICY)

    def test_safe_cancelled_admission_is_not_a_nominal_completed_cycle(self):
        receipt = nominal(restart=True)
        receipt["admitted_jobs"] = 1
        with self.assertRaises(ReproductionFailure):
            assert_attempt_accounting(receipt, expected_attempted_repositories=(), policy=POLICY)


class ActualOfflineRecipeTests(unittest.TestCase):
    def run_recipe(self, behaviour):
        examples = ROOT / "cookbook/security-review-pipeline"
        configuration = RecipeConfiguration.from_file(examples / "config.example.json")
        with tempfile.TemporaryDirectory(prefix="reproduction-contract-") as temporary:
            def scanner(**options):
                self.assertFalse(options.get("isolated"))
                return SyntheticScanner(behaviour=behaviour)

            with mock.patch("fleet_security.recipe.SyntheticScanner", side_effect=scanner):
                def cycle():
                    return RecurringSecurityRecipe.from_files(
                        configuration_path=examples / "config.example.json",
                        inventory_path=examples / "inventory.example.json",
                        approvals_path=examples / "approvals.example.json",
                        state_directory=Path(temporary) / "state", docker=False,
                    ).cycle()
                first, restart = cycle(), cycle()
        return first, restart, configuration.policy

    def test_actual_transient_recipe_and_restart_have_separate_job_attempt_retry_counts(self):
        first, restart, policy = self.run_recipe({"synthetic/payments-api": ("transient", "success")})
        for receipt, ids, label in ((first, ATTEMPTED, "first_cycle"), (restart, (), "restart_cycle")):
            assert_cycle_accounting(receipt, expected_attempted_repositories=ids,
                                    expected_statuses=EXPECTED, policy=policy,
                                    expected_isolation_receipts=0, context=label)
        self.assertEqual((first["scanner_invocations"], first["retry_attempts"],
                          restart["scanner_invocations"], restart["retry_attempts"]), (5, 1, 0, 0))

    def test_actual_hostile_timeout_exhaustion_fails_even_with_the_same_final_state_counts(self):
        first, _, policy = self.run_recipe({"synthetic/adversarial-docs": ("timeout", "timeout")})
        self.assertEqual(first["decision_states"], dict(Counter(EXPECTED.values())))
        with self.assertRaises(ReproductionFailure) as caught:
            assert_cycle_accounting(first, expected_attempted_repositories=ATTEMPTED,
                                    expected_statuses=EXPECTED, policy=policy,
                                    expected_isolation_receipts=0)
        self.assertEqual(caught.exception.diagnostic["check"], "hostile_fixture_refusal")

    def test_actual_hostile_transient_then_content_refusal_has_an_accounted_retry(self):
        first, _, policy = self.run_recipe({"synthetic/adversarial-docs": ("transient", "success")})
        result = assert_cycle_accounting(first, expected_attempted_repositories=ATTEMPTED,
                                         expected_statuses=EXPECTED, policy=policy,
                                         expected_isolation_receipts=0)
        self.assertEqual((result["scanner_invocations"], result["retry_attempts"]), (5, 1))


class NotebookFailureDiagnosticsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="notebook-failure-test-")
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name)
        self.notebook = self.workspace / "tutorial.ipynb"

    def write_notebook(self, cells):
        document = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": [
            {"cell_type": kind, "id": f"cell-{number}", "metadata": {}, "source": [source],
             **({"outputs": [], "execution_count": None} if kind == "code" else {})}
            for number, (kind, source) in enumerate(cells)
        ]}
        self.notebook.write_text(json.dumps(document))
        return hashlib.sha256(self.notebook.read_bytes()).hexdigest()

    def test_failure_distinguishes_raw_and_code_cell_numbers_and_never_runs_later_cell(self):
        before = self.write_notebook([
            ("markdown", "Intro"), ("code", f"secret = {CANARY!r}"),
            ("markdown", "First cycle"), ("code", "raise AssertionError(secret)"),
            ("code", "from pathlib import Path\nPath('should-not-run').touch()"),
        ])
        cwd = Path.cwd()
        with self.assertRaises(RUNNER.NotebookExecutionFailure) as caught:
            RUNNER.execute_notebook(self.notebook)
        report = caught.exception.diagnostic
        self.assertEqual((report["raw_cell_index_zero_based"], report["notebook_cell_number_one_based"],
                          report["code_cell_number_one_based"], report["code_cells_completed"],
                          report["line_in_cell_one_based"]), (3, 4, 2, 1, 1))
        self.assertNotIn(CANARY, str(caught.exception))
        self.assertEqual(Path.cwd(), cwd)
        self.assertFalse((self.workspace / "should-not-run").exists())
        self.assertEqual(hashlib.sha256(self.notebook.read_bytes()).hexdigest(), before)

    def test_first_cycle_helper_failure_names_contract_and_safe_actual_counts(self):
        receipt = nominal()
        receipt["scanner_invocations"] = 5
        code = (
            "from fleet_security.reproduction import assert_cycle_accounting\n"
            "from fleet_security.pipeline import FleetPolicy\n"
            f"receipt = {receipt!r}\n"
            f"assert_cycle_accounting(receipt, expected_attempted_repositories={ATTEMPTED!r}, "
            f"expected_statuses={EXPECTED!r}, policy=FleetPolicy(), "
            "expected_isolation_receipts=0, context='first_cycle')\n"
        )
        self.write_notebook([("markdown", "Intro"), ("code", code)])
        with self.assertRaises(RUNNER.NotebookExecutionFailure) as caught:
            RUNNER.execute_notebook(self.notebook)
        report = caught.exception.diagnostic["contract_failure"]
        self.assertEqual(report["check"], "raw_attempt_accounting")
        self.assertEqual(report["actual"]["scanner_invocations"], 5)
        self.assertEqual(report["actual"]["attempted_repositories"], 4)

    def test_failure_cleans_only_registered_temporary_state_and_preserves_source(self):
        tracking = self.workspace / "temporary-path.txt"
        source = (
            "import tempfile\nfrom pathlib import Path\n"
            "temporary_state = tempfile.TemporaryDirectory(prefix='owned-notebook-state-')\n"
            f"Path({str(tracking)!r}).write_text(temporary_state.name)\n"
            f"raise ValueError({CANARY!r})\n"
        )
        before = self.write_notebook([("code", source)])
        with self.assertRaises(RUNNER.NotebookExecutionFailure) as caught:
            RUNNER.execute_notebook(self.notebook)
        self.assertEqual(caught.exception.diagnostic["temporary_state_cleanup"], "complete")
        self.assertFalse(Path(tracking.read_text()).exists())
        self.assertNotIn(CANARY, str(caught.exception))
        self.assertEqual(hashlib.sha256(self.notebook.read_bytes()).hexdigest(), before)

    def test_cleanup_failure_is_reported_without_masking_the_original_assertion(self):
        self.write_notebook([("code", "assert False")])
        with mock.patch.object(RUNNER, "_cleanup_notebook_state", return_value="failed"):
            with self.assertRaises(RUNNER.NotebookExecutionFailure) as caught:
                RUNNER.execute_notebook(self.notebook)
        self.assertEqual(caught.exception.diagnostic["error_type"], "AssertionError")
        self.assertEqual(caught.exception.diagnostic["temporary_state_cleanup"], "failed")

    def test_system_exit_zero_cannot_masquerade_as_a_complete_notebook(self):
        self.write_notebook([("code", "raise SystemExit(0)")])
        with self.assertRaises(RUNNER.NotebookExecutionFailure) as caught:
            RUNNER.execute_notebook(self.notebook)
        self.assertNotEqual(caught.exception.returncode, 0)
        self.assertEqual(caught.exception.diagnostic["code_cells_completed"], 0)

    def test_cli_failure_outputs_one_safe_json_receipt_and_no_success(self):
        self.write_notebook([("code", f"raise RuntimeError({CANARY!r})")])
        output, errors = io.StringIO(), io.StringIO()
        with mock.patch.object(sys, "argv", ["execute_notebook", str(self.notebook)]):
            with mock.patch("sys.stdout", output), mock.patch("sys.stderr", errors):
                code = RUNNER.main()
        self.assertEqual(code, 1)
        self.assertEqual(output.getvalue(), "")
        self.assertEqual(json.loads(errors.getvalue())["status"], "FAIL")
        self.assertNotIn(CANARY, errors.getvalue())

    def test_verifier_preserves_only_safe_structured_failure_fields(self):
        failure = ReproductionFailure(check="raw_attempt_accounting", context="first_cycle", receipt=nominal())
        report = {
            "format": "governed-notebook-failure/v1", "status": "FAIL",
            "raw_cell_index_zero_based": 11, "code_cell_number_one_based": 5,
            "line_in_cell_one_based": 18, "error_type": "AssertionError",
            "contract_failure": failure.diagnostic, "namespace": CANARY,
        }
        completed = subprocess.CompletedProcess(["synthetic-command"], 1, CANARY,
                                                 CANARY + "\n" + json.dumps(report) + "\n")
        error = VERIFIER._command_failure("ordinary notebook-directory execution", completed)
        payload = json.loads(str(error))
        self.assertEqual(payload["notebook_failure"]["raw_cell_index_zero_based"], 11)
        self.assertEqual(payload["notebook_failure"]["contract_failure"]["check"], "raw_attempt_accounting")
        self.assertNotIn(CANARY, str(error))

    def test_verifier_does_not_echo_arbitrary_error_messages_or_fake_protocol_fields(self):
        completed = subprocess.CompletedProcess(["synthetic-command"], 1, CANARY, CANARY)
        self.assertNotIn(CANARY, str(VERIFIER._command_failure("synthetic-check", completed)))
        report = {"format": "governed-notebook-failure/v1", "status": "FAIL",
                  "error_type": CANARY, "raw_cell_index_zero_based": CANARY,
                  "temporary_state_cleanup": CANARY}
        self.assertNotIn(CANARY, json.dumps(VERIFIER._safe_notebook_failure(json.dumps(report))))


if __name__ == "__main__":
    unittest.main()
