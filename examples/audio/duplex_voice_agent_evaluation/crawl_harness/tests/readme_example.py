"""Regenerate the README result example from an actual offline RUN evaluation.

Run from the repository root: uv run python -m crawl_harness.tests.readme_example
"""

from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from run_harness.evaluate import parse_args, run_evals

PROJECT_ROOT = Path(__file__).resolve().parents[2]
EXAMPLE_PATH = PROJECT_ROOT / "docs" / "examples" / "run-results.json"
START = "<!-- generated-run-results:start -->"
END = "<!-- generated-run-results:end -->"


async def build_example_report(output_dir: Path) -> dict[str, Any]:
    """Exercise the real serializer, replacing only machine-specific run paths."""
    args = parse_args(
        [
            "--offline",
            "--scenario",
            "restaurant_date_correction",
            "--data",
            str(PROJECT_ROOT / "run_harness/data/scenarios.json"),
            "--results-dir",
            str(output_dir),
            "--model",
            "gpt-live-1",
            "--backend-model",
            "gpt-5.6-terra",
            "--voice",
            "marin",
            "--assistant",
            "responses",
            "--assistant-endpoint",
            "",
            "--simulator-model",
            "gpt-live-1",
            "--simulator-voice",
            "cedar",
            "--completion-model",
            "gpt-5.6-terra",
            "--no-semantic-drain",
            "--concurrency",
            "1",
            "--condition",
            "clean",
            "--seed",
            "7",
        ]
    )
    run_dir = await run_evals(args)
    report = json.loads((run_dir / "results.json").read_text(encoding="utf-8"))
    report["run"]["id"] = "run_offline_20260818_000000_000Z"
    report["run"]["dataset"] = "/path/to/scenarios.json"
    return report


def readme_excerpt(report: dict[str, Any]) -> dict[str, Any]:
    """Omit long optional details without inventing values or changing schema."""
    excerpt = copy.deepcopy(report)
    excerpt["run"]["configuration"] = {}
    for row in excerpt["results"]:
        row.pop("title", None)
        row.pop("assessment", None)
        observations = row["observability"]
        observations.pop("tools", None)
        observations["completion"] = {
            key: observations["completion"][key] for key in ("termination_reason", "policy", "passed")
        }
    return excerpt


def render_readme_example(report: dict[str, Any]) -> str:
    return "```json\n" + json.dumps(readme_excerpt(report), ensure_ascii=False, indent=2) + "\n```"


async def regenerate() -> None:
    with TemporaryDirectory(prefix="live-readme-example-") as directory:
        report = await build_example_report(Path(directory))
    EXAMPLE_PATH.parent.mkdir(parents=True, exist_ok=True)
    EXAMPLE_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    readme = PROJECT_ROOT / "README.md"
    before, remainder = readme.read_text(encoding="utf-8").split(START, 1)
    _, after = remainder.split(END, 1)
    readme.write_text(before + START + "\n" + render_readme_example(report) + "\n" + END + after, encoding="utf-8")


if __name__ == "__main__":
    asyncio.run(regenerate())
