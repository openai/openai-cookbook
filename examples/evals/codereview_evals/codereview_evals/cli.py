from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .evals_api import run_evals
from .github_cache import DEFAULT_CACHE_ROOT, fetch_pull_requests, repo_to_cache_key
from .prepare import prepare_dataset
from .state import reset_app_state


def _print_json(data: object) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=False))


def _resolve_cache_key(repo: str | None, cache_key: str | None) -> str:
    if cache_key:
        return cache_key
    if repo:
        return repo_to_cache_key(repo)
    raise ValueError("Either --cache-key or --repo must be provided.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="evalcr")
    subparsers = parser.add_subparsers(dest="command")

    fetch_parser = subparsers.add_parser("fetch-prs", help="Fetch and cache pull requests")
    fetch_parser.add_argument("--repo", required=True)
    fetch_parser.add_argument("--limit", type=int, default=50)
    fetch_parser.add_argument("--cache-key", default=None)
    fetch_parser.add_argument("--refresh", action="store_true")

    prepare_parser = subparsers.add_parser(
        "prepare-dataset",
        help="Prepare a JSONL dataset for one of the cookbook levels",
    )
    prepare_parser.add_argument("--level", type=int, choices=[1, 2, 3], required=True)
    prepare_parser.add_argument("--cache-key", default=None)
    prepare_parser.add_argument("--repo", default=None)
    prepare_parser.add_argument("--max-prs", type=int, default=None)
    prepare_parser.add_argument("--refresh-derived", action="store_true")

    run_parser = subparsers.add_parser(
        "run-evals",
        help="Upload a prepared dataset and execute an Evals API run",
    )
    run_parser.add_argument("--level", type=int, choices=[1, 2, 3], required=True)
    run_parser.add_argument("--cache-key", default=None)
    run_parser.add_argument("--repo", default=None)
    run_parser.add_argument("--dataset-path", default=None)
    run_parser.add_argument("--run-name", default=None)
    run_parser.add_argument("--poll-interval-seconds", type=int, default=5)
    run_parser.add_argument("--timeout-seconds", type=int, default=900)

    reset_parser = subparsers.add_parser(
        "reset",
        help="Delete cached PRs, prepared datasets, and generated run artifacts",
    )
    reset_parser.add_argument("--repo", default=None)
    reset_parser.add_argument("--cache-key", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "fetch-prs":
        cache_dir, manifest = fetch_pull_requests(
            repo=args.repo,
            limit=args.limit,
            cache_key=args.cache_key,
            refresh=args.refresh,
            cache_root=DEFAULT_CACHE_ROOT,
            progress_callback=print,
        )
        print(f"Cached pull requests in {cache_dir}")
        _print_json(manifest)
        return 0

    if args.command == "prepare-dataset":
        artifacts, summary = prepare_dataset(
            level=args.level,
            cache_key=_resolve_cache_key(args.repo, args.cache_key),
            max_prs=args.max_prs,
            refresh_derived=args.refresh_derived,
            progress_callback=print,
        )
        print(f"Prepared dataset: {artifacts.dataset_path}")
        _print_json(summary)
        return 0

    if args.command == "run-evals":
        cache_key = _resolve_cache_key(args.repo, args.cache_key)
        dataset_path = Path(args.dataset_path) if args.dataset_path else None
        artifacts, summary = run_evals(
            level=args.level,
            cache_key=cache_key,
            dataset_path=dataset_path,
            run_name=args.run_name,
            poll_interval_seconds=args.poll_interval_seconds,
            timeout_seconds=args.timeout_seconds,
            progress_callback=print,
        )
        print(f"Run directory: {artifacts.run_dir}")
        print(f"Dataset: {artifacts.dataset_path}")
        _print_json(summary)
        return 0

    if args.command == "reset":
        summary = reset_app_state(
            cache_key=_resolve_cache_key(args.repo, args.cache_key),
            cache_root=DEFAULT_CACHE_ROOT,
        )
        _print_json(summary)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
