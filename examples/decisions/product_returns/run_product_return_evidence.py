"""Run ten real Decisions requests and save a local report with photos and answers."""

import argparse
import getpass
import json
import os
from pathlib import Path
import sys
import warnings

# Find the adjacent helper even when the script is launched from another folder.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from return_evidence import (API_URL, build_request, grade_result, load_cases, load_expectations,
                             parse_answers, recommend_next_step, request_decision)
from return_reporting import display_request, validate_report_path, write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("outputs/product-return-results.html"),
                        help="Local HTML report path; JSON is saved alongside it")
    args = parser.parse_args()
    directory = Path(__file__).resolve().parent
    validate_report_path(args.output, directory)
    cases = load_cases(directory)
    expectations = load_expectations(cases, directory)
    print(f"Running {len(cases)} real, billable Decisions requests; no automatic retries.", flush=True)
    # Catch missing images or invalid paths before starting paid requests.
    payloads = [build_request(case, directory) for case in cases]
    # Reuse an environment key, or request one with hidden input below.
    key = os.environ.get("OPENAI_API_KEY")
    rows = []
    try:
        if not key:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                key = getpass.getpass("OpenAI API key (hidden): ")
        if not key:
            raise RuntimeError("No API key supplied; stopped before making requests")
        # Start a fresh report; save each completed case as the run progresses.
        write_report([], args.output, directory)
        for index, (case, payload) in enumerate(zip(cases, payloads), 1):
            print(f"\nExample {index}/{len(cases)}: {case['title']}", flush=True)
            print("POST", API_URL)
            print(json.dumps(display_request(payload), indent=2), flush=True)
            # One paid request per case; validation and grading run locally.
            response, latency = request_decision(payload, key)
            handoff = recommend_next_step(case, parse_answers(response))
            grade = grade_result(case["id"], handoff, expectations)
            print("ACTUAL RESPONSE", json.dumps(response, indent=2), flush=True)
            print("HANDOFF", json.dumps(handoff), flush=True)
            print("EVAL", json.dumps(grade), flush=True)
            rows.append({"case": case, "request": display_request(payload),
                         "response": response, "handoff": handoff,
                         "grade": grade, "latency_ms": latency})
            write_report(rows, args.output, directory)
    finally:
        # Drop this local key reference after success or failure.
        key = None
    print(f"\nCompleted {len(rows)}/{len(cases)} requests. Report: {args.output.resolve()}")
    print("Unusable API answers:", sum(parse_answers(r["response"]) is None for r in rows))
    print(f"Expected outcomes matched: {sum(row['grade']['passed'] for row in rows)}/{len(rows)}")
    return 0 if all(row["grade"]["passed"] for row in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
