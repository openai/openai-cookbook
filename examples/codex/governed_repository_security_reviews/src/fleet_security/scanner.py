"""Synthetic documented artifact adapter; no hosted Codex Security scan is invoked."""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import threading
from collections import Counter
from pathlib import Path
from typing import Any

from .inventory import Repository, stable_digest
from .threats import ThreatAssignment


_PACKAGE = Path(__file__).resolve().parents[2]
_LAB_ROOT = _PACKAGE.parent
_FIXTURES = _PACKAGE / "fixtures"
_UNTRUSTED = (
    re.compile(r"ignore\s+(?:all\s+)?(?:previous|prior|system|developer)\s+instructions", re.I),
    re.compile(r"(?:print|read|dump|send|upload|exfiltrate)\s+.{0,50}(?:secret|token|api[_ -]?key|credential|\.env)", re.I),
    re.compile(r"(?:curl|wget|ssh|netcat)\s+", re.I),
)
_RULES = {
    "SYNTHETIC_SQL_INJECTION": ("synthetic/sqli-001", "high", "high"),
    "SYNTHETIC_MISSING_AUTH": ("synthetic/auth-001", "critical", "high"),
    "SYNTHETIC_UNSAFE_DESERIALIZE": ("synthetic/deser-001", "high", "medium"),
}
_FORBIDDEN_SOURCE_NAMES = frozenset({".git", ".ssh", ".aws", "credentials.json", "id_rsa", "id_ed25519"})
_CONTENT_REFUSAL_EXIT = 65
_CONTENT_REFUSAL_REASONS = frozenset({
    "repository_instruction", "hidden_repository_entry", "symbolic_repository_entry",
    "source_inspection_budget",
})
_ISOLATION_HIDDEN_PATHS = frozenset({
    "/var/run/docker.sock", "/workspace/.env.local", "/workspace/.git", "/Users", "/host",
})
_ISOLATION_CREDENTIAL_NAMES = frozenset({
    "OPENAI_API_KEY", "CODEX_API_KEY", "GITHUB_TOKEN", "GH_TOKEN",
    "OPENAI_WEBHOOK_SECRET", "AWS_SECRET_ACCESS_KEY",
})
RETRY_REASON_CODES = frozenset({
    "retryable_scan_failure",
    "synthetic_provider_transient",
    "synthetic_deadline_exceeded",
    "restricted_worker_timeout",
    "restricted_worker_io_failure",
    "restricted_receipt_invalid",
})


class ScanFailure(RuntimeError):
    def __init__(
        self, message: str, *, retryable: bool = False, coverage: str | None = None,
        reason_code: str = "retryable_scan_failure",
    ) -> None:
        super().__init__(message)
        self.retryable = retryable
        self.coverage = coverage
        # Only host-defined categories enter retry evidence, never exception
        # text, repository instructions or caller-provided diagnostic fields.
        self.reason_code = (
            reason_code if isinstance(reason_code, str) and reason_code in RETRY_REASON_CODES
            else "retryable_scan_failure"
        )


def parse_restricted_content_refusal(returncode: object, stdout: object) -> str | None:
    """Recognise only the trusted fixture worker's bounded refusal protocol."""
    if type(returncode) is not int or returncode != _CONTENT_REFUSAL_EXIT:
        return None
    if type(stdout) is not str or len(stdout) > 512:
        return None
    try:
        refusal = json.loads(stdout)
    except json.JSONDecodeError:
        return None
    if (
        type(refusal) is dict and set(refusal) == {"status", "reason_code"}
        and refusal["status"] == "refused_untrusted_content"
        and type(refusal["reason_code"]) is str
        and refusal["reason_code"] in _CONTENT_REFUSAL_REASONS
    ):
        return refusal["reason_code"]
    return None


def restricted_isolation_verified(receipt: object) -> bool:
    """Require positive, complete isolation evidence; absence is not false."""
    if type(receipt) is not dict:
        return False
    hidden = receipt.get("hiddenPathPresence")
    credentials = receipt.get("credentialPresence")
    capabilities = receipt.get("effectiveCapabilities")
    return (
        type(receipt.get("uid")) is int and receipt["uid"] == 65532
        and receipt.get("networkBlocked") is True
        and receipt.get("rootReadOnly") is True
        and type(receipt.get("mountChecks")) is dict
        and receipt["mountChecks"] == {
            "source": "read_only", "protectedTests": "read_only", "scratch": "writable",
        }
        and type(capabilities) is str
        and re.fullmatch(r"[0-9a-fA-F]{1,16}", capabilities) is not None
        and int(capabilities, 16) == 0
        and receipt.get("noNewPrivileges") == "1"
        and type(hidden) is dict and set(hidden) == _ISOLATION_HIDDEN_PATHS
        and all(value is False for value in hidden.values())
        and type(credentials) is dict and set(credentials) == _ISOLATION_CREDENTIAL_NAMES
        and all(value is False for value in credentials.values())
    )


# Constant, owner-selected program: repository data is read as inert text, never executed.
_DOCKER_PROGRAM = r"""
import errno,json,os,pathlib,re,socket,stat
def refuse(reason):
 print(json.dumps({'status':'refused_untrusted_content','reason_code':reason}))
 raise SystemExit(65)
rules={"SYNTHETIC_SQL_INJECTION":"synthetic/sqli-001","SYNTHETIC_MISSING_AUTH":"synthetic/auth-001","SYNTHETIC_UNSAFE_DESERIALIZE":"synthetic/deser-001"}
blocked=[r"ignore\s+(?:all\s+)?(?:previous|prior|system|developer)\s+instructions",r"(?:print|read|dump|send|upload|exfiltrate)\s+.{0,50}(?:secret|token|api[_ -]?key|credential|\.env)",r"(?:curl|wget|ssh|netcat)\s+"]
matches=[]
for root,dirs,files in os.walk('/workspace/src',followlinks=False):
 for name in dirs+files:
  if name.lower().startswith('.env') or name.lower() in ('.git','.ssh','.aws','credentials.json','id_rsa','id_ed25519'): refuse('hidden_repository_entry')
  candidate=pathlib.Path(root)/name
  if stat.S_ISLNK(candidate.lstat().st_mode): refuse('symbolic_repository_entry')
 for name in files:
  candidate=pathlib.Path(root)/name
  if candidate.stat().st_size>65536: refuse('source_inspection_budget')
  content=candidate.read_text(encoding='utf-8')
  if any(re.search(pattern,content,re.I) for pattern in blocked): refuse('repository_instruction')
  for number,line in enumerate(content.splitlines(),1):
   for marker,rule in rules.items():
    if marker in line: matches.append({'path':str(candidate.relative_to('/workspace')),'line':number,'rule':rule})
network_blocked=False
try: socket.create_connection(('203.0.113.1',443),timeout=1)
except OSError: network_blocked=True
root_readonly=False
try: pathlib.Path('/fleet-isolation-proof').write_text('synthetic')
except OSError as error: root_readonly=error.errno in (errno.EROFS,errno.EACCES)
mount_checks={}
for label,target in (('source','/workspace/src/fleet-proof'),('protectedTests','/workspace/tests/fleet-proof'),('scratch','/workspace/.scratch/fleet-proof')):
 try: pathlib.Path(target).write_text('synthetic'); mount_checks[label]='writable'
 except OSError: mount_checks[label]='read_only'
status=dict(line.split(':',1) for line in pathlib.Path('/proc/self/status').read_text().splitlines() if ':' in line)
hidden=('/var/run/docker.sock','/workspace/.env.local','/workspace/.git','/Users','/host')
names=('OPENAI_API_KEY','CODEX_API_KEY','GITHUB_TOKEN','GH_TOKEN','OPENAI_WEBHOOK_SECRET','AWS_SECRET_ACCESS_KEY')
print(json.dumps({'matches':matches,'uid':os.getuid(),'networkBlocked':network_blocked,'rootReadOnly':root_readonly,'mountChecks':mount_checks,'effectiveCapabilities':status['CapEff'].strip(),'noNewPrivileges':status['NoNewPrivs'].strip(),'hiddenPathPresence':{key:pathlib.Path(key).exists() for key in hidden},'credentialPresence':{key:key in os.environ for key in names}}))
""".strip()


class SyntheticScanner:
    """Deterministic adapter, optionally reusing the verified real Docker executor."""

    version = "synthetic-security-adapter/1.0"
    product_execution = False

    def __init__(
        self, *, isolated: bool = False,
        behaviour: dict[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.isolated = isolated
        self.behaviour = dict(behaviour or {})
        self.invocations: Counter[str] = Counter()
        self.max_active_workers = 0
        self._active_workers = 0
        self._lock = threading.Lock()
        self.isolation_receipts: list[dict[str, Any]] = []

    def scan(self, repository: Repository, assignment: ThreatAssignment) -> dict[str, Any]:
        with self._lock:
            self.invocations[repository.repo_id] += 1
            attempt = self.invocations[repository.repo_id]
            self._active_workers += 1
            self.max_active_workers = max(self.max_active_workers, self._active_workers)
        try:
            sequence = self.behaviour.get(repository.repo_id, ())
            behaviour = sequence[min(attempt - 1, len(sequence) - 1)] if sequence else "success"
            if behaviour == "transient":
                raise ScanFailure(
                    "synthetic provider temporarily unavailable", retryable=True,
                    reason_code="synthetic_provider_transient",
                )
            if behaviour == "timeout":
                raise ScanFailure(
                    "synthetic scan exceeded its enforced deadline", retryable=True,
                    reason_code="synthetic_deadline_exceeded",
                )
            if behaviour == "permanent":
                raise ScanFailure("synthetic scanner access was denied", retryable=False)
            if behaviour == "cancelled":
                raise ScanFailure("synthetic scan was cancelled by its owner", retryable=False)
            if behaviour == "partial":
                raise ScanFailure("synthetic scanner returned exit 2 with partial coverage", coverage="partial")
            if behaviour == "unknown":
                raise ScanFailure("synthetic scanner returned exit 2 with unknown coverage", coverage="unknown")
            fixture = self._fixture(repository)
            matches, isolation = self._isolated_matches(fixture, repository) if self.isolated else self._offline_matches(fixture)
            scan_id = "synthetic-" + stable_digest({
                "repository": repository.repo_id, "revision": repository.commit_sha,
                "context": assignment.effective_model_hash,
            })[:24]
            findings = [self._finding(repository, scan_id, row) for row in matches]
            findings_document = {
                "documentType": "codex-security.findings",
                "schemaVersion": "1.0",
                "scanId": scan_id,
                "synthetic": True,
                "findings": findings,
            }
            coverage = {
                "documentType": "codex-security.coverage",
                "schemaVersion": "1.0",
                "scanId": scan_id,
                "synthetic": True,
                "mode": "repository",
                "completeness": "complete",
                "inventoryStrategy": "repository",
                "includePaths": ["src/"],
                "excludePaths": [],
                "surfaces": [{
                    "id": "synthetic-source",
                    "label": "Approved synthetic source fixture",
                    "disposition": "reported" if findings else "no_issue_found",
                    "receiptRefs": [],
                }],
                "explicitExclusions": [{
                    "pattern": "production-runtime",
                    "reason": "The synthetic local fixture does not prove production/runtime coverage.",
                }],
                "deferred": [],
            }
            report = (
                f"# Synthetic security review: {repository.repo_id}\n\n"
                f"Pinned revision: {repository.commit_sha}\n"
                f"Findings: {len(findings)}\n"
                "This is a deterministic local simulation, not a product scan.\n"
            )
            return {
                "report.md": report,
                "findings.json": findings_document,
                "coverage.json": coverage,
                "isolation": isolation,
                "scan_id": scan_id,
            }
        finally:
            with self._lock:
                self._active_workers -= 1

    @staticmethod
    def _fixture(repository: Repository) -> Path:
        if not repository.repo_id.startswith("synthetic/"):
            raise ScanFailure("synthetic scanner refuses non-synthetic repository identities")
        if not repository.fixture:
            raise ScanFailure("synthetic scanner requires an explicit approved fixture; no fallback is permitted")
        name = repository.fixture
        try:
            candidate = (_FIXTURES / name).resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise ScanFailure("approved synthetic fixture is unavailable; no fallback is permitted") from error
        if not candidate.is_relative_to(_FIXTURES.resolve()) or not candidate.is_dir():
            raise ScanFailure("approved synthetic fixture escaped its controlled boundary")
        return candidate

    def _offline_matches(self, fixture: Path) -> tuple[list[dict[str, Any]], str]:
        source = fixture / "src"
        if not source.is_dir() or source.is_symlink():
            raise ScanFailure("approved synthetic fixture has no safe source directory")
        matches: list[dict[str, Any]] = []
        for root, directories, names in os.walk(source, followlinks=False):
            for name in (*directories, *names):
                lowered = name.casefold()
                if lowered.startswith(".env") or lowered in _FORBIDDEN_SOURCE_NAMES:
                    raise ScanFailure("hidden secret or credential repository entry requires safe abstention")
                if stat.S_ISLNK((Path(root) / name).lstat().st_mode):
                    raise ScanFailure("untrusted symbolic repository entry requires safe abstention")
            for name in names:
                path = Path(root) / name
                if path.stat().st_size > 65_536:
                    raise ScanFailure("untrusted source exceeds its safe inspection budget")
                try:
                    content = path.read_text(encoding="utf-8")
                except (OSError, UnicodeError) as error:
                    raise ScanFailure("untrusted source cannot be decoded safely") from error
                if any(pattern.search(content) for pattern in _UNTRUSTED):
                    raise ScanFailure("untrusted repository instruction requires safe abstention")
                for line_number, line in enumerate(content.splitlines(), 1):
                    for marker, (rule, _, _) in _RULES.items():
                        if marker in line:
                            matches.append({
                                "path": path.relative_to(fixture).as_posix(),
                                "line": line_number,
                                "rule": rule,
                            })
        return matches, "synthetic_offline_not_sandboxed"

    def _isolated_matches(self, fixture: Path, repository: Repository) -> tuple[list[dict[str, Any]], str]:
        # Import lazily: ordinary inventory and planning cannot initialise credentials or network.
        bundled_source = _PACKAGE / "src"
        lab_source = str(bundled_source if (bundled_source / "field_autonomy").is_dir() else _LAB_ROOT / "src")
        if lab_source not in sys.path:
            sys.path.insert(0, lab_source)
        from field_autonomy.policy import PolicyViolation
        from field_autonomy.sandbox import ContainerRuntime

        try:
            with ContainerRuntime().open(fixture, "synthetic-fleet-" + repository.repo_id.split("/")[-1]) as workspace:
                if workspace.executor is None:
                    raise ScanFailure("restricted executor did not initialise; fallback is prohibited")
                result = workspace.executor.run(["python3", "-I", "-c", _DOCKER_PROGRAM], timeout=10)
                if result.returncode != 0:
                    # A Docker launch failure or killed worker is not proof of
                    # a deliberate content refusal. Only this trusted program's
                    # exact bounded protocol may establish that outcome. Never
                    # copy arbitrary stdout/stderr into a refusal or retry event.
                    refusal = parse_restricted_content_refusal(result.returncode, result.stdout)
                    if refusal is not None:
                        if refusal == "repository_instruction":
                            raise ScanFailure("restricted synthetic scan abstained on untrusted repository content")
                        raise ScanFailure("restricted synthetic scan refused an unsafe repository entry")
                    raise ScanFailure("restricted synthetic worker failed without a verified content refusal")
                receipt = json.loads(result.stdout)
                if not restricted_isolation_verified(receipt):
                    raise ScanFailure("restricted execution failed a mandatory isolation property")
                with self._lock:
                    self.isolation_receipts.append(receipt)
                return receipt["matches"], workspace.isolation
        except PolicyViolation as error:
            raise ScanFailure("restricted container policy failed closed; no local fallback is permitted") from error
        except subprocess.TimeoutExpired as error:
            raise ScanFailure(
                "restricted synthetic scan failed or timed out", retryable=True,
                reason_code="restricted_worker_timeout",
            ) from error
        except OSError as error:
            raise ScanFailure(
                "restricted synthetic scan failed or timed out", retryable=True,
                reason_code="restricted_worker_io_failure",
            ) from error
        except json.JSONDecodeError as error:
            raise ScanFailure(
                "restricted synthetic scan failed or timed out", retryable=True,
                reason_code="restricted_receipt_invalid",
            ) from error

    @staticmethod
    def _finding(repository: Repository, scan_id: str, match: dict[str, Any]) -> dict[str, Any]:
        metadata = next(value for value in _RULES.values() if value[0] == match["rule"])
        rule, severity, confidence = metadata
        stable = hashlib.sha256(f"{repository.repo_id}:{rule}:{match['path']}".encode()).hexdigest()
        occurrence = hashlib.sha256(f"{stable}:{repository.commit_sha}:{match['line']}".encode()).hexdigest()
        return {
            "findingId": "csf_" + stable[:24],
            "occurrenceId": "occ_" + occurrence[:24],
            "ruleId": rule,
            "identity": {"anchor": f"{rule}/{match['path']}"},
            "fingerprints": {
                "algorithm": "codex-security/v1",
                "primary": "codex-security/v1:sha256:" + stable,
                "occurrence": occurrence,
            },
            "title": "Synthetic " + rule,
            "summary": "Deterministic synthetic marker detected in an approved fixture.",
            "severity": {"level": severity},
            "confidence": {
                "level": confidence,
                "rationale": "A deterministic synthetic marker was observed in the approved fixture.",
            },
            "taxonomy": {"category": "synthetic-regression", "cwe": []},
            "locations": [{"path": match["path"], "startLine": match["line"]}],
            "remediation": "Prepare a human-reviewed synthetic remediation packet.",
            "provenance": {
                "source": "synthetic-local-adapter",
                "repositoryId": repository.repo_id,
                "revision": repository.commit_sha,
                "scanId": scan_id,
                "adapter": "synthetic-security-adapter/1.0",
                "productExecution": False,
            },
        }
