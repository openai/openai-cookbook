import json
import os
from pathlib import Path

import assert_codex_result
import assert_result
from dotenv import load_dotenv

load_dotenv()
RUN_LIVE = os.environ.get("RUN_LIVE") == "1"


def trace(recorded: str, live: str | None = None) -> str:
    return live if RUN_LIVE and live else recorded


def grade_row(row: dict, get_assert) -> dict:
    response = row.get("response") or {}
    if response.get("error") or response.get("output") is None:
        error = response.get("error") or row.get("error") or "no output"
        return {"pass": False, "reason": str(error).splitlines()[0]}
    return get_assert(response["output"], {"vars": row["vars"], "providerResponse": response})


RUNS = [
    ("Standalone loop", trace("data/l2-trace.json", "outputs/l2-results.json"), assert_result.get_assert),
    (
        "Codex, empty instructions",
        trace("data/l3-trace-before.json", "outputs/l3-results.json"),
        assert_codex_result.get_assert,
    ),
    ("Codex, with instructions", trace("data/l3-trace-after.json"), assert_codex_result.get_assert),
]

if __name__ == "__main__":
    for label, path, get_assert in RUNS:
        if not Path(path).is_file():
            raise FileNotFoundError(
                f"{label}: no eval results at {path}. Rerun the eval that writes it, "
                "or unset RUN_LIVE to replay the recorded runs under data/."
            )
        rows = json.loads(Path(path).read_text())["results"]["results"]
        graded = [(row["testCase"]["description"], grade_row(row, get_assert)) for row in rows]
        passed = sum(verdict["pass"] for _, verdict in graded)
        print(f"{label}: {passed}/{len(graded)} from {path}")
        for description, verdict in graded:
            if not verdict["pass"]:
                print(f"    {description}: {verdict['reason']}")
