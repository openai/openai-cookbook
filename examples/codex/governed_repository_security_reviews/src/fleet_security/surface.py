"""Inert, documented Codex Security bulk-scan planning; never launches a CLI."""
from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from dataclasses import asdict, dataclass
from pathlib import PurePosixPath

from .inventory import Repository, stable_digest
from .threats import ThreatCatalogue


CSV_COLUMNS = ("id", "repository", "revision", "scope", "mode", "prompt")
# Inspected public release, not a claim that a scan or entitlement was verified.
CODEX_SECURITY_VERSION = "0.1.20"
CODEX_SECURITY_PACKAGE = f"@openai/codex-security@{CODEX_SECURITY_VERSION}"
CODEX_SECURITY_SOURCE_COMMIT = "59d026a0579af084b419cd7f33b8e1b867338ee8"
# The documented bulk --max-cost threshold is a per-repository estimate, not a
# hard aggregate campaign cap. Customer-owned admission controls remain mandatory.
UNSUPPORTED_BULK_FLAGS = frozenset({"--auth", "--max-time-hours", "--diff", "--head"})
_CAMPAIGN_ID = re.compile(r"[A-Za-z0-9._-]+\Z")
_MODEL_ID = re.compile(r"gpt-[a-z0-9][a-z0-9._-]{0,95}\Z")
_VERSION_OUTPUT = re.compile(
    r"(?:(?:codex-security(?: version)?|@openai/codex-security) )?v?"
    r"([0-9]+\.[0-9]+\.[0-9]+)\Z"
)
_OPTION_LINE = re.compile(r"^  (?P<flag>--[a-z][a-z0-9-]*)(?=\s|$)")
_EFFORTS = frozenset({"minimal", "low", "medium", "high", "xhigh", "max"})
_MAX_RECORDED_HELP_BYTES = 262_144
_REQUIRED_BULK_FLAGS = frozenset({
    "--output-dir", "--workers", "--max-attempts", "--knowledge-base",
    "--model", "--effort",
})
_VERIFIED_BULK_FLAGS = _REQUIRED_BULK_FLAGS | frozenset({
    "--mode", "--scan-prompt-file", "--validation-prompt-file",
    "--post-scan-prompt-file", "--provider", "--max-cost", "--plugin-path",
    "--python", "--codex",
})


@dataclass(frozen=True)
class RecordedCliHelp:
    """Untrusted recorded stdout, not evidence of the reader's installation.

    The tutorial ships recordings from an isolated help-only inspection. This
    type also accepts a reader's own recordings. Neither source proves model
    access, a successful scan, or permission to publish a change.
    """

    version_output: str
    bulk_help: str
    scan_help: str | None = None


@dataclass(frozen=True)
class ProductPreflight:
    """A syntactic compatibility receipt that never authorises execution."""

    status: str
    blockers: tuple[str, ...]
    observed_version: str | None
    selected_model: str | None
    selected_effort: str | None
    advertised_bulk_flags: tuple[str, ...]
    draft_pr_capability: str
    evidence_sha256: dict[str, str]
    per_attempt_max_cost_usd: float | None

    @property
    def compatible(self) -> bool:
        return self.status == "compatible_contract_only"

    def to_dict(self) -> dict[str, object]:
        receipt: dict[str, object] = asdict(self)
        receipt.update({
            "format": "codex-security-recorded-help-preflight/v1",
            "expected_package": CODEX_SECURITY_PACKAGE,
            "source_commit": CODEX_SECURITY_SOURCE_COMMIT,
            "evidence_kind": "recorded_version_and_help",
            "compatible": self.compatible,
            "current_installation_verified": False,
            "model_entitlement_verified": False,
            "real_scan_verified": False,
            "execution_authorised": False,
            "external_write_authorised": False,
            "review_route": "review_packet_only",
            "cost_semantics": "per_repository_attempt_estimate_may_overshoot",
            "hard_campaign_cap": False,
            "warnings": [
                "Recorded help does not prove a current installation or service entitlement.",
                "Model syntax and advertised effort are checked; model access is not checked.",
                "The native cost estimate is per repository attempt and in-flight requests may overshoot.",
                "Independent admission budgets and named human approvals remain mandatory.",
                "Draft PR support does not grant patch, push, PR, merge, or deployment authority.",
            ],
        })
        return receipt


def _recording_digest(text: object) -> str | None:
    if not isinstance(text, str) or not text or len(text) > _MAX_RECORDED_HELP_BYTES:
        return None
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError:
        return None
    if not encoded or len(encoded) > _MAX_RECORDED_HELP_BYTES:
        return None
    if any(ord(character) < 32 and character not in "\n\r\t" for character in text):
        return None
    return hashlib.sha256(encoded).hexdigest()


def _advertised_options(text: str, command: str) -> dict[str, str] | None:
    """Read declarations, never examples or instructions embedded in help."""

    lines = text.splitlines()
    if not lines or not lines[0].startswith(f"codex-security {command} "):
        return None
    if not any(line.startswith(f"Usage: codex-security {command} ") for line in lines):
        return None
    options: dict[str, str] = {}
    in_options = False
    for line in lines:
        if line == "Options:":
            if in_options:
                return None
            in_options = True
            continue
        if not in_options:
            continue
        if line and not line[0].isspace():
            break
        match = _OPTION_LINE.match(line)
        if match:
            flag = match.group("flag")
            if flag in options:
                return None
            options[flag] = line
    return options if in_options and options else None


def inspect_codex_security_capabilities(
    recording: RecordedCliHelp, *, model: str, effort: str,
    requested_bulk_flags: tuple[str, ...] = (),
    per_attempt_max_cost_usd: float | None = None,
    require_hard_campaign_cap: bool = False,
    require_draft_pr_authority: bool = False,
) -> ProductPreflight:
    """Fail closed against the pinned, help-inspected v0.1.20 contract.

    This pure function performs no file access, subprocess execution, network
    access, authentication or scan. A compatible receipt says only that the
    recorded declarations meet this recipe's requirements. Even a successful
    result leaves every real execution and external write unauthorised.
    """

    blockers: list[str] = []
    hashes: dict[str, str] = {}
    for name, value in (
        ("version", recording.version_output),
        ("bulk_help", recording.bulk_help),
        ("scan_help", recording.scan_help),
    ):
        if name == "scan_help" and value is None:
            continue
        digest = _recording_digest(value)
        if digest is None:
            blockers.append(f"invalid_{name}_recording")
        else:
            hashes[name] = digest

    version_match = (
        _VERSION_OUTPUT.fullmatch(recording.version_output.strip())
        if "version" in hashes else None
    )
    version = version_match.group(1) if version_match else None
    if version != CODEX_SECURITY_VERSION:
        blockers.append("package_version_mismatch_or_unreadable")

    bulk_options = (
        _advertised_options(recording.bulk_help, "bulk-scan")
        if "bulk_help" in hashes else None
    )
    if bulk_options is None:
        blockers.append("bulk_help_is_not_command_option_help")
    bulk_options = bulk_options or {}

    flags_valid = isinstance(requested_bulk_flags, tuple) and all(
        isinstance(flag, str) and flag in _VERIFIED_BULK_FLAGS
        for flag in requested_bulk_flags
    )
    if not flags_valid:
        blockers.append("requested_bulk_flag_is_not_in_verified_contract")
    requested = set(requested_bulk_flags) if flags_valid else set()
    required = _REQUIRED_BULK_FLAGS | requested
    if per_attempt_max_cost_usd is not None:
        required |= {"--max-cost"}
    if not required.issubset(bulk_options):
        blockers.append("required_bulk_flag_missing_from_recorded_help")

    model_valid = isinstance(model, str) and bool(_MODEL_ID.fullmatch(model))
    if not model_valid:
        blockers.append("explicit_safe_gpt_model_id_required")
    effort_valid = isinstance(effort, str) and effort in _EFFORTS
    effort_declaration = re.search(r"<([^>]+)>", bulk_options.get("--effort", ""))
    if not effort_valid or not effort_declaration or effort not in effort_declaration.group(1).split("|"):
        blockers.append("effort_not_in_verified_and_advertised_values")

    cost: float | None = None
    if per_attempt_max_cost_usd is not None:
        try:
            cost_value = float(per_attempt_max_cost_usd)
        except (ValueError, TypeError, OverflowError):
            cost_value = math.nan
        if (isinstance(per_attempt_max_cost_usd, bool)
            or not isinstance(per_attempt_max_cost_usd, (int, float))
            or not math.isfinite(cost_value) or cost_value <= 0):
            blockers.append("cost_estimate_must_be_positive_and_finite")
        else:
            cost = cost_value
    if not isinstance(require_hard_campaign_cap, bool) or require_hard_campaign_cap:
        blockers.append("native_estimate_is_not_a_hard_campaign_cap")
    if not isinstance(require_draft_pr_authority, bool) or require_draft_pr_authority:
        blockers.append("help_inspection_never_grants_draft_pr_authority")

    draft_pr_capability = "unverified"
    if recording.scan_help is not None:
        scan_options = (
            _advertised_options(recording.scan_help, "scan")
            if "scan_help" in hashes else None
        )
        if scan_options is None:
            blockers.append("scan_help_is_not_command_option_help")
        elif (
            version == CODEX_SECURITY_VERSION
            and {"--patch", "--create-pr"}.issubset(scan_options)
            and "draft" in scan_options["--create-pr"].casefold().split()
        ):
            draft_pr_capability = "advertised_for_scan_patch_only"

    return ProductPreflight(
        status="abstain" if blockers else "compatible_contract_only",
        blockers=tuple(dict.fromkeys(blockers)),
        observed_version=version,
        selected_model=model if model_valid else None,
        selected_effort=effort if effort_valid else None,
        advertised_bulk_flags=tuple(sorted(set(bulk_options) & _VERIFIED_BULK_FLAGS)),
        draft_pr_capability=draft_pr_capability,
        evidence_sha256=hashes,
        per_attempt_max_cost_usd=cost,
    )


@dataclass(frozen=True)
class NativeBulkCampaign:
    """A campaign shares knowledge-base files; repository deltas live in CSV prompts."""

    archetype: str
    rows: tuple[dict[str, str], ...]
    knowledge_base_paths: tuple[str, ...]
    workers: int = 4
    max_attempts: int = 3

    def __post_init__(self) -> None:
        if not self.rows or not 1 <= self.workers <= 32 or not 1 <= self.max_attempts <= 5:
            raise ValueError("native campaign rows, workers, or attempts are invalid")
        for row in self.rows:
            if tuple(row) != CSV_COLUMNS:
                raise ValueError("native bulk CSV must match its documented exact header")
            if not _CAMPAIGN_ID.fullmatch(row["id"]):
                raise ValueError("native bulk campaign identity allows only letters, digits, period, underscore, hyphen")
            if len(row["revision"]) not in {40, 64}:
                raise ValueError("native bulk campaign requires a full immutable 40/64-character revision")
            scope = row["scope"]
            if scope and (scope.startswith(("/", "~")) or ".." in scope.split("/") or "\\" in scope):
                raise ValueError("native bulk campaign scope must be empty or an approved repository-relative path")
        identifiers = [row["id"] for row in self.rows]
        if len(set(identifiers)) != len(identifiers):
            raise ValueError("native bulk campaign contains colliding canonical repository identifiers")

    def csv_text(self) -> str:
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(self.rows)
        return buffer.getvalue()

    @property
    def fingerprint(self) -> str:
        return stable_digest({
            "csv": self.csv_text(),
            "product_package": CODEX_SECURITY_PACKAGE,
            "archetype": self.archetype,
            "knowledge_base_paths": self.knowledge_base_paths,
            "workers": self.workers,
            "max_attempts": self.max_attempts,
        })

    def command(self, *, csv_path: str, output_dir: str) -> tuple[str, ...]:
        """Render an inspectable contract only. This project never invokes the command."""

        if not csv_path or not output_dir:
            raise ValueError("native campaign requires explicit CSV and output paths")
        arguments = [
            "npx", CODEX_SECURITY_PACKAGE, "bulk-scan", csv_path,
            "--output-dir", output_dir,
            "--workers", str(self.workers),
            "--max-attempts", str(self.max_attempts),
        ]
        for knowledge_base in self.knowledge_base_paths:
            arguments.extend(("--knowledge-base", knowledge_base))
        return tuple(arguments)


def group_native_campaigns(
    repositories: tuple[Repository, ...], catalogue: ThreatCatalogue,
    *, workers: int = 4, max_attempts: int = 3,
) -> tuple[NativeBulkCampaign, ...]:
    groups: dict[str, list[dict[str, str]]] = {}
    canonical_identities: dict[str, str] = {}
    for repository in repositories:
        assignment = catalogue.assign(repository)
        archetype = assignment.archetype_model_id
        if archetype is None:
            raise ValueError("hierarchical native campaigns require an archetype")
        identity = repository.repo_id.replace("/", "-")
        previous_identity = canonical_identities.get(identity)
        if previous_identity is not None and previous_identity != repository.repo_id:
            raise ValueError("native bulk campaign contains colliding canonical repository identifiers")
        canonical_identities[identity] = repository.repo_id
        groups.setdefault(archetype, []).append({
            "id": identity,
            "repository": repository.repo_id,
            "revision": repository.commit_sha,
            # Empty official scope means the whole authorised repository.
            "scope": "",
            "mode": "deep" if repository.risk_tier == "high" else "standard",
            # Trusted host-generated context, never README/tool instructions.
            "prompt": (
                f"Trusted per-repository threat delta: data={repository.data_class}; "
                f"authentication={repository.authentication}; "
                f"criticality={repository.criticality}; "
                f"effective_context_sha256={assignment.effective_model_hash}"
            ),
        })
    campaigns = []
    for archetype in sorted(groups):
        filename = archetype.replace(":", "-") + ".md"
        safe_path = PurePosixPath("/trusted/archetypes") / filename
        campaigns.append(NativeBulkCampaign(
            archetype=archetype,
            rows=tuple(groups[archetype]),
            knowledge_base_paths=("/trusted/organisation.md", str(safe_path)),
            workers=workers,
            max_attempts=max_attempts,
        ))
    return tuple(campaigns)


class CampaignResumeLedger:
    """Native campaign resume is valid only for identical pinned rows and shared context."""

    def __init__(self) -> None:
        self._campaigns: dict[str, str] = {}

    def admit(self, output_dir: str, campaign: NativeBulkCampaign) -> str:
        if not output_dir:
            raise ValueError("native campaign requires a stable output destination")
        previous = self._campaigns.get(output_dir)
        if previous is not None and previous != campaign.fingerprint:
            raise ValueError("native campaign CSV, revision, prompt, or context changed; use a new output campaign")
        self._campaigns[output_dir] = campaign.fingerprint
        return "resumed" if previous else "created"
