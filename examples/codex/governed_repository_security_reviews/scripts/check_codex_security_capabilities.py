#!/usr/bin/env python3
"""Inspect recorded Codex Security help without invoking or installing any CLI.

Example from the repository root:

    python3 scripts/check_codex_security_capabilities.py \
      --version-file contracts/codex-security-cli/version.stdout.txt \
      --bulk-help-file contracts/codex-security-cli/bulk-help.stdout.txt \
      --scan-help-file contracts/codex-security-cli/scan-help.stdout.txt \
      --model gpt-5.6-terra --effort high

Exit 0 means recorded command declarations match the pinned recipe contract.
Exit 2 means abstain. Neither result permits a scan, spend, or external write.
This program only reads explicit regular files and prints a JSON receipt. It
does not inspect environment credentials, run npm, or execute product commands.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[1]
# The read-only contract must survive cleared environments and Python -I.
sys.dont_write_bytecode = True
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from fleet_security.surface import (  # noqa: E402
    RecordedCliHelp,
    inspect_codex_security_capabilities,
)


MAX_RECORDING_BYTES = 262_144


def read_recording(path: Path) -> str:
    """Read bounded UTF-8 evidence; refuse symlinks, devices and pipes."""

    if path.is_symlink():
        raise ValueError("recording must be a regular file")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as stream:
        metadata = os.fstat(stream.fileno())
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_RECORDING_BYTES:
            raise ValueError("recording must be a bounded regular file")
        data = stream.read(MAX_RECORDING_BYTES + 1)
    if not data or len(data) > MAX_RECORDING_BYTES:
        raise ValueError("recording is empty or too large")
    return data.decode("utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version-file", required=True, type=Path)
    parser.add_argument("--bulk-help-file", required=True, type=Path)
    parser.add_argument("--scan-help-file", type=Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--effort", required=True)
    parser.add_argument(
        "--bulk-flag", action="append", default=[],
        help="Additional required flag, for example --bulk-flag=--max-cost.",
    )
    parser.add_argument(
        "--per-attempt-max-cost-usd", type=float,
        help="Validate an intended positive estimated threshold; no spend is made.",
    )
    parser.add_argument(
        "--require-hard-campaign-cap", action="store_true",
        help="Fail closed: the native estimated threshold is not a hard campaign cap.",
    )
    parser.add_argument(
        "--require-draft-pr-authority", action="store_true",
        help="Fail closed: help inspection never grants external-write authority.",
    )
    arguments = parser.parse_args(argv)
    try:
        recording = RecordedCliHelp(
            version_output=read_recording(arguments.version_file),
            bulk_help=read_recording(arguments.bulk_help_file),
            scan_help=(
                read_recording(arguments.scan_help_file)
                if arguments.scan_help_file is not None else None
            ),
        )
    except (OSError, ValueError, UnicodeError):
        # Never echo recorded content, file contents or credentials in failures.
        print(json.dumps({
            "format": "codex-security-recorded-help-preflight/v1",
            "status": "abstain",
            "blockers": ["recorded_evidence_unreadable_or_unsafe"],
            "execution_authorised": False,
            "external_write_authorised": False,
        }, sort_keys=True))
        return 2
    report = inspect_codex_security_capabilities(
        recording,
        model=arguments.model,
        effort=arguments.effort,
        requested_bulk_flags=tuple(arguments.bulk_flag),
        per_attempt_max_cost_usd=arguments.per_attempt_max_cost_usd,
        require_hard_campaign_cap=arguments.require_hard_campaign_cap,
        require_draft_pr_authority=arguments.require_draft_pr_authority,
    )
    print(json.dumps(report.to_dict(), indent=2, sort_keys=True, allow_nan=False))
    return 0 if report.compatible else 2


if __name__ == "__main__":
    raise SystemExit(main())
