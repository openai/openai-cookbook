"""Scaffold a repo-local realtime eval folder that points at the shared harnesses."""

import argparse
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


HARNESS_ROOT = Path(__file__).resolve().parents[3]
ROOT_DIR = HARNESS_ROOT.parents[2]

CRAWL_REQUIRED_COLUMNS = [
    "example_id",
    "user_text",
    "gt_tool_call",
    "gt_tool_call_arg",
]
WALK_REQUIRED_COLUMNS = CRAWL_REQUIRED_COLUMNS + ["audio_path"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a realtime eval starter folder under examples/evals/realtime_evals.",
    )
    parser.add_argument(
        "--name", required=True, help="Eval name, used in the folder name."
    )
    parser.add_argument(
        "--harness",
        required=True,
        choices=["crawl", "walk", "run"],
        help="Realtime eval harness to target.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional explicit output directory. Defaults to examples/evals/realtime_evals/<name>_realtime_eval.",
    )
    parser.add_argument(
        "--system-prompt-file",
        type=Path,
        default=None,
        help="Existing system prompt file to copy into the generated folder.",
    )
    parser.add_argument(
        "--tools-file",
        type=Path,
        default=None,
        help="Existing tools JSON file to copy into the generated folder.",
    )
    parser.add_argument(
        "--data-path",
        type=Path,
        default=None,
        help="Existing data file to normalize or copy into the generated folder.",
    )
    parser.add_argument(
        "--scenario",
        type=str,
        default="",
        help="Short scenario or task summary used in starter data and the README.",
    )
    parser.add_argument(
        "--fixed-first-user-turn",
        type=str,
        default="",
        help="Starter first user utterance for run harness, or a representative prompt for crawl/walk.",
    )
    parser.add_argument(
        "--simulator-system-prompt",
        type=str,
        default="",
        help="Simulator prompt for run harness starter files.",
    )
    parser.add_argument(
        "--expected-tool-name",
        type=str,
        default="",
        help="Expected tool name for starter data.",
    )
    parser.add_argument(
        "--expected-tool-args-json",
        type=str,
        default="",
        help="Expected tool arguments as a JSON object string.",
    )
    parser.add_argument(
        "--tool-mocks-json",
        type=str,
        default="",
        help="Tool mocks as a JSON array string for run harness starter simulations.",
    )
    parser.add_argument(
        "--turn-grader",
        action="append",
        default=[],
        help="Turn-level grader criterion. May be provided multiple times.",
    )
    parser.add_argument(
        "--trace-grader",
        action="append",
        default=[],
        help="Trace-level grader criterion. May be provided multiple times.",
    )
    parser.add_argument(
        "--notes",
        type=str,
        default="",
        help="Optional notes that will be included in the README and manifest.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing output directory.",
    )
    return parser.parse_args()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.strip().lower())
    slug = re.sub(r"_+", "_", slug).strip("_")
    return slug or "starter"


def repo_relative(path: Path) -> str:
    return path.relative_to(ROOT_DIR).as_posix()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str) -> None:
    ensure_dir(path.parent)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def copy_or_write_text(
    source_path: Path | None, destination_path: Path, default_text: str
) -> None:
    ensure_dir(destination_path.parent)
    if source_path is not None:
        shutil.copy2(source_path, destination_path)
        return
    write_text(destination_path, default_text)


def write_tools_file(source_path: Path | None, destination_path: Path) -> None:
    ensure_dir(destination_path.parent)
    if source_path is not None:
        shutil.copy2(source_path, destination_path)
        return
    destination_path.write_text("[]\n", encoding="utf-8")


def parse_json_object(json_text: str) -> dict[str, Any]:
    if not json_text.strip():
        return {}
    parsed = json.loads(json_text)
    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object.")
    return parsed


def parse_json_array(json_text: str) -> list[dict[str, Any]]:
    if not json_text.strip():
        return []
    parsed = json.loads(json_text)
    if not isinstance(parsed, list):
        raise ValueError("Expected a JSON array.")
    normalized: list[dict[str, Any]] = []
    for item in parsed:
        if isinstance(item, dict):
            normalized.append(item)
    return normalized


def profile_dataframe(dataframe: pd.DataFrame) -> dict[str, Any]:
    missing_counts = {
        column: int(dataframe[column].isna().sum())
        for column in dataframe.columns
        if int(dataframe[column].isna().sum()) > 0
    }
    return {
        "rows": int(dataframe.shape[0]),
        "columns": list(dataframe.columns),
        "duplicate_rows": int(dataframe.duplicated().sum()),
        "missing_counts": missing_counts,
    }


def normalize_crawl_dataset(
    data_path: Path | None,
    destination_path: Path,
    starter_user_text: str,
    scenario: str,
    expected_tool_name: str,
    expected_tool_args_json: str,
) -> dict[str, Any]:
    if data_path is None:
        dataframe = pd.DataFrame(columns=CRAWL_REQUIRED_COLUMNS)
        source_mode = "awaiting_model_authored_starter_data"
    else:
        dataframe = pd.read_csv(data_path)
        source_mode = "copied_csv"
        if "user_text" not in dataframe.columns:
            raise ValueError("CSV must include a user_text column for crawl or walk.")
        if "example_id" not in dataframe.columns:
            dataframe.insert(
                0,
                "example_id",
                [f"ex_{index + 1:03d}" for index in range(len(dataframe))],
            )
        if "gt_tool_call" not in dataframe.columns:
            dataframe["gt_tool_call"] = expected_tool_name
        if "gt_tool_call_arg" not in dataframe.columns:
            dataframe["gt_tool_call_arg"] = expected_tool_args_json
        dataframe = dataframe.loc[
            :,
            [
                column
                for column in CRAWL_REQUIRED_COLUMNS
                if column in dataframe.columns
            ],
        ]

    ensure_dir(destination_path.parent)
    dataframe.to_csv(destination_path, index=False)
    return {
        "data_path": repo_relative(destination_path),
        "profile": profile_dataframe(dataframe),
        "source_mode": source_mode,
    }


def normalize_walk_dataset(
    data_path: Path | None,
    data_dir: Path,
    starter_user_text: str,
    scenario: str,
    expected_tool_name: str,
    expected_tool_args_json: str,
) -> dict[str, Any]:
    if data_path is None:
        source_csv_path = data_dir / "source_eval_dataset.csv"
        crawl_info = normalize_crawl_dataset(
            None,
            source_csv_path,
            starter_user_text,
            scenario,
            expected_tool_name,
            expected_tool_args_json,
        )
        return {
            "source_csv_path": repo_relative(source_csv_path),
            "walk_csv_path": repo_relative(data_dir / "walk_dataset.csv"),
            "audio_dir": repo_relative(data_dir / "audio"),
            "audio_generation_required": True,
            "profile": crawl_info["profile"],
            "source_mode": "awaiting_model_authored_starter_data",
        }

    dataframe = pd.read_csv(data_path)
    if "audio_path" in dataframe.columns:
        for column in CRAWL_REQUIRED_COLUMNS:
            if column not in dataframe.columns:
                if column == "example_id":
                    dataframe.insert(
                        0,
                        "example_id",
                        [f"ex_{index + 1:03d}" for index in range(len(dataframe))],
                    )
                else:
                    dataframe[column] = (
                        expected_tool_name
                        if column == "gt_tool_call"
                        else expected_tool_args_json
                    )
        walk_csv_path = data_dir / "walk_dataset.csv"
        dataframe = dataframe.loc[:, WALK_REQUIRED_COLUMNS]
        dataframe.to_csv(walk_csv_path, index=False)
        return {
            "walk_csv_path": repo_relative(walk_csv_path),
            "audio_generation_required": False,
            "profile": profile_dataframe(dataframe),
            "source_mode": "copied_walk_csv",
        }

    source_csv_path = data_dir / "source_eval_dataset.csv"
    crawl_info = normalize_crawl_dataset(
        data_path,
        source_csv_path,
        starter_user_text,
        scenario,
        expected_tool_name,
        expected_tool_args_json,
    )
    return {
        "source_csv_path": repo_relative(source_csv_path),
        "walk_csv_path": repo_relative(data_dir / "walk_dataset.csv"),
        "audio_dir": repo_relative(data_dir / "audio"),
        "audio_generation_required": True,
        "profile": crawl_info["profile"],
        "source_mode": "normalized_from_text_csv",
    }


def build_turn_level_graders(
    expected_tool_name: str,
    turn_graders: list[str],
) -> list[dict[str, Any]]:
    graders: list[dict[str, Any]] = []
    if expected_tool_name:
        graders.append({"id": "tool_call", "type": "tool_call"})
        graders.append({"id": "tool_call_args", "type": "tool_call_args"})
    for index, criterion in enumerate(turn_graders, start=1):
        graders.append(
            {
                "id": f"turn_grader_{index}",
                "type": "llm_as_judge",
                "criteria": criterion,
            }
        )
    return graders


def build_trace_level_graders(trace_graders: list[str]) -> list[dict[str, Any]]:
    graders: list[dict[str, Any]] = []
    for index, criterion in enumerate(trace_graders, start=1):
        graders.append(
            {
                "id": f"trace_grader_{index}",
                "type": "llm_as_judge",
                "criteria": criterion,
            }
        )
    if graders:
        return graders
    return [
        {
            "id": "goal_completion",
            "type": "llm_as_judge",
            "criteria": "The conversation resolves the user request correctly and ends cleanly.",
        }
    ]


def normalize_run_dataset(
    data_path: Path | None,
    eval_slug: str,
    eval_dir: Path,
    scenario: str,
    fixed_first_user_turn: str,
    simulator_system_prompt: str,
    expected_tool_name: str,
    expected_tool_args_json: str,
    tool_mocks_json: str,
    turn_graders: list[str],
    trace_graders: list[str],
) -> dict[str, Any]:
    simulations_csv_path = eval_dir / "data" / "simulations.csv"
    if data_path is not None:
        simulations_df = pd.read_csv(data_path)
        simulations_df.to_csv(simulations_csv_path, index=False)
        return {
            "simulations_csv_path": repo_relative(simulations_csv_path),
            "profile": profile_dataframe(simulations_df),
            "source_mode": "copied_csv",
        }

    template_path = eval_dir / "data" / f"{eval_slug}_simulation_template.json"
    expected_tool_args = (
        parse_json_object(expected_tool_args_json) if expected_tool_args_json else {}
    )
    tool_mocks = parse_json_array(tool_mocks_json) if tool_mocks_json else []
    template_simulation = {
        "simulation_id": f"{eval_slug}_replace_me",
        "scenario": scenario or "Replace with the scenario being evaluated.",
        "assistant": {
            "system_prompt_file": f"{eval_dir.name}/system_prompt.txt",
            "tools_file": f"{eval_dir.name}/tools.json",
            "model": "gpt-realtime",
        },
        "simulator": {
            "system_prompt": simulator_system_prompt
            or "Replace with the simulator prompt.",
            "model": "gpt-realtime",
            "voice": "marin",
        },
        "audio": {
            "input_format": "pcm16",
            "output_format": "pcm16",
            "sample_rate_hz": 24000,
            "chunk_ms": 20,
            "real_time": False,
        },
        "turns": {
            "fixed_first_user_turn": fixed_first_user_turn
            or "Replace with the first user turn.",
            "max_turns": 4,
        },
        "tool_mocks": tool_mocks,
        "expected_tool_call": {
            "name": expected_tool_name,
            "arguments": expected_tool_args,
        },
        "graders": {
            "turn_level": build_turn_level_graders(expected_tool_name, turn_graders),
            "trace_level": build_trace_level_graders(trace_graders),
        },
    }
    write_text(template_path, json.dumps(template_simulation, indent=2))
    simulations_df = pd.DataFrame(
        columns=[
            "simulation_id",
            "simulation_path",
            "enabled",
            "notes",
            "max_turns_override",
        ]
    )
    simulations_df.to_csv(simulations_csv_path, index=False)

    return {
        "simulations_csv_path": repo_relative(simulations_csv_path),
        "simulation_template_path": repo_relative(template_path),
        "profile": profile_dataframe(simulations_df),
        "source_mode": "awaiting_model_authored_starter_data",
    }


def build_run_commands(
    harness: str, eval_dir: Path, walk_info: dict[str, Any]
) -> dict[str, str]:
    results_dir = repo_relative(eval_dir / "results")
    prompt_path = repo_relative(eval_dir / "system_prompt.txt")
    tools_path = repo_relative(eval_dir / "tools.json")

    if harness == "crawl":
        data_path = repo_relative(eval_dir / "data" / "eval_dataset.csv")
        base_command = (
            "uv run python examples/evals/realtime_evals/crawl_harness/run_realtime_evals.py "
            f"--data-csv {data_path} "
            f"--system-prompt-file {prompt_path} "
            f"--tools-file {tools_path} "
            f"--results-dir {results_dir}"
        )
        return {
            "prep": "",
            "smoke": base_command + " --run-name smoke --max-examples 1",
            "full": base_command + " --run-name full",
        }

    if harness == "walk":
        if walk_info["audio_generation_required"]:
            prep_command = (
                "uv run python examples/evals/realtime_evals/walk_harness/generate_audio.py "
                f"--source-csv {walk_info['source_csv_path']} "
                f"--output-dir {walk_info['audio_dir']} "
                f"--output-csv {walk_info['walk_csv_path']}"
            )
        else:
            prep_command = ""
        data_path = walk_info["walk_csv_path"]
        base_command = (
            "uv run python examples/evals/realtime_evals/walk_harness/run_realtime_evals.py "
            f"--data-csv {data_path} "
            f"--system-prompt-file {prompt_path} "
            f"--tools-file {tools_path} "
            f"--results-dir {results_dir}"
        )
        return {
            "prep": prep_command,
            "smoke": base_command + " --run-name smoke --max-examples 1",
            "full": base_command + " --run-name full",
        }

    data_path = repo_relative(eval_dir / "data" / "simulations.csv")
    base_command = (
        "uv run python examples/evals/realtime_evals/run_harness/run_realtime_evals.py "
        f"--data-csv {data_path} "
        f"--assistant-system-prompt-file {prompt_path} "
        f"--assistant-tools-file {tools_path} "
        f"--results-dir {results_dir}"
    )
    return {
        "prep": "",
        "smoke": base_command + " --run-name smoke --max-examples 1",
        "full": base_command + " --run-name full",
    }


def markdown_list(items: list[str]) -> str:
    if not items:
        return "- None provided yet."
    return "\n".join(f"- {item}" for item in items)


def build_readme(
    eval_name: str,
    harness: str,
    eval_dir: Path,
    commands: dict[str, str],
    manifest: dict[str, Any],
    prompt_source: Path | None,
    tools_source: Path | None,
) -> str:
    harness_explanation = {
        "crawl": "Chosen for fast single-turn iteration with text prompts, expected tool calls, and deterministic replay.",
        "walk": "Chosen for saved-audio replay and more realistic telephony-style evaluation while staying comparable across runs.",
        "run": "Chosen for multi-turn simulated conversations, tool mocks, and conversation-level grading.",
    }[harness]

    file_edit_lines = [
        f"- `system_prompt.txt`: assistant instructions for this eval.",
        f"- `tools.json`: tool schema the assistant can call.",
    ]
    if harness == "run":
        file_edit_lines.append("- `data/simulations.csv`: index of simulations to run.")
        file_edit_lines.append(
            "- `data/*.json`: scenario, simulator, tool mocks, and graders."
        )
    elif harness == "walk" and manifest["data"].get("audio_generation_required"):
        file_edit_lines.append(
            "- `data/source_eval_dataset.csv`: source rows used to generate walk audio."
        )
        file_edit_lines.append(
            "- `data/walk_dataset.csv`: generated walk dataset used by the harness."
        )
    else:
        file_edit_lines.append("- `data/`: harness-specific dataset files.")

    next_step_lines = {
        "crawl": [
            "- Replace the starter prompt and empty tools file with your real assistant configuration.",
            "- Expand `data/eval_dataset.csv` so it covers the main user requests you care about.",
            "- Run the smoke test first, then the full run once the outputs look sane.",
        ],
        "walk": [
            "- Decide whether to keep generating audio from `data/source_eval_dataset.csv` or switch to your own CSV with `audio_path`.",
            "- Replace the starter prompt and empty tools file with your real assistant configuration.",
            "- Regenerate audio after changing the source CSV, then run the smoke test before the full run.",
        ],
        "run": [
            "- Edit the starter `data/*.json` file so the scenario, simulator prompt, tool mocks, and grader criteria match your use case.",
            "- Replace the starter prompt and empty tools file with your real assistant configuration.",
            "- Keep the first simulation small until the smoke run looks correct, then add more scenarios to `data/simulations.csv`.",
        ],
    }[harness]

    data_profile = manifest["data"].get("profile", {})
    missing_counts = data_profile.get("missing_counts", {})
    if missing_counts:
        missing_summary = "\n".join(
            f"- `{column}`: {count} missing value(s)"
            for column, count in missing_counts.items()
        )
    else:
        missing_summary = "- None detected in the scaffolded CSV."

    data_contract = {
        "crawl": "- Required columns: `example_id`, `user_text`.\n- Optional tool-grading columns: `gt_tool_call`, `gt_tool_call_arg`.",
        "walk": "- Required columns: `example_id`, `user_text`, `audio_path`.\n- Optional tool-grading columns: `gt_tool_call`, `gt_tool_call_arg`.",
        "run": "- Required index columns: `simulation_id`, `simulation_path`.\n- Each `sim_*.json` file should define assistant config, simulator prompt, audio config, turns, tool mocks, and graders.",
    }[harness]

    if data_profile:
        if missing_counts:
            missing_section = "- Missing values:\n" + missing_summary
        else:
            missing_section = "- Missing values: none detected in the scaffolded CSV."
        data_profile_section = (
            f"- Rows: `{data_profile.get('rows', 'n/a')}`\n"
            f"- Columns: `{', '.join(data_profile.get('columns', [])) or 'n/a'}`\n"
            f"- Duplicate rows: `{data_profile.get('duplicate_rows', 'n/a')}`\n"
            f"{missing_section}"
        )
    elif harness == "run":
        data_profile_section = (
            f"- Simulations CSV: `{manifest['data'].get('simulations_csv_path', 'n/a')}`\n"
            f"- Simulation template JSON: `{manifest['data'].get('simulation_template_path', 'n/a')}`\n"
            "- You should replace the template with 2 use-case-specific starter simulations before the first run."
        )
    else:
        data_profile_section = "- No CSV profile available yet."

    prep_section = ""
    if commands["prep"]:
        prep_section = (
            "## Preparation\n\n"
            "Run this once before the eval commands:\n\n"
            "```bash\n"
            f"{commands['prep']}\n"
            "```\n\n"
        )

    source_notes = [
        (
            f"- Prompt source: `{prompt_source}`"
            if prompt_source is not None
            else "- Prompt source: generated starter prompt."
        ),
        (
            f"- Tools source: `{tools_source}`"
            if tools_source is not None
            else "- Tools source: generated empty tools list."
        ),
        f"- Data source mode: `{manifest['data']['source_mode']}`.",
    ]
    if manifest["data"]["source_mode"] == "awaiting_model_authored_starter_data":
        source_notes.append(
            "- The scaffold script created template files only. You should author the initial starter data from the user’s use case."
        )

    troubleshooting_lines = [
        "- If commands fail with authentication errors, confirm `OPENAI_API_KEY` is set in the current shell.",
        "- If the harness reports missing columns, compare your dataset against the data contract above before changing the harness code.",
        "- Results land under `results/<run_name>/` inside this folder, including `results.csv`, `summary.json`, and event logs.",
    ]
    if harness == "walk":
        troubleshooting_lines.insert(
            1,
            "- If audio generation fails, install `ffmpeg` first: `brew install ffmpeg`.",
        )

    return f"""# {eval_name} Realtime Eval

## Overview

This folder bootstraps a **{harness}** realtime eval under `examples/evals/realtime_evals/`.

{harness_explanation}

## Why This Harness

- `crawl` is best for fast tool-calling and instruction-following iteration.
- `walk` is best when audio realism matters and you want to replay saved or generated phone-style audio.
- `run` is best when the eval target depends on multiple turns, tool outputs, or conversation-level success.
- For this folder, **{harness}** was selected because it matches the current request most closely.

## Files To Edit First

{chr(10).join(file_edit_lines)}

## Suggested Next Steps

{chr(10).join(next_step_lines)}

## Environment Setup

From the repository root:

```bash
uv venv .venv
source .venv/bin/activate
uv sync --group dev
export OPENAI_API_KEY="your_api_key"
```

{prep_section}## Smoke Test

```bash
{commands["smoke"]}
```

## Full Run

```bash
{commands["full"]}
```

## Harness Test Suite

```bash
pytest examples/evals/realtime_evals/tests -q
```

## Results Viewer

After a run finishes, inspect it in the shared Streamlit viewer:

```bash
make streamlit
```

Then open the local Streamlit URL and use:

- `Comparison View` to compare this folder's runs against other saved runs for the same harness.
- `Run Viewer` to inspect rows, text input/output, audio, and event logs.

The viewer auto-discovers runs written under `{repo_relative(eval_dir / "results")}`.

## Data Contract

{data_contract}

## Current Data Profile

{data_profile_section}

## Requested Graders

### Turn-Level

{markdown_list(manifest["grader_requests"]["turn_level"])}

### Trace-Level

{markdown_list(manifest["grader_requests"]["trace_level"])}

## Bootstrap Notes

{chr(10).join(source_notes)}
{f"- Notes: {manifest['notes']}" if manifest['notes'] else "- Notes: none."}

## Troubleshooting

{chr(10).join(troubleshooting_lines)}
"""


def main() -> None:
    args = parse_args()

    eval_slug = slugify(args.name)
    output_dir = args.output_dir or (HARNESS_ROOT / f"{eval_slug}_realtime_eval")
    output_dir = output_dir.resolve()
    try:
        output_dir.relative_to(HARNESS_ROOT)
    except ValueError as exc:
        raise ValueError(f"Output directory must live under {HARNESS_ROOT}") from exc

    if output_dir.exists():
        if not args.force:
            raise FileExistsError(
                f"{output_dir} already exists. Use --force to overwrite it."
            )
        shutil.rmtree(output_dir)

    ensure_dir(output_dir)
    ensure_dir(output_dir / "data")
    ensure_dir(output_dir / "results")

    prompt_path = output_dir / "system_prompt.txt"
    tools_path = output_dir / "tools.json"
    starter_user_text = (
        args.fixed_first_user_turn
        or args.scenario
        or "Please replace this with a representative user request."
    )
    system_prompt_text = (
        "Replace this starter prompt with the assistant instructions for your realtime eval.\n"
        "Keep tool-calling behavior, safety constraints, and response style explicit.\n"
    )
    simulator_prompt_text = (
        args.simulator_system_prompt
        or "You are the user in a voice call. Stay in character, answer briefly, and end with END_CALL once the goal is complete."
    )

    copy_or_write_text(args.system_prompt_file, prompt_path, system_prompt_text)
    write_tools_file(args.tools_file, tools_path)

    expected_tool_args_json = args.expected_tool_args_json.strip()
    if expected_tool_args_json:
        parse_json_object(expected_tool_args_json)

    if args.harness == "crawl":
        data_info = normalize_crawl_dataset(
            args.data_path,
            output_dir / "data" / "eval_dataset.csv",
            starter_user_text,
            args.scenario,
            args.expected_tool_name.strip(),
            expected_tool_args_json,
        )
    elif args.harness == "walk":
        data_info = normalize_walk_dataset(
            args.data_path,
            output_dir / "data",
            starter_user_text,
            args.scenario,
            args.expected_tool_name.strip(),
            expected_tool_args_json,
        )
    else:
        data_info = normalize_run_dataset(
            data_path=args.data_path,
            eval_slug=eval_slug,
            eval_dir=output_dir,
            scenario=args.scenario or "Replace this with the scenario being evaluated.",
            fixed_first_user_turn=starter_user_text,
            simulator_system_prompt=simulator_prompt_text,
            expected_tool_name=args.expected_tool_name.strip(),
            expected_tool_args_json=expected_tool_args_json,
            tool_mocks_json=args.tool_mocks_json.strip(),
            turn_graders=args.turn_grader,
            trace_graders=args.trace_grader,
        )

    manifest = {
        "name": args.name,
        "slug": eval_slug,
        "harness": args.harness,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "eval_dir": repo_relative(output_dir),
        "data": data_info,
        "grader_requests": {
            "turn_level": args.turn_grader,
            "trace_level": args.trace_grader,
        },
        "notes": args.notes.strip(),
    }

    commands = build_run_commands(args.harness, output_dir, data_info)
    readme_text = build_readme(
        args.name,
        args.harness,
        output_dir,
        commands,
        manifest,
        args.system_prompt_file,
        args.tools_file,
    )
    write_text(output_dir / "README.md", readme_text)
    write_text(output_dir / "bootstrap_manifest.json", json.dumps(manifest, indent=2))

    print(
        json.dumps(
            {"eval_dir": repo_relative(output_dir), "harness": args.harness}, indent=2
        )
    )


if __name__ == "__main__":
    main()
