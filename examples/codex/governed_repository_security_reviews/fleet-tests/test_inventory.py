from __future__ import annotations

import hashlib
import unittest
from dataclasses import replace

from support import repository
from fleet_security import InventoryError, classify, generate_inventory, load_inventory


class InventoryValidationTests(unittest.TestCase):
    def test_generates_exactly_two_thousand_distinct_owner_attributed_repositories(self) -> None:
        fleet = generate_inventory(2_000)
        self.assertEqual(len(fleet), 2_000)
        self.assertEqual(len({row.repo_id for row in fleet}), 2_000)
        self.assertEqual(len({row.owner for row in fleet}), 25)

    def test_full_40_and_64_character_revisions_are_accepted(self) -> None:
        self.assertEqual(len(repository().commit_sha), 40)
        sha64 = hashlib.sha256(b"synthetic").hexdigest()
        self.assertEqual(replace(repository(), commit_sha=sha64).commit_sha, sha64)

    def test_partial_uppercase_and_symbolic_revisions_fail_closed(self) -> None:
        for candidate in ("main", "deadbeef", "a" * 39, "A" * 40, "a" * 41, "a" * 63):
            with self.subTest(candidate=candidate), self.assertRaises(InventoryError):
                replace(repository(), commit_sha=candidate)

    def test_unknown_owner_and_missing_core_attributes_are_rejected(self) -> None:
        for changes in ({"owner": ""}, {"owner": "unknown owner"}, {"language": "unknown"},
                        {"data_class": ""}, {"exposure": "unknown"}, {"authentication": "saml"}):
            with self.subTest(changes=changes), self.assertRaises(InventoryError):
                replace(repository(), **changes)

    def test_duplicate_identical_rows_are_idempotent(self) -> None:
        row = repository()
        self.assertEqual(load_inventory((row, row)), (row,))

    def test_contradictory_revision_owner_or_exposure_is_rejected(self) -> None:
        row = repository()
        for changes in ({"owner": "replacement-owner"}, {"exposure": "internet"},
                        {"commit_sha": hashlib.sha1(b"replacement").hexdigest()}):
            with self.subTest(changes=changes), self.assertRaises(InventoryError):
                load_inventory((row, replace(row, **changes)))

    def test_dependency_and_control_order_are_canonical(self) -> None:
        for changes in ({"dependencies": ("z", "a")}, {"controls": ("x", "x")}):
            with self.subTest(changes=changes), self.assertRaises(InventoryError):
                replace(repository(), **changes)

    def test_changed_path_traversal_and_absolute_paths_are_rejected(self) -> None:
        for path in ("../secret", "/private/secret", "~/.ssh/id", "src\\..\\secret"):
            with self.subTest(path=path), self.assertRaises(InventoryError):
                replace(repository(), changed_paths=(path,))

    def test_classification_includes_archetype_owner_data_and_authentication(self) -> None:
        value = classify(repository())
        self.assertEqual(value.archetype, "python:fastapi:container:private")
        self.assertEqual(value.attributes["owner"], "named-owner")
        self.assertEqual(value.attributes["data_class"], "internal")
        self.assertEqual(value.attributes["authentication"], "service_identity")

    def test_material_boundary_changes_update_hash_but_revision_does_not(self) -> None:
        record = repository()
        self.assertEqual(record.boundary_hash, replace(record, commit_sha="a" * 40).boundary_hash)
        for changes in ({"data_class": "restricted"}, {"exposure": "internet"},
                        {"authentication": "mtls"}, {"controls": ("extra",)}):
            with self.subTest(changes=changes):
                self.assertNotEqual(record.boundary_hash, replace(record, **changes).boundary_hash)

    def test_high_risk_classification_uses_criticality_exposure_and_divergence(self) -> None:
        self.assertEqual(repository().risk_tier, "standard")
        for changes in ({"criticality": "critical"}, {"material_divergence": True},
                        {"exposure": "internet", "authentication": "none"},
                        {"exposure": "internet", "data_class": "restricted"}):
            with self.subTest(changes=changes):
                self.assertEqual(replace(repository(), **changes).risk_tier, "high")

    def test_invalid_fleet_size_fails_closed(self) -> None:
        for size in (0, -1, 20_001, True):
            with self.subTest(size=size), self.assertRaises(InventoryError):
                generate_inventory(size)


if __name__ == "__main__":
    unittest.main()
