"""Owner-private, wholly synthetic helpers for independently authored stress tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import threading
import unittest


ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "cookbook" / "security-review-pipeline"


def _private_evidence_root() -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    """Keep optional test receipts outside the exact-manifest checkout."""

    configured = os.environ.get("GOVERNED_STRESS_EVIDENCE_DIR")
    temporary: tempfile.TemporaryDirectory[str] | None = None
    if configured:
        root = Path(configured).expanduser().absolute()
        if root.is_relative_to(ROOT) or root.resolve().is_relative_to(ROOT.resolve()):
            raise RuntimeError("stress evidence must remain outside the checkout")
        if not root.exists():
            root.mkdir(mode=0o700, parents=True)
    else:
        temporary = tempfile.TemporaryDirectory(prefix="governed-security-stress-")
        root = Path(temporary.name)
    if root.is_symlink() or not root.is_dir():
        raise RuntimeError("stress evidence must be a real owner-private directory")
    if root.resolve().is_relative_to(ROOT.resolve()):
        raise RuntimeError("stress evidence must not resolve into the checkout")
    details = root.stat()
    if details.st_uid != os.geteuid() or stat.S_IMODE(details.st_mode) != 0o700:
        raise RuntimeError("stress evidence must be owned by the current user with mode 0700")
    return root, temporary


EVIDENCE, _DEFAULT_PRIVATE_EVIDENCE = _private_evidence_root()
for candidate in (ROOT / "src", ROOT / "fleet-tests"):
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))

from fleet_security.recipe import RecurringSecurityRecipe


EXPECTED_STATES = {
    "awaiting_finding_disposition": 2,
    "awaiting_scope_approval": 1,
    "awaiting_threat_model_approval": 1,
    "failed_safe_abstention": 1,
    "review_packet_ready": 1,
}
LEDGER_LOCK = threading.Lock()


def append_container_receipt(test_id: str, *, kind: str, details: dict | None = None) -> None:
    """Persist one independently observed real container, never credentials."""
    record = {"test_id": test_id, "kind": kind, "details": details or {}}
    encoded = (json.dumps(record, sort_keys=True) + "\n").encode("utf-8")
    with LEDGER_LOCK:
        descriptor = os.open(
            EVIDENCE / "actual-container-receipts.jsonl",
            os.O_CREAT | os.O_APPEND | os.O_WRONLY | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        try:
            details = os.fstat(descriptor)
            if not stat.S_ISREG(details.st_mode) or details.st_uid != os.geteuid():
                raise RuntimeError("stress container receipts must be owner-private regular files")
            if stat.S_IMODE(details.st_mode) != 0o600:
                raise RuntimeError("stress container receipts must have mode 0600")
            os.write(descriptor, encoded)
        finally:
            os.close(descriptor)


class PrivateRecipeCase(unittest.TestCase):
    """Per-test synthetic config and signed state live wholly outside the checkout."""

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="private-stress-", dir=EVIDENCE)
        self.private_root = Path(self.temporary.name)
        self.private_root.chmod(0o700)
        self.config = self.private_root / "configuration.json"
        self.inventory = self.private_root / "inventory.json"
        self.approvals = self.private_root / "approvals.json"
        self.events = self.private_root / "events.jsonl"
        for label, destination in (("config", self.config), ("inventory", self.inventory), ("approvals", self.approvals)):
            destination.write_bytes((EXAMPLES / f"{label}.example.json").read_bytes())
            destination.chmod(0o600)
        self.state = self.private_root / "owner-private-state"
        self.now = 1_788_000_000
        self.addCleanup(self.temporary.cleanup)

    def read(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def save(self, path: Path, payload: dict) -> None:
        path.write_text(json.dumps(payload), encoding="utf-8")
        path.chmod(0o600)

    def cycle(self, *, docker: bool = False) -> dict:
        return RecurringSecurityRecipe.from_files(
            configuration_path=self.config,
            inventory_path=self.inventory,
            approvals_path=self.approvals,
            state_directory=self.state,
            docker=docker,
            clock=lambda: self.now,
        ).cycle()

    def repository(self, short_name: str) -> dict:
        return next(row for row in self.read(self.inventory)["repositories"] if row["repo_id"] == f"synthetic/{short_name}")

    def artifact(self, short_name: str, filename: str) -> Path:
        record = self.repository(short_name)
        return self.state / "evidence" / f"synthetic-{short_name}" / record["commit_sha"][:12] / filename

    def write_events(self, rows: list[dict | str]) -> Path:
        lines = [row if isinstance(row, str) else json.dumps(row, sort_keys=True) for row in rows]
        self.events.write_text("".join(f"{line}\n" for line in lines), encoding="utf-8")
        self.events.chmod(0o600)
        return self.events

    def event(self, short_name: str = "catalog-service", *, event_id: str = "event-001", event_type: str = "repository_changed") -> dict:
        record = self.repository(short_name)
        return {
            "event_id": event_id,
            "repository_id": record["repo_id"],
            "revision": record["commit_sha"],
            "event_type": event_type,
        }

    def assert_owner_private_tree(self, root: Path) -> None:
        self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
        for child in root.rglob("*"):
            self.assertFalse(child.is_symlink(), str(child))
            self.assertEqual(stat.S_IMODE(child.stat().st_mode), 0o700 if child.is_dir() else 0o600, str(child))
