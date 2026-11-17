"""Compare saved assessments with local labels without making API calls."""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from review import ROOT


def summarize(records, labels):
    if len({row["case_id"] for row in records}) != len(records):
        raise ValueError("Duplicate case IDs would inflate evaluation counts.")
    metrics = {}
    for group in sorted({row["group"] for row in records}):
        counts = Counter()
        for row in records:
            if row["group"] != group:
                continue
            expected = labels[row["case_id"]]
            if {a["name"] for a in row["answers"]} != set(expected):
                raise ValueError("Saved checks do not match the local labels.")
            counts["cases"] += 1
            for answer in row["answers"]:
                actual, gold = answer["choice"], expected[answer["name"]]
                counts["checks"] += 1
                counts["agreements"] += actual == gold
                counts["mismatches_in_labels"] += gold == "mismatch"
                counts["missed_mismatch_flags"] += gold == "mismatch" and actual != "mismatch"
                counts["false_mismatch_flags"] += gold != "mismatch" and actual == "mismatch"
                counts["unclear_in_labels"] += gold == "insufficient_evidence"
                counts["unclear_marked_match"] += gold == "insufficient_evidence" and actual == "match"
                counts["unusable_answers"] += actual == "unusable_answer"
            counts["editor_ready_cases"] += row["next_step"] == "ready_for_editor_review"
            counts["mismatch_cases_marked_ready"] += (
                "mismatch" in expected.values() and row["next_step"] == "ready_for_editor_review")
        metrics[group] = dict(counts)
    return metrics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, help="Saved results.json from a live run")
    args = parser.parse_args()
    records = json.loads(args.results.read_text())
    labels = json.loads((ROOT / "labels.json").read_text())
    print(json.dumps(summarize(records, labels), indent=2))


if __name__ == "__main__":
    main()
