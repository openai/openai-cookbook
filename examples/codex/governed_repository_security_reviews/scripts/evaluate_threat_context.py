#!/usr/bin/env python3
"""Check explicit synthetic context labels; never run a security scanner.

The expected labels come only from the checked-in scenario file. Catalogue
outputs are observations, never an oracle for their own expected coverage.
The separate generated inventory counts artefacts, not security effectiveness.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "src"))

from fleet_security.inventory import Repository, classify, generate_inventory
from fleet_security.threats import ThreatCatalogue


DEFAULT_CASES = ROOT / "evals" / "security_context_cases.json"
STRATEGIES = ("per_repository", "shared", "hierarchical")
REQUIRED_STRATEGIES = ("per_repository", "hierarchical")
EXPECTED_KEYS = frozenset({
    "archetype", "risk_tier", "human_acceptance_required",
    "bespoke_model_required", "scenarios",
})
LABEL = re.compile(r"[a-z][a-z0-9_]{1,79}\Z")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("scenario JSON contains a duplicate object key")
        result[key] = value
    return result


def _strings(value: Any, *, label: str, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ) or len(value) != len(set(value)) or (nonempty and not value):
        raise ValueError(f"{label} must be a list of unique nonempty strings")
    return value


def _expected(value: Any) -> None:
    if not isinstance(value, dict) or set(value) != EXPECTED_KEYS:
        raise ValueError("each case needs complete independent expected labels and gates")
    labels = _strings(value["scenarios"], label="expected scenarios", nonempty=True)
    if any(not LABEL.fullmatch(label) for label in labels):
        raise ValueError("expected scenario label is invalid")
    if not isinstance(value["archetype"], str) or not value["archetype"]:
        raise ValueError("expected archetype must be explicitly labelled")
    if value["risk_tier"] not in {"standard", "high"}:
        raise ValueError("expected risk tier is invalid")
    for key in ("human_acceptance_required", "bespoke_model_required"):
        if type(value[key]) is not bool:
            raise ValueError("expected approval and bespoke gates must be booleans")


def _repository(values: dict[str, Any]) -> Repository:
    fields = dict(values)
    for name in ("dependencies", "controls", "changed_paths"):
        if name in fields:
            fields[name] = tuple(_strings(fields[name], label=name))
    return Repository(**fields)


def _catalogue(values: dict[str, Any]) -> ThreatCatalogue:
    fields = dict(values)
    if "organisation_controls" in fields:
        fields["organisation_controls"] = tuple(_strings(
            fields["organisation_controls"], label="organisation controls", nonempty=True,
        ))
    if "archetype_overrides" in fields:
        overrides = fields["archetype_overrides"]
        if not isinstance(overrides, dict):
            raise ValueError("archetype overrides must be an object")
        fields["archetype_overrides"] = {
            key: tuple(_strings(labels, label="archetype scenarios"))
            for key, labels in overrides.items()
        }
    return ThreatCatalogue(**fields)


def validate_cases(document: Any) -> dict[str, Any]:
    if not isinstance(document, dict) or type(document.get("schema_version")) is not int:
        raise ValueError("scenario set requires an integer schema_version")
    if document["schema_version"] != 1:
        raise ValueError("unsupported scenario-set version")
    if not isinstance(document.get("repository_defaults"), dict):
        raise ValueError("scenario set requires repository_defaults")
    if not isinstance(document.get("catalogue"), dict):
        raise ValueError("scenario set requires a trusted catalogue definition")
    _catalogue(document["catalogue"])
    cases = document.get("cases")
    drifts = document.get("drift_cases")
    if not isinstance(cases, list) or not 1 <= len(cases) <= 64:
        raise ValueError("scenario set must contain 1 to 64 explicit cases")
    if not isinstance(drifts, list) or not 1 <= len(drifts) <= 32:
        raise ValueError("scenario set must contain 1 to 32 drift cases")
    ids: set[str] = set()
    repository_ids: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or not isinstance(case.get("id"), str) or not case["id"]:
            raise ValueError("every case requires an explicit identity")
        if case["id"] in ids:
            raise ValueError("scenario identities must be unique")
        if not isinstance(case.get("repository"), dict):
            raise ValueError("every case requires repository metadata")
        _expected(case.get("expected"))
        record = _repository(document["repository_defaults"] | case["repository"])
        if record.repo_id in repository_ids:
            raise ValueError("labelled repository identities must be unique")
        repository_ids.add(record.repo_id)
        ids.add(case["id"])
    drift_ids: set[str] = set()
    for drift in drifts:
        if not isinstance(drift, dict) or not isinstance(drift.get("id"), str) or not drift["id"]:
            raise ValueError("every drift case requires an explicit identity")
        if drift["id"] in drift_ids:
            raise ValueError("drift identities must be unique")
        drift_ids.add(drift["id"])
        for key in ("catalogue_changes", "repository_changes", "expected_after"):
            if not isinstance(drift.get(key), dict):
                raise ValueError("drift changes and expected_after must be objects")
        for key in ("expected_revalidation_case_ids", "expected_boundary_change_case_ids"):
            if not set(_strings(drift.get(key), label=key)) <= ids:
                raise ValueError("drift expectation refers to an unknown case")
        for key in ("repository_changes", "expected_after"):
            if not set(drift[key]) <= ids:
                raise ValueError("drift change refers to an unknown case")
        for expected in drift["expected_after"].values():
            _expected(expected)
        for changes in drift["repository_changes"].values():
            if not isinstance(changes, dict) or "repo_id" in changes:
                raise ValueError("a drift case must preserve repository identity")
        _catalogue(document["catalogue"] | drift["catalogue_changes"])
        for case in cases:
            _repository(document["repository_defaults"] | case["repository"] |
                        drift["repository_changes"].get(case["id"], {}))
    return document


def load_cases(path: Path = DEFAULT_CASES) -> dict[str, Any]:
    if path.stat().st_size > 1_000_000:
        raise ValueError("scenario set exceeds the 1 MB local fixture limit")
    return validate_cases(json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object))


def _observe(
    record: Repository, expected: dict[str, Any], catalogue: ThreatCatalogue,
    strategy: str, drop_scenario: str | None,
) -> tuple[dict[str, Any], tuple[str, str]]:
    assignment = catalogue.assign(record, strategy=strategy)
    classification = classify(record)
    actual = set(assignment.covered_scenarios)
    if drop_scenario is not None:
        actual.discard(drop_scenario)
    required = set(expected["scenarios"])
    bespoke_id = f"repository:{record.repo_id}"
    expected_model = bespoke_id if strategy == "per_repository" or (
        strategy == "hierarchical" and expected["bespoke_model_required"]
    ) else None
    expected_archetype = expected["archetype"] if strategy == "hierarchical" else None
    checks = {
        "organisation_model_matches": assignment.organisation_model_id == catalogue.version,
        "classification_matches": classification.archetype == expected["archetype"]
        and classification.risk_tier == expected["risk_tier"],
        "human_acceptance_matches": assignment.requires_human_acceptance
        == expected["human_acceptance_required"],
        "bespoke_gate_satisfied": not expected["bespoke_model_required"]
        or assignment.repository_model_id == bespoke_id,
        "model_placement_matches": assignment.repository_model_id == expected_model
        and assignment.archetype_model_id == expected_archetype,
    }
    row = {
        "matched_labels": sorted(required & actual),
        "missing_labels": sorted(required - actual),
        "extra_labels": sorted(actual - required),
        "exact_label_match": actual == required,
        "expected_human_acceptance": expected["human_acceptance_required"],
        "actual_human_acceptance": assignment.requires_human_acceptance,
        "bespoke_required": expected["bespoke_model_required"],
        "bespoke_present": assignment.repository_model_id == bespoke_id,
        **checks,
    }
    row["status"] = "PASS" if actual == required and all(checks.values()) else "FAIL"
    return row, (assignment.effective_model_hash, assignment.boundary_hash)


def _summary(rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
    values = list(rows.values())
    return {
        "cases": len(values),
        "passing_cases": sum(row["status"] == "PASS" for row in values),
        "exact_label_matches": sum(row["exact_label_match"] for row in values),
        "matched_label_occurrences": sum(len(row["matched_labels"]) for row in values),
        "missing_label_occurrences": sum(len(row["missing_labels"]) for row in values),
        "extra_label_occurrences": sum(len(row["extra_labels"]) for row in values),
        "human_acceptance_required": sum(row["expected_human_acceptance"] for row in values),
        "human_acceptance_observed": sum(row["actual_human_acceptance"] for row in values),
        "human_acceptance_matches": sum(row["human_acceptance_matches"] for row in values),
        "bespoke_required": sum(row["bespoke_required"] for row in values),
        "required_bespoke_present": sum(
            row["bespoke_required"] and row["bespoke_present"] for row in values
        ),
    }


def metadata_artefacts(count: int) -> dict[str, Any]:
    """Count observed model IDs separately; these records have no gold labels."""
    records = generate_inventory(count)
    catalogue = ThreatCatalogue()
    results: dict[str, Any] = {}
    for strategy in STRATEGIES:
        assignments = [catalogue.assign(record, strategy=strategy) for record in records]
        organisation = len({item.organisation_model_id for item in assignments})
        archetypes = len({item.archetype_model_id for item in assignments if item.archetype_model_id})
        repositories = len({item.repository_model_id for item in assignments if item.repository_model_id})
        results[strategy] = {
            "organisation_models": organisation,
            "archetype_models": archetypes,
            "repository_models": repositories,
            "substantial_model_artefacts": organisation + archetypes + repositories,
            "repository_delta_records": sum(bool(item.delta) for item in assignments),
            "repositories_requiring_human_acceptance": sum(
                item.requires_human_acceptance for item in assignments
            ),
        }
    return {
        "records": count,
        "scope": "Generated metadata artefact counts only; not an independent coverage evaluation",
        "actual_repository_scans": 0,
        "strategies": results,
    }


def evaluate(
    document: dict[str, Any], *, metadata_records: int = 2_000,
    drop_scenario: str | None = None,
) -> dict[str, Any]:
    validate_cases(document)
    if type(metadata_records) is not int or not 0 <= metadata_records <= 20_000:
        raise ValueError("metadata record count must be an integer from 0 to 20,000")
    all_labels = {label for case in document["cases"] for label in case["expected"]["scenarios"]}
    if drop_scenario is not None and drop_scenario not in all_labels:
        raise ValueError("mutation must remove a scenario required by the labelled cases")
    catalogue = _catalogue(document["catalogue"])
    results: dict[str, Any] = {}
    for strategy in STRATEGIES:
        rows: dict[str, Any] = {}
        hashes: dict[str, tuple[str, str]] = {}
        for case in document["cases"]:
            record = _repository(document["repository_defaults"] | case["repository"])
            rows[case["id"]], hashes[case["id"]] = _observe(
                record, case["expected"], catalogue, strategy, drop_scenario,
            )
        drift_results = []
        for drift in document["drift_cases"]:
            updated = _catalogue(document["catalogue"] | drift["catalogue_changes"])
            changed_models: set[str] = set()
            changed_boundaries: set[str] = set()
            after_rows = {}
            for case in document["cases"]:
                case_id = case["id"]
                record = _repository(document["repository_defaults"] | case["repository"] |
                                     drift["repository_changes"].get(case_id, {}))
                expected = drift["expected_after"].get(case_id, case["expected"])
                after_rows[case_id], current_hashes = _observe(
                    record, expected, updated, strategy, drop_scenario,
                )
                if hashes[case_id][0] != current_hashes[0]:
                    changed_models.add(case_id)
                if hashes[case_id][1] != current_hashes[1]:
                    changed_boundaries.add(case_id)
            changed_context = changed_models | changed_boundaries
            required_context = set(drift["expected_revalidation_case_ids"])
            required_boundary = set(drift["expected_boundary_change_case_ids"])
            failures = {key: row for key, row in after_rows.items() if row["status"] != "PASS"}
            exact = changed_context == required_context and changed_boundaries == required_boundary
            drift_results.append({
                "id": drift["id"],
                "model_hash_changed_case_ids": sorted(changed_models),
                "boundary_hash_changed_case_ids": sorted(changed_boundaries),
                "revalidation_case_ids": sorted(changed_context),
                "missing_revalidation_case_ids": sorted(required_context - changed_context),
                "extra_revalidation_case_ids": sorted(changed_context - required_context),
                "missing_boundary_change_case_ids": sorted(required_boundary - changed_boundaries),
                "extra_boundary_change_case_ids": sorted(changed_boundaries - required_boundary),
                "drift_matches": exact,
                "post_change_summary": _summary(after_rows),
                "post_change_failures": failures,
                "status": "PASS" if exact and not failures else "FAIL",
            })
        passed = all(row["status"] == "PASS" for row in rows.values()) and all(
            row["status"] == "PASS" for row in drift_results
        )
        results[strategy] = {
            "status": "PASS" if passed else "FAIL", "summary": _summary(rows),
            "cases": rows, "drift": drift_results,
        }
    passed = all(results[strategy]["status"] == "PASS" for strategy in REQUIRED_STRATEGIES)
    canonical = json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return {
        "format": "independent-synthetic-threat-context-eval/v1",
        "status": "PASS" if passed else "FAIL",
        "pass_criteria": "All labelled context, gate and drift checks pass for the required strategies; shared is a comparison baseline",
        "required_strategies": list(REQUIRED_STRATEGIES),
        "comparison_only_strategies": ["shared"],
        "case_set_sha256": hashlib.sha256(canonical).hexdigest(),
        "case_set_hash_encoding": "SHA-256 of canonical JSON with sorted keys and compact separators",
        "evidence_scope": "Explicit synthetic scenario/context retention only; not vulnerability detection, real repository coverage, cost or throughput",
        "label_provenance": copy.deepcopy(document.get("label_provenance", {})),
        "labelled_cases": len(document["cases"]),
        "labelled_scenario_occurrences": sum(len(case["expected"]["scenarios"]) for case in document["cases"]),
        "unique_baseline_scenario_labels": len(all_labels),
        "labelled_drift_cases": len(document["drift_cases"]),
        "mutation": None if drop_scenario is None else {
            "operation": "remove_observed_scenario_after_assignment",
            "scenario": drop_scenario,
            "expected_labels_unchanged": True,
        },
        "strategies": results,
        "metadata_artefact_counts": metadata_artefacts(metadata_records) if metadata_records else {
            "records": 0, "status": "not_requested", "actual_repository_scans": 0,
        },
        "paid_api_calls": 0,
        "actual_repository_scans": 0,
        "external_writes": 0,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    parser.add_argument("--metadata-records", type=int, default=2_000,
                        help="Separate generated metadata count; 0 skips it (default: 2000)")
    parser.add_argument("--drop-scenario", help="Mutation demonstration: remove one observed required label")
    args = parser.parse_args(argv)
    try:
        report = evaluate(load_cases(args.cases), metadata_records=args.metadata_records,
                          drop_scenario=args.drop_scenario)
    except (OSError, UnicodeError, ValueError, TypeError) as error:
        print(json.dumps({"status": "ERROR", "error": str(error)}, separators=(",", ":")))
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
