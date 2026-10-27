from __future__ import annotations

import unittest
from dataclasses import replace

from support import repository
from fleet_security import ThreatCatalogue, compare_strategies, generate_inventory


class HierarchicalThreatModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.catalogue = ThreatCatalogue()

    def test_standard_repository_inherits_platform_archetype_and_its_delta(self) -> None:
        assignment = self.catalogue.assign(repository())
        self.assertEqual(assignment.organisation_model_id, "synthetic-org-v1")
        self.assertEqual(assignment.archetype_model_id, "python:fastapi:container:private")
        self.assertIsNone(assignment.repository_model_id)
        self.assertEqual(assignment.delta["data_class"], "internal")
        self.assertFalse(assignment.requires_human_acceptance)

    def test_high_risk_repository_receives_full_bespoke_model_and_human_gate(self) -> None:
        record = repository(criticality="critical", data_class="restricted")
        assignment = self.catalogue.assign(record)
        self.assertEqual(assignment.repository_model_id, f"repository:{record.repo_id}")
        self.assertTrue(assignment.requires_human_acceptance)
        self.assertIn("regulated_data_boundary", assignment.covered_scenarios)

    def test_materially_unique_repository_receives_bespoke_boundary_coverage(self) -> None:
        assignment = self.catalogue.assign(repository(material_divergence=True))
        self.assertTrue(assignment.requires_human_acceptance)
        self.assertIn("bespoke_trust_boundary", assignment.covered_scenarios)

    def test_effective_hash_changes_with_platform_archetype_and_delta(self) -> None:
        record = repository()
        initial = self.catalogue.assign(record).effective_model_hash
        self.assertNotEqual(initial, ThreatCatalogue(version="synthetic-org-v2").assign(record).effective_model_hash)
        self.assertNotEqual(initial, self.catalogue.assign(replace(record, topology="serverless")).effective_model_hash)
        self.assertNotEqual(initial, self.catalogue.assign(replace(record, data_class="confidential")).effective_model_hash)

    def test_platform_drift_propagates_to_every_impacted_repository(self) -> None:
        fleet = generate_inventory(50)
        updated = ThreatCatalogue(version="synthetic-org-v2")
        self.assertEqual(sum(
            self.catalogue.assign(record).effective_model_hash != updated.assign(record).effective_model_hash
            for record in fleet
        ), 50)

    def test_archetype_override_changes_only_its_matching_workload(self) -> None:
        primary = repository()
        other = repository(2, language="go", framework="stdlib")
        changed = ThreatCatalogue(archetype_overrides={
            "python:fastapi:container:private": ("workload_specific_attack",),
        })
        self.assertNotEqual(self.catalogue.assign(primary).effective_model_hash, changed.assign(primary).effective_model_hash)
        self.assertEqual(self.catalogue.assign(other).effective_model_hash, changed.assign(other).effective_model_hash)

    def test_full_fleet_comparison_preserves_complete_coverage_with_fewer_reviewer_models(self) -> None:
        comparison = compare_strategies(generate_inventory(2_000), self.catalogue)
        individual = comparison["per_repository"]
        shared = comparison["shared"]
        hierarchical = comparison["hierarchical"]
        self.assertEqual(individual["coverage_percent"], 100)
        self.assertEqual(hierarchical["coverage_percent"], 100)
        self.assertLess(shared["coverage_percent"], 100)
        self.assertEqual(individual["reviewer_artifacts"], 2_000)
        self.assertLess(hierarchical["reviewer_artifacts"], 100)
        self.assertEqual(hierarchical["archetype_models"], 10)
        self.assertEqual(hierarchical["high_risk_repositories"], hierarchical["high_risk_fully_covered"])

    def test_hierarchy_limits_platform_drift_and_synthetic_context_units(self) -> None:
        comparison = compare_strategies(generate_inventory(2_000))
        individual = comparison["per_repository"]
        hierarchical = comparison["hierarchical"]
        self.assertEqual(individual["platform_drift_model_updates"], 2_000)
        self.assertEqual(hierarchical["platform_drift_model_updates"], 1)
        self.assertLess(hierarchical["synthetic_relative_context_units"], individual["synthetic_relative_context_units"])

    def test_empty_or_unknown_strategy_fails_closed(self) -> None:
        with self.assertRaises(ValueError):
            compare_strategies(())
        with self.assertRaises(ValueError):
            self.catalogue.assign(repository(), strategy="invented")


if __name__ == "__main__":
    unittest.main()
