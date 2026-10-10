import datetime
import json
import os
import sys
from collections import Counter
from pathlib import Path

import yaml
from jsonschema import Draft7Validator, FormatChecker

GITHUB_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = GITHUB_DIR.parent


def load_yaml(path: Path):
    """
    Loads a YAML file, converting dates back to ISO strings so they can be
    checked against the JSON schemas.
    """
    with open(path, "r", encoding="utf-8") as f:
        return stringify_dates(yaml.safe_load(f))


def stringify_dates(value):
    """
    Recursively converts date and datetime values to ISO strings.
    """
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return [stringify_dates(item) for item in value]
    if isinstance(value, dict):
        return {key: stringify_dates(item) for key, item in value.items()}
    return value


def validate_schema(data, schema_path: Path, label: str) -> list[str]:
    """
    Returns one error per schema violation in `data`.
    """
    with open(schema_path, "r", encoding="utf-8") as f:
        schema = json.load(f)
    validator = Draft7Validator(schema, format_checker=FormatChecker())
    errors = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        location = "/".join(str(part) for part in error.path) or "<root>"
        errors.append(f"{label}: {location}: {error.message}")
    return errors


def find_duplicates(values: list[str]) -> list[str]:
    """
    Returns the values that appear more than once, sorted.
    """
    return sorted(value for value, count in Counter(values).items() if count > 1)


def check_registry_entries(entries: list[dict], repo_root: Path) -> list[str]:
    """
    Checks that registry entries point at existing files and that slugs and
    redirects do not collide.
    """
    errors = []
    root = repo_root.resolve()
    paths = []
    for entry in entries:
        full_path = (root / entry["path"]).resolve()
        if not full_path.is_relative_to(root) or not full_path.is_file():
            errors.append(f"registry.yaml: {entry['path']}: file does not exist in the repo")
        paths.append(str(full_path))

    for full_path in find_duplicates(paths):
        errors.append(f"registry.yaml: {os.path.relpath(full_path, root)}: path is listed more than once")

    slugs = [e["slug"] for e in entries]
    for slug in find_duplicates(slugs):
        errors.append(f"registry.yaml: {slug}: slug is used more than once")

    redirects = [r for e in entries for r in e.get("redirects", [])]
    for redirect in find_duplicates(redirects):
        errors.append(f"registry.yaml: {redirect}: redirect is used more than once")
    for redirect in sorted(set(redirects) & set(slugs)):
        errors.append(f"registry.yaml: {redirect}: redirect matches an existing slug")
    return errors


def main() -> None:
    """
    Main function to validate registry.yaml and authors.yaml.
    """
    registry = load_yaml(REPO_ROOT / "registry.yaml")
    authors = load_yaml(REPO_ROOT / "authors.yaml")

    registry_errors = validate_schema(
        registry, GITHUB_DIR / "registry_schema.json", "registry.yaml"
    )
    errors = registry_errors
    if isinstance(authors, dict) and not all(isinstance(key, str) for key in authors):
        errors.append("authors.yaml: every author key must be a string")
    else:
        errors += validate_schema(authors, GITHUB_DIR / "authors_schema.json", "authors.yaml")
    # The entry checks assume schema-valid entries.
    if not registry_errors:
        errors += check_registry_entries(registry, REPO_ROOT)

    for error in errors:
        print(error)
    if errors:
        print(f"{len(errors)} registry problem(s) found.")
        sys.exit(1)
    print(f"registry.yaml ({len(registry)} entries) and authors.yaml are valid.")


if __name__ == "__main__":
    main()
