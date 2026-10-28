"""Route four public messages through Decisions by default; requires OPENAI_API_KEY."""

import argparse
import json
import os

from routing import (API_URL, build_request, parse_prediction,
                     request_prediction, sample_public_messages)


def positive_count(value):
    count = int(value)
    if count < 1:
        raise argparse.ArgumentTypeError("Samples per route must be positive")
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--message", help="Route one custom message instead of loading BANKING77.")
    source.add_argument("--samples-per-route", type=positive_count, default=1,
                        help="Public examples per route: default 1 means 4 API calls; 2 means 8.")
    args = parser.parse_args()
    if not os.environ.get("OPENAI_API_KEY"):
        parser.error("Set OPENAI_API_KEY securely, or use bash examples/decisions/run_demo.sh for hidden input")
    if args.message is not None:
        cases = [{"id": "custom", "message": args.message}]
    else:
        print(f"Configured {4 * args.samples_per_route} billable requests from public BANKING77.", flush=True)
        cases = sample_public_messages(args.samples_per_route)
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
