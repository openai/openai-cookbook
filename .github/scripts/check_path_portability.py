from __future__ import annotations

import subprocess
import sys
from collections import defaultdict
from collections.abc import Iterable
from pathlib import PurePosixPath


WINDOWS_RESERVED_NAMES = {
    "aux",
    "con",
    "nul",
    "prn",
    *(f"com{number}" for number in range(1, 10)),
    *(f"lpt{number}" for number in range(1, 10)),
    *(f"com{number}" for number in "¹²³"),
    *(f"lpt{number}" for number in "¹²³"),
}
WINDOWS_INVALID_CHARACTERS = frozenset('<>:"\\|?*')


def get_tracked_paths() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        check=True,
        stdout=subprocess.PIPE,
    )
    return [path.decode("utf-8") for path in result.stdout.split(b"\0") if path]


def normalize_windows_component(component: str) -> str:
    return component.lstrip(" ").rstrip(" .").casefold()


def is_reserved_windows_name(component: str) -> bool:
    stem = normalize_windows_component(component).split(".", 1)[0]
    return stem in WINDOWS_RESERVED_NAMES


def find_path_errors(tracked_paths: Iterable[str]) -> list[str]:
    errors: list[str] = []
    collisions: defaultdict[str, set[str]] = defaultdict(set)

    for path in sorted(tracked_paths):
        parts = PurePosixPath(path).parts
        normalized_path = "/".join(normalize_windows_component(part) for part in parts)
        collisions[normalized_path].add(path)

        for part in parts:
            if part.startswith(" "):
                errors.append(f"Leading space in path component: {path!r}")

            if part.endswith((" ", ".")):
                errors.append(f"Trailing space or period in path component: {path!r}")

            if is_reserved_windows_name(part):
                errors.append(f"Windows reserved device name in path: {path!r}")

            control_characters = sorted({ord(char) for char in part if ord(char) < 32})
            if control_characters:
                code_points = ", ".join(f"U+{value:04X}" for value in control_characters)
                errors.append(f"Windows control character ({code_points}) in path: {path!r}")

            invalid_characters = sorted(set(part) & WINDOWS_INVALID_CHARACTERS)
            if invalid_characters:
                characters = ", ".join(repr(char) for char in invalid_characters)
                errors.append(f"Windows-invalid character ({characters}) in path: {path!r}")

    for normalized_path, original_paths in sorted(collisions.items()):
        if len(original_paths) > 1:
            rendered_paths = "\n".join(f"  - {path!r}" for path in sorted(original_paths))
            errors.append(
                "Windows-normalized path collision:\n"
                f"  normalized: {normalized_path!r}\n"
                f"{rendered_paths}"
            )

    return errors


def main() -> None:
    tracked_paths = get_tracked_paths()
    errors = find_path_errors(tracked_paths)

    if errors:
        print("Path portability check failed:\n")
        print("\n\n".join(errors))
        sys.exit(1)

    print(f"Path portability check passed for {len(tracked_paths)} tracked paths.")


if __name__ == "__main__":
    main()
