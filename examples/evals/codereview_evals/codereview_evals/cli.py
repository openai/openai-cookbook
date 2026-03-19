from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .benchmark import DEFAULT_HARNESS_DIR, render_benchmark_report, run_benchmark
from .github_cache import DEFAULT_CACHE_ROOT, fetch_pull_requests, repo_to_cache_key
from .state import reset_app_state


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
    run_parser.add_argument("--max-prs", type=int, default=5)
    run_parser.add_argument("--run-name", type=str, default="")

    report_parser = benchmark_subparsers.add_parser(
        "report",
        help="Re-render the HTML report for an existing Level 1 run.",
    )
    report_parser.add_argument("--run-dir", type=Path, required=True)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

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
        artifacts, summary = run_benchmark(
            cache_key=args.cache_key,
            max_prs=args.max_prs,
            run_name=args.run_name,
            harness_dir=DEFAULT_HARNESS_DIR,
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
