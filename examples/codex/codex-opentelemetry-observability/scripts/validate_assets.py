#!/usr/bin/env python3
"""Validate the cookbook assets without requiring third-party Python packages."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise SystemExit(
            "ERROR - TOML validation requires Python 3.11+ or the tomli package"
        ) from exc


SENSITIVE_DASHBOARD_PATTERNS = {
    "prompt data": re.compile(r"\b(?:user[._ -]?)?prompts?\b", re.IGNORECASE),
    "tool arguments": re.compile(r"\btool[._ -]?arguments?\b", re.IGNORECASE),
    "tool output": re.compile(
        r"\b(?:tool[._ -]?)?(?:outputs?|results?)\b", re.IGNORECASE
    ),
    "email": re.compile(r"\bemails?\b", re.IGNORECASE),
    "conversation identifier": re.compile(
        r"\bconversation[._ -]?ids?\b", re.IGNORECASE
    ),
    "call identifier": re.compile(r"\bcall[._ -]?ids?\b", re.IGNORECASE),
    "request identifier": re.compile(r"\brequest[._ -]?ids?\b", re.IGNORECASE),
    "account identifier": re.compile(r"\baccount[._ -]?ids?\b", re.IGNORECASE),
    "user identifier": re.compile(r"\buser[._ -]?ids?\b", re.IGNORECASE),
    "host name": re.compile(r"\b(?:hostname|host[._ -]?name)\b", re.IGNORECASE),
    "endpoint": re.compile(r"\bendpoints?\b", re.IGNORECASE),
    "error text": re.compile(r"\berror[._ -]?(?:message|text)\b", re.IGNORECASE),
}

SENSITIVE_KEYS = {
    "api-key",
    "api_key",
    "authorization",
    "client-secret",
    "client_secret",
    "password",
    "passwd",
    "token",
}
EXPECTED_LOCAL_SERVICES = {
    "grafana",
    "loki",
    "otel-collector",
    "prometheus",
    "tempo",
}


def iter_json_strings(value: Any, location: str = "$") -> Iterable[tuple[str, str]]:
    if isinstance(value, dict):
        for key, child in value.items():
            key_location = f"{location}.{key}"
            yield key_location, str(key)
            yield from iter_json_strings(child, key_location)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from iter_json_strings(child, f"{location}[{index}]")
    elif isinstance(value, str):
        yield location, value


def iter_panels(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        if "type" in value and ("targets" in value or "panels" in value):
            yield value
        for child in value.values():
            yield from iter_panels(child)
    elif isinstance(value, list):
        for child in value:
            yield from iter_panels(child)


def validate_dashboard(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        dashboard = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"{path} - invalid JSON - {exc}"]

    if not isinstance(dashboard, dict):
        errors.append(f"{path} - dashboard root must be an object")
        return errors
    if not isinstance(dashboard.get("title"), str):
        errors.append(f"{path} - dashboard must have a string title")
    if not isinstance(dashboard.get("panels"), list):
        errors.append(f"{path} - dashboard must have a panels array")

    for panel in iter_panels(dashboard):
        if str(panel.get("type", "")).lower() == "logs":
            title = panel.get("title", "untitled")
            errors.append(f"{path} - raw log panel is not allowed - {title}")
        panel_datasource = panel.get("datasource")
        panel_datasource_type = ""
        if isinstance(panel_datasource, dict):
            panel_datasource_type = str(panel_datasource.get("type", "")).lower()
        targets = panel.get("targets", [])
        if not isinstance(targets, list):
            continue
        for target in targets:
            if not isinstance(target, dict):
                continue
            target_datasource = target.get("datasource")
            target_datasource_type = panel_datasource_type
            if isinstance(target_datasource, dict):
                target_datasource_type = str(
                    target_datasource.get("type", panel_datasource_type)
                ).lower()
            expression = str(target.get("expr", ""))
            if target_datasource_type == "loki" and "$__rate_interval" in expression:
                errors.append(
                    f"{path} - Loki targets cannot use the Prometheus "
                    "$__rate_interval macro"
                )
            if target_datasource_type == "tempo" and target.get("queryType") in {
                "nativeSearch",
                "traceql",
                "traceqlSearch",
            }:
                errors.append(
                    f"{path} - Grafana 11.2 dashboard targets do not support "
                    "Tempo search queries; provide an Explore workflow"
                )

    findings: set[tuple[str, str]] = set()
    for location, text in iter_json_strings(dashboard):
        for label, pattern in SENSITIVE_DASHBOARD_PATTERNS.items():
            if pattern.search(text):
                findings.add((label, location))
    for label, location in sorted(findings):
        errors.append(f"{path} - forbidden {label} term at {location}")
    return errors


def validate_toml(path: Path) -> list[str]:
    try:
        with path.open("rb") as file_handle:
            tomllib.load(file_handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return [f"{path} - invalid TOML - {exc}"]
    return []


def validate_compose_source(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path} - cannot read Compose file - {exc}"]

    images = [
        match.group(1).strip()
        for match in re.finditer(r"(?m)^\s+image:\s*([^#\n]+?)\s*$", text)
    ]
    if not images:
        errors.append(f"{path} - no service images found")
    for image in images:
        if not image_is_pinned(image):
            errors.append(f"{path} - Compose image is not pinned - {image}")

    services_text = text.split("\nvolumes:\n", 1)[0]
    service_names = set(
        re.findall(r"(?m)^  ([a-z0-9][a-z0-9-]*):\s*$", services_text)
    )
    missing_services = EXPECTED_LOCAL_SERVICES - service_names
    if missing_services:
        errors.append(
            f"{path} - missing local services - {', '.join(sorted(missing_services))}"
        )

    if "0.0.0.0:" in text:
        errors.append(f"{path} - published ports must not bind to 0.0.0.0")
    published_ports = re.findall(r"127\.0\.0\.1:\$\{CODEX_OTEL_[A-Z_]+:-\d+}:\d+", text)
    if len(published_ports) != 6:
        errors.append(
            f"{path} - expected six localhost-only published ports, got "
            f"{len(published_ports)}"
        )

    forbidden_settings = {
        "privileged Compose service": r"(?m)^\s*privileged:\s*true\s*$",
        "host network mode": r"(?m)^\s*network_mode:\s*host\s*$",
        "added Linux capability": r"(?m)^\s*cap_add:\s*$",
        "unconfined seccomp": r"seccomp[=:]unconfined",
    }
    for label, pattern in forbidden_settings.items():
        if re.search(pattern, text, re.IGNORECASE):
            errors.append(f"{path} - forbidden {label}")

    if "GF_AUTH_ANONYMOUS_ORG_ROLE: Viewer" not in text:
        errors.append(f"{path} - local Grafana anonymous role must remain Viewer")
    errors.extend(literal_credential_findings(text, str(path)))
    return errors


def validate_collector_source(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path} - cannot read Collector config - {exc}"]

    required_markers = {
        "OTLP/HTTP receiver": "http:\n        endpoint: 0.0.0.0:4318",
        "memory limiter": "memory_limiter:",
        "sensitive log drop": "filter/drop_sensitive_logs:",
        "privacy transform": "transform/privacy:",
        "privacy redaction": "redaction/privacy:",
        "batch processor": "batch:",
        "Loki exporter": "otlp_http/logs:",
        "Tempo exporter": "otlp_http/traces:",
        "Prometheus exporter": "prometheus:\n    endpoint: 0.0.0.0:9464",
    }
    for label, marker in required_markers.items():
        if marker not in text:
            errors.append(f"{path} - missing {label}")
    if re.search(r"(?m)^\s*debug(?:/[^:]+)?:\s*$", text):
        errors.append(f"{path} - debug exporter is not allowed")
    return errors


def image_is_pinned(image: str) -> bool:
    image = image.strip().strip("'\"")
    if not image or "{{" in image or "}}" in image:
        return False
    return bool(re.search(r"@sha256:[0-9a-fA-F]{64}$", image))


def literal_credential_findings(document: str, resource: str) -> list[str]:
    errors: list[str] = []
    if "-----BEGIN PRIVATE KEY-----" in document:
        errors.append(f"{resource} - embedded private key")
    if re.search(r"https?://[^/@\s:]+:[^/@\s]+@", document):
        errors.append(f"{resource} - URL contains embedded credentials")
    if re.search(r"\b(?:Basic|Bearer)\s+[A-Za-z0-9+/=_-]{8,}", document):
        errors.append(f"{resource} - embedded authorization value")

    for line_number, line in enumerate(document.splitlines(), start=1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        match = re.match(
            r"^\s*(?:-\s*)?['\"]?([A-Za-z0-9_.-]+)['\"]?\s*:\s*(.*?)\s*$",
            line,
        )
        if not match or match.group(1).lower() not in SENSITIVE_KEYS:
            continue
        value = match.group(2).strip().strip("'\"")
        if not value or value.lower() in {"null", "~"}:
            continue
        if "${" in value or value.startswith("<"):
            continue
        errors.append(
            f"{resource} - possible embedded credential on rendered line {line_number}"
        )
    return errors


def validate_source_assets(root: Path) -> list[str]:
    errors: list[str] = []
    toml_files = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and (path.name.endswith(".toml") or path.name.endswith(".toml.example"))
    )
    if not toml_files:
        errors.append(f"{root} - no TOML configuration template found")
    for path in toml_files:
        errors.extend(validate_toml(path))

    dashboard_files = sorted((root / "dashboards").glob("*.json"))
    if not dashboard_files:
        errors.append(f"{root / 'dashboards'} - no Grafana dashboard JSON found")
    for path in dashboard_files:
        errors.extend(validate_dashboard(path))

    compose_path = root / "docker" / "docker-compose.yml"
    if not compose_path.is_file():
        errors.append(f"{compose_path} - local Docker Compose file not found")
    else:
        errors.extend(validate_compose_source(compose_path))

    collector_path = root / "docker" / "otel-collector-config.yaml"
    if not collector_path.is_file():
        errors.append(f"{collector_path} - local Collector config not found")
    else:
        errors.extend(validate_collector_source(collector_path))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True, help="Cookbook example root")
    args = parser.parse_args()

    root = args.root.resolve()
    errors = validate_source_assets(root)

    if errors:
        for error in errors:
            print(f"ERROR - {error}", file=sys.stderr)
        print(f"FAILED - {len(errors)} validation error(s)", file=sys.stderr)
        return 1

    print("PASS - TOML, dashboard, Compose, and Collector source validation")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
