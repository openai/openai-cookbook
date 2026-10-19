#!/usr/bin/env python3
"""Build or verify the self-contained starter download using Python's stdlib.

For contribution maintainers: run this after changing the example, then include
the refreshed ZIP with the source change. Python is not a user prerequisite.
"""

import argparse
import hashlib
import io
import json
from pathlib import Path
import zipfile


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "assets/chatgpt-usage-budget-starter.zip"
PREFIX = "chatgpt-usage-budget-starter/"
SOURCE_PATTERNS = (
    ".gitignore", "README.md", "package.json", "package-lock.json",
    "assets/*.svg", "assets/release-explorer.html", "docs/*.md", "src/*.mjs",
    "test/*.test.mjs", "aws/*.mjs", "aws/template.yaml",
    "aws/parameters.example.json", "aws/package.json", "aws/package-lock.json",
)
EXCLUDED_PARTS = {".private", ".local", "node_modules", "dist", ".git"}


def source_files():
    """Allow only documented source types; never package runtime state."""
    files = {}
    for pattern in SOURCE_PATTERNS:
        matches = sorted(ROOT.glob(pattern))
        if not matches:
            raise ValueError(f"No source matches required pattern: {pattern}")
        for path in matches:
            relative = path.relative_to(ROOT)
            if path.is_symlink() or EXCLUDED_PARTS.intersection(relative.parts):
                raise ValueError(f"Unsafe source path: {relative}")
            files[relative.as_posix()] = path.read_bytes()
    license_path = ROOT.parents[2] / "LICENSE"
    files["LICENSE"] = license_path.read_bytes()
    return dict(sorted(files.items()))


def build_archive(files):
    manifest = {
        "files": [{"path": name, "sha256": hashlib.sha256(data).hexdigest()}
                  for name, data in files.items()]
    }
    contents = dict(files)
    contents["source-manifest.json"] = (json.dumps(manifest, indent=2) + "\n").encode()
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(contents.items()):
            entry = zipfile.ZipInfo(PREFIX + name, date_time=(2000, 1, 1, 0, 0, 0))
            entry.create_system = 3
            entry.external_attr = 0o100644 << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(entry, data, compresslevel=9)
    return buffer.getvalue()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="verify that the download matches current source")
    args = parser.parse_args()
    files = source_files()
    expected = build_archive(files)
    if args.check:
        if not ARCHIVE.exists() or ARCHIVE.read_bytes() != expected:
            raise SystemExit("Starter download is stale; rerun this script without --check.")
    else:
        ARCHIVE.write_bytes(expected)
    with zipfile.ZipFile(io.BytesIO(expected)) as archive:
        if archive.testzip() is not None:
            raise SystemExit("Starter download failed ZIP validation.")
    action = "Verified" if args.check else "Packaged"
    print(f"{action} {len(files)} source files + manifest ({len(expected):,} bytes).")


if __name__ == "__main__":
    main()
