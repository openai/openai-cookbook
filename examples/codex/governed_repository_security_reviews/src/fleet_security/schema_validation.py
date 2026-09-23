"""Small dependency-free validator for the installed official artifact schema subset."""
from __future__ import annotations

import math
import os
import re
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from .evidence import EvidenceError


OFFICIAL_SCHEMA_NAMES = ("findings", "coverage", "scan-manifest")
_PLUGIN_VERSION = re.compile(r"(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?:[-+].*)?\Z")
_PUBLIC_SCHEMA_COMMIT = "59d026a0579af084b419cd7f33b8e1b867338ee8"
_PUBLIC_SCHEMA_SHA256 = {
    "findings.schema.json": "a480337cc0fa4c48c44fc7be17c6c4348767815570775cda80f2aaf797b8e56c",
    "coverage.schema.json": "7964b132998ca4dcdd19c75f5d92483e1d44cb71462237709b968ec548c10652",
    "scan-manifest.schema.json": "265a48629113f77cd65a3127f1f7e95d3c39ae60e868685837a6aa31d4133310",
}
_PUBLIC_LICENSE_SHA256 = "d17f227e4df5da1600391338865ce0f3055211760a36688f816941d58232d8dc"


def official_schema_directory(
    *, schema_root: str | Path | None = None, plugin_cache: str | Path | None = None,
    bundled_root: str | Path | None = None,
) -> Path:
    """Locate current official schemas without pinning a machine, user or plugin version.

    A trusted host may provide ``CODEX_SECURITY_SCHEMA_ROOT`` or an explicit
    ``schema_root``. Otherwise the highest complete installed Codex Security
    plugin version is selected. A pinned, Apache-licensed public upstream
    snapshot is a portable fallback when no plugin is installed. Every bundled
    file and its redistributed licence must match the signed-off SHA-256
    provenance manifest; invented or tampered contracts still fail closed.
    """

    configured = schema_root if schema_root is not None else os.environ.get("CODEX_SECURITY_SCHEMA_ROOT")
    if configured is not None:
        candidate = Path(configured).expanduser()
        if _complete_official_schema_directory(candidate):
            return candidate.resolve()
        raise EvidenceError(
            "configured Codex Security schema directory is missing an official findings, "
            "coverage or scan-manifest schema"
        )

    cache = (
        Path(plugin_cache).expanduser()
        if plugin_cache is not None
        else Path.home() / ".codex" / "plugins" / "cache" / "openai-curated-remote" / "codex-security"
    )
    versions: list[tuple[tuple[int, int, int], Path]] = []
    if cache.is_dir():
        for directory in cache.iterdir():
            match = _PLUGIN_VERSION.fullmatch(directory.name)
            if match is None or not directory.is_dir():
                continue
            candidate = directory / "schemas"
            if _complete_official_schema_directory(candidate):
                versions.append((tuple(int(match.group(part)) for part in ("major", "minor", "patch")), candidate))
    if versions:
        return max(versions, key=lambda item: item[0])[1].resolve()
    candidates = (
        (Path(bundled_root).expanduser(),)
        if bundled_root is not None
        else () if plugin_cache is not None else (
            Path(__file__).resolve().parents[2] / "contracts" / "codex-security-schemas",
            Path(__file__).resolve().parents[3] / "cookbook" / "security-review-pipeline"
            / "contracts" / "codex-security-schemas",
        )
    )
    for candidate in candidates:
        if candidate.exists():
            return _verified_public_schema_directory(candidate)
    raise EvidenceError(
        "official Codex Security schemas are unavailable; install the supported plugin, "
        "set CODEX_SECURITY_SCHEMA_ROOT, or restore the pinned public schema snapshot"
    )


def _complete_official_schema_directory(directory: Path) -> bool:
    return directory.is_dir() and all(
        (directory / f"{name}.schema.json").is_file() for name in OFFICIAL_SCHEMA_NAMES
    )


def _verified_public_schema_directory(directory: Path) -> Path:
    if directory.is_symlink() or not _complete_official_schema_directory(directory):
        raise EvidenceError("bundled public Codex Security schema snapshot is incomplete or unsafe")
    provenance_path = directory / "PROVENANCE.json"
    if provenance_path.is_symlink() or not provenance_path.is_file():
        raise EvidenceError("bundled public Codex Security schema provenance is missing")
    try:
        provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise EvidenceError("bundled public Codex Security schema provenance is malformed") from error
    expected = provenance.get("schemas")
    if (
        provenance.get("format") != "public-official-codex-security-schema-snapshot/v1"
        or provenance.get("source_repository") != "https://github.com/openai/codex-security"
        or provenance.get("source_commit") != _PUBLIC_SCHEMA_COMMIT
        or provenance.get("license") != "Apache-2.0"
        or not isinstance(expected, dict)
        or expected != _PUBLIC_SCHEMA_SHA256
        or provenance.get("license_file") != "UPSTREAM-LICENSE-APACHE-2.0.txt"
        or provenance.get("license_sha256") != _PUBLIC_LICENSE_SHA256
    ):
        raise EvidenceError("bundled public Codex Security schema provenance is untrusted")
    files = {**expected, provenance.get("license_file", ""): provenance.get("license_sha256")}
    for name, digest in files.items():
        if not isinstance(name, str) or Path(name).name != name:
            raise EvidenceError("bundled public schema provenance contains an unsafe filename")
        path = directory / name
        if (
            path.is_symlink()
            or not path.is_file()
            or not isinstance(digest, str)
            or hashlib.sha256(path.read_bytes()).hexdigest() != digest
        ):
            raise EvidenceError("bundled public Codex Security schema or licence failed integrity verification")
    return directory.resolve()


def validate_schema(instance: Any, schema: Mapping[str, Any], *, path: str = "$") -> None:
    """Check the JSON Schema constructs used by the three bundled product contracts."""

    declared = schema.get("type")
    if declared is not None:
        permitted = declared if isinstance(declared, list) else [declared]
        validators = {
            "object": lambda value: isinstance(value, dict),
            "array": lambda value: isinstance(value, list),
            "string": lambda value: isinstance(value, str),
            "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
            "number": lambda value: isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value),
            "boolean": lambda value: isinstance(value, bool),
            "null": lambda value: value is None,
        }
        if any(value not in validators for value in permitted):
            raise EvidenceError(f"unsupported official schema type at {path}")
        if not any(validators[value](instance) for value in permitted):
            raise EvidenceError(f"official artifact schema type mismatch at {path}")
    if "const" in schema and instance != schema["const"]:
        raise EvidenceError(f"official artifact schema constant mismatch at {path}")
    if "enum" in schema and instance not in schema["enum"]:
        raise EvidenceError(f"official artifact schema enumeration mismatch at {path}")
    if isinstance(instance, str):
        if len(instance) < schema.get("minLength", 0):
            raise EvidenceError(f"official artifact schema string is too short at {path}")
        if "pattern" in schema and re.search(schema["pattern"], instance) is None:
            raise EvidenceError(f"official artifact schema pattern mismatch at {path}")
        if schema.get("format") == "date-time":
            try:
                datetime.fromisoformat(instance.replace("Z", "+00:00"))
            except ValueError as error:
                raise EvidenceError(f"official artifact schema timestamp is invalid at {path}") from error
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if instance < schema.get("minimum", instance) or instance > schema.get("maximum", instance):
            raise EvidenceError(f"official artifact schema numeric bound failed at {path}")
    if isinstance(instance, dict):
        for required in schema.get("required", []):
            if required not in instance:
                raise EvidenceError(f"official artifact schema required field missing at {path}.{required}")
        for name, child in schema.get("properties", {}).items():
            if name in instance:
                validate_schema(instance[name], child, path=f"{path}.{name}")
    if isinstance(instance, list):
        if len(instance) < schema.get("minItems", 0):
            raise EvidenceError(f"official artifact schema array is too short at {path}")
        if "items" in schema:
            for index, value in enumerate(instance):
                validate_schema(value, schema["items"], path=f"{path}[{index}]")
        if "contains" in schema:
            matches = sum(_matches(value, schema["contains"], f"{path}[{index}]")
                          for index, value in enumerate(instance))
            minimum = schema.get("minContains", 1)
            maximum = schema.get("maxContains", len(instance))
            if not minimum <= matches <= maximum:
                raise EvidenceError(f"official artifact schema array containment failed at {path}")
    for subschema in schema.get("allOf", []):
        validate_schema(instance, subschema, path=path)
    if "if" in schema and _matches(instance, schema["if"], path):
        if "then" in schema:
            validate_schema(instance, schema["then"], path=path)
    elif "if" in schema and "else" in schema:
        validate_schema(instance, schema["else"], path=path)


def _matches(instance: Any, schema: Mapping[str, Any], path: str) -> bool:
    try:
        validate_schema(instance, schema, path=path)
    except EvidenceError:
        return False
    return True
