from __future__ import annotations

import argparse
from dataclasses import replace
import functools
import http.server
import json
import socketserver
import sys
from pathlib import Path
from typing import Sequence

from .benchmark import DEFAULT_HARNESS_DIR, load_harness_bundle, render_benchmark_report, run_benchmark
from .github_cache import DEFAULT_CACHE_ROOT, fetch_pull_requests, load_cached_pull_requests, repo_to_cache_key
from .pairwise import (
    DEFAULT_PAIRWISE_HARNESS_DIR,
    load_pairwise_harness_bundle,
    render_pairwise_report,
    run_pairwise,
)
from .optimizer import (
    DEFAULT_OPTIMIZER_HARNESS_DIR,
    load_optimizer_harness_bundle,
    render_optimizer_report,
    run_optimizer,
)
from .reporting import default_run_id
from .state import reset_app_state

HARNESS_TYPE_TO_DIR = {
    "benchmark": "Level 1 benchmark harness",
    "pairwise": "Level 2 pairwise harness",
    "optimizer": "Level 3 optimizer harness",
}
REASONING_EFFORT_CHOICES = ("default", "none", "minimal", "low", "medium", "high", "xhigh")


def _find_missing_subcommand_parser(
    parser: argparse.ArgumentParser, argv: Sequence[str]
) -> argparse.ArgumentParser | None:
    current_parser = parser
    index = 0

    while True:
        subparsers_action = next(
            (
                action
                for action in current_parser._actions
                if isinstance(action, argparse._SubParsersAction)
            ),
            None,
        )
        if subparsers_action is None:
            return None

        matched_choice = None
        matched_index = None
        for offset, token in enumerate(argv[index:], start=index):
            if token in subparsers_action.choices:
                matched_choice = token
                matched_index = offset
                break
            if not token.startswith("-"):
                return None

        if matched_choice is None:
            return current_parser

        current_parser = subparsers_action.choices[matched_choice]
        index = matched_index + 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="evalcr",
        description="Code review eval CLI backed by cached GitHub PR data.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser(
        "fetch-prs",
        help="Fetch pull requests from GitHub and persist a reusable local cache.",
    )
    fetch_parser.add_argument("--repo", type=str, default="openai/codex")
    fetch_parser.add_argument("--limit", type=int, default=50)
    fetch_parser.add_argument("--cache-key", type=str, default="")
    fetch_parser.add_argument("--refresh", action="store_true")

    reset_parser = subparsers.add_parser(
        "reset",
        help="Delete cached PR data and generated benchmark artifacts.",
    )
    reset_parser.add_argument("--cache-key", type=str, default="")
    reset_parser.add_argument("--repo", type=str, default="openai/codex")

    benchmark_parser = subparsers.add_parser(
        "benchmark",
        help="Commands for the benchmark, pairwise, and optimizer harnesses.",
    )
    benchmark_subparsers = benchmark_parser.add_subparsers(
        dest="benchmark_command", required=True
    )

    run_parser = benchmark_subparsers.add_parser(
        "run",
        help="Run a harness from cached PR data.",
    )
    run_parser.add_argument(
        "--type",
        choices=tuple(HARNESS_TYPE_TO_DIR),
        required=True,
        help="Harness type: benchmark (Level 1), pairwise (Level 2), optimizer (Level 3).",
    )
    run_parser.add_argument("--cache-key", type=str, default="openai_codex")
    run_parser.add_argument("--max-prs", type=int, default=None)
    run_parser.add_argument("--run-name", type=str, default="")
    run_parser.add_argument("--reviewer-model", type=str, default="")
    run_parser.add_argument("--grader-model", type=str, default="")
    run_parser.add_argument("--optimizer-model", type=str, default="")
    run_parser.add_argument(
        "--reviewer-reasoning-effort",
        choices=REASONING_EFFORT_CHOICES,
        default="",
        help="Override reviewer reasoning effort. Use 'default' to clear the harness setting.",
    )
    run_parser.add_argument(
        "--grader-reasoning-effort",
        choices=REASONING_EFFORT_CHOICES,
        default="",
        help="Override grader reasoning effort. Use 'default' to clear the harness setting.",
    )
    run_parser.add_argument(
        "--optimizer-reasoning-effort",
        choices=REASONING_EFFORT_CHOICES,
        default="",
        help="Override optimizer reasoning effort. Use 'default' to clear the harness setting.",
    )
    run_parser.add_argument("--reviewer-max-output-tokens", type=int, default=None)
    run_parser.add_argument("--grader-max-output-tokens", type=int, default=None)
    run_parser.add_argument("--optimizer-max-output-tokens", type=int, default=None)
    run_parser.add_argument("--max-concurrency", type=int, default=None)
    run_parser.add_argument(
        "--disable-benchmark-cache",
        action="store_true",
        help="Disable persistent pointwise benchmark caching for '--type optimizer'.",
    )
    run_parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Override the optimizer step cap for '--type optimizer'.",
    )
    run_parser.add_argument(
        "--score-threshold",
        type=float,
        default=None,
        help="Override the optimizer composite score threshold for '--type optimizer'.",
    )

    report_parser = benchmark_subparsers.add_parser(
        "report",
        help="Re-render the HTML report for an existing saved run.",
    )
    report_parser.add_argument("--run-dir", type=Path, required=True)

    visualize_parser = subparsers.add_parser(
        "visualize",
        help="Serve a completed harness run over HTTP on port 8000.",
    )
    visualize_parser.add_argument(
        "--run-id",
        type=str,
        required=True,
        help="Run directory name under the selected harness results folder.",
    )
    visualize_parser.add_argument(
        "--type",
        choices=tuple(HARNESS_TYPE_TO_DIR),
        default="benchmark",
        help="Harness type to visualize. Defaults to benchmark.",
    )

    return parser


def _resolve_run_harness_dir(harness_type: str) -> Path:
    if harness_type == "benchmark":
        return DEFAULT_HARNESS_DIR
    if harness_type == "pairwise":
        return DEFAULT_PAIRWISE_HARNESS_DIR
    if harness_type == "optimizer":
        return DEFAULT_OPTIMIZER_HARNESS_DIR
    raise KeyError(f"Unknown harness type: {harness_type}")


def _resolve_report_renderer(run_dir: Path):
    harness_name = run_dir.parent.parent.name
    if harness_name == DEFAULT_OPTIMIZER_HARNESS_DIR.name:
        return render_optimizer_report
    if harness_name == DEFAULT_PAIRWISE_HARNESS_DIR.name:
        return render_pairwise_report
    return render_benchmark_report


def _resolve_visualize_run_dir(
    run_id: str, harness_dir: Path | None = None
) -> Path:
    harness_dir = harness_dir or DEFAULT_HARNESS_DIR
    run_dir = harness_dir / "results" / run_id
    if not run_dir.exists():
        raise FileNotFoundError(f"No benchmark run found for {run_id!r} at {run_dir}.")
    report_path = run_dir / "report.html"
    if not report_path.exists():
        raise FileNotFoundError(f"Expected rendered report at {report_path}, but it was not found.")
    return run_dir


def _serve_run_visualization(run_dir: Path, port: int = 8000) -> None:
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(run_dir))
    with socketserver.TCPServer(("", port), handler) as server:
        print(f"Serving benchmark run from: {run_dir}")
        print(f"Report URL: http://127.0.0.1:{port}/report.html")
        print("Press Ctrl+C to stop.")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nStopped visualization server.")


def _resolve_reasoning_override(raw_value: str, current_value: str | None) -> str | None:
    if not raw_value:
        return current_value
    if raw_value == "default":
        return None
    return raw_value


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    raw_args = list(sys.argv[1:] if argv is None else argv)
    if not raw_args:
        parser.print_help()
        return 0
    missing_subcommand_parser = _find_missing_subcommand_parser(parser, raw_args)
    if missing_subcommand_parser is not None:
        missing_subcommand_parser.print_help()
        return 0

    args = parser.parse_args(raw_args)

    if args.command == "fetch-prs":
        key = args.cache_key or repo_to_cache_key(args.repo)
        cache_dir, manifest = fetch_pull_requests(
            repo=args.repo,
            limit=args.limit,
            cache_key=key,
            refresh=args.refresh,
            cache_root=DEFAULT_CACHE_ROOT,
            progress_callback=print,
        )
        print(f"Cache key: {key}")
        print(f"Cache directory: {cache_dir}")
        print(json.dumps(manifest, indent=2, ensure_ascii=False))
        return 0

    if args.command == "reset":
        key = args.cache_key or repo_to_cache_key(args.repo)
        summary = reset_app_state(
            cache_key=key,
            cache_root=DEFAULT_CACHE_ROOT,
            harness_dir=DEFAULT_HARNESS_DIR,
        )
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    if args.command == "benchmark" and args.benchmark_command == "run":
        harness_dir = _resolve_run_harness_dir(args.type)
        if args.type == "benchmark":
            config, _, _, _, _, _ = load_harness_bundle(harness_dir)
            config = replace(
                config,
                model=args.reviewer_model or config.model,
                grader_model=args.grader_model or config.grader_model,
                reviewer_reasoning_effort=_resolve_reasoning_override(
                    args.reviewer_reasoning_effort, config.reviewer_reasoning_effort
                ),
                grader_reasoning_effort=_resolve_reasoning_override(
                    args.grader_reasoning_effort, config.grader_reasoning_effort
                ),
                reviewer_max_output_tokens=(
                    args.reviewer_max_output_tokens
                    if args.reviewer_max_output_tokens is not None
                    else config.reviewer_max_output_tokens
                ),
                grader_max_output_tokens=(
                    args.grader_max_output_tokens
                    if args.grader_max_output_tokens is not None
                    else config.grader_max_output_tokens
                ),
                max_concurrency=args.max_concurrency or config.max_concurrency,
            )
        elif args.type == "pairwise":
            config, _, _, _, _, _, _, _ = load_pairwise_harness_bundle(harness_dir)
            config = replace(
                config,
                model=args.reviewer_model or config.model,
                grader_model=args.grader_model or config.grader_model,
                reviewer_reasoning_effort=_resolve_reasoning_override(
                    args.reviewer_reasoning_effort, config.reviewer_reasoning_effort
                ),
                grader_reasoning_effort=_resolve_reasoning_override(
                    args.grader_reasoning_effort, config.grader_reasoning_effort
                ),
                reviewer_max_output_tokens=(
                    args.reviewer_max_output_tokens
                    if args.reviewer_max_output_tokens is not None
                    else config.reviewer_max_output_tokens
                ),
                grader_max_output_tokens=(
                    args.grader_max_output_tokens
                    if args.grader_max_output_tokens is not None
                    else config.grader_max_output_tokens
                ),
                max_concurrency=args.max_concurrency or config.max_concurrency,
            )
        else:
            config, *_ = load_optimizer_harness_bundle(harness_dir)
            config = replace(
                config,
                model=args.reviewer_model or config.model,
                grader_model=args.grader_model or config.grader_model,
                optimizer_model=args.optimizer_model or config.optimizer_model,
                reviewer_reasoning_effort=_resolve_reasoning_override(
                    args.reviewer_reasoning_effort, config.reviewer_reasoning_effort
                ),
                grader_reasoning_effort=_resolve_reasoning_override(
                    args.grader_reasoning_effort, config.grader_reasoning_effort
                ),
                optimizer_reasoning_effort=_resolve_reasoning_override(
                    args.optimizer_reasoning_effort, config.optimizer_reasoning_effort
                ),
                reviewer_max_output_tokens=(
                    args.reviewer_max_output_tokens
                    if args.reviewer_max_output_tokens is not None
                    else config.reviewer_max_output_tokens
                ),
                grader_max_output_tokens=(
                    args.grader_max_output_tokens
                    if args.grader_max_output_tokens is not None
                    else config.grader_max_output_tokens
                ),
                optimizer_max_output_tokens=(
                    args.optimizer_max_output_tokens
                    if args.optimizer_max_output_tokens is not None
                    else config.optimizer_max_output_tokens
                ),
                max_concurrency=args.max_concurrency or config.max_concurrency,
            )
        snapshots = load_cached_pull_requests(DEFAULT_CACHE_ROOT, cache_key=args.cache_key)
        if args.max_prs and args.max_prs > 0:
            snapshots = snapshots[: args.max_prs]

        print("Benchmark run configuration:")
        print(f"- Harness type: {args.type}")
        print(f"- Reviewer model: {config.model}")
        print(f"- Grader model: {config.grader_model}")
        print(f"- Reviewer reasoning effort: {config.reviewer_reasoning_effort or 'default'}")
        print(f"- Grader reasoning effort: {config.grader_reasoning_effort or 'default'}")
        print(
            f"- Reviewer max output tokens: {config.reviewer_max_output_tokens if config.reviewer_max_output_tokens is not None else 'unbounded'}"
        )
        print(
            f"- Grader max output tokens: {config.grader_max_output_tokens if config.grader_max_output_tokens is not None else 'unbounded'}"
        )
        print(f"- Max concurrency: {config.max_concurrency}")
        if args.type == "optimizer":
            print(f"- Optimizer model: {config.optimizer_model}")
            print(f"- Optimizer reasoning effort: {config.optimizer_reasoning_effort or 'default'}")
            print(
                f"- Optimizer max output tokens: {config.optimizer_max_output_tokens if config.optimizer_max_output_tokens is not None else 'unbounded'}"
            )
            print(f"- Benchmark cache: {'disabled' if args.disable_benchmark_cache else 'enabled'}")
            print(f"- Max steps: {args.max_steps if args.max_steps is not None else config.max_steps}")
            print(
                f"- Score threshold: {args.score_threshold if args.score_threshold is not None else config.score_threshold}"
            )
        print(f"- Cache key: {args.cache_key}")
        print(f"- Selected PRs: {len(snapshots)}")
        try:
            confirmation = input("Press Enter to start, or type 'cancel' to abort: ")
        except KeyboardInterrupt:
            print("\nCancelled.")
            return 0
        if confirmation.strip().lower() == "cancel":
            print("Cancelled.")
            return 0

        resolved_run_name = default_run_id(args.run_name)
        print(f"Run name: {resolved_run_name}")
        if args.type == "benchmark":
            artifacts, summary = run_benchmark(
                cache_key=args.cache_key,
                max_prs=args.max_prs,
                run_name=resolved_run_name,
                harness_dir=harness_dir,
                progress_callback=print,
                reviewer_model_override=args.reviewer_model or None,
                grader_model_override=args.grader_model or None,
                reviewer_reasoning_effort_override=args.reviewer_reasoning_effort or None,
                grader_reasoning_effort_override=args.grader_reasoning_effort or None,
                reviewer_max_output_tokens_override=args.reviewer_max_output_tokens,
                grader_max_output_tokens_override=args.grader_max_output_tokens,
                max_concurrency_override=args.max_concurrency,
            )
        elif args.type == "pairwise":
            artifacts, summary = run_pairwise(
                cache_key=args.cache_key,
                max_prs=args.max_prs,
                run_name=resolved_run_name,
                harness_dir=harness_dir,
                progress_callback=print,
                reviewer_model_override=args.reviewer_model or None,
                grader_model_override=args.grader_model or None,
                reviewer_reasoning_effort_override=args.reviewer_reasoning_effort or None,
                grader_reasoning_effort_override=args.grader_reasoning_effort or None,
                reviewer_max_output_tokens_override=args.reviewer_max_output_tokens,
                grader_max_output_tokens_override=args.grader_max_output_tokens,
                max_concurrency_override=args.max_concurrency,
            )
        else:
            artifacts, summary = run_optimizer(
                cache_key=args.cache_key,
                max_prs=args.max_prs,
                run_name=resolved_run_name,
                harness_dir=harness_dir,
                progress_callback=print,
                max_steps=args.max_steps,
                score_threshold=args.score_threshold,
                reviewer_model_override=args.reviewer_model or None,
                grader_model_override=args.grader_model or None,
                optimizer_model_override=args.optimizer_model or None,
                reviewer_reasoning_effort_override=args.reviewer_reasoning_effort or None,
                grader_reasoning_effort_override=args.grader_reasoning_effort or None,
                optimizer_reasoning_effort_override=args.optimizer_reasoning_effort or None,
                reviewer_max_output_tokens_override=args.reviewer_max_output_tokens,
                grader_max_output_tokens_override=args.grader_max_output_tokens,
                optimizer_max_output_tokens_override=args.optimizer_max_output_tokens,
                max_concurrency_override=args.max_concurrency,
                enable_benchmark_cache=not args.disable_benchmark_cache,
            )
        print(f"Run directory: {artifacts.run_dir}")
        print(f"Report: {artifacts.report_html}")
        print(f"Visualizer: evalcr visualize --type {args.type} --run-id {resolved_run_name}")
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    if args.command == "benchmark" and args.benchmark_command == "report":
        report_renderer = _resolve_report_renderer(args.run_dir)
        report_path = report_renderer(run_dir=args.run_dir)
        print(f"Wrote report: {report_path}")
        return 0

    if args.command == "visualize":
        harness_dir = _resolve_run_harness_dir(args.type)
        run_dir = _resolve_visualize_run_dir(args.run_id, harness_dir=harness_dir)
        _serve_run_visualization(run_dir=run_dir, port=8000)
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
