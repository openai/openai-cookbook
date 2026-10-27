"""Independent synthetic labels detect missing context without paid model calls."""
from __future__ import annotations

import copy
from dataclasses import replace
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "evaluate_threat_context.py"
CASES = ROOT / "evals" / "security_context_cases.json"
SPEC = importlib.util.spec_from_file_location("independent_context_eval", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
EVAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(EVAL)


class IndependentThreatContextTests(unittest.TestCase):
    def setUp(self) -> None:
        self.cases = EVAL.load_cases(CASES)

    def result(self, **options):
        return EVAL.evaluate(self.cases, metadata_records=0, **options)

    def test_explicit_labels_compare_all_strategies_without_a_generated_oracle(self) -> None:
        report = self.result()
        self.assertEqual(report["status"], "PASS")
        self.assertEqual((report["labelled_cases"], report["labelled_scenario_occurrences"]), (8, 45))
        self.assertEqual(report["unique_baseline_scenario_labels"], 12)
        for strategy in ("per_repository", "hierarchical"):
            row = report["strategies"][strategy]
            self.assertEqual(row["status"], "PASS")
            self.assertEqual(row["summary"]["exact_label_matches"], 8)
            self.assertEqual(row["summary"]["matched_label_occurrences"], 45)
            self.assertEqual(row["summary"]["missing_label_occurrences"], 0)
            self.assertEqual(row["summary"]["extra_label_occurrences"], 0)
        shared = report["strategies"]["shared"]["summary"]
        self.assertEqual((shared["exact_label_matches"], shared["matched_label_occurrences"]), (1, 24))
        self.assertEqual(shared["missing_label_occurrences"], 21)
        self.assertEqual(report["strategies"]["shared"]["status"], "FAIL")

    def test_each_declared_high_risk_case_retains_human_and_bespoke_gates(self) -> None:
        rows = self.result()["strategies"]
        for strategy in ("per_repository", "hierarchical"):
            summary = rows[strategy]["summary"]
            self.assertEqual(summary["human_acceptance_required"], 4)
            self.assertEqual(summary["human_acceptance_matches"], 8)
            self.assertEqual(summary["required_bespoke_present"], 4)
        self.assertEqual(rows["shared"]["summary"]["human_acceptance_observed"], 4)
        self.assertEqual(rows["shared"]["summary"]["required_bespoke_present"], 0)

    def test_deleting_a_real_catalogue_scenario_fails_the_independent_labels(self) -> None:
        original = EVAL.ThreatCatalogue._archetype_scenarios

        def omit_authentication(catalogue, repository, classification):
            return original(catalogue, repository, classification) - {"authentication_bypass"}

        with patch.object(EVAL.ThreatCatalogue, "_archetype_scenarios", omit_authentication):
            report = self.result()
        self.assertEqual(report["status"], "FAIL")
        observed = report["strategies"]["hierarchical"]
        self.assertEqual(observed["summary"]["missing_label_occurrences"], 3)
        self.assertEqual(observed["cases"]["public-api"]["missing_labels"], ["authentication_bypass"])

    def test_extra_scenarios_are_reported_instead_of_hidden_by_recall_only(self) -> None:
        original = EVAL.ThreatCatalogue._unique_scenarios
        with patch.object(EVAL.ThreatCatalogue, "_unique_scenarios", staticmethod(
            lambda record: original(record) | {"unexpected_synthetic_scenario"}
        )):
            report = self.result()
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(report["strategies"]["hierarchical"]["summary"]["extra_label_occurrences"], 8)

    def test_missing_human_acceptance_is_detected_even_when_all_labels_match(self) -> None:
        original = EVAL.ThreatCatalogue.assign

        def remove_gate(catalogue, record, *, strategy="hierarchical"):
            return replace(original(catalogue, record, strategy=strategy), requires_human_acceptance=False)

        with patch.object(EVAL.ThreatCatalogue, "assign", remove_gate):
            report = self.result()
        row = report["strategies"]["hierarchical"]["summary"]
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(row["exact_label_matches"], 8)
        self.assertEqual(row["human_acceptance_matches"], 4)

    def test_missing_bespoke_model_is_detected_independently_of_the_human_flag(self) -> None:
        original = EVAL.ThreatCatalogue.assign

        def remove_bespoke(catalogue, record, *, strategy="hierarchical"):
            return replace(original(catalogue, record, strategy=strategy), repository_model_id=None)

        with patch.object(EVAL.ThreatCatalogue, "assign", remove_bespoke):
            report = self.result()
        row = report["strategies"]["hierarchical"]["summary"]
        self.assertEqual(report["status"], "FAIL")
        self.assertEqual(row["human_acceptance_matches"], 8)
        self.assertEqual(row["required_bespoke_present"], 0)

    def test_org_archetype_and_repository_drift_match_declared_affected_cases(self) -> None:
        report = self.result()
        for strategy in ("per_repository", "hierarchical"):
            drifts = {row["id"]: row for row in report["strategies"][strategy]["drift"]}
            self.assertEqual(len(drifts), 6)
            self.assertTrue(all(row["status"] == "PASS" for row in drifts.values()))
            self.assertEqual(len(drifts["organisation-control-change"]["revalidation_case_ids"]), 8)
            self.assertEqual(drifts["archetype-scenario-change"]["revalidation_case_ids"], ["private-api"])
            self.assertEqual(drifts["repository-data-change"]["boundary_hash_changed_case_ids"], ["private-api"])
            self.assertEqual(drifts["repository-authentication-change"]["post_change_summary"]["human_acceptance_required"], 5)
            self.assertEqual(drifts["unchanged-repeat"]["revalidation_case_ids"], [])
        shared = {row["id"]: row for row in report["strategies"]["shared"]["drift"]}
        self.assertEqual(shared["archetype-scenario-change"]["missing_revalidation_case_ids"], ["private-api"])

    def test_boundary_drift_is_visible_even_when_scenario_names_do_not_change(self) -> None:
        report = self.result()
        drifts = {row["id"]: row for row in report["strategies"]["per_repository"]["drift"]}
        topology = drifts["repository-topology-change"]
        self.assertEqual(topology["model_hash_changed_case_ids"], [])
        self.assertEqual(topology["boundary_hash_changed_case_ids"], ["private-api"])
        self.assertEqual(topology["revalidation_case_ids"], ["private-api"])
        self.assertEqual(topology["status"], "PASS")

    def test_two_thousand_metadata_artefacts_are_separate_from_label_coverage(self) -> None:
        counts = EVAL.metadata_artefacts(2_000)
        self.assertEqual(counts["records"], 2_000)
        self.assertEqual(counts["actual_repository_scans"], 0)
        self.assertEqual(counts["strategies"]["per_repository"]["substantial_model_artefacts"], 2_001)
        self.assertEqual(counts["strategies"]["shared"]["substantial_model_artefacts"], 1)
        hierarchy = counts["strategies"]["hierarchical"]
        self.assertEqual(hierarchy["substantial_model_artefacts"], 68)
        self.assertEqual(hierarchy["repository_delta_records"], 2_000)
        self.assertEqual(hierarchy["archetype_models"], 10)
        self.assertEqual(hierarchy["repository_models"], 57)

    def test_empty_or_incomplete_gold_labels_cannot_produce_a_pass(self) -> None:
        for damage in (
            "empty_cases", "empty_labels", "missing_expected", "duplicate_label",
            "duplicate_case", "non_boolean_gate", "empty_drift_cases",
        ):
            document = copy.deepcopy(self.cases)
            if damage == "empty_cases":
                document["cases"] = []
            elif damage == "empty_labels":
                document["cases"][0]["expected"]["scenarios"] = []
            elif damage == "missing_expected":
                document["cases"][0].pop("expected")
            elif damage == "duplicate_label":
                document["cases"][0]["expected"]["scenarios"].append("identity_abuse")
            elif damage == "duplicate_case":
                document["cases"].append(copy.deepcopy(document["cases"][0]))
            elif damage == "non_boolean_gate":
                document["cases"][0]["expected"]["human_acceptance_required"] = 0
            else:
                document["drift_cases"] = []
            with self.subTest(damage=damage), self.assertRaises(ValueError):
                EVAL.evaluate(document, metadata_records=0)

    def test_unknown_or_duplicate_drift_identity_is_rejected(self) -> None:
        for damage in ("unknown", "duplicate"):
            document = copy.deepcopy(self.cases)
            if damage == "unknown":
                document["drift_cases"][0]["expected_revalidation_case_ids"].append("not-a-case")
            else:
                document["drift_cases"].append(copy.deepcopy(document["drift_cases"][0]))
            with self.subTest(damage=damage), self.assertRaises(ValueError):
                EVAL.evaluate(document, metadata_records=0)

    def test_unknown_mutation_is_an_input_error_not_a_passing_mutation(self) -> None:
        with self.assertRaisesRegex(ValueError, "required by the labelled cases"):
            self.result(drop_scenario="not-a-required-label")

    def test_evaluation_does_not_modify_expected_labels(self) -> None:
        original = copy.deepcopy(self.cases)
        self.result(drop_scenario="authentication_bypass")
        self.assertEqual(self.cases, original)


class ThreatContextCommandTests(unittest.TestCase):
    def run_command(self, script: Path, cwd: Path, *arguments: str):
        return subprocess.run(
            [sys.executable, "-I", "-B", str(script), "--metadata-records", "0", *arguments],
            cwd=cwd, env={"PATH": os.environ.get("PATH", os.defpath), "PYTHONDONTWRITEBYTECODE": "1"},
            text=True, capture_output=True, timeout=30, check=False,
        )

    def test_script_runs_from_root_or_an_unrelated_directory(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-cli-") as temporary:
            for directory in (ROOT, Path(temporary)):
                with self.subTest(directory=directory.name):
                    completed = self.run_command(SCRIPT, directory)
                    self.assertEqual(completed.returncode, 0, completed.stderr)
                    report = json.loads(completed.stdout)
                    self.assertEqual(report["status"], "PASS")
                    self.assertEqual(report["paid_api_calls"], 0)
                    self.assertEqual(len(completed.stdout.splitlines()), 1)

    def test_cli_mutation_has_failure_exit_and_identifies_the_missing_label(self) -> None:
        completed = self.run_command(SCRIPT, ROOT, "--drop-scenario", "authentication_bypass")
        self.assertEqual(completed.returncode, 1, completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], "FAIL")
        self.assertTrue(report["mutation"]["expected_labels_unchanged"])
        self.assertEqual(report["strategies"]["hierarchical"]["summary"]["missing_label_occurrences"], 3)

    def test_minimal_focused_package_needs_no_development_workflow_or_workspace(self) -> None:
        with tempfile.TemporaryDirectory(prefix="context-portable-") as temporary:
            package = Path(temporary) / "sample"
            shutil.copytree(ROOT / "src/fleet_security", package / "src/fleet_security",
                            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            dependency = package / "src/field_autonomy"
            dependency.mkdir()
            (dependency / "__init__.py").write_text('"""Restricted executor dependency slice."""\n')
            for name in ("models.py", "policy.py", "sandbox.py"):
                shutil.copy2(ROOT / "src/field_autonomy" / name, dependency / name)
            (package / "scripts").mkdir()
            (package / "evals").mkdir()
            shutil.copy2(SCRIPT, package / "scripts" / SCRIPT.name)
            shutil.copy2(CASES, package / "evals" / CASES.name)
            completed = self.run_command(package / "scripts" / SCRIPT.name, Path(temporary))
            self.assertEqual(completed.returncode, 0, completed.stderr)
            self.assertEqual(json.loads(completed.stdout)["status"], "PASS")


if __name__ == "__main__":
    unittest.main()
