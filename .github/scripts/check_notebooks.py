import subprocess
import sys
from pathlib import Path

import nbformat


def get_changed_notebooks(base_ref: str = "origin/main") -> list[Path]:
    """
    Returns a list of changed notebook paths in the current git branch
    compared to the specified base reference.
    """
    result = subprocess.run(
        ["git", "diff", "--name-only", base_ref, "--", "*.ipynb"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]


def is_valid_notebook(path: Path) -> bool:
    """
    Checks if the notebook at the given path is valid by attempting to read it
    with nbformat.
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            nbformat.read(f, as_version=4)
        return True
    except Exception as e:
        print(f"{path}: INVALID - {e}")
        return False


def main() -> None:
    """
    Main function to validate the format of changed notebooks.
    """
    changed_notebooks = get_changed_notebooks()
    if not changed_notebooks:
        print("No changed .ipynb files to validate.")
        sys.exit(0)

    print(f"Validating {len(changed_notebooks)} notebook(s)...")
    errors = 0
    for path in changed_notebooks:
        if not path.exists():
            continue  # skip deleted files
        if not is_valid_notebook(path):
            errors += 1

    if errors:
        print(f"{errors} invalid notebook(s) found.")
        sys.exit(1)
    else:
        print("All changed notebooks are valid.")


if __name__ == "__main__":
    main()
