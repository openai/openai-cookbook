"""New independent tests for the bounded, human-governed local supervisor."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import unittest

from stress_helpers import EXPECTED_STATES, ROOT, PrivateRecipeCase, append_container_receipt
from fleet_security.recipe import RecipeConfiguration
from fleet_security.reproduction import (
    DEMO_ATTEMPTED_REPOSITORIES, DEMO_EXPECTED_STATUSES, assert_cycle_accounting,
)


SUPERVISOR = ROOT / "scripts" / "run_bounded_security_supervisor.py"


class SupervisorCase(PrivateRecipeCase):
    def command(self, *extra: str, events: bool = False) -> list[str]:
        arguments = [
            sys.executable,
            str(SUPERVISOR),
            "--config", str(self.config),
            "--inventory", str(self.inventory),
            "--approvals", str(self.approvals),
            "--state-dir", str(self.state),
        ]
        if events:
            arguments.extend(("--events", str(self.events)))
        arguments.extend(str(value) for value in extra)
        return arguments

    def invoke(self, *extra: str, events: bool = False) -> subprocess.CompletedProcess[str]:
        environment = os.environ.copy()
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            self.command(*extra, events=events),
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    def successful(self, *extra: str, events: bool = False) -> dict:
        result = self.invoke(*extra, events=events)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def refused(self, *extra: str, events: bool = False, contains: str | None = None) -> dict:
        result = self.invoke(*extra, events=events)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        payload = json.loads(result.stderr)
        self.assertEqual(payload["status"], "failed_closed")
        self.assertEqual(payload["paid_api_calls"], 0)
        self.assertEqual(payload["external_writes"], 0)
        if contains:
            self.assertIn(contains, payload["error"])
        return payload


class BoundedSupervisorGovernanceStress(SupervisorCase):
    def test_two_bounded_cycles_scan_four_then_zero(self) -> None:
        receipt = self.successful("--max-cycles", "2")
        self.assertEqual(receipt["cycles_completed"], 2)
        self.assertEqual(receipt["scanner_invocations_per_cycle"], [4, 0])
        self.assertEqual(receipt["execution_boundary"], "trusted_host_offline_not_sandboxed")
        self.assertTrue(all(row["decision_states"] == EXPECTED_STATES for row in receipt["cycle_metrics"]))
        self.assertFalse(receipt["live_product_execution"])
        self.assertFalse(receipt["automatic_pr_merge_or_deploy"])

    def test_restarting_supervisor_reuses_signed_state_without_rescan(self) -> None:
        first = self.successful("--max-cycles", "1")
        second = self.successful("--max-cycles", "2")
        self.assertEqual(first["scanner_invocations_per_cycle"], [4])
        self.assertEqual(second["scanner_invocations_per_cycle"], [0, 0])
        self.assertEqual(second["cycle_metrics"][0]["recipe_run_number"], 2)

    def test_twelve_duplicate_events_coalesce_to_one_queue_item(self) -> None:
        self.write_events([self.event(event_id=f"duplicate-{index:02d}") for index in range(12)])
        receipt = self.successful("--max-cycles", "1", events=True)
        self.assertEqual(receipt["event_lines_consumed"], 12)
        self.assertEqual(receipt["events_processed"], 1)
        self.assertEqual(receipt["duplicate_events_coalesced"], 11)
        self.assertEqual(receipt["max_pending_observed"], 1)

    def test_pending_queue_backpressure_preserves_remaining_events_for_later_cycles(self) -> None:
        self.write_events([
            self.event("catalog-service", event_id="pending-01"),
            self.event("payments-api", event_id="pending-02"),
            self.event("edge-auth", event_id="pending-03"),
        ])
        receipt = self.successful("--max-cycles", "3", "--max-pending-events", "1", events=True)
        self.assertEqual(receipt["events_processed"], 3)
        self.assertGreaterEqual(receipt["backpressure_events"], 2)
        self.assertEqual(receipt["max_pending_observed"], 1)
        self.assertEqual(receipt["scanner_invocations_per_cycle"], [4, 0, 0])

    def test_max_events_per_cycle_backpressure_remains_bounded(self) -> None:
        self.write_events([self.event(event_id=f"bounded-{index:02d}") for index in range(7)])
        receipt = self.successful("--max-cycles", "4", "--max-events-per-cycle", "2", events=True)
        self.assertEqual(receipt["event_lines_consumed"], 7)
        self.assertGreaterEqual(receipt["backpressure_events"], 3)
        self.assertTrue(all(row["queue_event_lines_consumed"] <= 2 for row in receipt["cycle_metrics"]))

    def test_unknown_event_type_is_rejected_without_extra_scan_authority(self) -> None:
        self.write_events([self.event(event_type="deploy_to_production")])
        receipt = self.successful("--max-cycles", "2", events=True)
        self.assertEqual((receipt["rejected_events"], receipt["events_processed"]), (1, 0))
        self.assertEqual(receipt["scanner_invocations_per_cycle"], [4, 0])

    def test_non_synthetic_event_repository_is_rejected(self) -> None:
        row = self.event()
        row["repository_id"] = "actual-private-customer/private-repository"
        self.write_events([row])
        receipt = self.successful("--max-cycles", "1", events=True)
        self.assertEqual((receipt["rejected_events"], receipt["events_processed"]), (1, 0))
        self.assertEqual(receipt["real_customer_repository_access"], 0)

    def test_stale_event_revision_is_rejected(self) -> None:
        row = self.event()
        row["revision"] = "f" * 40
        self.write_events([row])
        receipt = self.successful("--max-cycles", "1", events=True)
        self.assertEqual((receipt["rejected_events"], receipt["events_processed"]), (1, 0))

    def test_forged_event_authority_field_is_rejected(self) -> None:
        row = self.event()
        row["approve_merge"] = True
        self.write_events([row])
        receipt = self.successful("--max-cycles", "1", events=True)
        self.assertEqual((receipt["rejected_events"], receipt["events_processed"]), (1, 0))
        self.assertFalse(receipt["automatic_pr_merge_or_deploy"])

    def test_malformed_and_non_object_event_lines_are_rejected(self) -> None:
        self.write_events(["{not-json", "[]", "null", self.event(event_id="valid-tail")])
        receipt = self.successful("--max-cycles", "1", events=True)
        self.assertEqual((receipt["rejected_events"], receipt["events_processed"]), (3, 1))

    def test_oversized_event_stream_fails_before_scanner_dispatch(self) -> None:
        self.write_events([self.event()])
        self.refused("--max-cycles", "1", "--max-event-file-bytes", "1", events=True, contains="bounded byte budget")
        self.assertFalse((self.state / "runs").exists())

    def test_oversized_event_line_fails_before_scanner_dispatch(self) -> None:
        self.events.write_text("x" * 8_300 + "\n", encoding="utf-8")
        self.events.chmod(0o600)
        self.refused("--max-cycles", "1", events=True, contains="inspection budget")
        self.assertFalse((self.state / "runs").exists())

    def test_signed_cursor_tampering_is_rejected_on_restart(self) -> None:
        self.write_events([self.event()])
        self.successful("--max-cycles", "1", events=True)
        cursor = self.state / "supervisor-cursor.json"
        envelope = self.read(cursor)
        envelope["payload"]["offset"] = 0
        self.save(cursor, envelope)
        self.refused("--max-cycles", "1", events=True, contains="integrity verification")

    def test_event_prefix_rewrite_is_rejected_on_restart(self) -> None:
        self.write_events([self.event(event_id="before-001")])
        self.successful("--max-cycles", "1", events=True)
        self.write_events([self.event(event_id="forged-001")])
        self.refused("--max-cycles", "1", events=True, contains="changed before its authenticated cursor")

    def test_world_readable_configuration_is_rejected_before_state(self) -> None:
        self.config.chmod(0o644)
        self.refused("--max-cycles", "1", contains="mode 0600")
        self.assertFalse(self.state.exists())

    def test_world_readable_named_approvals_are_rejected_before_state(self) -> None:
        self.approvals.chmod(0o644)
        self.refused("--max-cycles", "1", contains="mode 0600")
        self.assertFalse(self.state.exists())

    def test_world_readable_event_stream_is_rejected_before_state(self) -> None:
        self.write_events([self.event()])
        self.events.chmod(0o644)
        self.refused("--max-cycles", "1", events=True, contains="mode 0600")
        self.assertFalse(self.state.exists())

    def test_symbolic_trusted_configuration_is_rejected(self) -> None:
        target = self.private_root / "trusted-original.json"
        target.write_bytes(self.config.read_bytes())
        target.chmod(0o600)
        self.config.unlink()
        self.config.symlink_to(target)
        self.refused("--max-cycles", "1", contains="real trusted regular file")

    def test_insecure_state_directory_fails_closed(self) -> None:
        self.state.mkdir(mode=0o755)
        self.state.chmod(0o755)
        self.refused("--max-cycles", "1", contains="mode 0700")

    def test_symbolic_state_directory_fails_closed(self) -> None:
        actual = self.private_root / "actual-private-state"
        actual.mkdir(mode=0o700)
        self.state.symlink_to(actual, target_is_directory=True)
        self.refused("--max-cycles", "1", contains="real owner-private directory")

    def test_checkout_state_path_is_refused_without_creating_it(self) -> None:
        forbidden = ROOT / "forbidden-supervisor-state"
        original = self.state
        self.state = forbidden
        try:
            self.refused("--max-cycles", "1", contains="outside the repository checkout")
        finally:
            self.state = original
        self.assertFalse(forbidden.exists())

    def test_forged_scope_actor_fails_closed_before_cycle(self) -> None:
        approvals = self.read(self.approvals)
        approvals["approvals"][0]["actor"] = "untrusted-event-actor"
        self.save(self.approvals, approvals)
        self.refused("--max-cycles", "1", contains="not authorised")

    def test_provider_write_and_draft_pr_policy_fails_closed(self) -> None:
        config = self.read(self.config)
        config["policy"].update(allow_draft_pr=True, provider_write_authorised=True)
        self.save(self.config, config)
        self.refused("--max-cycles", "1", contains="never grants provider writes")

    def test_required_service_isolation_cannot_be_claimed_on_host(self) -> None:
        self.refused("--max-cycles", "1", "--require-container-isolation", contains="explicit restricted service runtime")

    def test_service_runtime_without_actual_isolation_verification_is_refused(self) -> None:
        self.refused("--max-cycles", "1", "--runtime-label", "restricted_service_container", contains="verify its actual outer isolation")

    def test_docker_in_docker_is_refused_without_launch(self) -> None:
        self.refused(
            "--max-cycles", "1", "--runtime-label", "restricted_service_container",
            "--require-container-isolation", "--docker", contains="Docker-in-Docker",
        )

    def test_zero_cycles_are_rejected_by_bounded_argument_parser(self) -> None:
        result = self.invoke("--max-cycles", "0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("between 1 and 1000", result.stderr)
        self.assertFalse(self.state.exists())

    def test_infinite_interval_is_rejected_by_bounded_argument_parser(self) -> None:
        result = self.invoke("--interval-seconds", "inf")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("between zero and 60", result.stderr)
        self.assertFalse(self.state.exists())

    def test_zero_pending_queue_capacity_is_rejected(self) -> None:
        result = self.invoke("--max-pending-events", "0")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("between 1 and 10000", result.stderr)
        self.assertFalse(self.state.exists())

    def test_sigterm_gracefully_stops_between_bounded_cycles(self) -> None:
        process = subprocess.Popen(
            self.command("--max-cycles", "100", "--interval-seconds", "10"),
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            deadline = time.monotonic() + 8
            while not (self.state / "runs" / "run-0001.json").exists() and time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                time.sleep(0.02)
            self.assertTrue((self.state / "runs" / "run-0001.json").exists(), "first cycle did not finish")
            process.send_signal(signal.SIGTERM)
            output, errors = process.communicate(timeout=8)
            self.assertEqual(process.returncode, 0, errors)
            receipt = json.loads(output)
            self.assertTrue(receipt["graceful_shutdown"])
            self.assertEqual(receipt["shutdown_reason"], "signal:SIGTERM")
            self.assertGreaterEqual(receipt["cycles_completed"], 1)
            self.assertLess(receipt["cycles_completed"], 100)
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


@unittest.skipUnless(os.environ.get("RUN_STRESS_DOCKER") == "1", "actual restricted supervisor Docker requires RUN_STRESS_DOCKER=1")
class GenuineSupervisorDockerStress(SupervisorCase):
    def test_actual_supervisor_workers_use_restricted_docker_and_restart_without_rescan(self) -> None:
        receipt = self.successful("--max-cycles", "2", "--docker")
        self.assertEqual(receipt["execution_boundary"], "trusted_host_with_restricted_workers")
        policy = RecipeConfiguration.from_file(self.config).policy
        measured_attempts = []
        for index, cycle in enumerate(receipt["cycle_metrics"]):
            run_number = cycle["recipe_run_number"]
            full = self.read(self.state / "runs" / f"run-{run_number:04d}.json")
            assert_cycle_accounting(
                full,
                expected_attempted_repositories=DEMO_ATTEMPTED_REPOSITORIES if index == 0 else (),
                expected_statuses=DEMO_EXPECTED_STATUSES, policy=policy,
                expected_isolation_receipts=3 if index == 0 else 0,
                context="supervisor_cycle",
            )
            self.assertEqual(cycle["scanner_invocations"], full["scanner_invocations"])
            self.assertEqual(cycle["restricted_docker_receipts"], full["restricted_docker_receipts"])
            self.assertEqual(cycle["decision_states"], full["decision_states"])
            measured_attempts.append(full["scanner_invocations"])
        self.assertEqual(len(measured_attempts), 2)
        self.assertEqual(measured_attempts[1], 0)
        self.assertEqual(receipt["scanner_invocations_per_cycle"], measured_attempts)
        self.assertEqual(receipt["restricted_docker_receipts_per_cycle"], [3, 0])
        self.assertEqual(receipt["isolated_worker_receipts_total"], 3)
        self.assertFalse(receipt["live_product_execution"])
        self.assertEqual(receipt["external_writes"], 0)
        self.assertEqual(receipt["scan_attempts_total"], sum(measured_attempts))
        self.assertEqual(receipt["cycle_metrics"][0]["decision_states"]["failed_safe_abstention"], 1)
        # The subprocess exposes validated successful isolation receipts, not
        # actual launch observations for failed or pre-launch retry attempts.
        for index in range(receipt["isolated_worker_receipts_total"]):
            append_container_receipt(
                self.id(),
                kind="restricted-supervisor-verified-success",
                details={
                    "success_receipt_index": index + 1,
                    "successful_isolation_receipts_total": 3,
                    "scanner_attempts_total": receipt["scan_attempts_total"],
                    "all_container_starts_measured": False,
                },
            )
        self.assert_owner_private_tree(self.state)


if __name__ == "__main__":
    unittest.main()
