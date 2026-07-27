#!/usr/bin/env python3
"""Validate the versioned policy registry without external dependencies."""

from __future__ import annotations

import argparse
import json
import pathlib
import re
from typing import Any


DEFAULT_ROOT = pathlib.Path(__file__).resolve().parents[1] / "policies"
EXPECTED_REGISTRIES = {
    "shared": "shared.yaml",
    "elcid": "elcid.yaml",
    "aumara": "aumara.yaml",
}
EXPECTED_SOURCE_PRECEDENCE = [
    "verified_beds24_configuration",
    "verified_booking_com_configuration",
    "official_property_documentation",
    "approved_internal_document",
    "confirmed_guest_reply",
]
FORBIDDEN_KEYS = {
    "api_key",
    "amount",
    "bank_account",
    "beds24_property_id",
    "credential",
    "email",
    "fee",
    "phone",
    "price",
    "property_id",
    "room_id",
    "room_ids",
    "secret",
    "token",
}
SENSITIVE_VALUE_PATTERNS = (
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"(?<![\d-])\d{6,}(?![\d-])"),
    re.compile(r"https?://", re.IGNORECASE),
)
SENSITIVE_TOKEN_PREFIXES = (
    "be" + "arer ",
    "s" + "k-",
    "g" + "hp_",
    "github" + "_pat_",
)


class RegistryValidationError(ValueError):
    """Raised when a registry file violates schema or policy invariants."""


def _load_json_yaml(path: pathlib.Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryValidationError(f"{path.name}: invalid JSON-compatible YAML") from exc


def _json_type_matches(value: Any, expected: str) -> bool:
    checks = {
        "array": lambda item: isinstance(item, list),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
        "object": lambda item: isinstance(item, dict),
        "string": lambda item: isinstance(item, str),
    }
    return expected in checks and checks[expected](value)


def _resolve_ref(root_schema: dict[str, Any], reference: str) -> dict[str, Any]:
    if not reference.startswith("#/"):
        raise RegistryValidationError(f"unsupported schema reference: {reference}")
    node: Any = root_schema
    for component in reference[2:].split("/"):
        try:
            node = node[component]
        except (KeyError, TypeError) as exc:
            raise RegistryValidationError(f"unresolved schema reference: {reference}") from exc
    if not isinstance(node, dict):
        raise RegistryValidationError(f"schema reference is not an object: {reference}")
    return node


def _validate_schema(
    value: Any,
    schema: dict[str, Any],
    root_schema: dict[str, Any],
    path: str,
) -> None:
    if "$ref" in schema:
        _validate_schema(value, _resolve_ref(root_schema, schema["$ref"]), root_schema, path)
        return

    expected_types = schema.get("type")
    if isinstance(expected_types, str):
        expected_types = [expected_types]
    if expected_types and not any(
        _json_type_matches(value, expected) for expected in expected_types
    ):
        raise RegistryValidationError(f"{path}: expected {' or '.join(expected_types)}")

    if "const" in schema and value != schema["const"]:
        raise RegistryValidationError(f"{path}: unexpected constant value")
    if "enum" in schema and value not in schema["enum"]:
        raise RegistryValidationError(f"{path}: value is outside the allowed set")

    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            raise RegistryValidationError(f"{path}: string is too short")
        pattern = schema.get("pattern")
        if pattern and not re.fullmatch(pattern, value):
            raise RegistryValidationError(f"{path}: string does not match schema pattern")

    if isinstance(value, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in value]
        if missing:
            raise RegistryValidationError(f"{path}: missing {', '.join(missing)}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = sorted(set(value) - set(properties))
            if extra:
                raise RegistryValidationError(f"{path}: unexpected {', '.join(extra)}")
        for key, child_schema in properties.items():
            if key in value:
                _validate_schema(
                    value[key],
                    child_schema,
                    root_schema,
                    f"{path}.{key}",
                )

    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            raise RegistryValidationError(f"{path}: too few items")
        if "maxItems" in schema and len(value) > schema["maxItems"]:
            raise RegistryValidationError(f"{path}: too many items")
        if schema.get("uniqueItems"):
            serialized = [json.dumps(item, sort_keys=True) for item in value]
            if len(serialized) != len(set(serialized)):
                raise RegistryValidationError(f"{path}: duplicate items")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(value):
                _validate_schema(
                    item,
                    item_schema,
                    root_schema,
                    f"{path}[{index}]",
                )


def _reject_private_data(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                raise RegistryValidationError(f"{path}: forbidden private-data key")
            _reject_private_data(child, f"{path}.{key}")
        return
    if isinstance(value, list):
        for index, child in enumerate(value):
            _reject_private_data(child, f"{path}[{index}]")
        return
    if isinstance(value, str):
        for pattern in SENSITIVE_VALUE_PATTERNS:
            if pattern.search(value):
                raise RegistryValidationError(f"{path}: possible private operational value")
        lowered = value.lower()
        if any(prefix in lowered for prefix in SENSITIVE_TOKEN_PREFIXES):
            raise RegistryValidationError(f"{path}: possible private operational value")


def validate_registry(root: pathlib.Path = DEFAULT_ROOT) -> dict[str, Any]:
    """Validate schema, versions, namespaces, and fail-closed automation flags."""
    root = pathlib.Path(root)
    schema = _load_json_yaml(root / "schema.json")
    index = _load_json_yaml(root / "registry.yaml")
    _reject_private_data(index)
    _validate_schema(index, {"$ref": "#/$defs/registry_index"}, schema, "registry")

    if index["registries"] != EXPECTED_REGISTRIES:
        raise RegistryValidationError("registry: exact product registries are required")
    if index["source_precedence"] != EXPECTED_SOURCE_PRECEDENCE:
        raise RegistryValidationError("registry: source precedence has changed")

    version = index["policy_version"]
    policy_ids: set[str] = set()
    policy_count = 0

    for property_key, filename in EXPECTED_REGISTRIES.items():
        document = _load_json_yaml(root / filename)
        _reject_private_data(document)
        _validate_schema(
            document,
            {"$ref": "#/$defs/policy_file"},
            schema,
            filename,
        )
        if document["property"] != property_key:
            raise RegistryValidationError(f"{filename}: property boundary mismatch")
        if document["policy_version"] != version:
            raise RegistryValidationError(f"{filename}: policy version drift")

        for policy in document["policies"]:
            policy_id = policy["policy_id"]
            if policy_id in policy_ids:
                raise RegistryValidationError(f"{filename}: duplicate policy ID")
            policy_ids.add(policy_id)
            policy_count += 1

            if not policy_id.startswith(f"{property_key}."):
                raise RegistryValidationError(f"{filename}: policy namespace mismatch")
            if policy["property"] != property_key:
                raise RegistryValidationError(f"{filename}: policy property mismatch")
            if policy["policy_version"] != version:
                raise RegistryValidationError(f"{filename}: entry version drift")
            if policy["status"] == "verified" and policy["verified_at"] is None:
                raise RegistryValidationError(f"{filename}: verified entry lacks date")
            if policy["status"] != "verified" and (
                policy["allowed_auto_reply"] or policy["allowed_beds24_action"]
            ):
                raise RegistryValidationError(
                    f"{filename}: unresolved policy enables automation"
                )
            for template_id in policy["response_template_ids"]:
                if not template_id.startswith(f"{property_key}."):
                    raise RegistryValidationError(
                        f"{filename}: response template crosses product boundary"
                    )

    return {
        "policy_version": version,
        "policy_count": policy_count,
        "registry_count": len(EXPECTED_REGISTRIES),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=pathlib.Path,
        default=DEFAULT_ROOT,
        help="Policy registry directory",
    )
    args = parser.parse_args()
    result = validate_registry(args.root)
    print(
        "Policy registry "
        f"{result['policy_version']} valid: "
        f"{result['policy_count']} policies across "
        f"{result['registry_count']} registries."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
