from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .benchmark import DEFAULT_HARNESS_DIR, load_harness_bundle, render_benchmark_report, run_benchmark
from .github_cache import DEFAULT_CACHE_ROOT, fetch_pull_requests, load_cached_pull_requests, repo_to_cache_key
from .reporting import default_run_id
from .state import reset_app_state


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
        help="Commands for the Level 1 benchmark harness.",
    )
    benchmark_subparsers = benchmark_parser.add_subparsers(
        dest="benchmark_command", required=True
    )

    run_parser = benchmark_subparsers.add_parser(
        "run",
        help="Run the Level 1 benchmark harness from cached PR data.",
    )
    run_parser.add_argument("--cache-key", type=str, default="openai_codex")
    run_parser.add_argument("--max-prs", type=int, default=None)
    run_parser.add_argument("--run-name", type=str, default="")

    report_parser = benchmark_subparsers.add_parser(
        "report",
        help="Re-render the HTML report for an existing Level 1 run.",
    )
    report_parser.add_argument("--run-dir", type=Path, required=True)

    return parser


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
        config, _, _, _, _, _ = load_harness_bundle(DEFAULT_HARNESS_DIR)
        snapshots = load_cached_pull_requests(DEFAULT_CACHE_ROOT, cache_key=args.cache_key)
        if args.max_prs and args.max_prs > 0:
            snapshots = snapshots[: args.max_prs]

        print("Benchmark run configuration:")
        print(f"- Reviewer model: {config.model}")
        print(f"- Grader model: {config.grader_model}")
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
        artifacts, summary = run_benchmark(
            cache_key=args.cache_key,
            max_prs=args.max_prs,
            run_name=resolved_run_name,
            harness_dir=DEFAULT_HARNESS_DIR,
            progress_callback=print,
        )
        print(f"Run directory: {artifacts.run_dir}")
        print(f"Report: {artifacts.report_html}")
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0

    if args.command == "benchmark" and args.benchmark_command == "report":
        report_path = render_benchmark_report(run_dir=args.run_dir)
        print(f"Wrote report: {report_path}")
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
