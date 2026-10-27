"""Prepare public-data Promptfoo tests and summarize a completed run.

This module reuses notebook definitions without executing its API collection loop.
No API calls are made by this script. Promptfoo performs the opt-in live run.
"""

import argparse
import contextlib
import datetime
import hashlib
import io
import json
import math
import os
from pathlib import Path
import statistics
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
GENERATED = ROOT / ".generated"
NOTEBOOK = ROOT.parent / "customer_request_routing.ipynb"


def notebook_definitions():
    """Load the companion's data, request schema, and metrics in offline mode."""
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    namespace = {}
    with patch.dict(os.environ, {"RUN_DECISIONS_API": "0"}):
        with contextlib.redirect_stdout(io.StringIO()):
            for index in (2, 4, 6, 8, 10):
                source = notebook["cells"][index]["source"]
                source = source if isinstance(source, str) else "".join(source)
                exec(compile(source, f"{NOTEBOOK.name}:cell-{index}", "exec"), namespace)
    return namespace


def build_config(cases, question, model):
    assertion = """const answers = JSON.parse(output).answers;
if (!Array.isArray(answers) || answers.length !== 1) return false;
const a = answers[0];
return a.type === 'choice' && a.name === 'route'
  && a.choice === context.vars.expected
  && typeof a.confidence === 'number'
  && Number.isFinite(a.confidence)
  && a.confidence >= 0 && a.confidence <= 1;"""
    return {
        "description": "BANKING77 four-intent routing replication: 40 calibration + 80 test",
        "sharing": False,
        "prompts": ["{{message}}"],
        "providers": [{
            "id": f"openai:decisions:{model}",
            "config": {"questions": [question], "maxRetries": 0,
                       "apiBaseUrl": "https://api.openai.com/v1"},
        }],
        "evaluateOptions": {"maxConcurrency": 1, "cache": False},
        "defaultTest": {"assert": [{"type": "javascript", "value": assertion}]},
        "tests": [{
            "description": case_id,
            "vars": {"message": message, "expected": expected,
                     "case_id": case_id, "split": split},
        } for case_id, split, expected, message in cases],
    }


def prepare():
    if (GENERATED / "results.json").exists():
        raise ValueError("A run already exists; inspect it before replacing its config")
    scope = notebook_definitions()
    cases = scope["load_public_cases"]()
    config = build_config(cases, scope["QUESTION"], scope["MODEL"])
    GENERATED.mkdir(exist_ok=True)
    (GENERATED / "promptfooconfig.json").write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = {
        "dataset": "BANKING77 four-intent subset",
        "dataset_commit": scope["DATASET_COMMIT"],
        "dataset_sha256": scope["DATASET_HASHES"],
        "question_sha256": hashlib.sha256(json.dumps(
            scope["QUESTION"], sort_keys=True).encode()).hexdigest(),
        "requested_model": scope["MODEL"],
        "case_ids": [case[0] for case in cases],
        "note": "Previously evaluated cases; this is a replication, not a new unseen test set.",
    }
    (GENERATED / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"Prepared {len(cases)} public examples: 40 calibration, 80 test.")
    print("Only {{message}} is sent as input. Expected labels remain in the local grader.")
    print("No OpenAI requests were made. Next: npm run validate, then npm run eval.")


def result_rows(export, config, scope):
    """Reject incomplete, duplicate, foreign, or provider-error results."""
    container = export.get("results", {})
    results = container.get("results")
    if not isinstance(results, list):
        raise ValueError("Expected Promptfoo JSON export results.results list")
    expected = {test["vars"]["case_id"]: test["vars"] for test in config["tests"]}
    seen = set()
    rows = []
    for result in results:
        variables = result.get("testCase", {}).get("vars", {})
        case_id = variables.get("case_id")
        if case_id not in expected or case_id in seen or variables != expected[case_id]:
            raise ValueError("Missing, duplicate, foreign, or changed test variables")
        seen.add(case_id)
        response = result.get("response") or {}
        # Promptfoo also sets `error` for an ordinary failed assertion. Its
        # ResultFailureReason enum uses 1 for assertions and 2 for runtime errors.
        assertion_failure = (result.get("failureReason") == 1
                             and isinstance(result.get("gradingResult"), dict)
                             and result["gradingResult"].get("pass") is False)
        if ((result.get("error") and not assertion_failure)
                or result.get("failureReason") == 2
                or response.get("error") or "output" not in response):
            raise ValueError(f"Provider/runtime error for {case_id}; inspect results before retrying")
        output = response["output"]
        output = json.loads(output) if isinstance(output, str) else output
        route, confidence = scope["parse_prediction"](output)
        rows.append({"id": case_id, "split": variables["split"],
                     "expected": variables["expected"], "predicted": route,
                     "confidence": confidence, "latency_ms": result.get("latencyMs")})
    if seen != set(expected):
        raise ValueError(f"Incomplete run: {len(seen)}/{len(expected)} examples")
    return rows


def config_matches(actual, expected):
    """Allow exporter-added defaults while checking all supplied config fields."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            key in actual and config_matches(actual[key], value)
            for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(
            config_matches(a, e) for a, e in zip(actual, expected))
    return actual == expected


def summarize(results_path):
    scope = notebook_definitions()
    config = json.loads((GENERATED / "promptfooconfig.json").read_text())
    export = json.loads(results_path.read_text())
    if not config_matches(export.get("config"), config):
        raise ValueError("Export config differs from prepared config; cannot verify this run")
    rows = result_rows(export, config, scope)
    calibration = [row for row in rows if row["split"] == "calibration"]
    test = [row for row in rows if row["split"] == "test"]
    evaluate = scope["evaluate"]
    candidates = [evaluate(calibration, t) for t in scope["CANDIDATE_THRESHOLDS"]]
    selected = min(candidates, key=lambda r: (
        r["average_loss"], -r["coverage"], r["threshold"]))["threshold"]
    manifest = json.loads((GENERATED / "manifest.json").read_text())
    latencies = sorted(row["latency_ms"] for row in rows
                       if isinstance(row["latency_ms"], (int, float))
                       and not isinstance(row["latency_ms"], bool)
                       and math.isfinite(row["latency_ms"]) and row["latency_ms"] >= 0)
    summary = {
        "completed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "evidence": "Promptfoo live replication; public data; exact-match grader",
        "manifest": manifest,
        "selected_threshold": selected,
        "calibration": candidates,
        "held_out_policy": evaluate(test, selected),
        "held_out_no_filter": evaluate(test, 0),
        "per_route": {route: evaluate([r for r in test if r["expected"] == route], selected)
                      for route in scope["ROUTES"]},
        "latency": {"measured_requests": len(latencies),
                    "median_ms": statistics.median(latencies) if latencies else None,
                    "p95_ms": latencies[math.ceil(0.95 * len(latencies)) - 1] if latencies else None},
        "misroutes": [r["id"] for r in test if r["predicted"] is not None
                      and r["confidence"] >= selected and r["predicted"] != r["expected"]],
        "limits": ["Four intents only; not full BANKING77 or production accuracy.",
                   "These cases were evaluated previously; no new generalization evidence.",
                   "Operational loss weights (5 per misroute, 1 per review) are illustrative."],
    }
    (GENERATED / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print("Saved .generated/summary.json; inspect .generated/report.html for individual responses.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["prepare", "summarize"])
    parser.add_argument("--results", type=Path, default=GENERATED / "results.json")
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    else:
        summarize(args.results)


if __name__ == "__main__":
    main()
