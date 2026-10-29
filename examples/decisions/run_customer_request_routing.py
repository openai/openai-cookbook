"""Route ten public customer-support messages through Decisions; requires OPENAI_API_KEY."""

import argparse
import json
import os
from pathlib import Path
import sys

# Locate the adjacent helper even when Python safe-path mode is enabled.
example_dir = str(Path(__file__).resolve().parent)
if example_dir not in sys.path:
    sys.path.insert(0, example_dir)

from routing import (API_URL, build_request, parse_prediction,
                     request_prediction, load_demo_messages)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--message", help="Optionally route one custom message instead of the ten examples.")
    args = parser.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("Set OPENAI_API_KEY securely, or use bash examples/decisions/run_demo.sh for hidden input")
    if args.message is not None:
        cases = [{"id": "custom", "message": args.message}]
    else:
        cases = load_demo_messages()
        print("Running ten public customer-support examples: ten billable API requests.", flush=True)
    for index, case in enumerate(cases, start=1):
        print(f"Example {index}/{len(cases)}: {case['message']}")
        if "source_label" in case:
            print("Public dataset label (local context only):", case["source_label"])
        print("POST", API_URL)
        print(json.dumps(build_request(case["message"]), indent=2))
        response, latency_ms = request_prediction(case["message"])
        print("LIVE API RESPONSE")
        print(json.dumps(response, indent=2))
        route, confidence = parse_prediction(response)
        print(json.dumps({"route": route or "human_review", "confidence": confidence,
                          "latency_ms": latency_ms}, indent=2))



if __name__ == "__main__":
    main()
