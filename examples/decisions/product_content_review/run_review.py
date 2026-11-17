"""Run product-content review with the live Decisions API."""

import argparse
import getpass
import json
import os
import sys
import time
from pathlib import Path

# Resolve our own helpers even when PYTHONSAFEPATH disables the script directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evaluate import summarize
from report import write_report
from review import (ROOT, REQUEST_DELAY_SECONDS, create_client,
                    load_cases, review_case)


def run(selected, products, client, output):
    output.mkdir(parents=True, exist_ok=True)
    records = []
    for number, case in enumerate(selected, 1):
        if number > 1:
            print(f"Waiting {REQUEST_DELAY_SECONDS}s before the next request...", flush=True)
            time.sleep(REQUEST_DELAY_SECONDS)
        print(f"Example {number}/{len(selected)}: {case['title']}", flush=True)
        row = review_case(client, case, products[case["product_id"]])
        records.append(row)
        # Save completed calls immediately; a failed later call is never retried.
        (output / "results.json").write_text(json.dumps(records, indent=2) + "\n")
        write_report(records, output / "report.html")
        print("REQUEST (image bytes omitted)")
        print(json.dumps(row["request"], indent=2))
        print("ACTUAL API RESPONSE")
        print(json.dumps(row["response"], indent=2))
        print("SUGGESTED NEXT STEP:", row["next_step"], flush=True)
    labels = json.loads((ROOT / "labels.json").read_text())
    metrics = summarize(records, labels)
    (output / "metrics.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print("LOCAL LABEL COMPARISON")
    print(json.dumps(metrics, indent=2))
    print(f"Saved report: {output / 'report.html'}")
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--all", action="store_true", help="Run every bundled case")
    parser.add_argument("--case", help="Run one case ID instead of the first case")
    parser.add_argument("--output", type=Path, default=ROOT / "results" / "latest",
                        help="Replace results in this directory on each run")
    args = parser.parse_args()
    if args.all and args.case:
        parser.error("Choose --all or --case.")
    data = load_cases()
    selected = data["cases"] if args.all else [next(
        (c for c in data["cases"] if c["id"] == args.case), data["cases"][0])]
    if args.case and selected[0]["id"] != args.case:
        parser.error("Unknown case ID.")
    # Remove stale reports before calls so failed reruns cannot look successful.
    if args.output.exists() and any(args.output.iterdir()):
        for name in ["results.json", "metrics.json", "report.html"]:
            (args.output / name).unlink(missing_ok=True)
    print(f"Running {len(selected)} paid API request(s), four questions per request.", flush=True)
    key = os.environ.get("OPENAI_API_KEY") or getpass.getpass("OpenAI API key (hidden): ")
    if not key.strip():
        parser.error("An API key is required.")
    try:
        with create_client(key) as client:
            run(selected, data["products"], client, args.output.resolve())
    except Exception as error:
        # Print machine-readable error details without exposing request content.
        if getattr(error, "status_code", None) is not None:
            print(f"API status: {error.status_code}; error code: {getattr(error, 'code', None)}")
        print(f"Stopped after {type(error).__name__}. Completed results are saved. "
              "Check API access and network connectivity before rerunning. No automatic retry.")
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
