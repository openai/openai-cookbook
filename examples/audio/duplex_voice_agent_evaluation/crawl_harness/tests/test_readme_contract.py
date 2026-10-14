"""Keep Cookbook README examples synchronized with runnable harness contracts."""

from __future__ import annotations

import json
import re
import shlex
import tomllib
from pathlib import Path

import pytest

from assistants.client.service import parse_args as parse_service_args
from crawl_harness.evaluate import parse_args as parse_crawl_args
from crawl_harness.tests.readme_example import (
    END,
    EXAMPLE_PATH,
    START,
    build_example_report,
    readme_excerpt,
    render_readme_example,
)
from run_harness.evaluate import parse_args as parse_run_args
from run_harness.scenarios import validate_run_scenario
from run_harness.visualization.export_viewer import parse_args as parse_viewer_args
from shared.reporting.results import AUDIO_METRICS, SCHEMA_VERSION, TASK_METRICS
from shared.scenarios import ScenarioDataset
from walk_harness.evaluate import parse_args as parse_walk_args
from walk_harness.generate_audio import parse_args as parse_generator_args

PROJECT_ROOT = Path(__file__).resolve().parents[2]
READMES = tuple(
    sorted(
        {
            PROJECT_ROOT / "README.md",
            *(PROJECT_ROOT / "assistants").rglob("README.md"),
            *(PROJECT_ROOT / "shared").glob("README.md"),
            *(PROJECT_ROOT / "crawl_harness").glob("README.md"),
            *(PROJECT_ROOT / "walk_harness").glob("README.md"),
            *(PROJECT_ROOT / "run_harness").glob("README.md"),
        }
    )
)
PARSERS = {
    "crawl-eval": parse_crawl_args,
    "walk-eval": parse_walk_args,
    "run-eval": parse_run_args,
    "walk-generate-audio": parse_generator_args,
    "run-view": parse_viewer_args,
    "client-assistant": parse_service_args,
}


def _heading_slug(heading: str) -> str:
    return re.sub(r"[^\w\- ]", "", heading.casefold(), flags=re.UNICODE).replace(" ", "-")


def _headings(path: Path) -> set[str]:
    return {
        _heading_slug(match.group(1))
        for match in re.finditer(r"^#{1,6}\s+(.+?)\s*$", path.read_text(encoding="utf-8"), re.MULTILINE)
    }


def _fenced_examples(readme: Path, language: str) -> list[tuple[int, str]]:
    text = readme.read_text(encoding="utf-8")
    pattern = rf"^[ \t]*(?:>\s*)?```{re.escape(language)}[ \t]*\n(.*?)^[ \t]*(?:>\s*)?```[ \t]*$"
    return [
        (
            text.count("\n", 0, match.start()) + 1,
            "\n".join(re.sub(r"^>\s?", "", line) for line in match.group(1).splitlines()),
        )
        for match in re.finditer(pattern, text, flags=re.DOTALL | re.MULTILINE)
    ]


@pytest.mark.parametrize("readme", READMES, ids=lambda path: str(path.relative_to(PROJECT_ROOT)))
def test_readme_local_links_and_heading_anchors_exist(readme: Path) -> None:
    for match in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", readme.read_text(encoding="utf-8")):
        target = match.group(1).strip().split(" ", 1)[0]
        if target.startswith(("http://", "https://", "mailto:")):
            continue
        relative, _, fragment = target.partition("#")
        linked = (readme.parent / relative).resolve() if relative else readme
        assert linked.exists(), f"{readme.relative_to(PROJECT_ROOT)} links to missing {target!r}"
        if fragment and linked.suffix == ".md":
            assert fragment in _headings(linked), f"Missing heading #{fragment} in {linked}"


@pytest.mark.parametrize("readme", READMES, ids=lambda path: str(path.relative_to(PROJECT_ROOT)))
def test_readme_json_examples_are_valid_and_match_documented_scenarios(readme: Path) -> None:
    phase = readme.parent.name
    actual = (
        {
            scenario.id: scenario
            for scenario in ScenarioDataset.model_validate_json(
                (readme.parent / "data/scenarios.json").read_text(encoding="utf-8")
            ).scenarios
        }
        if phase in {"crawl_harness", "walk_harness", "run_harness"}
        else {}
    )

    for line, content in _fenced_examples(readme, "json"):
        try:
            document = json.loads(content)
        except json.JSONDecodeError as exc:
            pytest.fail(f"Invalid JSON in {readme.relative_to(PROJECT_ROOT)}:{line}: {exc}")

        if not isinstance(document, dict) or "schema_version" not in document or "scenarios" not in document:
            continue
        examples = ScenarioDataset.model_validate(document)
        for scenario in examples.scenarios:
            if scenario.interaction == "multi_turn":
                validate_run_scenario(scenario)
            if scenario.id not in actual:
                continue
            expected = actual[scenario.id]
            assert scenario.input.text == expected.input.text
            assert [tool.name for tool in scenario.expected.tools.required] == [
                tool.name for tool in expected.expected.tools.required
            ]
            if scenario.input.recordings:
                assert scenario.input.recordings[0].condition == expected.input.recordings[0].condition
                assert scenario.input.recordings[0].metadata == expected.input.recordings[0].metadata
            if scenario.simulation_parameters is not None:
                assert expected.simulation_parameters is not None
                assert [item.id for item in scenario.simulation_parameters.agenda] == [
                    item.id for item in expected.simulation_parameters.agenda
                ]


@pytest.mark.parametrize(
    "readme",
    [path for path in READMES if path.parent.name.endswith("_harness")],
    ids=lambda path: str(path.relative_to(PROJECT_ROOT)),
)
def test_readme_toml_examples_match_module_configuration(readme: Path) -> None:
    actual = tomllib.loads((readme.parent / "config.toml").read_text(encoding="utf-8"))
    examples = _fenced_examples(readme, "toml")
    assert len(examples) == 1
    for _, example in examples:
        assert tomllib.loads(example) == actual


@pytest.mark.parametrize("readme", READMES, ids=lambda path: str(path.relative_to(PROJECT_ROOT)))
def test_readme_cli_examples_use_supported_harness_options(readme: Path) -> None:
    for _, example in _fenced_examples(readme, "bash"):
        for command in example.replace("\\\n", " ").splitlines():
            if not (command := command.strip()) or command.startswith("#"):
                continue
            arguments = shlex.split(command)
            if len(arguments) < 3 or arguments[:2] != ["uv", "run"] or arguments[2] not in PARSERS:
                continue
            options = arguments[3:]
            if "--config" in options:
                index = options.index("--config")
                if index + 1 < len(options) and not Path(options[index + 1]).exists():
                    options = [*options[:index], *options[index + 2 :]]
            try:
                PARSERS[arguments[2]](options)
            except SystemExit:
                pytest.fail(f"Unsupported CLI options in {readme.relative_to(PROJECT_ROOT)}: {command}")


async def test_root_results_example_matches_the_current_serializer(tmp_path: Path) -> None:
    expected = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
    assert await build_example_report(tmp_path) == expected
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    assert readme.split(START, 1)[1].split(END, 1)[0].strip() == render_readme_example(expected)
    documents = [json.loads(content) for _, content in _fenced_examples(PROJECT_ROOT / "README.md", "json")]
    report = next(document for document in documents if isinstance(document, dict) and "results" in document)
    assert report == readme_excerpt(expected)
    assert report["schema_version"] == SCHEMA_VERSION
    scenario = report["results"][0]
    semantic_quality = scenario["metrics"]["task"]["semantic_quality"]
    actual = next(
        item
        for item in ScenarioDataset.model_validate_json(
            (PROJECT_ROOT / "run_harness/data/scenarios.json").read_text(encoding="utf-8")
        ).scenarios
        if item.id == scenario["scenario_id"]
    )

    assert scenario["metrics"]["task"]["tool_calls"]["expected"] == len(actual.expected.tools.required)
    assert semantic_quality == {"score": None, "dimensions": {}}
    assert set(scenario["metrics"]["task"]) == set(TASK_METRICS)
    assert set(scenario["metrics"]["audio"]) == set(AUDIO_METRICS) | {
        "metrics_version",
        "response_deadline_ms",
        "response_opportunities",
        "response_exclusion_reasons",
    }
    assert "floor" not in scenario["observability"]
    assert scenario["observability"]["interaction"]["attribution"] == "post_hoc_audio_and_transcript"
    assert scenario["observability"]["completion"]["policy"] == "caller_finish_tool_or_verified_outcome"
    assert "semantic_quality" not in report["summary"]


def test_readme_parsers_cover_all_public_console_commands() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert set(PARSERS) == set(project["project"]["scripts"])


def test_docs_do_not_advertise_retired_simulator_features() -> None:
    sources = [*READMES]
    for phase in ("crawl_harness", "walk_harness", "run_harness"):
        sources.extend((PROJECT_ROOT / phase / "assets").glob("*.ts"))
        sources.extend((PROJECT_ROOT / phase / "assets").glob("*.json"))
        sources.extend((PROJECT_ROOT / phase / "assets").glob("*.svg"))
    forbidden = (
        "optional floor control",
        "floor-monitor decisions",
        "RUN floor decisions",
        "records floor decisions",
        "pacing, floor decisions",
        "floor policy, caller models",
        "turn-based Realtime caller",
        '"policy": "caller_agenda"',
    )
    for path in sources:
        text = " ".join(path.read_text(encoding="utf-8").split()).casefold()
        for phrase in forbidden:
            assert phrase.casefold() not in text, f"Retired feature in {path.relative_to(PROJECT_ROOT)}: {phrase}"
