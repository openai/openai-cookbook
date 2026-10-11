"""Independent adversarial checks for durable, signed cross-run audit events."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
from unittest import mock

from stress_helpers import PrivateRecipeCase
from fleet_security.evidence import AuditLog, EvidenceError
from fleet_security.inventory import stable_digest
from fleet_security.recipe import RecurringSecurityRecipe
from fleet_security.scanner import SyntheticScanner


class DurableCrossRunAuditStress(PrivateRecipeCase):
    def audit(self, run: int) -> Path:
        return self.state / "audit" / f"run-{run:04d}.json"

    def expect_pre_dispatch_refusal(self, expression: str = "audit") -> None:
        with mock.patch.object(SyntheticScanner, "scan") as scan:
            with self.assertRaisesRegex(EvidenceError, expression):
                self.cycle()
        scan.assert_not_called()

    def test_first_cycle_persists_full_verified_event_chain(self) -> None:
        receipt = self.cycle()
        document = self.read(self.audit(1))
        self.assertGreater(document["event_count"], 0)
        self.assertEqual(document["event_count"], len(document["events"]))
        self.assertTrue(AuditLog().verify(tuple(document["events"])))
        self.assertEqual(receipt["durable_audit_event_count"], document["event_count"])

    def test_two_restarts_link_exact_previous_audit_digests(self) -> None:
        self.cycle()
        self.cycle()
        self.cycle()
        first, second, third = (self.read(self.audit(number)) for number in (1, 2, 3))
        self.assertEqual(first["previous_audit_digest"], "0" * 64)
        self.assertEqual(second["previous_audit_digest"], first["audit_digest"])
        self.assertEqual(third["previous_audit_digest"], second["audit_digest"])

    def test_signed_checkpoint_anchors_tail_run_and_event_count(self) -> None:
        self.cycle()
        self.cycle()
        state = self.read(self.state / "state.json")["payload"]
        documents = [self.read(self.audit(run)) for run in (1, 2)]
        self.assertEqual(state["audit_tail_digest"], documents[-1]["audit_digest"])
        self.assertEqual(state["audit_run_count"], 2)
        self.assertEqual(state["audit_event_count"], sum(row["event_count"] for row in documents))

    def test_all_audit_directories_and_files_are_owner_private(self) -> None:
        self.cycle()
        self.cycle()
        self.assertEqual(stat.S_IMODE((self.state / "audit").stat().st_mode), 0o700)
        for run in (1, 2):
            self.assertEqual(stat.S_IMODE(self.audit(run).stat().st_mode), 0o600)
            self.assertEqual(self.audit(run).stat().st_uid, os.geteuid())
        self.assert_owner_private_tree(self.state)

    def test_missing_prior_event_file_refuses_before_dispatch(self) -> None:
        self.cycle()
        self.audit(1).unlink()
        self.expect_pre_dispatch_refusal()

    def test_missing_audit_directory_refuses_before_dispatch(self) -> None:
        self.cycle()
        self.audit(1).unlink()
        (self.state / "audit").rmdir()
        self.expect_pre_dispatch_refusal()

    def test_tampered_event_text_refuses_before_dispatch(self) -> None:
        self.cycle()
        document = self.read(self.audit(1))
        document["events"][0]["event"] = "forged_named_human_approval"
        self.save(self.audit(1), document)
        self.expect_pre_dispatch_refusal()

    def test_tampered_event_hash_refuses_before_dispatch(self) -> None:
        self.cycle()
        document = self.read(self.audit(1))
        document["events"][0]["eventHash"] = "f" * 64
        self.save(self.audit(1), document)
        self.expect_pre_dispatch_refusal()

    def test_tampered_cross_run_digest_refuses_before_dispatch(self) -> None:
        self.cycle()
        self.cycle()
        document = self.read(self.audit(2))
        document["previous_audit_digest"] = "f" * 64
        self.save(self.audit(2), document)
        self.expect_pre_dispatch_refusal()

    def test_tampered_audit_envelope_digest_refuses_before_dispatch(self) -> None:
        self.cycle()
        document = self.read(self.audit(1))
        document["audit_digest"] = "f" * 64
        self.save(self.audit(1), document)
        self.expect_pre_dispatch_refusal()

    def test_recomputed_forged_audit_cannot_match_signed_tail(self) -> None:
        self.cycle()
        document = self.read(self.audit(1))
        document["organisation_id"] = "forged-organisation"
        unsigned = {key: value for key, value in document.items() if key != "audit_digest"}
        document["audit_digest"] = stable_digest(unsigned)
        self.save(self.audit(1), document)
        self.expect_pre_dispatch_refusal()

    def test_wrong_run_number_is_refused_before_dispatch(self) -> None:
        self.cycle()
        document = self.read(self.audit(1))
        document["run_number"] = 9001
        self.save(self.audit(1), document)
        self.expect_pre_dispatch_refusal()

    def test_empty_events_are_refused_before_dispatch(self) -> None:
        self.cycle()
        document = self.read(self.audit(1))
        document["events"] = []
        document["event_count"] = 0
        self.save(self.audit(1), document)
        self.expect_pre_dispatch_refusal()

    def test_unexpected_audit_artifact_is_refused_before_dispatch(self) -> None:
        self.cycle()
        additional = self.state / "audit" / "unapproved.json"
        self.save(additional, {"unexpected": True})
        self.expect_pre_dispatch_refusal()

    def test_world_readable_audit_file_is_refused_before_dispatch(self) -> None:
        self.cycle()
        self.audit(1).chmod(0o644)
        self.expect_pre_dispatch_refusal("0600|owner-private|audit")

    def test_world_readable_audit_directory_is_refused_before_dispatch(self) -> None:
        self.cycle()
        (self.state / "audit").chmod(0o755)
        self.expect_pre_dispatch_refusal("0700|owner-private|audit")

    def test_audit_file_symbolic_link_is_refused_before_dispatch(self) -> None:
        self.cycle()
        original = self.private_root / "audit-original.json"
        original.write_bytes(self.audit(1).read_bytes())
        original.chmod(0o600)
        self.audit(1).unlink()
        self.audit(1).symlink_to(original)
        self.expect_pre_dispatch_refusal("symbolic|audit")

    def test_audit_directory_symbolic_link_is_refused_before_dispatch(self) -> None:
        self.cycle()
        directory = self.state / "audit"
        moved = self.private_root / "moved-audit"
        directory.rename(moved)
        directory.symlink_to(moved, target_is_directory=True)
        self.expect_pre_dispatch_refusal("symbolic|audit")

    def test_signed_state_rollback_with_newer_audit_is_refused(self) -> None:
        self.cycle()
        first_state = (self.state / "state.json").read_bytes()
        self.cycle()
        (self.state / "state.json").write_bytes(first_state)
        self.expect_pre_dispatch_refusal()

    def test_original_authenticated_event_bytes_recover_idempotently(self) -> None:
        self.cycle()
        self.cycle()
        path = self.audit(1)
        original = path.read_bytes()
        document = self.read(path)
        document["events"][0]["event"] = "forged"
        self.save(path, document)
        self.expect_pre_dispatch_refusal()
        path.write_bytes(original)
        path.chmod(0o600)
        receipt = self.cycle()
        self.assertEqual(receipt["run_number"], 3)
        self.assertEqual(receipt["scanner_invocations"], 0)
        self.assertTrue(receipt["durable_audit_valid"])

    def test_audit_event_metadata_contains_no_secret_keys(self) -> None:
        self.cycle()
        forbidden = {"secret", "token", "api_key", "credential", "source", "prompt"}
        for event in self.read(self.audit(1))["events"]:
            self.assertTrue(all(not any(word in key.casefold() for word in forbidden)
                                for key in event["metadata"]))

    def test_failed_state_write_removes_uncommitted_audit_file(self) -> None:
        self.cycle()
        recipe = RecurringSecurityRecipe.from_files(
            configuration_path=self.config,
            inventory_path=self.inventory,
            approvals_path=self.approvals,
            state_directory=self.state,
        )
        with mock.patch.object(recipe.store, "write", side_effect=OSError("synthetic state write failure")):
            with self.assertRaises(OSError):
                recipe.cycle()
        self.assertFalse(self.audit(2).exists())
        recovered = self.cycle()
        self.assertEqual((recovered["run_number"], recovered["scanner_invocations"]), (2, 0))

    def test_legacy_signed_state_without_audit_anchor_fails_closed(self) -> None:
        self.cycle()
        recipe = RecurringSecurityRecipe.from_files(
            configuration_path=self.config,
            inventory_path=self.inventory,
            approvals_path=self.approvals,
            state_directory=self.state,
        )
        payload = recipe.store.read()
        assert payload is not None
        for key in ("audit_tail_digest", "audit_run_count", "audit_event_count"):
            payload.pop(key, None)
        recipe.store.write(payload)
        self.expect_pre_dispatch_refusal("audit|legacy")
