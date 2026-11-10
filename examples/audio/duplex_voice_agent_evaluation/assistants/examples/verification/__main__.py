"""Run the verification example through CRAWL's offline protocol fixtures."""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Sequence
from pathlib import Path

from assistants.config import ASSISTANT_ENV_DEFAULTS
from assistants.examples.verification.resources import SCENARIOS_PATH, load_scenarios, resources_for_scenario
from crawl_harness.evaluate import run_single_eval
from shared.artifacts import create_run_directory
from shared.paths import require_external_output
from shared.reporting.results import build_results_report, ensure_dir, write_json
from shared.single_turn.types import CrawlEvalRunConfig, SingleTurnEvalResult


async def run_examples(out: Path, *, scenario_id: str | None = None) -> list[SingleTurnEvalResult]:
    """Save native reports for explicit offline scripts; never instantiate API clients."""
    scenarios = load_scenarios()
    if scenario_id is not None:
        scenarios = [scenario for scenario in scenarios if scenario.id == scenario_id]
        if not scenarios:
            raise ValueError(f"Unknown verification scenario: {scenario_id}")
    out = require_external_output(out)
    out = create_run_directory(out.parent, out.name)
    audio_dir, events_dir, transcripts_dir = (ensure_dir(out / name) for name in ("audio", "events", "transcripts"))
    results = []
    for scenario in scenarios:
        resources = resources_for_scenario(scenario.id)
        config = CrawlEvalRunConfig(
            run_name=out.name,
            model=ASSISTANT_ENV_DEFAULTS["OPENAI_LIVE_MODEL"],
            backend_model=ASSISTANT_ENV_DEFAULTS["OPENAI_LIVE_BACKEND_MODEL"],
            endpoint="https://unused.invalid/v1/live/sessions",
            response_timeout_seconds=15,
            tts_model="unused-offline",
            voice=ASSISTANT_ENV_DEFAULTS["OPENAI_LIVE_VOICE"],
            chunk_ms=20,
            sample_rate_hz=24_000,
            input_audio_format="pcm16",
            output_audio_format="pcm16",
            real_time=False,
            data=SCENARIOS_PATH,
            system_prompt_file=resources.system_prompt_file,
            backend_system_prompt_file=resources.backend_system_prompt_file,
            tools_file=resources.tools_file,
            offline=True,
        )
        results.append(
            await run_single_eval(
                tts_client=None,
                judge_client=None,
                scenario=scenario,
                system_prompt=resources.system_prompt_file.read_text(encoding="utf-8"),
                backend_system_prompt=resources.backend_system_prompt_file.read_text(encoding="utf-8"),
                tools=json.loads(resources.tools_file.read_text(encoding="utf-8")),
                resources=resources,
                business_facts=resources.load_facts(),
                config=config,
                run_audio_dir=audio_dir,
                run_events_dir=events_dir,
                run_transcript_dir=transcripts_dir,
            )
        )
    report = build_results_report(
        module="crawl",
        run_name=out.name,
        execution_mode="offline_fixture",
        interaction="single_turn",
        dataset=SCENARIOS_PATH,
        configuration={"application": "verification", "audio_source": "synthetic_tone", "assistant_mode": "responses"},
        rows=[result.to_result_row() for result in results],
        run_dir=out,
        scenario_id_key="example_id",
    )
    write_json(out / "results.json", report)
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, required=True, help="New output directory; existing runs are never overwritten."
    )
    parser.add_argument("--scenario", choices=[scenario.id for scenario in load_scenarios()], help="Run one fixture.")
    args = parser.parse_args(argv)
    results = asyncio.run(run_examples(args.out, scenario_id=args.scenario))
    passed = sum(result.assessment["passed"] for result in results)
    print(f"Offline fixture checks: {passed}/{len(results)} passed. Semantic judgment was not run.")
    print(f"Results: {args.out.expanduser().resolve() / 'results.json'}")
    return int(passed != len(results) or any(result.error_info.status != "ok" for result in results))


if __name__ == "__main__":
    raise SystemExit(main())
