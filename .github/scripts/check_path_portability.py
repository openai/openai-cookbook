from __future__ import annotations

import subprocess
import sys
import unicodedata
from collections import defaultdict
from pathlib import PurePosixPath


WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}
WINDOWS_INVALID_CHARS = set('<>:"\\|?*')


def get_tracked_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        capture_output=True,
        check=True,
    )
    return [
        path.decode("utf-8")
        for path in result.stdout.split(b"\0")
        if path
    ]


def normalize_windows_component(component: str) -> str:
    return component.rstrip(" .").casefold()


def has_control_characters(component: str) -> bool:
    return any(
        unicodedata.category(char).startswith("C")
        for char in component
    )


def is_reserved_windows_name(component: str) -> bool:
    stripped = component.rstrip(" .")
    stem = stripped.split(".", 1)[0].casefold()
    return stem in WINDOWS_RESERVED_NAMES


def has_windows_invalid_characters(component: str) -> bool:
    return any(char in WINDOWS_INVALID_CHARS for char in component)


def main() -> None:
    tracked_paths = get_tracked_paths()
    errors: list[str] = []
    collisions: defaultdict[str, list[str]] = defaultdict(list)

    for path in tracked_paths:
        parts = PurePosixPath(path).parts
        normalized_path = "/".join(normalize_windows_component(part) for part in parts)
        collisions[normalized_path].append(path)

        for part in parts:
            if part.endswith(" ") or part.endswith("."):
                errors.append(f"Trailing space or period in path component: {path}")

            if is_reserved_windows_name(part):
                errors.append(f"Windows reserved device name in path: {path}")

            if has_control_characters(part):
                errors.append(f"Control character in path: {path}")

            if has_windows_invalid_characters(part):
                errors.append(f"Windows-invalid character in path: {path}")

    for normalized_path, original_paths in sorted(collisions.items()):
        unique_paths = sorted(set(original_paths))
        if len(unique_paths) > 1:
            joined_paths = "\n".join(f"  - {path}" for path in unique_paths)
            errors.append(
                "Windows-normalized path collision:\n"
                f"  normalized: {normalized_path}\n"
                f"{joined_paths}"
            )

    if errors:
        print("Path portability check failed:\n")
        print("\n\n".join(errors))
        sys.exit(1)

    print(f"Path portability check passed for {len(tracked_paths)} tracked paths.")


if __name__ == "__main__":
    main()
