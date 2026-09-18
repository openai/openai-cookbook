"""Current-cycle accounting separates admitted jobs, scanner calls and retries."""
from __future__ import annotations

import json
import subprocess
import tempfile
import threading
import unittest
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from support import ROOT, approve_scope, pipeline, repository
from field_autonomy.policy import PolicyViolation
from fleet_security.evidence import AuditLog
from fleet_security.pipeline import FleetPolicy
from fleet_security.recipe import RecurringSecurityRecipe
from fleet_security.scanner import RETRY_REASON_CODES, ScanFailure, SyntheticScanner


class AccountingAssertions(unittest.TestCase):
    def assert_accounting(self, receipt, counts, *, admitted):
        self.assertEqual(receipt["admitted_jobs"], admitted)
        self.assertEqual(receipt["attempted_repositories"], len(counts))
        self.assertEqual(receipt["scanner_attempts_by_repository"], counts)
        self.assertEqual(receipt["retry_attempts"], sum(count - 1 for count in counts.values()))
        for event in receipt["transient_retry_events"]:
            self.assertEqual(set(event), {"repository_id", "failed_attempt", "reason_code"})
            self.assertIn(event["reason_code"], RETRY_REASON_CODES)


class PipelineAttemptAccountingTests(AccountingAssertions):
    def run_record(self, *, behaviour=(), policy=None):
        record = repository()
        scanner = SyntheticScanner(behaviour={record.repo_id: behaviour})
        flow = pipeline(scanner=scanner, policy=policy)
        approve_scope(flow, record)
        return flow, record, flow.run((record,))

    def test_four_nominal_jobs_have_four_calls_and_no_retry(self):
        records = tuple(repository(index) for index in range(1, 5))
        flow = pipeline()
        for record in records:
            approve_scope(flow, record)
        result = flow.run(records)
        self.assert_accounting(result, {row.repo_id: 1 for row in records}, admitted=4)
        self.assertEqual(result["scanner_invocations"], 4)
        self.assertEqual(result["transient_retry_events"], [])
        self.assertEqual((result["consumed_units"], result["reserved_units"]), (20, 0))

    def test_recovered_transient_is_one_job_two_calls_and_one_retry(self):
        _, record, result = self.run_record(behaviour=("transient", "success"))
        self.assert_accounting(result, {record.repo_id: 2}, admitted=1)
        self.assertEqual(result["scanner_invocations"], 2)
        self.assertEqual(result["records"][record.repo_id]["status"], "review_packet_ready")
        self.assertEqual(result["transient_retry_events"], [{
            "repository_id": record.repo_id,
            "failed_attempt": 1,
            "reason_code": "synthetic_provider_transient",
        }])

    def test_exhaustion_counts_only_executed_retries_and_preserves_abstention(self):
        _, record, result = self.run_record(behaviour=("timeout", "timeout", "success"))
        self.assert_accounting(result, {record.repo_id: 2}, admitted=1)
        self.assertEqual(result["scanner_invocations"], 2)
        self.assertEqual(result["records"][record.repo_id]["status"], "failed_safe_abstention")
        self.assertEqual(result["transient_retry_events"], [{
            "repository_id": record.repo_id,
            "failed_attempt": 1,
            "reason_code": "synthetic_deadline_exceeded",
        }])
        self.assertEqual(result["reserved_units"], 0)

    def test_single_attempt_policy_never_creates_retry_evidence(self):
        _, record, result = self.run_record(
            behaviour=("transient", "success"), policy=FleetPolicy(max_attempts=1),
        )
        self.assert_accounting(result, {record.repo_id: 1}, admitted=1)
        self.assertEqual(result["records"][record.repo_id]["status"], "failed_safe_abstention")
        self.assertEqual(result["transient_retry_events"], [])

    def test_two_retries_each_have_a_distinct_failed_attempt(self):
        _, record, result = self.run_record(
            behaviour=("transient", "timeout", "success"), policy=FleetPolicy(max_attempts=3),
        )
        self.assert_accounting(result, {record.repo_id: 3}, admitted=1)
        self.assertEqual([event["failed_attempt"] for event in result["transient_retry_events"]], [1, 2])
        self.assertEqual(result["records"][record.repo_id]["status"], "review_packet_ready")

    def test_cached_state_does_not_recount_previous_calls_or_retries(self):
        flow, record, first = self.run_record(behaviour=("transient", "success"))
        self.assertEqual(first["retry_attempts"], 1)
        for _ in range(3):
            restarted = flow.run((record,))
            self.assert_accounting(restarted, {}, admitted=0)
            self.assertEqual(restarted["transient_retry_events"], [])
            self.assertEqual(restarted["records"][record.repo_id]["attempts"], 2)
            # This older field deliberately remains the scanner lifetime count.
            self.assertEqual(restarted["scanner_invocations"], 2)

    def test_new_revision_is_not_misclassified_as_a_lifetime_retry(self):
        flow, record, _ = self.run_record()
        changed = replace(record, commit_sha="b" * 40)
        approve_scope(flow, changed)
        result = flow.run((changed,))
        self.assert_accounting(result, {record.repo_id: 1}, admitted=1)
        self.assertEqual(result["transient_retry_events"], [])
        self.assertEqual(result["scanner_invocations"], 2)

    def test_gate_and_pre_admission_cancellation_make_no_attempts(self):
        flow = pipeline()
        record = repository()
        blocked = flow.run((record,))
        self.assert_accounting(blocked, {}, admitted=0)
        approve_scope(flow, record)
        flow.cancel(record.repo_id, actor="scope-owner")
        cancelled = flow.run((record,))
        self.assert_accounting(cancelled, {}, admitted=0)
        self.assertEqual(cancelled["scanner_invocations"], 0)

    def cancellation_flow(self, trigger_event, *, behaviour=()):
        class CancellingAudit(AuditLog):
            cancel_hook = None

            def append(self, event, repository_id, **metadata):
                result = super().append(event, repository_id, **metadata)
                if event == trigger_event and self.cancel_hook is not None:
                    self.cancel_hook(repository_id)
                return result

        record = repository()
        flow = pipeline(scanner=SyntheticScanner(behaviour={record.repo_id: behaviour}))
        audit = CancellingAudit()
        audit.cancel_hook = lambda repo_id: flow.cancel(repo_id, actor="scope-owner")
        flow.audit = audit
        approve_scope(flow, record)
        return record, flow.run((record,))

    def test_cancel_after_admission_can_leave_a_job_with_no_started_call(self):
        record, result = self.cancellation_flow("scan_admitted")
        self.assert_accounting(result, {}, admitted=1)
        self.assertEqual(result["records"][record.repo_id]["status"], "cancelled")
        self.assertEqual(result["scanner_invocations"], 0)
        self.assertEqual(result["transient_retry_events"], [])

    def test_cancel_after_retry_is_scheduled_does_not_invent_a_second_call(self):
        record, result = self.cancellation_flow(
            "transient_retry", behaviour=("transient", "success"),
        )
        self.assert_accounting(result, {record.repo_id: 1}, admitted=1)
        self.assertEqual(result["records"][record.repo_id]["status"], "cancelled")
        self.assertEqual(result["scanner_invocations"], 1)
        self.assertEqual(result["retry_attempts"], 0)
        self.assertEqual(len(result["transient_retry_events"]), 1)
        self.assertEqual(result["transient_retry_events"][0]["failed_attempt"], 1)

    def test_concurrent_recovery_counts_each_repository_without_a_counter_race(self):
        barrier = threading.Barrier(4, timeout=10)

        class ConcurrentScanner(SyntheticScanner):
            def _offline_matches(self, fixture):
                barrier.wait()
                return super()._offline_matches(fixture)

        records = tuple(repository(index) for index in range(1, 5))
        recovering = records[0].repo_id
        scanner = ConcurrentScanner(behaviour={recovering: ("transient", "success")})
        flow = pipeline(scanner=scanner, policy=FleetPolicy(max_concurrent=4))
        for record in records:
            approve_scope(flow, record)
        result = flow.run(records)
        expected = {row.repo_id: 2 if row.repo_id == recovering else 1 for row in records}
        self.assert_accounting(result, expected, admitted=4)
        self.assertEqual(result["scanner_invocations"], 5)
        self.assertEqual(result["max_active_workers"], 4)
        self.assertTrue(all(row["status"] == "review_packet_ready" for row in result["records"].values()))
        self.assertEqual(result["transient_retry_events"][0]["repository_id"], recovering)

    def test_internal_duplicate_invocations_are_not_excused_as_authorised_retries(self):
        class DuplicateScanner(SyntheticScanner):
            def scan(self, record, assignment):
                super().scan(record, assignment)
                return super().scan(record, assignment)

        record = repository()
        flow = pipeline(scanner=DuplicateScanner())
        approve_scope(flow, record)
        result = flow.run((record,))
        self.assert_accounting(result, {record.repo_id: 1}, admitted=1)
        self.assertEqual(result["scanner_invocations"], 2)
        self.assertEqual(result["transient_retry_events"], [])
        # A verifier can reject this mismatch instead of labelling it a retry.
        self.assertNotEqual(result["scanner_invocations"], sum(result["scanner_attempts_by_repository"].values()))

    def test_unexpected_adapter_failure_counts_the_host_call_without_private_details(self):
        private_marker = "synthetic-private-adapter-marker"

        class InterruptedScanner(SyntheticScanner):
            def scan(self, record, assignment):
                raise OSError(private_marker)

        record = repository()
        flow = pipeline(scanner=InterruptedScanner())
        approve_scope(flow, record)
        result = flow.run((record,))
        self.assert_accounting(result, {record.repo_id: 1}, admitted=1)
        self.assertEqual(result["records"][record.repo_id]["status"], "failed_safe_abstention")
        self.assertEqual(result["transient_retry_events"], [])
        self.assertNotIn(private_marker, json.dumps(result))
        self.assertNotIn(private_marker, json.dumps(flow.audit.events))

    def test_mutated_retry_reason_is_replaced_by_safe_enumerated_code(self):
        private_marker = "synthetic-private-retry-marker"

        class MutatedFailureScanner(SyntheticScanner):
            def scan(self, record, assignment):
                try:
                    return super().scan(record, assignment)
                except ScanFailure as error:
                    error.reason_code = private_marker
                    raise

        record = repository()
        scanner = MutatedFailureScanner(behaviour={record.repo_id: ("transient", "success")})
        flow = pipeline(scanner=scanner)
        approve_scope(flow, record)
        result = flow.run((record,))
        self.assertEqual(result["transient_retry_events"][0]["reason_code"], "retryable_scan_failure")
        self.assertNotIn(private_marker, json.dumps(result))
        self.assertNotIn(private_marker, json.dumps(flow.audit.events))


class RecipeAttemptAccountingTests(AccountingAssertions):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="recipe-attempt-accounting-")
        self.addCleanup(self.temporary.cleanup)
        self.state = Path(self.temporary.name) / "private-state"

    def cycle(self, *, behaviour=None):
        examples = ROOT / "cookbook" / "security-review-pipeline"
        scanner_factory = lambda *, isolated: SyntheticScanner(isolated=isolated, behaviour=behaviour)
        with mock.patch("fleet_security.recipe.SyntheticScanner", side_effect=scanner_factory):
            return RecurringSecurityRecipe.from_files(
                configuration_path=examples / "config.example.json",
                inventory_path=examples / "inventory.example.json",
                approvals_path=examples / "approvals.example.json",
                state_directory=self.state, clock=lambda: 1_788_000_000,
            ).cycle()

    def expected_counts(self, *, recovering=False):
        return {
            "synthetic/adversarial-docs": 1,
            "synthetic/catalog-service": 2 if recovering else 1,
            "synthetic/edge-auth": 1,
            "synthetic/payments-api": 1,
        }

    def test_nominal_six_record_recipe_admits_and_attempts_only_four_jobs(self):
        receipt = self.cycle()
        self.assert_accounting(receipt, self.expected_counts(), admitted=4)
        self.assertEqual(receipt["scanner_invocations"], 4)
        self.assertEqual(receipt["decision_states"], {
            "awaiting_finding_disposition": 2,
            "awaiting_scope_approval": 1,
            "awaiting_threat_model_approval": 1,
            "failed_safe_abstention": 1,
            "review_packet_ready": 1,
        })

    def test_recovered_first_cycle_and_two_clean_restarts_have_separate_accounting(self):
        recovering = "synthetic/catalog-service"
        receipt = self.cycle(behaviour={recovering: ("timeout", "success")})
        self.assert_accounting(receipt, self.expected_counts(recovering=True), admitted=4)
        self.assertEqual(receipt["scanner_invocations"], 5)
        self.assertEqual(receipt["records"][recovering]["status"], "review_packet_ready")
        for run_number in (2, 3):
            restarted = self.cycle()
            self.assert_accounting(restarted, {}, admitted=0)
            self.assertEqual(restarted["scanner_invocations"], 0)
            self.assertEqual(restarted["transient_retry_events"], [])
            self.assertEqual(restarted["records"][recovering]["attempts"], 2)
            self.assertEqual(restarted["run_number"], run_number)
            self.assertTrue(restarted["durable_audit_valid"])

    def test_exhausted_job_is_quarantined_without_recounting_attempts_on_restart(self):
        failing = "synthetic/catalog-service"
        receipt = self.cycle(behaviour={failing: ("timeout", "timeout")})
        self.assert_accounting(receipt, self.expected_counts(recovering=True), admitted=4)
        self.assertEqual(receipt["records"][failing]["status"], "failed_safe_abstention")
        restarted = self.cycle()
        self.assert_accounting(restarted, {}, admitted=0)
        self.assertEqual(restarted["scanner_invocations"], 0)
        self.assertEqual(restarted["transient_retry_events"], [])
        self.assertIn(failing, restarted["quarantined_unchanged"])


class RestrictedAdapterReasonCodeTests(AccountingAssertions):
    """Fake executor tests classify errors; they do not prove Docker isolation."""

    def valid_result(self):
        receipt = {
            "matches": [], "uid": 65532, "networkBlocked": True, "rootReadOnly": True,
            "mountChecks": {"source": "read_only", "protectedTests": "read_only", "scratch": "writable"},
            "effectiveCapabilities": "0", "noNewPrivileges": "1",
            "hiddenPathPresence": {name: False for name in (
                "/var/run/docker.sock", "/workspace/.env.local", "/workspace/.git", "/Users", "/host",
            )},
            "credentialPresence": {name: False for name in (
                "OPENAI_API_KEY", "CODEX_API_KEY", "GITHUB_TOKEN", "GH_TOKEN",
                "OPENAI_WEBHOOK_SECRET", "AWS_SECRET_ACCESS_KEY",
            )},
        }
        return subprocess.CompletedProcess(["synthetic-fake-executor"], 0, json.dumps(receipt), "")

    def run_fake_executor(self, first):
        executor = mock.Mock()
        executor.run.side_effect = [first, self.valid_result()]

        @contextmanager
        def fake_open(*_args):
            yield SimpleNamespace(executor=executor, isolation="synthetic_fake_executor_not_docker")

        record = repository()
        flow = pipeline(scanner=SyntheticScanner(isolated=True))
        approve_scope(flow, record)
        with mock.patch("field_autonomy.sandbox.ContainerRuntime") as runtime:
            runtime.return_value.open.side_effect = fake_open
            result = flow.run((record,))
        return record, result, executor

    def test_restricted_timeout_recovery_has_specific_safe_reason(self):
        record, result, executor = self.run_fake_executor(
            subprocess.TimeoutExpired(["synthetic-fake-executor"], 10),
        )
        self.assert_accounting(result, {record.repo_id: 2}, admitted=1)
        self.assertEqual(executor.run.call_count, 2)
        self.assertEqual(result["transient_retry_events"][0]["reason_code"], "restricted_worker_timeout")

    def test_restricted_io_recovery_has_specific_safe_reason(self):
        record, result, _ = self.run_fake_executor(OSError("synthetic-private-path-marker"))
        self.assert_accounting(result, {record.repo_id: 2}, admitted=1)
        self.assertEqual(result["transient_retry_events"][0]["reason_code"], "restricted_worker_io_failure")
        self.assertNotIn("synthetic-private-path-marker", json.dumps(result))

    def test_invalid_receipt_recovery_has_specific_safe_reason(self):
        record, result, _ = self.run_fake_executor(
            subprocess.CompletedProcess(["synthetic-fake-executor"], 0, "{invalid-private-marker", ""),
        )
        self.assert_accounting(result, {record.repo_id: 2}, admitted=1)
        self.assertEqual(result["transient_retry_events"][0]["reason_code"], "restricted_receipt_invalid")
        self.assertNotIn("invalid-private-marker", json.dumps(result))

    def test_nonzero_worker_exit_is_not_relabelled_as_a_retry(self):
        record, result, executor = self.run_fake_executor(
            subprocess.CompletedProcess(["synthetic-fake-executor"], 1, "", "synthetic-private-marker"),
        )
        self.assert_accounting(result, {record.repo_id: 1}, admitted=1)
        self.assertEqual(executor.run.call_count, 1)
        self.assertEqual(result["records"][record.repo_id]["status"], "failed_safe_abstention")
        self.assertEqual(result["transient_retry_events"], [])
        self.assertNotIn("synthetic-private-marker", json.dumps(result))

    def test_generic_worker_exits_are_not_proof_of_hostile_content_refusal(self):
        for code in (1, 125, 126, 127, 137):
            with self.subTest(exit_code=code):
                record, result, executor = self.run_fake_executor(
                    subprocess.CompletedProcess(["synthetic-fake-executor"], code, "", "private-marker"),
                )
                self.assert_accounting(result, {record.repo_id: 1}, admitted=1)
                self.assertEqual(executor.run.call_count, 1)
                self.assertEqual(result["records"][record.repo_id]["reason"],
                                 "restricted synthetic worker failed without a verified content refusal")
                self.assertEqual(result["transient_retry_events"], [])
                self.assertNotIn("private-marker", json.dumps(result))

    def test_instruction_refusal_requires_the_exact_exit_and_trusted_protocol(self):
        payload = json.dumps({"status": "refused_untrusted_content", "reason_code": "repository_instruction"})
        for code in (0, 1, 65, 125, 137):
            with self.subTest(exit_code=code):
                record, result, _ = self.run_fake_executor(
                    subprocess.CompletedProcess(["synthetic-fake-executor"], code, payload, ""),
                )
                reason = result["records"][record.repo_id]["reason"]
                self.assertEqual(
                    reason == "restricted synthetic scan abstained on untrusted repository content",
                    code == 65,
                )
                self.assertEqual(result["transient_retry_events"], [])

    def test_refusal_exit_with_malformed_or_extended_payload_fails_closed(self):
        payloads = (
            "", "{private-marker", "null", "[]",
            '{"status":"refused_untrusted_content","reason_code":"unknown"}',
            '{"status":"refused_untrusted_content","reason_code":[]}',
            '{"status":"refused_untrusted_content","reason_code":"repository_instruction","extra":"private-marker"}',
            '{"status":"refused_untrusted_content","reason_code":"repository_instruction"}' + " " * 512,
        )
        for payload in payloads:
            with self.subTest(payload_length=len(payload)):
                record, result, executor = self.run_fake_executor(
                    subprocess.CompletedProcess(["synthetic-fake-executor"], 65, payload, "private-marker"),
                )
                self.assertEqual(executor.run.call_count, 1)
                self.assertEqual(result["records"][record.repo_id]["reason"],
                                 "restricted synthetic worker failed without a verified content refusal")
                self.assertEqual(result["transient_retry_events"], [])
                self.assertNotIn("private-marker", json.dumps(result))

    def test_other_verified_content_refusals_are_not_instruction_refusal_proof(self):
        for reason in ("hidden_repository_entry", "symbolic_repository_entry", "source_inspection_budget"):
            with self.subTest(reason_code=reason):
                payload = json.dumps({"status": "refused_untrusted_content", "reason_code": reason})
                record, result, executor = self.run_fake_executor(
                    subprocess.CompletedProcess(["synthetic-fake-executor"], 65, payload, ""),
                )
                self.assertEqual(executor.run.call_count, 1)
                self.assertEqual(result["records"][record.repo_id]["reason"],
                                 "restricted synthetic scan refused an unsafe repository entry")
                self.assertEqual(result["transient_retry_events"], [])

    def assert_incomplete_isolation_rejected(self, mutate):
        completed = self.valid_result()
        payload = json.loads(completed.stdout)
        mutate(payload)
        completed.stdout = json.dumps(payload)
        record, result, executor = self.run_fake_executor(completed)
        self.assertEqual(executor.run.call_count, 1)
        self.assertEqual(result["records"][record.repo_id]["status"], "failed_safe_abstention")
        self.assertEqual(result["records"][record.repo_id]["reason"],
                         "restricted execution failed a mandatory isolation property")
        self.assertEqual(result["transient_retry_events"], [])

    def test_missing_credential_presence_is_not_absence_proof(self):
        self.assert_incomplete_isolation_rejected(lambda payload: payload.pop("credentialPresence"))

    def test_missing_hidden_path_presence_is_not_absence_proof(self):
        self.assert_incomplete_isolation_rejected(lambda payload: payload.pop("hiddenPathPresence"))

    def test_presence_maps_require_every_expected_key_and_no_unknown_keys(self):
        for name in ("credentialPresence", "hiddenPathPresence"):
            for value in ({}, {"unrecognised": False}):
                with self.subTest(field=name, keys=len(value)):
                    self.assert_incomplete_isolation_rejected(
                        lambda payload, name=name, value=value: payload.__setitem__(name, value),
                    )

    def test_falsey_values_are_not_literal_absence_evidence(self):
        for name in ("credentialPresence", "hiddenPathPresence"):
            for value in (0, None, "", [], {}):
                with self.subTest(field=name, value_type=type(value).__name__):
                    def mutate(payload):
                        first_key = next(iter(payload[name]))
                        payload[name][first_key] = value
                    self.assert_incomplete_isolation_rejected(mutate)

    def test_non_root_identity_requires_the_exact_integer_worker_uid(self):
        for value in (None, "0", "65532", 0, 1, True, 65532.0):
            with self.subTest(uid_type=type(value).__name__):
                self.assert_incomplete_isolation_rejected(lambda payload: payload.__setitem__("uid", value))
        self.assert_incomplete_isolation_rejected(lambda payload: payload.pop("uid"))

    def test_isolation_maps_and_capabilities_cannot_be_missing_or_ill_typed(self):
        for field, value in (("mountChecks", {}), ("mountChecks", None),
                             ("effectiveCapabilities", None), ("effectiveCapabilities", 0),
                             ("effectiveCapabilities", "1"), ("noNewPrivileges", 1)):
            with self.subTest(field=field, value_type=type(value).__name__):
                self.assert_incomplete_isolation_rejected(
                    lambda payload, field=field, value=value: payload.__setitem__(field, value),
                )

    def test_policy_failure_does_not_retry_or_fall_back_to_offline_execution(self):
        record = repository()
        scanner = SyntheticScanner(isolated=True)
        flow = pipeline(scanner=scanner)
        approve_scope(flow, record)
        with mock.patch("field_autonomy.sandbox.ContainerRuntime") as runtime:
            runtime.return_value.open.side_effect = PolicyViolation("synthetic-private-policy-marker")
            with mock.patch.object(scanner, "_offline_matches", side_effect=AssertionError("fallback")):
                result = flow.run((record,))
        self.assert_accounting(result, {record.repo_id: 1}, admitted=1)
        self.assertEqual(result["records"][record.repo_id]["status"], "failed_safe_abstention")
        self.assertEqual(result["transient_retry_events"], [])
        self.assertNotIn("synthetic-private-policy-marker", json.dumps(result))

    def test_reason_code_constructor_does_not_copy_arbitrary_diagnostic_data(self):
        for untrusted in ("synthetic-private-code-marker", [], None):
            with self.subTest(value=type(untrusted).__name__):
                failure = ScanFailure("synthetic", retryable=True, reason_code=untrusted)
                self.assertEqual(failure.reason_code, "retryable_scan_failure")


if __name__ == "__main__":
    unittest.main()
