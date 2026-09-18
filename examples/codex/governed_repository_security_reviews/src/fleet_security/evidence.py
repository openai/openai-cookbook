"""Host-sealed synthetic scan receipts, deduplication and tamper-evident audit."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .inventory import stable_digest


class EvidenceError(ValueError):
    """Scanner evidence was incomplete, forged, or inconsistent."""


def _bytes(value: str | Mapping[str, object]) -> bytes:
    if isinstance(value, str):
        return value.encode("utf-8")
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


@dataclass
class EvidenceSealer:
    """One process-local trusted host MAC; the signing key is never an artifact."""

    _key: bytes = field(default_factory=lambda: secrets.token_bytes(32), repr=False)

    def seal(
        self, *, repository_id: str, commit_sha: str, scan_id: str,
        scanner_version: str, report: str, findings: Mapping[str, object],
        coverage: Mapping[str, object],
    ) -> dict[str, object]:
        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        payload: dict[str, object] = {
            "documentType": "codex-security.scan-manifest",
            "schemaVersion": "1.0",
            "synthetic": True,
            "scan": {
                "id": scan_id,
                "producer": {"name": "synthetic-local-adapter", "version": scanner_version},
                "status": "completed",
                "startedAt": timestamp,
                "completedAt": timestamp,
                "sealedAt": timestamp,
                "target": {
                    "kind": "git_revision",
                    "targetId": repository_id,
                    "displayName": repository_id,
                    "revision": commit_sha,
                },
                "scope": {"includePaths": ["src/"], "excludePaths": []},
                "coverageRef": "coverage.json",
                "findingsRef": "findings.json",
                "artifacts": [
                    {"path": "report.md", "sha256": hashlib.sha256(_bytes(report)).hexdigest(), "mediaType": "text/markdown"},
                    {"path": "findings.json", "sha256": hashlib.sha256(_bytes(findings)).hexdigest(), "mediaType": "application/json"},
                    {"path": "coverage.json", "sha256": hashlib.sha256(_bytes(coverage)).hexdigest(), "mediaType": "application/json"},
                ],
            },
        }
        payload["hostIntegrityMac"] = hmac.new(self._key, _bytes(payload), "sha256").hexdigest()
        return payload

    def verify(self, bundle: Mapping[str, object]) -> None:
        try:
            manifest = deepcopy(bundle["scan-manifest.json"])
            if not isinstance(manifest, dict):
                raise EvidenceError("scan manifest is not an object")
            supplied = manifest.pop("hostIntegrityMac")
            expected = hmac.new(self._key, _bytes(manifest), "sha256").hexdigest()
            if not isinstance(supplied, str) or not hmac.compare_digest(expected, supplied):
                raise EvidenceError("trusted host manifest signature is invalid")
            scan = manifest["scan"]
            artifacts = scan["artifacts"]
            if not isinstance(artifacts, list):
                raise EvidenceError("scan manifest artifact inventory is invalid")
            indexed = {item["path"]: item["sha256"] for item in artifacts}
            for name in ("report.md", "findings.json", "coverage.json"):
                digest = hashlib.sha256(_bytes(bundle[name])).hexdigest()
                if not hmac.compare_digest(digest, str(indexed[name])):
                    raise EvidenceError(f"scan artifact hash mismatch: {name}")
            findings = bundle["findings.json"]
            coverage = bundle["coverage.json"]
            if not isinstance(findings, Mapping) or findings.get("documentType") != "codex-security.findings":
                raise EvidenceError("documented security findings schema is absent")
            if findings.get("scanId") != scan["id"]:
                raise EvidenceError("findings scan identity does not match the manifest")
            if not isinstance(coverage, Mapping) or coverage.get("completeness") not in {"complete", "partial", "unknown"}:
                raise EvidenceError("scanner coverage evidence is absent or unrecognised")
            if coverage.get("scanId") != scan["id"]:
                raise EvidenceError("coverage scan identity does not match the manifest")
            target = scan["target"]
            if not isinstance(target, Mapping):
                raise EvidenceError("scan manifest has no reviewed repository target")
            rows = findings.get("findings")
            if not isinstance(rows, list):
                raise EvidenceError("scanner findings are not an array")
            for row in rows:
                if not isinstance(row, Mapping) or row.get("provenance", {}).get("repositoryId") != target["targetId"]:
                    raise EvidenceError("finding provenance does not match the reviewed repository")
                if row.get("provenance", {}).get("revision") != target["revision"]:
                    raise EvidenceError("finding provenance does not match the pinned revision")
        except EvidenceError:
            raise
        except (KeyError, TypeError, AttributeError) as error:
            raise EvidenceError("scan evidence is incomplete or malformed") from error


class AuditLog:
    """Owner-private append-only hash chain; repository source and secrets are excluded."""

    def __init__(self) -> None:
        self._events: list[dict[str, object]] = []
        self._lock = threading.Lock()

    def append(self, event: str, repository_id: str, **metadata: object) -> dict[str, object]:
        if not event or not repository_id:
            raise EvidenceError("audit event and repository identity are mandatory")
        forbidden = {"secret", "token", "api_key", "credential", "source", "prompt"}
        if any(any(marker in key.casefold() for marker in forbidden) for key in metadata):
            raise EvidenceError("audit evidence must not contain secrets, prompts, or repository source")
        with self._lock:
            previous = self._events[-1]["eventHash"] if self._events else "0" * 64
            row = {
                "sequence": len(self._events) + 1,
                "event": event,
                "repositoryId": repository_id,
                "metadata": deepcopy(metadata),
                "previousHash": previous,
            }
            row["eventHash"] = stable_digest(row)
            self._events.append(row)
            return deepcopy(row)

    @property
    def events(self) -> tuple[dict[str, Any], ...]:
        with self._lock:
            return tuple(deepcopy(self._events))

    def verify(self, events: tuple[dict[str, Any], ...] | None = None) -> bool:
        rows = self.events if events is None else events
        previous = "0" * 64
        for index, row in enumerate(rows, start=1):
            copy = deepcopy(row)
            digest = copy.pop("eventHash", None)
            if copy.get("sequence") != index or copy.get("previousHash") != previous:
                return False
            if not isinstance(digest, str) or not hmac.compare_digest(stable_digest(copy), digest):
                return False
            previous = digest
        return True


class FindingRegistry:
    """Stable cross-revision dedupe by trusted finding identity."""

    def __init__(self) -> None:
        self._findings: dict[str, dict[str, object]] = {}
        self._lock = threading.Lock()

    def admit(self, findings: IterableMapping) -> tuple[tuple[dict[str, object], ...], int]:
        fresh: list[dict[str, object]] = []
        duplicates = 0
        with self._lock:
            for finding in findings:
                identity = finding.get("findingId")
                if not isinstance(identity, str) or not identity:
                    raise EvidenceError("finding has no stable identity")
                if identity in self._findings:
                    duplicates += 1
                    continue
                copied = deepcopy(dict(finding))
                self._findings[identity] = copied
                fresh.append(deepcopy(copied))
        return tuple(fresh), duplicates

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._findings)


IterableMapping = tuple[Mapping[str, object], ...] | list[Mapping[str, object]]


class SecureArtifactStore:
    """Owner-only temporary receipt material; closure removes the entire directory."""

    def __init__(self) -> None:
        self._temporary: tempfile.TemporaryDirectory[str] | None = None
        self.path: Path | None = None

    def __enter__(self) -> "SecureArtifactStore":
        self._temporary = tempfile.TemporaryDirectory(prefix="synthetic-fleet-evidence-")
        self.path = Path(self._temporary.name)
        self.path.chmod(0o700)
        return self

    def write(self, name: str, payload: Mapping[str, object]) -> Path:
        if self.path is None or not name or "/" in name or "\\" in name or name.startswith("."):
            raise EvidenceError("artifact name must stay inside its owner-private directory")
        path = self.path / name
        descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, sort_keys=True)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return path

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()
        self._temporary = None
        self.path = None
