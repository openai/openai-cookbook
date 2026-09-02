"""New independent signed-state, approvals and recovery stress cases."""
from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
import time
import unittest
from unittest import mock

from stress_helpers import EXPECTED_STATES, ROOT, PrivateRecipeCase
from fleet_security.evidence import EvidenceError
from fleet_security.inventory import InventoryError, stable_digest
from fleet_security.pipeline import PipelineError
from fleet_security.recipe import RecipeConfiguration, RecurringSecurityRecipe


class DurableRecipeAdversarialStress(PrivateRecipeCase):
    def _parallel_processes(self, *, count: int, cold_bootstrap: bool = False) -> list[dict]:
        ready = self.private_root / "parallel-ready"
        ready.mkdir(mode=0o700)
        start = self.private_root / "parallel-start"
        worker = ROOT / "stress-tests" / "concurrent_recipe_worker.py"
        processes = []
        for index in range(count):
            command = [
                sys.executable, str(worker), "--checkout", str(ROOT),
                "--config", str(self.config), "--inventory", str(self.inventory), "--approvals", str(self.approvals),
                "--state", str(self.state), "--ready", str(ready), "--start", str(start), "--worker", str(index),
            ]
            if cold_bootstrap:
                command.append("--barrier-before-bootstrap")
            processes.append(subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True))
        deadline = time.monotonic() + 20
        try:
            while len(list(ready.glob("*.ready"))) < count:
                self.assertLess(time.monotonic(), deadline, "bounded worker start barrier expired")
                self.assertFalse(any(process.poll() not in (None, 0) for process in processes), "worker exited before start barrier")
                time.sleep(0.004)
            descriptor = os.open(start, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            results = []
            for process in processes:
                output, errors = process.communicate(timeout=35)
                self.assertEqual(process.returncode, 0, errors)
                result = json.loads(output)
                self.assertEqual(result["status"], "PASS", result)
                results.append(result)
            return results
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate(timeout=5)

    def test_eight_independent_processes_preserve_every_signed_cycle_update(self) -> None:
        initial = self.cycle()
        self.assertEqual(initial["run_number"], 1)
        results = self._parallel_processes(count=8)
        self.assertEqual(len({row["pid"] for row in results}), 8)
        self.assertEqual(sorted(row["run_number"] for row in results), list(range(2, 10)))
        self.assertTrue(all(row["scanner_invocations"] == 0 for row in results))
        self.assertEqual(self.read(self.state / "state.json")["payload"]["run_number"], 9)
        self.assertEqual(stat.S_IMODE((self.state / ".cycle.lock").stat().st_mode), 0o600)

    def test_six_concurrent_first_bootstraps_share_one_private_signing_key(self) -> None:
        self.assertFalse(self.state.exists())
        results = self._parallel_processes(count=6, cold_bootstrap=True)
        self.assertEqual(len({row["pid"] for row in results}), 6)
        self.assertEqual(sorted(row["run_number"] for row in results), list(range(1, 7)))
        self.assertEqual(sorted(row["scanner_invocations"] for row in results), [0, 0, 0, 0, 0, 4])
        self.assertEqual(self.read(self.state / "state.json")["payload"]["run_number"], 6)
        self.assert_owner_private_tree(self.state)

    def test_interprocess_lock_contention_times_out_before_scanner_construction(self) -> None:
        self.cycle()
        recipe = RecurringSecurityRecipe.from_files(
            configuration_path=self.config, inventory_path=self.inventory,
            approvals_path=self.approvals, state_directory=self.state,
        )
        lock = self.state / ".cycle.lock"
        held = self.private_root / "lock-held.ready"
        release = self.private_root / "release-lock.ready"
        program = (
            "import fcntl,os,sys,time;fd=os.open(sys.argv[1],os.O_RDWR);"
            "fcntl.flock(fd,fcntl.LOCK_EX);"
            "d=os.open(sys.argv[2],os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.close(d);"
            "deadline=time.monotonic()+10;"
            "\nwhile not os.path.exists(sys.argv[3]) and time.monotonic()<deadline:time.sleep(.005)\n"
            "fcntl.flock(fd,fcntl.LOCK_UN);os.close(fd)"
        )
        holder = subprocess.Popen([sys.executable, "-c", program, str(lock), str(held), str(release)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            deadline = time.monotonic() + 5
            while not held.exists():
                self.assertLess(time.monotonic(), deadline, "separate lock-holder process never became ready")
                time.sleep(0.004)
            original = recipe.store.cycle_lock
            with mock.patch.object(recipe.store, "cycle_lock", side_effect=lambda: original(timeout=0.08, poll_interval=0.005)):
                with mock.patch("fleet_security.recipe.SyntheticScanner") as scanner:
                    started = time.monotonic()
                    with self.assertRaisesRegex(EvidenceError, "timed out"):
                        recipe.cycle()
                    self.assertLess(time.monotonic() - started, 1)
                    scanner.assert_not_called()
            self.assertEqual(self.read(self.state / "state.json")["payload"]["run_number"], 1)
        finally:
            descriptor = os.open(release, os.O_CREAT | os.O_WRONLY, 0o600)
            os.close(descriptor)
            _, errors = holder.communicate(timeout=5)
            self.assertEqual(holder.returncode, 0, errors)

    def test_symbolic_cycle_lock_is_rejected_without_dispatch(self) -> None:
        self.cycle()
        lock = self.state / ".cycle.lock"
        target = self.private_root / "forged-lock"
        target.touch(mode=0o600)
        lock.unlink()
        lock.symlink_to(target)
        with self.assertRaisesRegex(EvidenceError, "symbolic link"):
            self.cycle()
        self.assertEqual(self.read(self.state / "state.json")["payload"]["run_number"], 1)

    def test_world_readable_cycle_lock_is_rejected_without_dispatch(self) -> None:
        self.cycle()
        lock = self.state / ".cycle.lock"
        lock.chmod(0o644)
        with self.assertRaisesRegex(EvidenceError, "0600"):
            self.cycle()

    def test_hard_linked_cycle_lock_is_rejected_without_dispatch(self) -> None:
        self.cycle()
        os.link(self.state / ".cycle.lock", self.private_root / "forged-hardlink")
        with self.assertRaisesRegex(EvidenceError, "regular 0600"):
            self.cycle()

    def test_cycle_lock_releases_after_exception(self) -> None:
        self.cycle()
        recipe = RecurringSecurityRecipe.from_files(
            configuration_path=self.config, inventory_path=self.inventory,
            approvals_path=self.approvals, state_directory=self.state,
        )
        with self.assertRaisesRegex(RuntimeError, "synthetic interruption"):
            with recipe.store.cycle_lock(timeout=1):
                raise RuntimeError("synthetic interruption")
        with recipe.store.cycle_lock(timeout=0.1):
            pass
        self.assertEqual(recipe.cycle()["run_number"], 2)

    def test_cycle_lock_rejects_unbounded_timeout_values(self) -> None:
        self.cycle()
        recipe = RecurringSecurityRecipe.from_files(
            configuration_path=self.config, inventory_path=self.inventory,
            approvals_path=self.approvals, state_directory=self.state,
        )
        for timeout in (0, -1, 61, float("nan"), float("inf"), True):
            with self.subTest(timeout=timeout), self.assertRaisesRegex(EvidenceError, "bounded finite"):
                with recipe.store.cycle_lock(timeout=timeout):
                    pass

    def test_twelve_process_style_restarts_reuse_signed_checkpoint_without_scans(self) -> None:
        first = self.cycle()
        runs = [self.cycle() for _ in range(12)]
        self.assertEqual(first["scanner_invocations"], 4)
        self.assertTrue(all(row["scanner_invocations"] == 0 for row in runs))
        self.assertEqual(runs[-1]["run_number"], 13)
        self.assertTrue(all(row["decision_states"] == EXPECTED_STATES for row in runs))

    def test_prompt_injection_remains_quarantined_across_six_restarts(self) -> None:
        self.cycle()
        for _ in range(6):
            result = self.cycle()
            self.assertEqual(result["quarantined_unchanged"], ["synthetic/adversarial-docs"])
            self.assertEqual(result["records"]["synthetic/adversarial-docs"]["status"], "failed_safe_abstention")
            self.assertEqual(result["scanner_invocations"], 0)

    def test_owner_private_state_tree_is_enforced_after_multiple_restarts(self) -> None:
        self.cycle()
        self.cycle()
        self.assert_owner_private_tree(self.state)

    def test_signed_checkpoint_tampering_fails_before_dispatch_and_backup_recovers(self) -> None:
        self.cycle()
        path = self.state / "state.json"
        original = path.read_bytes()
        envelope = self.read(path)
        envelope["payload"]["run_number"] = 987654
        self.save(path, envelope)
        with self.assertRaisesRegex(EvidenceError, "signature"):
            self.cycle()
        path.write_bytes(original)
        path.chmod(0o600)
        recovered = self.cycle()
        self.assertEqual((recovered["run_number"], recovered["scanner_invocations"]), (2, 0))

    def test_signed_checkpoint_signature_forgery_fails_before_dispatch(self) -> None:
        self.cycle()
        path = self.state / "state.json"
        envelope = self.read(path)
        envelope["signature"] = "0" * 64
        self.save(path, envelope)
        with self.assertRaisesRegex(EvidenceError, "signature"):
            self.cycle()

    def test_tampered_finding_is_refused_then_original_bytes_recover(self) -> None:
        self.cycle()
        path = self.artifact("payments-api", "findings.json")
        original = path.read_bytes()
        document = self.read(path)
        document["findings"][0]["title"] = "forged external disposition"
        self.save(path, document)
        with self.assertRaisesRegex(EvidenceError, "signed checkpoint"):
            self.cycle()
        path.write_bytes(original)
        path.chmod(0o600)
        self.assertEqual(self.cycle()["scanner_invocations"], 0)

    def test_tampered_coverage_is_refused_before_any_rescan(self) -> None:
        self.cycle()
        path = self.artifact("payments-api", "coverage.json")
        document = self.read(path)
        document["completeness"] = "partial"
        self.save(path, document)
        with self.assertRaises(EvidenceError):
            self.cycle()

    def test_removed_evidence_report_fails_closed(self) -> None:
        self.cycle()
        self.artifact("payments-api", "report.md").unlink()
        with self.assertRaisesRegex(EvidenceError, "missing"):
            self.cycle()

    def test_missing_signing_key_refuses_and_restored_key_recovers(self) -> None:
        self.cycle()
        key = self.state / ".local-state-key"
        backup = self.private_root / "synthetic-key-backup"
        os.replace(key, backup)
        with self.assertRaisesRegex(EvidenceError, "original host key"):
            self.cycle()
        os.replace(backup, key)
        self.assertEqual(self.cycle()["scanner_invocations"], 0)

    def test_insecure_state_root_mode_is_refused_and_private_mode_recovers(self) -> None:
        self.cycle()
        self.state.chmod(0o755)
        with self.assertRaisesRegex(EvidenceError, "0700"):
            self.cycle()
        self.state.chmod(0o700)
        self.assertEqual(self.cycle()["scanner_invocations"], 0)

    def test_world_readable_signing_key_is_rejected(self) -> None:
        self.cycle()
        (self.state / ".local-state-key").chmod(0o644)
        with self.assertRaisesRegex(EvidenceError, "0600"):
            self.cycle()

    def test_world_readable_evidence_is_rejected_and_private_mode_recovers(self) -> None:
        self.cycle()
        evidence = self.artifact("payments-api", "coverage.json")
        evidence.chmod(0o644)
        with self.assertRaisesRegex(EvidenceError, "owner-private"):
            self.cycle()
        evidence.chmod(0o600)
        self.assertEqual(self.cycle()["scanner_invocations"], 0)

    def test_symbolic_signed_checkpoint_is_rejected(self) -> None:
        self.cycle()
        state = self.state / "state.json"
        original = self.private_root / "state-copy.json"
        original.write_bytes(state.read_bytes())
        original.chmod(0o600)
        state.unlink()
        state.symlink_to(original)
        with self.assertRaisesRegex(EvidenceError, "symbolic link"):
            self.cycle()

    def test_scope_revocation_blocks_cached_evidence_without_rescan(self) -> None:
        self.cycle()
        document = self.read(self.approvals)
        document["approvals"] = [row for row in document["approvals"] if row["repository_id"] != "synthetic/payments-api"]
        self.save(self.approvals, document)
        result = self.cycle()
        self.assertEqual(result["records"]["synthetic/payments-api"]["status"], "awaiting_scope_approval")
        self.assertEqual(result["scanner_invocations"], 0)

    def test_stale_scope_owner_rejected_before_any_dispatch(self) -> None:
        approvals = self.read(self.approvals)
        approvals["approvals"][0]["service_owner"] = "stale-owner"
        self.save(self.approvals, approvals)
        with self.assertRaisesRegex(PipelineError, "currently named repository owner"):
            self.cycle()

    def test_forged_scope_actor_rejected_before_any_dispatch(self) -> None:
        approvals = self.read(self.approvals)
        approvals["approvals"][0]["actor"] = "untrusted-repository-actor"
        self.save(self.approvals, approvals)
        with self.assertRaisesRegex(PipelineError, "not authorised"):
            self.cycle()

    def test_stale_high_risk_threat_digest_rejected_before_dispatch(self) -> None:
        approvals = self.read(self.approvals)
        next(row for row in approvals["approvals"] if row["gate"] == "threat_model")["context_sha256"] = "f" * 64
        self.save(self.approvals, approvals)
        with self.assertRaisesRegex(PipelineError, "current effective context"):
            self.cycle()

    def test_high_risk_without_threat_approval_has_zero_attempts(self) -> None:
        result = self.cycle()["records"]["synthetic/restricted-worker"]
        self.assertEqual((result["status"], result["attempts"]), ("awaiting_threat_model_approval", 0))

    def test_missing_scope_has_zero_attempts(self) -> None:
        result = self.cycle()["records"]["synthetic/unapproved-service"]
        self.assertEqual((result["status"], result["attempts"]), ("awaiting_scope_approval", 0))

    def test_exact_named_finding_disposition_promotes_review_without_rescan(self) -> None:
        self.cycle()
        target = self.repository("payments-api")
        finding = self.read(self.artifact("payments-api", "findings.json"))["findings"][0]
        state = next(row for row in self.read(self.state / "state.json")["payload"]["states"]
                     if row["repository_id"] == target["repo_id"])
        approvals = self.read(self.approvals)
        approvals["approvals"].append({
            "gate": "finding_disposition",
            "repository_id": target["repo_id"],
            "revision": target["commit_sha"],
            "finding_id": finding["findingId"],
            "target_sha256": stable_digest({
                "repository_id": state["repository_id"],
                "commit_sha": state["reviewed_revision"],
                "idempotency_key": state["idempotency_key"],
                "finding_id": finding["findingId"],
            }),
            "expires_at": self.now + 3_600,
            "actor": "finding-owner",
        })
        self.save(self.approvals, approvals)
        result = self.cycle()
        self.assertEqual(result["records"][target["repo_id"]]["status"], "review_packet_ready")
        self.assertEqual(result["scanner_invocations"], 0)

    def test_changed_single_approved_revision_triggers_one_scan(self) -> None:
        self.cycle()
        inventory = self.read(self.inventory)
        row = next(item for item in inventory["repositories"] if item["repo_id"] == "synthetic/catalog-service")
        row["commit_sha"] = "b" * 40
        self.save(self.inventory, inventory)
        approvals = self.read(self.approvals)
        next(item for item in approvals["approvals"] if item["repository_id"] == row["repo_id"])["revision"] = row["commit_sha"]
        self.save(self.approvals, approvals)
        self.assertEqual(self.cycle()["scanner_invocations"], 1)

    def test_revalidation_expiry_rescans_only_three_clean_authorised_fixtures(self) -> None:
        self.cycle()
        self.now += 169 * 3600
        result = self.cycle()
        self.assertEqual((result["scanner_invocations"], len(result["revalidation_due"])), (3, 3))
        self.assertEqual(result["quarantined_unchanged"], ["synthetic/adversarial-docs"])

    def test_one_scan_limit_holds_three_remaining_authorised_fixtures(self) -> None:
        config = self.read(self.config)
        config["policy"]["max_scans_per_run"] = 1
        self.save(self.config, config)
        result = self.cycle()
        self.assertEqual(result["scanner_invocations"], 1)
        self.assertEqual(result["decision_states"]["deferred_rate_limit"], 3)

    def test_exhausted_campaign_capacity_never_dispatches(self) -> None:
        config = self.read(self.config)
        config["policy"]["max_campaign_units"] = 13
        self.save(self.config, config)
        result = self.cycle()
        self.assertEqual(result["scanner_invocations"], 0)
        self.assertEqual(result["decision_states"]["deferred_budget"], 4)

    def test_missing_human_deploy_owner_rejects_trusted_configuration(self) -> None:
        config = self.read(self.config)
        config["owners"].pop("deploy_owner")
        self.save(self.config, config)
        with self.assertRaisesRegex(PipelineError, "every human gate"):
            self.cycle()

    def test_provider_write_and_draft_pr_configuration_is_refused(self) -> None:
        config = self.read(self.config)
        config["policy"].update(allow_draft_pr=True, provider_write_authorised=True)
        self.save(self.config, config)
        with self.assertRaisesRegex(PipelineError, "never grants provider writes"):
            self.cycle()

    def test_disabled_human_merge_or_deploy_is_refused(self) -> None:
        for field in ("require_human_merge", "require_human_deploy"):
            with self.subTest(field=field):
                config = self.read(self.config)
                config["policy"][field] = False
                self.save(self.config, config)
                with self.assertRaisesRegex(PipelineError, "cannot be disabled"):
                    RecipeConfiguration.from_file(self.config)
                config["policy"][field] = True
                self.save(self.config, config)

    def test_missing_explicit_fixture_never_substitutes_clean_example(self) -> None:
        inventory = self.read(self.inventory)
        inventory["repositories"][0].pop("fixture")
        self.save(self.inventory, inventory)
        with self.assertRaisesRegex(PipelineError, "explicit synthetic fixture"):
            self.cycle()

    def test_non_synthetic_repository_identity_is_refused_before_state(self) -> None:
        inventory = self.read(self.inventory)
        inventory["repositories"][0]["repo_id"] = "fictional-private-company/private-repository"
        self.save(self.inventory, inventory)
        with self.assertRaisesRegex(PipelineError, "synthetic/"):
            self.cycle()
        self.assertFalse(self.state.exists())

    def test_modified_policy_without_named_policy_owner_is_rejected(self) -> None:
        self.cycle()
        config = self.read(self.config)
        config["policy"]["max_concurrent"] = 2
        self.save(self.config, config)
        with self.assertRaisesRegex(PipelineError, "policy-owner approval"):
            self.cycle()

    def test_named_exact_configuration_digest_allows_restart_without_rescan(self) -> None:
        self.cycle()
        config = self.read(self.config)
        config["policy"]["max_concurrent"] = 2
        self.save(self.config, config)
        approvals = self.read(self.approvals)
        approvals["approvals"].append({
            "gate": "policy_change",
            "repository_id": "fleet",
            "configuration_sha256": RecipeConfiguration.from_file(self.config).fingerprint,
            "expires_at": self.now + 3_600,
            "actor": "policy-owner",
        })
        self.save(self.approvals, approvals)
        result = self.cycle()
        self.assertEqual((result["run_number"], result["scanner_invocations"]), (2, 0))


if __name__ == "__main__":
    unittest.main()
