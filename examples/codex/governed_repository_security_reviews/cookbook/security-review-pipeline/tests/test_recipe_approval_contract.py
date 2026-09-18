"""Exact, expiring approval bindings and previously trusted owner transitions.

All identities, findings and repository contents are fictional. These checks
never invoke a live scanner, provider write, model API or customer repository.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


ROOT = next(parent for parent in Path(__file__).resolve().parents
            if (parent / "src" / "fleet_security" / "recipe.py").is_file())
sys.path.insert(0, str(ROOT / "src"))

from fleet_security.evidence import EvidenceError  # noqa: E402
from fleet_security.inventory import stable_digest  # noqa: E402
from fleet_security.pipeline import FleetPolicy, PipelineError  # noqa: E402
from fleet_security.recipe import (  # noqa: E402
    DurableRecipeStore, RecipeConfiguration, RecurringSecurityRecipe, load_recipe_inventory,
)
from fleet_security.threats import ThreatCatalogue  # noqa: E402


class RecipeApprovalContractTests(unittest.TestCase):
    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory(prefix="recipe-approval-contract-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.config = self.root / "config.json"
        self.inventory = self.root / "inventory.json"
        self.approvals = self.root / "approvals.json"
        self.state = self.root / "state"
        examples = ROOT / "cookbook" / "security-review-pipeline"
        self.configuration = json.loads((examples / "config.example.json").read_text())
        rows = json.loads((examples / "inventory.example.json").read_text())["repositories"]
        self.record = next(row for row in rows if row["repo_id"] == "synthetic/catalog-service")
        self.record["fixture"] = "vulnerable_service"
        scope = next(row for row in json.loads((examples / "approvals.example.json").read_text())["approvals"]
                     if row["repository_id"] == self.record["repo_id"] and row["gate"] == "scope")
        self.scope = scope
        self.grants = [deepcopy(scope)]
        self.now = 1_788_000_000

    def materialise(self) -> None:
        self.config.write_text(json.dumps(self.configuration))
        self.inventory.write_text(json.dumps({"repositories": [self.record]}))
        self.approvals.write_text(json.dumps({"approvals": self.grants}))

    def cycle(self) -> dict:
        self.materialise()
        return self.recipe().cycle()

    def recipe(self) -> RecurringSecurityRecipe:
        return RecurringSecurityRecipe.from_files(
            configuration_path=self.config, inventory_path=self.inventory,
            approvals_path=self.approvals, state_directory=self.state, clock=lambda: self.now,
        )

    def config_grant(self, *, actor: str = "policy-owner") -> dict:
        self.config.write_text(json.dumps(self.configuration))
        return {
            "gate": "policy_change", "repository_id": "fleet", "actor": actor,
            "configuration_sha256": RecipeConfiguration.from_file(self.config).fingerprint,
            "expires_at": self.now + 3_600,
        }

    def saved_state(self) -> dict:
        return json.loads((self.state / "state.json").read_text())["payload"]

    def finding_grant(self, gate: str = "finding_disposition") -> dict:
        reviewed = self.saved_state()["states"][0]
        finding_id = reviewed["current_findings"][0]["findingId"]
        actors = {"finding_disposition": "finding-owner", "patch": "patch-owner", "exception": "risk-owner"}
        return {
            "gate": gate, "repository_id": reviewed["repository_id"],
            "revision": reviewed["reviewed_revision"], "finding_id": finding_id,
            "target_sha256": stable_digest({
                "repository_id": reviewed["repository_id"], "commit_sha": reviewed["reviewed_revision"],
                "idempotency_key": reviewed["idempotency_key"], "finding_id": finding_id,
            }),
            "actor": actors[gate], "expires_at": self.now + 3_600,
        }

    def context_digest(self) -> str:
        self.materialise()
        configuration = RecipeConfiguration.from_file(self.config)
        catalogue = ThreatCatalogue(organisation_controls=configuration.organisation_controls,
                                     version=configuration.organisation_model_version)
        return catalogue.assign(load_recipe_inventory(self.inventory)[0]).effective_model_hash

    def reject_without_dispatch(self, *, exception_type=PipelineError, message: str | None = None) -> None:
        checkpoint = self.state / "state.json"
        before = checkpoint.read_bytes() if checkpoint.exists() else None
        with mock.patch("fleet_security.recipe.SyntheticScanner.scan", side_effect=AssertionError("dispatch forbidden")):
            if message is None:
                with self.assertRaises(exception_type):
                    self.cycle()
            else:
                with self.assertRaisesRegex(exception_type, message):
                    self.cycle()
        if before is not None:
            self.assertEqual((self.state / "state.json").read_bytes(), before)

    def test_fresh_state_persists_all_trusted_roles_and_restarts_without_rescan(self) -> None:
        self.assertEqual(self.cycle()["scanner_invocations"], 1)
        self.assertEqual(self.saved_state()["trusted_owner_policy"], self.configuration["owners"])
        self.assertEqual(self.cycle()["scanner_invocations"], 0)

    def test_legacy_policy_only_grant_is_rejected(self) -> None:
        self.grants.append({
            "gate": "policy_change", "repository_id": "fleet", "actor": "policy-owner",
            "policy_sha256": stable_digest(asdict(FleetPolicy(**self.configuration["policy"]))),
            "expires_at": self.now + 3_600,
        })
        self.reject_without_dispatch(message="missing required fields|unsupported constraints")

    def test_full_configuration_approval_allows_the_exact_budget_change(self) -> None:
        self.cycle()
        self.configuration["policy"]["max_concurrent"] = 2
        self.grants.append(self.config_grant())
        receipt = self.cycle()
        self.assertEqual((receipt["run_number"], receipt["scanner_invocations"]), (2, 0))
        self.assertEqual(self.saved_state()["configuration_hash"], self.config_grant()["configuration_sha256"])
        events = json.loads((self.state / "audit" / "run-0002.json").read_text())["events"]
        approved = next(event for event in events if event["event"] == "configuration_change_approved")
        self.assertEqual(approved["metadata"]["actor"], "policy-owner")
        self.assertEqual(approved["metadata"]["configuration_sha256"], self.saved_state()["configuration_hash"])

    def test_old_full_configuration_grant_does_not_cover_other_configuration_fields(self) -> None:
        self.grants.append(self.config_grant())
        self.cycle()
        baseline = deepcopy(self.configuration)
        mutations = [
            lambda value: value["organisation_controls"].append("new_control"),
            lambda value: value.update(organisation_model_version="different-baseline"),
            lambda value: value["model_selection"].update(model="gpt-different-model"),
            lambda value: value["model_selection"].update(effort="medium"),
            lambda value: value["model_selection"].update(approved=True),
            lambda value: value["model_selection"].update(owner="different-spend-owner"),
            lambda value: value["owners"].update(security_reviewer=["new-reviewer"]),
            lambda value: value.update(periodic_revalidation_hours=24),
        ]
        for index, mutate in enumerate(mutations):
            with self.subTest(mutation=index):
                self.configuration = deepcopy(baseline)
                mutate(self.configuration)
                self.reject_without_dispatch(message="exact full trusted configuration")

    def test_new_policy_owner_cannot_self_authorise_appointment(self) -> None:
        self.cycle()
        self.configuration["owners"]["policy_owner"] = ["self-appointed-owner"]
        self.grants.append(self.config_grant(actor="self-appointed-owner"))
        self.reject_without_dispatch(message="not authorised")

    def test_prior_policy_owner_can_authorise_exact_owner_handover(self) -> None:
        self.cycle()
        self.configuration["owners"]["policy_owner"] = ["successor-owner"]
        self.grants.append(self.config_grant())
        self.cycle()
        self.assertEqual(self.saved_state()["trusted_owner_policy"]["policy_owner"], ["successor-owner"])
        # Consumed transition grants are removed; only the successor may approve
        # the next configuration change under the newly signed owner policy.
        self.configuration["periodic_revalidation_hours"] = 24
        self.grants = [deepcopy(self.scope), self.config_grant(actor="successor-owner")]
        self.assertEqual(self.cycle()["run_number"], 3)

    def test_retired_policy_owner_cannot_authorise_a_later_configuration(self) -> None:
        self.cycle()
        self.configuration["owners"]["policy_owner"] = ["successor-owner"]
        self.grants.append(self.config_grant())
        self.cycle()
        self.configuration["periodic_revalidation_hours"] = 24
        self.grants = [deepcopy(self.scope), self.config_grant(actor="policy-owner")]
        self.reject_without_dispatch(message="not authorised")

    def test_policy_change_requires_future_whole_second_expiry(self) -> None:
        self.cycle()
        self.configuration["policy"]["max_concurrent"] = 2
        for expiry in (None, False, 1.5, "tomorrow", self.now - 1, self.now):
            with self.subTest(expiry=expiry):
                grant = self.config_grant()
                grant["expires_at"] = expiry
                self.grants = [deepcopy(self.scope), grant]
                self.reject_without_dispatch(message="expiration")

    def test_policy_change_without_expiry_is_rejected(self) -> None:
        self.cycle()
        self.configuration["policy"]["max_concurrent"] = 2
        grant = self.config_grant()
        del grant["expires_at"]
        self.grants.append(grant)
        self.reject_without_dispatch(message="missing required fields")

    def test_wrong_full_configuration_hash_cannot_authorise_change(self) -> None:
        self.cycle()
        self.configuration["policy"]["max_concurrent"] = 2
        grant = self.config_grant()
        grant["configuration_sha256"] = "0" * 64
        self.grants.append(grant)
        self.reject_without_dispatch(message="exact full trusted configuration")

    def test_signed_legacy_state_without_previous_owners_fails_closed(self) -> None:
        self.cycle()
        store = DurableRecipeStore(self.state)
        payload = store.read()
        del payload["trusted_owner_policy"]
        store.write(payload)
        self.configuration["owners"]["policy_owner"] = ["self-appointed-owner"]
        self.grants.append(self.config_grant(actor="self-appointed-owner"))
        self.reject_without_dispatch(exception_type=EvidenceError, message="previous owner policy")

    def test_malformed_signed_previous_owner_policy_fails_closed(self) -> None:
        self.cycle()
        original = self.saved_state()
        for owners in ({}, {"policy_owner": ["attacker"]}, {**self.configuration["owners"], "policy_owner": []},
                       {**self.configuration["owners"], "policy_owner": ["policy-owner", "policy-owner"]}):
            with self.subTest(owners=owners):
                payload = deepcopy(original)
                payload["trusted_owner_policy"] = owners
                DurableRecipeStore(self.state).write(payload)
                self.reject_without_dispatch(exception_type=EvidenceError, message="previous owner policy")

    def test_signed_owner_policy_must_agree_with_unchanged_configuration_hash(self) -> None:
        self.cycle()
        payload = self.saved_state()
        payload["trusted_owner_policy"]["policy_owner"] = ["different-owner"]
        DurableRecipeStore(self.state).write(payload)
        self.reject_without_dispatch(exception_type=EvidenceError, message="contradicts")

    def test_unsigned_previous_owner_policy_change_fails_before_dispatch(self) -> None:
        self.cycle()
        path = self.state / "state.json"
        envelope = json.loads(path.read_text())
        envelope["payload"]["trusted_owner_policy"]["policy_owner"] = ["attacker"]
        path.write_text(json.dumps(envelope))
        self.reject_without_dispatch(exception_type=EvidenceError, message="signature")

    def test_exact_finding_target_and_expiry_allow_review_without_rescan(self) -> None:
        self.cycle()
        self.grants.append(self.finding_grant())
        result = self.cycle()
        self.assertEqual(result["scanner_invocations"], 0)
        self.assertEqual(result["records"][self.record["repo_id"]]["status"], "review_packet_ready")
        self.assertEqual(result["external_writes"], 0)

    def test_exact_exception_target_with_future_expiry_allows_review_without_rescan(self) -> None:
        self.cycle()
        self.grants.append(self.finding_grant("exception"))
        result = self.cycle()
        self.assertEqual(result["scanner_invocations"], 0)
        self.assertEqual(result["records"][self.record["repo_id"]]["named_reviewers"]["exception"], "risk-owner")

    def test_valid_patch_grant_does_not_enable_provider_writes(self) -> None:
        self.cycle()
        self.grants.extend([self.finding_grant(), self.finding_grant("patch")])
        result = self.cycle()
        self.assertEqual(result["records"][self.record["repo_id"]]["route"], "review_packet")
        self.assertFalse(result["automatic_pr_merge_or_deploy"])
        self.assertEqual(result["external_writes"], 0)

    def test_every_post_scan_gate_requires_supplied_target_and_expiry(self) -> None:
        self.cycle()
        for gate in ("finding_disposition", "patch", "exception"):
            for field in ("target_sha256", "expires_at"):
                with self.subTest(gate=gate, missing=field):
                    grant = self.finding_grant(gate)
                    del grant[field]
                    self.grants = [deepcopy(self.scope), grant]
                    self.reject_without_dispatch(message="missing required fields")

    def test_every_post_scan_gate_rejects_wrong_target(self) -> None:
        self.cycle()
        for gate in ("finding_disposition", "patch", "exception"):
            with self.subTest(gate=gate):
                grant = self.finding_grant(gate)
                grant["target_sha256"] = "0" * 64
                self.grants = [deepcopy(self.scope), grant]
                self.reject_without_dispatch(message="exact current context")

    def test_every_post_scan_gate_rejects_expired_or_malformed_expiry(self) -> None:
        self.cycle()
        for gate in ("finding_disposition", "patch", "exception"):
            for expiry in (self.now, self.now - 1, True, None, float("inf"), "later"):
                with self.subTest(gate=gate, expiry=expiry):
                    grant = self.finding_grant(gate)
                    grant["expires_at"] = expiry
                    self.grants = [deepcopy(self.scope), grant]
                    self.reject_without_dispatch(message="expiration")

    def test_unchanged_finding_does_not_reuse_an_expired_disposition(self) -> None:
        self.cycle()
        self.grants.append(self.finding_grant())
        self.assertEqual(self.cycle()["records"][self.record["repo_id"]]["status"], "review_packet_ready")
        self.now += 3_600
        self.reject_without_dispatch(message="expiration")

    def test_same_revision_changed_context_rejects_each_old_post_scan_target(self) -> None:
        self.cycle()
        grants = {gate: self.finding_grant(gate) for gate in ("finding_disposition", "patch", "exception")}
        self.record["controls"] = sorted(set(self.record["controls"]) | {"new_control"})
        for gate, grant in grants.items():
            with self.subTest(gate=gate):
                self.grants = [deepcopy(self.scope), grant]
                self.reject_without_dispatch(message="exact current context")

    def test_old_target_rejected_when_scanner_or_policy_version_changes(self) -> None:
        self.cycle()
        original = deepcopy(self.configuration)
        old_finding = self.finding_grant()
        for field in ("scanner_version", "policy_version"):
            with self.subTest(field=field):
                self.configuration = deepcopy(original)
                self.configuration["policy"][field] += "-next"
                self.grants = [deepcopy(self.scope), self.config_grant(), old_finding]
                self.reject_without_dispatch(message="exact current context")

    def test_reissued_target_after_context_rescan_allows_only_the_new_review(self) -> None:
        self.cycle()
        old = self.finding_grant()
        self.record["controls"] = sorted(set(self.record["controls"]) | {"new_control"})
        self.assertEqual(self.cycle()["scanner_invocations"], 1)
        current = self.finding_grant()
        self.assertNotEqual(old["target_sha256"], current["target_sha256"])
        self.grants.append(current)
        self.assertEqual(self.cycle()["records"][self.record["repo_id"]]["status"], "review_packet_ready")

    def test_supplied_context_is_checked_even_with_valid_target(self) -> None:
        self.cycle()
        for gate in ("finding_disposition", "patch", "exception"):
            with self.subTest(gate=gate):
                grant = self.finding_grant(gate)
                grant["context_sha256"] = "0" * 64
                self.grants = [deepcopy(self.scope), grant]
                self.reject_without_dispatch(message="contradictory effective-context")

    def test_correct_optional_context_and_target_allow_disposition(self) -> None:
        self.cycle()
        grant = self.finding_grant()
        grant["context_sha256"] = self.context_digest()
        self.grants.append(grant)
        self.assertEqual(self.cycle()["records"][self.record["repo_id"]]["status"], "review_packet_ready")

    def test_changed_finding_id_does_not_reuse_another_findings_target(self) -> None:
        self.cycle()
        grant = self.finding_grant()
        grant["finding_id"] += "_other"
        self.grants.append(grant)
        self.reject_without_dispatch(message="exact current context")

    def test_unknown_constraints_are_rejected_for_every_gate(self) -> None:
        self.cycle()
        threat = {"gate": "threat_model", "repository_id": self.record["repo_id"],
                  "revision": self.record["commit_sha"], "context_sha256": self.context_digest(),
                  "actor": "threat-owner"}
        candidates = [deepcopy(self.scope), threat, self.config_grant(),
                      *[self.finding_grant(gate) for gate in ("finding_disposition", "patch", "exception")]]
        for grant in candidates:
            with self.subTest(gate=grant["gate"]):
                grant["ignore_this_constraint"] = "must-not-be-ignored"
                self.grants = [grant]
                self.reject_without_dispatch(message="unsupported constraints")

    def test_duplicate_grants_are_rejected_instead_of_last_wins(self) -> None:
        self.cycle()
        self.grants.append(deepcopy(self.scope))
        self.reject_without_dispatch(message="duplicate grants")

    def test_duplicate_json_fields_are_rejected_even_when_last_value_is_valid(self) -> None:
        self.materialise()
        encoded = json.dumps({"approvals": self.grants})
        encoded = encoded.replace('"actor": "security-owner"', '"actor": "untrusted", "actor": "security-owner"')
        self.approvals.write_text(encoded)
        with mock.patch("fleet_security.recipe.SyntheticScanner.scan", side_effect=AssertionError("dispatch forbidden")):
            with self.assertRaisesRegex(PipelineError, "duplicate fields"):
                self.recipe().cycle()

    def test_malformed_approval_identities_fail_as_policy_errors(self) -> None:
        for field, value in (("gate", []), ("actor", {}), ("repository_id", [])):
            with self.subTest(field=field):
                grant = deepcopy(self.scope)
                grant[field] = value
                self.grants = [grant]
                self.reject_without_dispatch()

    def test_supplied_scope_expiry_is_checked_but_omission_preserves_fixture_contract(self) -> None:
        self.cycle()
        self.assertEqual(self.cycle()["scanner_invocations"], 0)
        self.grants[0]["expires_at"] = self.now
        self.reject_without_dispatch(message="expiration")


if __name__ == "__main__":
    unittest.main()
