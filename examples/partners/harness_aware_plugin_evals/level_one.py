import yaml

from eval_grading import csv_values
from server import IndicatorQuery, resolve

with open("promptfooconfig.yaml") as f:
    CASES = [test["vars"] for test in yaml.safe_load(f)["tests"]]


def top_candidates(indicator: str) -> set[str]:
    result = resolve(indicators=[IndicatorQuery(indicator=indicator)])
    candidates = result["results"][0]["candidates"]
    if not candidates:
        return set()
    best = max(candidate["confidence"] for candidate in candidates)
    return {c["series_id"] for c in candidates if c["confidence"] == best}


if __name__ == "__main__":
    passed = 0
    for case in CASES:
        got = top_candidates(case["indicator"])
        expected = csv_values(case.get("expected_top_ids") or case["expected_series_ids"])
        ok = got == expected
        passed += ok
        print(f"{'PASS' if ok else 'FAIL'}  {case['indicator']!r:35} -> {', '.join(sorted(got)) or None}")
    print(f"\n{passed}/{len(CASES)} passed")
    raise SystemExit(0 if passed == len(CASES) else 1)
