"""Bounded scanner, evidence, and display helpers for the security review Cookbook."""

from __future__ import annotations

import ast
import hashlib
import html
import json
import os
import platform
import re
import selectors
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.request
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from textwrap import dedent
from typing import Any, Literal
from urllib.parse import quote, urlsplit

from IPython.display import Markdown, display
from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator, model_validator

class EvidenceError(ValueError):
    """Evidence failed a source, coverage, or identity check."""

class ApprovalRequiredError(PermissionError):
    """A side effect was requested without explicit approval."""

class CoverageError(EvidenceError):
    """Observed scanner or specialist execution did not close coverage."""

class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

def _record(name: str, /, **fields: tuple[Any, Any]) -> type[Contract]:
    return create_model(name, __base__=Contract, **fields)

APPROVAL_NAMES = frozenset({"network", "scanners", "model_agents"})
_CODE_SUFFIXES = frozenset({".py", ".java", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"})
_LANGUAGE = {".py": "python", ".java": "java", ".js": "javascript",
             ".jsx": "javascript", ".mjs": "javascript", ".cjs": "javascript",
             ".ts": "typescript", ".tsx": "typescript"}
_MAX_SOURCE = 2 * 1024 * 1024
_MAX_SCANNER_OUTPUT = 4 * 1024 * 1024

def _approvals(value: Iterable[str]) -> frozenset[str]:
    result = frozenset(value)
    unknown = result - APPROVAL_NAMES
    if unknown:
        raise ValueError(f"Unknown SECURITY_SWARM_APPROVALS values: {sorted(unknown)}")
    return result

def _require(approvals: Iterable[str], action: str) -> None:
    if action not in _approvals(approvals):
        raise ApprovalRequiredError(f"The {action!r} action requires explicit approval.")

def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _digest(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                         allow_nan=False, default=str).encode()
    return _sha256(payload)

def _safe_path(value: str) -> str:
    path = PurePosixPath(value.replace("\\", "/"))
    if (not value or path.is_absolute() or ".." in path.parts
            or any(part in {"", "."} for part in path.parts)
            or re.match(r"^[A-Za-z]:", value)
            or not re.fullmatch(r"[A-Za-z0-9._@+/-]+", value)):
        raise EvidenceError(f"Unsafe source path: {value!r}")
    return path.as_posix()

class ApprovedFile(Contract):
    path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        return _safe_path(value)

class TargetManifest(Contract):
    target_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=80)
    repository: str
    release: str
    commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    approved_files: tuple[ApprovedFile, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_manifest(self) -> "TargetManifest":
        if not re.fullmatch(r"https://github\.com/[^/]+/[^/]+?/?", self.repository):
            raise ValueError("Only GitHub repository URLs are supported.")
        paths = [item.path for item in self.approved_files]
        if len(paths) != len(set(paths)):
            raise ValueError("Approved source paths must be unique.")
        return self

SourceFile = _record("SourceFile", path=(str, ...),
    sha256=(str, Field(pattern=r"^[0-9a-f]{64}$")), size_bytes=(int, Field(ge=0)),
    production_source=(bool, ...))

class SourceSnapshot(Contract):
    root: Path
    target_id: str
    source_url: str
    source_revision: str
    files: tuple[SourceFile, ...] = Field(min_length=1)
    snapshot_digest: str = Field(pattern=r"^[0-9a-f]{64}$")

    @property
    def production_files(self) -> tuple[SourceFile, ...]:
        return tuple(item for item in self.files if item.production_source)

    def file(self, path: str) -> SourceFile:
        safe = _safe_path(path)
        for item in self.files:
            if item.path == safe:
                return item
        raise EvidenceError("Source path is outside the approved snapshot.")

RepositoryFingerprint = _record("RepositoryFingerprint",
    languages=(tuple[str, ...], ...), production_files=(tuple[str, ...], ...),
    semgrep_source_paths=(tuple[str, ...], ...), python_source_paths=(tuple[str, ...], ...),
    snapshot_digest=(str, ...))

def _repository_parts(manifest: TargetManifest) -> tuple[str, str]:
    match = re.fullmatch(r"https://github\.com/([^/]+)/([^/]+?)/?", manifest.repository)
    if not match:
        raise EvidenceError("Only GitHub repository URLs are supported.")
    return match.group(1), match.group(2).removesuffix(".git")

def _raw_url(manifest: TargetManifest, path: str) -> str:
    owner, repository = _repository_parts(manifest)
    return f"https://raw.githubusercontent.com/{owner}/{repository}/{manifest.commit}/{quote(path, safe='/')}"

def _download_file(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "openai-cookbook-security-swarm"})
    with urllib.request.urlopen(request, timeout=45) as response:
        final = urlsplit(response.geturl())
        if final.scheme != "https" or final.hostname != "raw.githubusercontent.com":
            raise EvidenceError("Pinned source redirected outside raw.githubusercontent.com.")
        declared = response.headers.get("Content-Length")
        if declared and int(declared) > _MAX_SOURCE:
            raise EvidenceError("Approved source file exceeds the size limit.")
        data = response.read(_MAX_SOURCE + 1)
    if len(data) > _MAX_SOURCE:
        raise EvidenceError("Approved source file exceeds the size limit.")
    return data

def _tree_files(root: Path) -> tuple[str, ...]:
    try:
        if root.is_symlink() or not stat.S_ISDIR(root.lstat().st_mode):
            raise EvidenceError("Approved source root must be a real directory.")
        files: list[str] = []
        for item in root.rglob("*"):
            if item.is_symlink():
                raise EvidenceError("Approved source tree contains a symlink.")
            if item.is_file():
                files.append(item.relative_to(root).as_posix())
        return tuple(sorted(files))
    except OSError as error:
        raise EvidenceError("Approved source tree could not be inspected.") from error

def _read_bound(root: Path, relative: str, limit: int = _MAX_SOURCE,
                expected_size: int | None = None) -> bytes:
    safe = PurePosixPath(_safe_path(relative))
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    file_flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    opened: list[int] = []
    try:
        current = os.open(root, directory_flags)
        opened.append(current)
        for part in safe.parts[:-1]:
            current = os.open(part, directory_flags, dir_fd=current)
            opened.append(current)
        descriptor = os.open(safe.parts[-1], file_flags, dir_fd=current)
        opened.append(descriptor)
        before = os.fstat(descriptor)
        if (not stat.S_ISREG(before.st_mode) or before.st_size > limit
                or expected_size is not None and before.st_size != expected_size):
            raise EvidenceError("Approved source is not a bounded regular file.")
        chunks, remaining = [], limit + 1
        while remaining and (chunk := os.read(descriptor, min(65536, remaining))):
            chunks.append(chunk)
            remaining -= len(chunk)
        data, after = b"".join(chunks), os.fstat(descriptor)
        identity = lambda value: (value.st_dev, value.st_ino, value.st_size,
                                  value.st_mtime_ns, value.st_ctime_ns)
        if len(data) > limit or len(data) != after.st_size or identity(before) != identity(after):
            raise EvidenceError("Approved source changed while it was read.")
        return data
    except OSError as error:
        raise EvidenceError("Approved source contains a symlink, missing path, or non-file.") from error
    finally:
        for descriptor in reversed(opened):
            try:
                os.close(descriptor)
            except OSError:
                pass

def snapshot_repository(root: Path, manifest: TargetManifest) -> SourceSnapshot:
    root = Path(root)
    expected = {item.path: item.sha256 for item in manifest.approved_files}
    if set(_tree_files(root)) != set(expected):
        raise EvidenceError("Materialized source membership differs from the approved manifest.")
    files = []
    for path in sorted(expected):
        data = _read_bound(root, path)
        if _sha256(data) != expected[path]:
            raise EvidenceError("Materialized source hash differs from the approved manifest.")
        files.append(SourceFile(path=path, sha256=expected[path], size_bytes=len(data),
                                production_source=PurePosixPath(path).suffix.lower() in _CODE_SUFFIXES))
    identity = {"source_url": manifest.repository, "source_revision": manifest.commit,
                "files": [item.model_dump(mode="json") for item in files]}
    return SourceSnapshot(root=root, target_id=manifest.target_id, source_url=manifest.repository,
                          source_revision=manifest.commit, files=tuple(files),
                          snapshot_digest=_digest(identity))

def verify_snapshot(snapshot: SourceSnapshot) -> None:
    if set(_tree_files(snapshot.root)) != {item.path for item in snapshot.files}:
        raise EvidenceError("Approved source membership changed after snapshotting.")
    for item in snapshot.files:
        data = _read_bound(snapshot.root, item.path, expected_size=item.size_bytes)
        if _sha256(data) != item.sha256:
            raise EvidenceError("Approved source changed after snapshotting.")
    identity = {"source_url": snapshot.source_url, "source_revision": snapshot.source_revision,
                "files": [item.model_dump(mode="json") for item in snapshot.files]}
    if _digest(identity) != snapshot.snapshot_digest:
        raise EvidenceError("Snapshot identity is inconsistent.")

def acquire_target(manifest: TargetManifest, work_dir: Path,
                   approvals: Iterable[str] = ()) -> Path:
    """Fetch only allowlisted files at an immutable commit, then verify every byte."""
    _require(approvals, "network")
    work_dir = Path(work_dir)
    for parent in reversed((work_dir.absolute(), *work_dir.absolute().parents)):
        if parent.is_symlink():
            raise EvidenceError("Source work directory cannot traverse a symlink.")
    work_dir.mkdir(parents=True, exist_ok=True)
    destination = work_dir / f"{manifest.target_id}-{manifest.commit[:12]}-slice"
    if destination.is_symlink():
        raise EvidenceError("Approved source destination cannot be a symlink.")
    if destination.exists():
        snapshot_repository(destination, manifest)
        return destination
    temporary = Path(tempfile.mkdtemp(prefix=f".{manifest.target_id}-", dir=work_dir))
    try:
        for approved in manifest.approved_files:
            data = _download_file(_raw_url(manifest, approved.path))
            if _sha256(data) != approved.sha256:
                raise EvidenceError("Downloaded source hash differs from the approved manifest.")
            output = temporary / approved.path
            output.parent.mkdir(parents=True, exist_ok=True)
            descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                 getattr(os, "O_NOFOLLOW", 0), 0o600)
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
        snapshot_repository(temporary, manifest)
        try:
            os.replace(temporary, destination)
        except OSError as error:
            if destination.exists():
                snapshot_repository(destination, manifest)
                return destination
            raise EvidenceError("Verified source could not be installed atomically.") from error
        return destination
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)

def _read_source(snapshot: SourceSnapshot, path: str) -> str:
    source = snapshot.file(path)
    data = _read_bound(snapshot.root, source.path, expected_size=source.size_bytes)
    if _sha256(data) != source.sha256:
        raise EvidenceError("Source excerpt failed its snapshot hash check.")
    return data.decode("utf-8", errors="strict")

def fingerprint_repository(snapshot: SourceSnapshot) -> RepositoryFingerprint:
    verify_snapshot(snapshot)
    production = tuple(item.path for item in snapshot.production_files)
    languages = tuple(sorted({_LANGUAGE[PurePosixPath(path).suffix.lower()] for path in production}))
    return RepositoryFingerprint(languages=languages, production_files=production,
        semgrep_source_paths=production,
        python_source_paths=tuple(path for path in production if path.endswith(".py")),
        snapshot_digest=snapshot.snapshot_digest)

ScannerStatus = Literal["ready", "not_applicable", "not_installed", "not_authorized"]
ScannerSpec = _record("ScannerSpec", name=(str, ...), description=(str, ...), priority=(int, ...))
ScannerAssessment = _record("ScannerAssessment", scanner=(str, ...), status=(ScannerStatus, ...),
    installed=(bool, ...), applicable=(bool, ...), authorized=(bool, ...), reason=(str, ...),
    executable=(str | None, None))
ScannerFinding = _record("ScannerFinding", observation_id=(str, ...), scanner=(str, ...),
    rule_id=(str, ...), title=(str, ...), severity=(Literal["critical", "high", "medium", "low"], ...),
    confidence=(str, ...), cwe=(str | None, None), relative_file_path=(str, ...),
    line_start=(int, Field(ge=1)), source_sha256=(str, ...), source_revision=(str, ...),
    snapshot_digest=(str, ...))
ScannerResult = _record("ScannerResult", scanner=(str, ...),
    status=(Literal["completed", "completed_with_findings", "failed", "timed_out"], ...),
    findings=(tuple[ScannerFinding, ...], ()), exit_code=(int | None, None),
    duration_seconds=(float | None, None), reason=(str | None, None),
    paths_reviewed=(tuple[str, ...], ()), snapshot_digest=(str, ...))
_SCANNERS = (
    ScannerSpec(name="semgrep", description="Bounded local source-pattern rules", priority=10),
    ScannerSpec(name="bandit", description="Bounded Python security checks", priority=20),
)

def scanner_registry() -> tuple[ScannerSpec, ...]:
    return _SCANNERS

def assess_scanners(fingerprint: RepositoryFingerprint, approvals: Iterable[str] = (),
                    *, executable_lookup: Any = shutil.which) -> tuple[ScannerAssessment, ...]:
    approved = "scanners" in _approvals(approvals)
    assessments = []
    for spec in scanner_registry():
        applicable = bool(fingerprint.semgrep_source_paths if spec.name == "semgrep"
                          else fingerprint.python_source_paths)
        executable = executable_lookup(spec.name)
        if not applicable:
            status, reason = "not_applicable", "No matching production-language surface."
        elif not approved:
            status, reason = "not_authorized", "Scanner execution was not approved."
        elif not executable:
            status, reason = "not_installed", "The scanner executable is not installed."
        else:
            status, reason = "ready", "Applicable, installed, adapted, and approved."
        assessments.append(ScannerAssessment(scanner=spec.name, status=status,
            installed=bool(executable), applicable=applicable, authorized=status == "ready",
            reason=reason, executable=str(executable) if executable else None))
    return tuple(assessments)

def select_scanners(assessments: Sequence[ScannerAssessment]) -> tuple[str, ...]:
    if any(item.applicable and item.status == "not_installed" for item in assessments):
        raise EvidenceError("An applicable bounded scanner is not installed.")
    order = {item.name: item.priority for item in scanner_registry()}
    return tuple(sorted((item.scanner for item in assessments if item.status == "ready"),
                        key=lambda name: (order[name], name)))

LOCAL_SEMGREP_RULES = r'''rules:
  - id: cookbook.security.java-spring-jdbc-sql-injection
    message: Request-derived input is concatenated into a JdbcTemplate query.
    languages: [java]
    severity: ERROR
    metadata: {cwe: CWE-89, confidence: high}
    mode: taint
    pattern-sources:
      - patterns:
          - pattern: $MAP.get(...)
          - pattern-inside: |
              $RET $METHOD(..., @RequestParam Map<$K, $V> $MAP, ...) { ... }
    pattern-sinks:
      - patterns:
          - pattern: $JDBC.query($SQL, ...)
          - focus-metavariable: $SQL
  - id: cookbook.security.javascript-sql-injection
    message: Request-controlled input reaches an unparameterized SQL query.
    languages: [javascript, typescript]
    severity: ERROR
    metadata: {cwe: CWE-89, confidence: high}
    mode: taint
    pattern-sources:
      - pattern: $REQUEST.body
      - pattern: $REQUEST.body.$FIELD
      - pattern: $REQUEST.body[$FIELD]
      - pattern: $REQUEST.query
      - pattern: $REQUEST.query.$FIELD
      - pattern: $REQUEST.query[$FIELD]
      - pattern: $REQUEST.params
      - pattern: $REQUEST.params.$FIELD
      - pattern: $REQUEST.params[$FIELD]
    pattern-sinks:
      - patterns:
          - pattern: $DATABASE.query($QUERY, ...)
          - focus-metavariable: $QUERY
  - id: cookbook.security.python-sql-injection
    message: Request-controlled input reaches an unparameterized database query.
    languages: [python]
    severity: ERROR
    metadata: {cwe: CWE-89, confidence: high}
    mode: taint
    pattern-sources:
      - pattern: $REQUEST.data
      - pattern: $REQUEST.data[$FIELD]
      - pattern: $REQUEST.POST
      - pattern: $REQUEST.POST[$FIELD]
      - pattern: $REQUEST.GET
      - pattern: $REQUEST.GET[$FIELD]
      - pattern: $REQUEST.query_params
      - pattern: $REQUEST.query_params[$FIELD]
    pattern-sinks:
      - patterns:
          - pattern: $CURSOR.execute($QUERY, ...)
          - focus-metavariable: $QUERY
  - id: cookbook.security.python-tls-verification-disabled
    message: An outbound request explicitly disables TLS certificate verification.
    languages: [python]
    severity: ERROR
    metadata: {cwe: CWE-295, confidence: high}
    pattern: requests.$METHOD(..., verify=False, ...)
  - id: cookbook.security.python-jwt-signature-disabled
    message: JWT decoding explicitly disables signature verification.
    languages: [python]
    severity: WARNING
    metadata: {cwe: CWE-347, confidence: high}
    pattern: 'jwt.decode(..., options={..., "verify_signature": False, ...}, ...)'
'''
LOCAL_SEMGREP_RULE_IDS = frozenset(re.findall(r"(?m)^\s*- id: ([\w.-]+)$", LOCAL_SEMGREP_RULES))

def _run_bounded_subprocess(command: Sequence[str], *, cwd: Path, timeout: int,
                            environment: Mapping[str, str] | None = None,
                            output_limit: int = _MAX_SCANNER_OUTPUT) -> tuple[int, bytes, bytes, float]:
    if os.name != "posix" or platform.system() == "Windows":
        raise EvidenceError("Scanner execution requires POSIX or WSL; native Windows is unsupported.")
    if timeout < 1 or output_limit < 1:
        raise ValueError("Scanner timeout and output limit must be positive.")
    started = time.perf_counter()
    process = subprocess.Popen(command, cwd=cwd, env=dict(environment) if environment else None,
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    selector: selectors.BaseSelector | None = None
    try:
        if process.stdout is None or process.stderr is None:
            raise EvidenceError("Scanner output pipes were not created.")
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        deadline = time.monotonic() + timeout
        while selector.get_map():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError
            for key, _ in selector.select(min(0.1, remaining)):
                chunk = os.read(key.fileobj.fileno(), 65536)
                if not chunk:
                    selector.unregister(key.fileobj)
                elif len(buffers[key.data]) + len(chunk) > output_limit:
                    raise EvidenceError(f"Scanner {key.data} exceeds the output limit.")
                else:
                    buffers[key.data].extend(chunk)
        code = process.wait(timeout=max(0.001, deadline - time.monotonic()))
        return code, bytes(buffers["stdout"]), bytes(buffers["stderr"]), time.perf_counter() - started
    except BaseException:
        if process.poll() is None:
            process.kill()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass
        raise
    finally:
        if selector is not None:
            selector.close()
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()

def _intended_paths(snapshot: SourceSnapshot, scanner: str) -> tuple[str, ...]:
    return tuple(item.path for item in snapshot.production_files
                 if scanner != "bandit" or item.path.endswith(".py"))

def _relative_scanner_path(snapshot: SourceSnapshot, value: str) -> str:
    candidate = Path(value)
    if candidate.is_absolute():
        try:
            return candidate.resolve(strict=True).relative_to(snapshot.root.resolve(strict=True)).as_posix()
        except (OSError, ValueError) as error:
            raise EvidenceError("Scanner path escaped the approved source root.") from error
    return _safe_path(value)

def _reported_paths(snapshot: SourceSnapshot, scanner: str, payload: Mapping[str, Any],
                    intended: Sequence[str]) -> tuple[str, ...]:
    if scanner == "semgrep":
        receipt = payload.get("paths")
        if (not isinstance(receipt, Mapping) or not isinstance(receipt.get("scanned"), list)
                or receipt.get("skipped", []) or payload.get("skipped_rules", [])):
            raise EvidenceError("Semgrep returned incomplete scanned-path evidence.")
        raw_paths = receipt["scanned"]
    else:
        metrics = payload.get("metrics")
        if not isinstance(metrics, Mapping):
            raise EvidenceError("Bandit did not return scanned-path metrics.")
        raw_paths = [path for path in metrics if path != "_totals"]
    if any(not isinstance(value, str) or not value for value in raw_paths):
        raise EvidenceError("Scanner returned a malformed path receipt.")
    paths = tuple(sorted(_relative_scanner_path(snapshot, value) for value in raw_paths))
    if len(paths) != len(set(paths)) or set(paths) != set(intended):
        raise EvidenceError("Scanner did not report complete intended-path coverage.")
    if any(not snapshot.file(path).production_source for path in paths):
        raise EvidenceError("Scanner coverage includes non-production source.")
    return paths

def _scanner_finding(snapshot: SourceSnapshot, scanner: str,
                     raw: Mapping[str, Any]) -> ScannerFinding:
    if scanner == "semgrep":
        path, start = raw.get("path"), raw.get("start")
        line = start.get("line") if isinstance(start, Mapping) else None
        reported = str(raw.get("check_id", ""))
        rule = next((item for item in LOCAL_SEMGREP_RULE_IDS
                     if reported == item or reported.endswith("." + item)), reported)
        if rule not in LOCAL_SEMGREP_RULE_IDS:
            raise EvidenceError("Semgrep returned an unknown local rule ID.")
        extra = raw.get("extra") if isinstance(raw.get("extra"), Mapping) else {}
        metadata = extra.get("metadata") if isinstance(extra.get("metadata"), Mapping) else {}
        severity = {"error": "high", "warning": "medium", "info": "low"}.get(
            str(extra.get("severity", "warning")).lower(), "medium")
        title = extra.get("message", "Semgrep observation")
        cwe, confidence = metadata.get("cwe"), metadata.get("confidence", "unknown")
    else:
        path, line, rule = raw.get("filename"), raw.get("line_number"), str(raw.get("test_id", ""))
        severity = str(raw.get("issue_severity", "medium")).lower()
        title, confidence = raw.get("issue_text", "Bandit observation"), raw.get("issue_confidence", "unknown")
        cwe_data = raw.get("issue_cwe") if isinstance(raw.get("issue_cwe"), Mapping) else {}
        cwe = f"CWE-{cwe_data['id']}" if cwe_data.get("id") else None
    if not isinstance(path, str) or not isinstance(line, int) or isinstance(line, bool) or line < 1:
        raise EvidenceError("Scanner evidence lacks an authentic source position.")
    path = _relative_scanner_path(snapshot, path)
    source = snapshot.file(path)
    if not source.production_source or line > len(_read_source(snapshot, path).splitlines()):
        raise EvidenceError("Scanner evidence does not bind to a valid approved source line.")
    identity = [scanner, rule, path, line, source.sha256, snapshot.source_revision]
    return ScannerFinding(observation_id=_digest(identity), scanner=scanner, rule_id=rule,
        title=re.sub(r"\s+", " ", str(title)).strip()[:400],
        severity=severity if severity in {"critical", "high", "medium", "low"} else "medium",
        confidence=str(confidence).lower(), cwe=str(cwe) if cwe else None,
        relative_file_path=path, line_start=line, source_sha256=source.sha256,
        source_revision=snapshot.source_revision, snapshot_digest=snapshot.snapshot_digest)

def run_selected_scanners(snapshot: SourceSnapshot, selected: Sequence[str],
                          approvals: Iterable[str], *, timeout_seconds: int = 60) -> tuple[ScannerResult, ...]:
    _require(approvals, "scanners")
    verify_snapshot(snapshot)
    selected = tuple(selected)
    if not selected or len(selected) != len(set(selected)) or set(selected) - {"semgrep", "bandit"}:
        raise EvidenceError("Selected scanners must be a nonempty unique subset of the bounded registry.")
    if not 0 < timeout_seconds <= 300:
        raise EvidenceError("Scanner timeout must be between one second and five minutes.")
    results = []
    with tempfile.TemporaryDirectory(prefix="security-swarm-scanners-") as temporary:
        state = Path(temporary)
        rules = state / "rules.yml"
        rules.write_text(LOCAL_SEMGREP_RULES, encoding="utf-8")
        (state / "cache").mkdir()
        (state / "config").mkdir()
        environment = {"PATH": os.environ.get("PATH", os.defpath), "PYTHONDONTWRITEBYTECODE": "1",
            "SEMGREP_SEND_METRICS": "off", "SEMGREP_ENABLE_VERSION_CHECK": "0",
            "SEMGREP_LOG_FILE": str(state / "semgrep.log"),
            "SEMGREP_SETTINGS_FILE": str(state / "settings.yml"),
            "XDG_CACHE_HOME": str(state / "cache"), "XDG_CONFIG_HOME": str(state / "config"),
            "NO_COLOR": "1"}
        for scanner in selected:
            paths = _intended_paths(snapshot, scanner)
            if not paths:
                raise EvidenceError("A selected scanner has no applicable source paths.")
            executable = shutil.which(scanner)
            if not executable:
                results.append(ScannerResult(scanner=scanner, status="failed",
                    reason="Executable unavailable at execution time.", paths_reviewed=paths,
                    snapshot_digest=snapshot.snapshot_digest))
                continue
            command = ([executable, "scan", "--json", "--metrics=off", "--disable-version-check",
                        "--no-git-ignore", "--jobs", "1", "--timeout", "10", "--config", str(rules), *paths]
                       if scanner == "semgrep" else
                       [executable, "--quiet", "--format", "json", "--ignore-nosec", *paths])
            try:
                code, stdout, _, elapsed = _run_bounded_subprocess(command, cwd=snapshot.root,
                    timeout=timeout_seconds, environment=environment)
                if code not in {0, 1}:
                    raise EvidenceError("Scanner returned a non-success exit code.")
                payload = json.loads(stdout.decode("utf-8", errors="strict"))
                if not isinstance(payload, Mapping) or not isinstance(payload.get("results"), list):
                    raise EvidenceError("Scanner returned malformed JSON evidence.")
                if payload.get("errors", []):
                    raise EvidenceError("Scanner reported an execution error.")
                reviewed = _reported_paths(snapshot, scanner, payload, paths)
                if any(not isinstance(item, Mapping) for item in payload["results"]):
                    raise EvidenceError("Scanner returned a malformed finding.")
                findings = tuple(_scanner_finding(snapshot, scanner, item) for item in payload["results"])
                if any(item.relative_file_path not in reviewed for item in findings):
                    raise EvidenceError("Scanner finding is outside its reported path coverage.")
                verify_snapshot(snapshot)
                results.append(ScannerResult(scanner=scanner,
                    status="completed_with_findings" if findings else "completed", findings=findings,
                    exit_code=code, duration_seconds=elapsed, paths_reviewed=reviewed,
                    snapshot_digest=snapshot.snapshot_digest))
            except TimeoutError:
                results.append(ScannerResult(scanner=scanner, status="timed_out",
                    reason="Bounded scanner timeout expired.", paths_reviewed=paths,
                    snapshot_digest=snapshot.snapshot_digest))
            except (EvidenceError, OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
                results.append(ScannerResult(scanner=scanner, status="failed",
                    reason=(str(error) or "Scanner output rejected.")[:240], paths_reviewed=paths,
                    snapshot_digest=snapshot.snapshot_digest))
    return tuple(results)

def require_complete_scanner_coverage(snapshot: SourceSnapshot, selected: Sequence[str],
                                      results: Sequence[ScannerResult]) -> tuple[str, ...]:
    selected = tuple(selected)
    if not selected or len(selected) != len(set(selected)):
        raise EvidenceError("An executed review requires unique selected scanners.")
    by_name = {item.scanner: item for item in results}
    if len(by_name) != len(results) or set(by_name) != set(selected):
        raise EvidenceError("Scanner results do not exactly match the selected scanners.")
    for scanner in selected:
        result, intended = by_name[scanner], _intended_paths(snapshot, scanner)
        if (result.snapshot_digest != snapshot.snapshot_digest
                or result.status not in {"completed", "completed_with_findings"}
                or set(result.paths_reviewed) != set(intended)
                or len(result.paths_reviewed) != len(set(result.paths_reviewed))
                or any(item.relative_file_path not in result.paths_reviewed for item in result.findings)):
            raise EvidenceError(f"Selected scanner {scanner} lacks complete path coverage.")
    return selected

FindingCategory = Literal["sql_injection", "tls_verification_disabled",
    "jwt_verification_disabled", "request_timeout", "other"]
RiskPriority = Literal["P0", "P1", "P2", "P3"]
FindingCandidate = _record("FindingCandidate", candidate_id=(str, ...),
    observation_ids=(tuple[str, ...], Field(min_length=1)), snapshot_digest=(str, ...),
    source_revision=(str, ...), scanner_names=(tuple[str, ...], Field(min_length=1)),
    rule_ids=(tuple[str, ...], Field(min_length=1)),
    scanner_rule_pairs=(tuple[str, ...], Field(min_length=1)),
    source_path=(str, ...), source_sha256=(str, ...),
    line=(int, Field(ge=1)), title=(str, ...), cwe=(str | None, None), severity=(str, ...),
    confidence=(str, ...), category=(FindingCategory, ...), priority=(RiskPriority, ...))

_CATEGORIES: dict[str, FindingCategory] = {
    "cookbook.security.java-spring-jdbc-sql-injection": "sql_injection", "B608": "sql_injection",
    "cookbook.security.javascript-sql-injection": "sql_injection",
    "cookbook.security.python-sql-injection": "sql_injection",
    "cookbook.security.python-tls-verification-disabled": "tls_verification_disabled",
    "cookbook.security.python-jwt-signature-disabled": "jwt_verification_disabled",
    "B501": "tls_verification_disabled", "B113": "request_timeout",
}

def _category(finding: ScannerFinding) -> FindingCategory:
    fallback = {"CWE-89": "sql_injection", "CWE-295": "tls_verification_disabled",
                "CWE-347": "jwt_verification_disabled"}
    return _CATEGORIES.get(finding.rule_id, fallback.get(finding.cwe, "other"))  # type: ignore[arg-type,return-value]

def _priority(category: FindingCategory, severity: str) -> RiskPriority:
    if category == "sql_injection":
        return "P1"
    if category in {"tls_verification_disabled", "jwt_verification_disabled"}:
        return "P2"
    return {"critical": "P0", "high": "P1", "medium": "P2"}.get(severity, "P3")  # type: ignore[return-value]

def _canonical_line(snapshot: SourceSnapshot, finding: ScannerFinding) -> int:
    if not finding.relative_file_path.endswith(".py"):
        return finding.line_start
    try:
        tree = ast.parse(_read_source(snapshot, finding.relative_file_path))
    except SyntaxError:
        return finding.line_start
    calls = [(node.lineno, getattr(node, "end_lineno", node.lineno)) for node in ast.walk(tree)
             if isinstance(node, ast.Call) and node.lineno <= finding.line_start <= getattr(node, "end_lineno", node.lineno)]
    return min(calls, key=lambda item: (item[1] - item[0], item[0]))[0] if calls else finding.line_start

def normalize_candidates(snapshot: SourceSnapshot,
                         results: Sequence[ScannerResult]) -> tuple[FindingCandidate, ...]:
    verify_snapshot(snapshot)
    observations = []
    for result in results:
        if result.snapshot_digest != snapshot.snapshot_digest:
            raise EvidenceError("Scanner result crossed the snapshot boundary.")
        if result.status not in {"completed", "completed_with_findings"}:
            continue
        for finding in result.findings:
            source = snapshot.file(finding.relative_file_path)
            if (finding.scanner != result.scanner or finding.snapshot_digest != snapshot.snapshot_digest
                    or finding.source_revision != snapshot.source_revision
                    or finding.source_sha256 != source.sha256 or not source.production_source):
                raise EvidenceError("Scanner observation failed source provenance checks.")
            observations.append(finding)
    if len({item.observation_id for item in observations}) != len(observations):
        raise EvidenceError("Observation IDs must be unique.")
    grouped: dict[tuple[str, int, FindingCategory], list[ScannerFinding]] = {}
    for finding in observations:
        key = (finding.relative_file_path, _canonical_line(snapshot, finding), _category(finding))
        grouped.setdefault(key, []).append(finding)
    candidates = []
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    for (path, line, category), values in sorted(grouped.items()):
        values.sort(key=lambda item: (rank[item.severity], item.scanner, item.rule_id))
        primary, source = values[0], snapshot.file(path)
        candidate_id = "cand-" + _digest([snapshot.snapshot_digest, path, line, category, source.sha256])[:16]
        candidates.append(FindingCandidate(candidate_id=candidate_id,
            observation_ids=tuple(item.observation_id for item in values),
            snapshot_digest=snapshot.snapshot_digest, source_revision=snapshot.source_revision,
            scanner_names=tuple(sorted({item.scanner for item in values})),
            rule_ids=tuple(sorted({item.rule_id for item in values})),
            scanner_rule_pairs=tuple(sorted({f"{item.scanner}:{item.rule_id}" for item in values})),
            source_path=path,
            source_sha256=source.sha256, line=line, title=primary.title, cwe=primary.cwe,
            severity=primary.severity, confidence=primary.confidence, category=category,
            priority=_priority(category, primary.severity)))
    return tuple(sorted(candidates, key=lambda item: item.candidate_id))

def _verify_candidates(snapshot: SourceSnapshot, candidates: Sequence[FindingCandidate],
                       results: Sequence[ScannerResult]) -> tuple[FindingCandidate, ...]:
    canonical = normalize_candidates(snapshot, results)
    supplied = tuple(sorted(candidates, key=lambda item: item.candidate_id))
    if supplied != canonical:
        raise EvidenceError("Candidate set is not the canonical normalization of scanner evidence.")
    return canonical

SpecialistRole = Literal["authentication", "injection", "configuration"]
SpecialistSpec = _record("SpecialistSpec", role=(SpecialistRole, ...),
    capability_summary=(str, ...), max_candidates=(int, Field(ge=1, le=100)))
_SPECIALISTS = (
    SpecialistSpec(role="authentication", max_candidates=12,
        capability_summary="Review identity, token, session, and authorization evidence."),
    SpecialistSpec(role="injection", max_candidates=12,
        capability_summary="Trace attacker-controlled input into executable sinks."),
    SpecialistSpec(role="configuration", max_candidates=12,
        capability_summary="Review transport, client, cryptographic, and deployment controls."),
)

def specialist_registry() -> tuple[SpecialistSpec, ...]:
    return _SPECIALISTS

class SpecialistToolRequest(Contract):
    candidate_ids: tuple[str, ...] = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def validate_request(self) -> "SpecialistToolRequest":
        if len(self.candidate_ids) != len(set(self.candidate_ids)):
            raise ValueError("Specialist candidate IDs must be unique.")
        if not self.reason.strip():
            raise ValueError("Specialist routing reason cannot be blank.")
        object.__setattr__(self, "reason", self.reason.strip())
        return self

SourceExcerpt = _record("SourceExcerpt", source_path=(str, ...), start_line=(int, Field(ge=1)),
    end_line=(int, Field(ge=1)), source_sha256=(str, ...), text=(str, ...))
SpecialistPacket = _record("SpecialistPacket", role=(SpecialistRole, ...),
    snapshot_digest=(str, ...), reason=(str, ...), candidates=(tuple[FindingCandidate, ...], Field(min_length=1)),
    excerpts=(tuple[SourceExcerpt, ...], Field(min_length=1)))

def _python_window(text: str, line: int, limit: int = 80) -> tuple[int, int] | None:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return None
    functions = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                 and node.lineno <= line <= getattr(node, "end_lineno", node.lineno)]
    if not functions:
        return None
    node = min(functions, key=lambda item: (getattr(item, "end_lineno", item.lineno) - item.lineno, item.lineno))
    start = min([node.lineno, *(item.lineno for item in node.decorator_list)])
    end = getattr(node, "end_lineno", node.lineno)
    if end - start + 1 > limit:
        start, end = max(start, line - 35), min(end, line + 44)
    return start, end

def _excerpt(snapshot: SourceSnapshot, candidate: FindingCandidate) -> SourceExcerpt:
    text = _read_source(snapshot, candidate.source_path)
    lines = text.splitlines()
    window = _python_window(text, candidate.line) if candidate.source_path.endswith(".py") else None
    start, end = window or (max(1, candidate.line - 8), min(len(lines), candidate.line + 12))
    excerpt = "\n".join(f"{number:04d}: {lines[number - 1]}" for number in range(start, end + 1))
    while len(excerpt.encode()) > 24_000 and end > start:
        if candidate.line - start > end - candidate.line:
            start += 1
        else:
            end -= 1
        excerpt = "\n".join(f"{number:04d}: {lines[number - 1]}" for number in range(start, end + 1))
    return SourceExcerpt(source_path=candidate.source_path, start_line=start, end_line=end,
                         source_sha256=candidate.source_sha256, text=excerpt)

def _coerce_request(value: Any) -> SpecialistToolRequest:
    if isinstance(value, SpecialistToolRequest):
        return value
    if isinstance(value, Mapping) and "params" in value:
        value = value["params"]
    if isinstance(value, str):
        value = json.loads(value)
    return SpecialistToolRequest.model_validate(value)

def build_trusted_specialist_packet(snapshot: SourceSnapshot, candidates: Sequence[FindingCandidate],
                                    role: SpecialistRole, request: Any) -> SpecialistPacket:
    verify_snapshot(snapshot)
    request = _coerce_request(request)
    by_id = {item.candidate_id: item for item in candidates}
    if len(by_id) != len(candidates) or any(item.snapshot_digest != snapshot.snapshot_digest for item in candidates):
        raise EvidenceError("Specialist candidates crossed the snapshot boundary.")
    unknown = set(request.candidate_ids) - set(by_id)
    if unknown:
        raise EvidenceError(f"Specialist requested unknown candidates: {sorted(unknown)}")
    ordered = tuple(by_id[candidate_id] for candidate_id in request.candidate_ids)
    return SpecialistPacket(role=role, snapshot_digest=snapshot.snapshot_digest, reason=request.reason,
                            candidates=ordered, excerpts=tuple(_excerpt(snapshot, item) for item in ordered))

AssessmentVerdict = Literal["supported", "needs_review", "not_supported"]

class SpecialistAssessment(Contract):
    candidate_id: str
    verdict: AssessmentVerdict
    reason: str = Field(min_length=1, max_length=600)
    proof_gaps: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_text(self) -> "SpecialistAssessment":
        reason, gaps = self.reason.strip(), tuple(item.strip() for item in self.proof_gaps)
        if not reason or any(not item for item in gaps):
            raise ValueError("Assessment text cannot be blank.")
        if self.verdict == "supported" and gaps:
            raise ValueError("A supported assessment cannot retain proof gaps.")
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "proof_gaps", gaps)
        return self

SpecialistReview = _record("SpecialistReview", role=(SpecialistRole, ...),
    assessments=(tuple[SpecialistAssessment, ...], Field(min_length=1)))

def coerce_specialist_review(value: Any) -> SpecialistReview:
    if isinstance(value, SpecialistReview):
        return value
    if isinstance(value, str):
        value = json.loads(value)
    return SpecialistReview.model_validate(value)

def verify_specialist_review(review: SpecialistReview, packet: SpecialistPacket) -> SpecialistReview:
    expected = tuple(item.candidate_id for item in packet.candidates)
    actual = tuple(item.candidate_id for item in review.assessments)
    if review.role != packet.role or len(actual) != len(set(actual)) or set(actual) != set(expected):
        raise EvidenceError("Specialist review does not exactly cover its trusted packet.")
    return review

def canonical_manager_view(fingerprint: RepositoryFingerprint, candidates: Sequence[FindingCandidate],
                           specialists: Sequence[SpecialistSpec] | None = None) -> dict[str, Any]:
    values = tuple(sorted(candidates, key=lambda item: item.candidate_id))
    if any(item.snapshot_digest != fingerprint.snapshot_digest for item in values):
        raise EvidenceError("Manager input crossed the fingerprint boundary.")
    return {"snapshot_digest": fingerprint.snapshot_digest,
        "fingerprint": {"languages": fingerprint.languages, "production_files": fingerprint.production_files},
        "candidates": [{"candidate_id": item.candidate_id, "category": item.category,
                        "priority": item.priority, "scanner_names": item.scanner_names,
                        "scanner_rule_pairs": item.scanner_rule_pairs,
                        "source_path": item.source_path, "line": item.line}
                       for item in values],
        "available_specialists": [item.model_dump(mode="json") for item in (specialists or specialist_registry())]}

class ManagerSession:
    """Validate and record only specialist calls the manager actually completes."""

    def __init__(self, snapshot: SourceSnapshot, candidates: Sequence[FindingCandidate],
                 scanner_results: Sequence[ScannerResult],
                 specialists: Sequence[SpecialistSpec] | None = None):
        self.snapshot = snapshot
        require_complete_scanner_coverage(snapshot,
            tuple(result.scanner for result in scanner_results), scanner_results)
        self.candidates = _verify_candidates(snapshot, candidates, scanner_results)
        if not self.candidates:
            raise CoverageError("A manager session requires at least one canonical candidate.")
        self.scanner_results = tuple(scanner_results)
        self.specialists = {item.role: item for item in (specialists or specialist_registry())}
        self.assignments: dict[str, tuple[str, ...]] = {}
        self.rationales: dict[str, str] = {}
        self.reviews: dict[str, SpecialistReview] = {}
        self._pending: dict[str, SpecialistToolRequest] = {}

    def available(self, role: str) -> bool:
        covered = {candidate_id for values in self.assignments.values() for candidate_id in values}
        covered |= {candidate_id for request in self._pending.values() for candidate_id in request.candidate_ids}
        return role in self.specialists and role not in self.reviews and role not in self._pending \
            and covered != {item.candidate_id for item in self.candidates}

    def packet(self, role: SpecialistRole, value: Any) -> SpecialistPacket:
        if not self.available(role):
            raise EvidenceError(f"Specialist role {role!r} is unavailable or already used.")
        request = _coerce_request(value)
        order = {item.candidate_id: index for index, item in enumerate(self.candidates)}
        unknown = set(request.candidate_ids) - set(order)
        reserved = {item for pending in self._pending.values() for item in pending.candidate_ids}
        reserved |= {item for values in self.assignments.values() for item in values}
        if unknown or set(request.candidate_ids) & reserved:
            raise EvidenceError("Manager selected an unknown or already assigned candidate.")
        if len(request.candidate_ids) > self.specialists[role].max_candidates:
            raise EvidenceError("Manager exceeded specialist capacity.")
        request = SpecialistToolRequest(candidate_ids=tuple(sorted(request.candidate_ids, key=order.get)),
                                        reason=request.reason)
        self._pending[role] = request
        return build_trusted_specialist_packet(self.snapshot, self.candidates, role, request)

    def complete(self, role: SpecialistRole, result: Any) -> SpecialistReview:
        pending = self._pending.get(role)
        invocation = getattr(result, "agent_tool_invocation", None)
        if (pending is None or invocation is None
                or getattr(invocation, "tool_name", None) != f"review_{role}"
                or not isinstance(getattr(invocation, "tool_call_id", None), str)
                or not invocation.tool_call_id
                or not isinstance(invocation.tool_arguments, str)):
            raise EvidenceError("Specialist completion lacks authenticated agent-tool arguments.")
        actual = _coerce_request(invocation.tool_arguments)
        order = {item.candidate_id: index for index, item in enumerate(self.candidates)}
        if set(actual.candidate_ids) - set(order):
            raise EvidenceError("Completed specialist arguments contain unknown candidates.")
        actual = SpecialistToolRequest(candidate_ids=tuple(sorted(actual.candidate_ids, key=order.get)),
                                       reason=actual.reason)
        if actual != pending:
            raise EvidenceError("Completed specialist arguments differ from the trusted reservation.")
        packet = build_trusted_specialist_packet(self.snapshot, self.candidates, role, pending)
        review = verify_specialist_review(coerce_specialist_review(result.final_output), packet)
        self.assignments[role] = pending.candidate_ids
        self.rationales[role] = pending.reason
        self.reviews[role] = review
        del self._pending[role]
        return review

    def ack(self, role: SpecialistRole) -> str:
        if role not in self.assignments:
            raise EvidenceError("Specialist result has not been recorded.")
        return json.dumps({"candidate_ids": self.assignments[role], "role": role, "status": "recorded"},
                          sort_keys=True, separators=(",", ":"))

    def finish(self) -> tuple[SpecialistReview, ...]:
        if self._pending:
            raise CoverageError("A specialist tool call has not completed.")
        actual = [item for values in self.assignments.values() for item in values]
        expected = {item.candidate_id for item in self.candidates}
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise CoverageError("Observed specialist calls do not exactly cover all candidates.")
        return tuple(self.reviews[role] for role in sorted(self.reviews))

ValidatorDisposition = Literal["confirmed", "needs_review", "not_actionable"]

class ValidatorFinding(Contract):
    candidate_id: str
    disposition: ValidatorDisposition
    reason: str = Field(min_length=1, max_length=600)
    proof_gaps: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_text(self) -> "ValidatorFinding":
        reason, gaps = self.reason.strip(), tuple(item.strip() for item in self.proof_gaps)
        if not reason or any(not item for item in gaps):
            raise ValueError("Validator text cannot be blank.")
        object.__setattr__(self, "reason", reason)
        object.__setattr__(self, "proof_gaps", gaps)
        return self

ModelValidationReport = _record("ModelValidationReport",
    findings=(tuple[ValidatorFinding, ...], Field(min_length=1)))
ValidatorItem = _record("ValidatorItem", candidate=(FindingCandidate, ...),
    excerpt=(SourceExcerpt, ...), specialist=(SpecialistAssessment, ...))
ValidatorPacket = _record("ValidatorPacket", snapshot_digest=(str, ...),
    items=(tuple[ValidatorItem, ...], Field(min_length=1)))

def _review_index(reviews: Sequence[SpecialistReview]) -> dict[str, SpecialistAssessment]:
    indexed: dict[str, SpecialistAssessment] = {}
    for review in reviews:
        for assessment in review.assessments:
            if assessment.candidate_id in indexed:
                raise EvidenceError("Specialist reviews contain duplicate candidate coverage.")
            indexed[assessment.candidate_id] = assessment
    return indexed

def build_validator_packet(snapshot: SourceSnapshot, candidates: Sequence[FindingCandidate],
                           scanner_results: Sequence[ScannerResult],
                           reviews: Sequence[SpecialistReview]) -> ValidatorPacket:
    canonical = _verify_candidates(snapshot, candidates, scanner_results)
    indexed = _review_index(reviews)
    if set(indexed) != {item.candidate_id for item in canonical}:
        raise EvidenceError("Validator input lacks exact specialist coverage.")
    return ValidatorPacket(snapshot_digest=snapshot.snapshot_digest,
        items=tuple(ValidatorItem(candidate=item, excerpt=_excerpt(snapshot, item),
                                  specialist=indexed[item.candidate_id]) for item in canonical))

def coerce_model_validation(value: Any) -> ModelValidationReport:
    if isinstance(value, ModelValidationReport):
        return value
    if isinstance(value, str):
        value = json.loads(value)
    return ModelValidationReport.model_validate(value)

def verify_model_validation(report: Any, snapshot: SourceSnapshot,
                            candidates: Sequence[FindingCandidate]) -> ModelValidationReport:
    report = coerce_model_validation(report)
    expected = {item.candidate_id for item in candidates}
    actual = [item.candidate_id for item in report.findings]
    if (len(actual) != len(set(actual)) or set(actual) != expected
            or any(item.snapshot_digest != snapshot.snapshot_digest for item in candidates)):
        raise EvidenceError("Validator report does not exactly cover the trusted candidates.")
    return report

ProvenanceFinding = _record("ProvenanceFinding", candidate_id=(str, ...), source_path=(str, ...),
    line=(int, Field(ge=1)), source_sha256=(str, ...), source_revision=(str, ...),
    snapshot_digest=(str, ...), scanner_names=(tuple[str, ...], ...), rule_ids=(tuple[str, ...], ...),
    scanner_rule_pairs=(tuple[str, ...], ...),
    category=(FindingCategory, ...), priority=(RiskPriority, ...), disposition=(ValidatorDisposition, ...),
    reason=(str, ...), proof_gaps=(tuple[str, ...], ()))
ProvenanceReport = _record("ProvenanceReport", snapshot_digest=(str, ...),
    findings=(tuple[ProvenanceFinding, ...], Field(min_length=1)))

def apply_provenance_gate(snapshot: SourceSnapshot, candidates: Sequence[FindingCandidate],
                          scanner_results: Sequence[ScannerResult], reviews: Sequence[SpecialistReview],
                          report: Any, *, selected_scanners: Sequence[str] | None = None) -> ProvenanceReport:
    if selected_scanners is not None:
        require_complete_scanner_coverage(snapshot, selected_scanners, scanner_results)
    canonical = _verify_candidates(snapshot, candidates, scanner_results)
    specialists = _review_index(reviews)
    report = verify_model_validation(report, snapshot, canonical)
    validation = {item.candidate_id: item for item in report.findings}
    if set(specialists) != set(validation):
        raise EvidenceError("Provenance inputs do not share exact candidate coverage.")
    findings = []
    for candidate in canonical:
        specialist, decision = specialists[candidate.candidate_id], validation[candidate.candidate_id]
        gaps = tuple(dict.fromkeys((*specialist.proof_gaps, *decision.proof_gaps)))
        if gaps or specialist.verdict == "needs_review" or decision.disposition == "needs_review":
            disposition: ValidatorDisposition = "needs_review"
        elif specialist.verdict == "supported" and decision.disposition == "confirmed":
            disposition = "confirmed"
        elif specialist.verdict == "not_supported" or decision.disposition == "not_actionable":
            disposition = "not_actionable"
        else:
            disposition = "needs_review"
        source = snapshot.file(candidate.source_path)
        if source.sha256 != candidate.source_sha256:
            raise EvidenceError("Candidate source binding changed before provenance adjudication.")
        findings.append(ProvenanceFinding(candidate_id=candidate.candidate_id,
            source_path=candidate.source_path, line=candidate.line, source_sha256=candidate.source_sha256,
            source_revision=candidate.source_revision, snapshot_digest=candidate.snapshot_digest,
            scanner_names=candidate.scanner_names, rule_ids=candidate.rule_ids,
            scanner_rule_pairs=candidate.scanner_rule_pairs, category=candidate.category,
            priority=candidate.priority, disposition=disposition, reason=decision.reason, proof_gaps=gaps))
    verify_snapshot(snapshot)
    return ProvenanceReport(snapshot_digest=snapshot.snapshot_digest, findings=tuple(findings))

FindingGroup = _record("FindingGroup", category=(FindingCategory, ...), title=(str, ...),
    priority=(RiskPriority, ...), candidate_ids=(tuple[str, ...], Field(min_length=1)),
    source_paths=(tuple[str, ...], Field(min_length=1)), remediation=(str, ...))
_GROUPS = {
    "sql_injection": ("Parameterize database queries", "Replace string-built SQL with bound parameters and preserve input validation."),
    "tls_verification_disabled": ("Restore TLS certificate verification", "Remove verify=False and configure a trusted CA bundle where necessary."),
    "jwt_verification_disabled": ("Require JWT signature verification", "Verify signatures, issuers, audiences, and accepted algorithms before trusting claims."),
    "request_timeout": ("Bound outbound request time", "Set an explicit connect/read timeout and handle timeout failures safely."),
    "other": ("Resolve the confirmed security finding", "Apply the narrowest source-bound remediation and add a regression test."),
}

def group_confirmed_findings(report: ProvenanceReport) -> tuple[FindingGroup, ...]:
    grouped: dict[FindingCategory, list[ProvenanceFinding]] = {}
    for finding in report.findings:
        if finding.disposition == "confirmed":
            grouped.setdefault(finding.category, []).append(finding)
    rank = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    groups = []
    for category, findings in grouped.items():
        findings.sort(key=lambda item: (item.source_path, item.line, item.candidate_id))
        title, remediation = _GROUPS[category]
        groups.append(FindingGroup(category=category, title=title,
            priority=min((item.priority for item in findings), key=rank.get),
            candidate_ids=tuple(item.candidate_id for item in findings),
            source_paths=tuple(sorted({item.source_path for item in findings})), remediation=remediation))
    return tuple(sorted(groups, key=lambda item: (rank[item.priority], item.category)))

ReviewStatus = Literal["executed", "partial", "not_authorized", "failed"]

class ReviewBundle(Contract):
    status: ReviewStatus
    target_id: str
    snapshot: SourceSnapshot | None = None
    fingerprint: RepositoryFingerprint | None = None
    assessments: tuple[ScannerAssessment, ...] = ()
    selected_scanners: tuple[str, ...] = ()
    scanner_results: tuple[ScannerResult, ...] = ()
    candidates: tuple[FindingCandidate, ...] = ()
    specialist_reviews: tuple[SpecialistReview, ...] = ()
    model_report: ModelValidationReport | None = None
    provenance: ProvenanceReport | None = None
    groups: tuple[FindingGroup, ...] = ()
    error: str | None = None

def finalize_review(snapshot: SourceSnapshot, fingerprint: RepositoryFingerprint,
                    selected: Sequence[str], scanner_results: Sequence[ScannerResult],
                    candidates: Sequence[FindingCandidate], reviews: Sequence[SpecialistReview],
                    model_report: Any, provenance: ProvenanceReport | None = None, *,
                    assessments: Sequence[ScannerAssessment] = ()) -> ReviewBundle:
    if fingerprint != fingerprint_repository(snapshot):
        raise EvidenceError("Repository fingerprint is not canonical for the approved snapshot.")
    require_complete_scanner_coverage(snapshot, selected, scanner_results)
    canonical = _verify_candidates(snapshot, candidates, scanner_results)
    computed = apply_provenance_gate(snapshot, canonical, scanner_results, reviews, model_report,
                                     selected_scanners=selected)
    if provenance is not None and provenance != computed:
        raise EvidenceError("Supplied provenance differs from deterministic adjudication.")
    provenance = computed
    report = verify_model_validation(model_report, snapshot, canonical)
    return ReviewBundle(status="executed", target_id=snapshot.target_id, snapshot=snapshot,
        fingerprint=fingerprint, assessments=tuple(assessments), selected_scanners=tuple(selected),
        scanner_results=tuple(scanner_results), candidates=canonical,
        specialist_reviews=tuple(reviews), model_report=report, provenance=provenance,
        groups=group_confirmed_findings(provenance))

def partial_review(*, status: ReviewStatus, error: str,
                   manifest: TargetManifest | None = None, snapshot: SourceSnapshot | None = None,
                   fingerprint: RepositoryFingerprint | None = None,
                   assessments: Sequence[ScannerAssessment] = (), selected: Sequence[str] = (),
                   scanner_results: Sequence[ScannerResult] = (),
                   candidates: Sequence[FindingCandidate] = ()) -> ReviewBundle:
    if status == "executed":
        raise ValueError("partial_review cannot create an executed bundle.")
    target_id = snapshot.target_id if snapshot else manifest.target_id if manifest else "unknown"
    return ReviewBundle(status=status, target_id=target_id, snapshot=snapshot, fingerprint=fingerprint,
        assessments=tuple(assessments), selected_scanners=tuple(selected),
        scanner_results=tuple(scanner_results), candidates=tuple(candidates),
        error=(error.strip() or "Review did not complete.")[:500])

def select_goal_bundle(reviews: Mapping[str, ReviewBundle]) -> ReviewBundle | None:
    eligible = [bundle for bundle in reviews.values() if bundle.status == "executed" and bundle.groups]
    return max(eligible, key=lambda item: (sum(len(group.candidate_ids) for group in item.groups),
                                           len(item.groups), item.target_id), default=None)

def render_codex_goal(bundle: ReviewBundle) -> str:
    if (bundle.status != "executed" or not bundle.snapshot or not bundle.model_report
            or not bundle.provenance or not bundle.groups
            or bundle.target_id != bundle.snapshot.target_id):
        raise EvidenceError("A deterministic goal requires an executed review with confirmed findings.")
    computed = apply_provenance_gate(bundle.snapshot, bundle.candidates, bundle.scanner_results,
        bundle.specialist_reviews, bundle.model_report, selected_scanners=bundle.selected_scanners)
    groups = group_confirmed_findings(computed)
    if computed != bundle.provenance or groups != bundle.groups:
        raise EvidenceError("Review provenance or confirmed groups were modified after adjudication.")
    lines = [f"/goal Remediate confirmed findings in {bundle.target_id}", "",
        f"Work only in repository {bundle.snapshot.source_url} at revision {bundle.snapshot.source_revision}.",
        "Keep production changes limited to the approved source paths listed below.",
        "You may add or update only the test files needed to cover those fixes with focused regression tests.",
        "Ask for approval before changing any other files. Do not alter unrelated behavior.", ""]
    for index, group in enumerate(groups, 1):
        lines.extend([f"{index}. {group.title} ({group.priority})",
            f"   Paths: {', '.join(group.source_paths)}",
            f"   Evidence IDs: {', '.join(group.candidate_ids)}",
            f"   Change: {group.remediation}"])
    lines.extend(["", "Validation requirements:",
        "- Add or update focused regression tests for each remediated path.",
        "- Run the repository's relevant tests and the applicable security scanners.",
        "- Report changed files, validation results, and any remaining limitations.",
        "- Stop and ask for review if the pinned source no longer matches the evidence above."])
    goal = "\n".join(lines)
    if len(goal) >= 4000:
        raise EvidenceError("Deterministic goal exceeds the 4,000-character handoff limit.")
    return goal


def prompt_text(*sections: str) -> str:
    return "\n".join(dedent(part).strip() for part in sections if part.strip())

def _text(value: Any, limit: int | None = 170) -> str:
    if isinstance(value, Markdown):
        return value.data  # Only caller-authored links use this wrapper.
    if isinstance(value, (list, tuple, set, frozenset)):
        value = ", ".join(str(item) for item in value) or "none"
    if value == "not_authorized":
        value = "not requested"
    value = str(value).replace("\n", " ")
    if limit is not None and len(value) > limit:
        value = value[: limit - 1] + "…"
    value = html.escape(value, quote=False)
    # Model text stays literal; it cannot create Markdown links or images.
    return "".join("\\" + char if char in "\\`*_{}[]()#+-.!|~$" else char for char in value)

def show_table(title: str, rows: Sequence[Mapping[str, Any]], columns: Sequence[str]):
    rows = list(rows)
    lines = [f"**{_text(title)}**", "",
             "| " + " | ".join(map(_text, columns)) + " |",
             "| " + " | ".join("---" for _ in columns) + " |"]
    body = ["| " + " | ".join(_text(row.get(column, "")) for column in columns)
            + " |" for row in rows]
    display(Markdown("\n".join((*lines, *body))))

def show_review_details(reviews: Mapping[str, Any]):
    pending = [
        (target, finding)
        for target, bundle in reviews.items()
        for finding in (bundle.provenance.findings if bundle.provenance else ())
        if finding.disposition == "needs_review"
    ]
    if not pending:
        return
    lines = ["**Findings that need more evidence**", ""]
    for target, finding in pending:
        location = f"{finding.source_path}:{finding.line}"
        lines.extend([
            f"**{_text(target)} — {_text(location, None)}**", "",
            f"Candidate: {_text(finding.candidate_id, None)}", "",
            _text(finding.reason, None), "",
            *(f"- Proof gap: {_text(gap, None)}" for gap in finding.proof_gaps), "",
        ])
    display(Markdown("\n".join(lines)))

def result_rows(target: str, bundle: Any):
    label = f"{target} / {', '.join(bundle.selected_scanners) or 'none'}"
    role_by_candidate = {
        assessment.candidate_id: review.role
        for review in bundle.specialist_reviews
        for assessment in review.assessments
    }
    proposed = {item.candidate_id: item for item in
                (bundle.model_report.findings if bundle.model_report else ())}
    final = {item.candidate_id: item for item in
             (bundle.provenance.findings if bundle.provenance else ())}
    rows = []
    for candidate in bundle.candidates:
        model_finding = proposed.get(candidate.candidate_id)
        final_finding = final.get(candidate.candidate_id)
        reason = getattr(final_finding, "reason", None) or getattr(model_finding, "reason", "not reviewed")
        gaps = getattr(final_finding, "proof_gaps", ()) or getattr(model_finding, "proof_gaps", ())
        rows.append({
            "target / scanners": label,
            "signal": f"{candidate.priority} / {candidate.category}",
            "source": f"{candidate.source_path}:{candidate.line}",
            "specialist": role_by_candidate.get(candidate.candidate_id, "not run"),
            "validator": getattr(model_finding, "disposition", "not run"),
            "final": getattr(final_finding, "disposition", "not adjudicated"),
            "reason or gap": f"{reason} Proof gap: {', '.join(gaps)}" if gaps else reason,
        })
    if not rows:
        rows.append({"target / scanners": label, "signal": bundle.status,
            "source": "none", "specialist": "not run", "validator": "not run",
            "final": "not adjudicated",
            "reason or gap": bundle.error or "No candidates were reviewed."})
    return rows
