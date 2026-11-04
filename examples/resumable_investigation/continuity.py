"""Offline application-job continuity, not a Realtime transport implementation.

SQLite coordinates this small single-host example. A persisted cursor means an
update was reserved for delivery, not that a human heard it. Ambiguous deliveries
are reported as unknown and are never automatically spoken again.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import math
from pathlib import Path
import sqlite3
from typing import Callable, Iterator, Protocol
import uuid


class NotFound(LookupError):
    """No investigation is visible within this authenticated tenant scope."""


class IntentConflict(ValueError):
    """An intent key was reused with different work."""


class EventConflict(ValueError):
    """An event was changed, reordered, or appended after completion."""


class OwnershipLost(RuntimeError):
    """The caller does not hold a current, unexpired polling lease."""


@dataclass(frozen=True)
class Scope:
    # A server must derive this from authentication, never trust a client header.
    tenant_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.tenant_id, str) or not self.tenant_id:
            raise ValueError("tenant_id is required")


@dataclass(frozen=True)
class Event:
    sequence: int
    kind: str
    text: str


@dataclass(frozen=True)
class Job:
    investigation_id: str
    prompt: str
    status: str
    cursor: int


@dataclass(frozen=True)
class Lease:
    investigation_id: str
    owner: str
    fence: int


@dataclass(frozen=True)
class Delivery:
    investigation_id: str
    event: Event
    state: str
    fence: int

    @property
    def delivery_id(self) -> str:
        return f"{self.investigation_id}:{self.event.sequence}"


class Sink(Protocol):
    def emit(self, delivery: Delivery) -> bool:
        """Return application receipt, NOT evidence that audio was heard."""


def _finite_time(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError(f"{name} must be a finite number")
    return float(value)


def _lease_deadline(now: float, ttl: float) -> float:
    now, ttl = _finite_time(now, "now"), _finite_time(ttl, "ttl")
    if ttl <= 0:
        raise ValueError("ttl must be positive")
    deadline = _finite_time(now + ttl, "lease deadline")
    if deadline <= now:
        raise ValueError("ttl must advance the lease deadline")
    return deadline


class Store:
    """A persistent local example; each process opens its own connection."""

    def __init__(self, path: str | Path) -> None:
        self.db = sqlite3.connect(str(path), isolation_level=None, timeout=5)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys = ON")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.db.close()
            raise ValueError("Unsupported database version; migration required")
        self.db.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                tenant TEXT NOT NULL,
                id TEXT NOT NULL,
                intent_key TEXT NOT NULL,
                prompt TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'running',
                cursor INTEGER NOT NULL DEFAULT 0 CHECK (cursor >= 0),
                owner TEXT,
                lease_until REAL NOT NULL DEFAULT 0,
                fence INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (tenant, id),
                UNIQUE (tenant, intent_key)
            );
            CREATE TABLE IF NOT EXISTS events (
                tenant TEXT NOT NULL,
                job_id TEXT NOT NULL,
                seq INTEGER NOT NULL CHECK (seq > 0),
                kind TEXT NOT NULL,
                text TEXT NOT NULL,
                PRIMARY KEY (tenant, job_id, seq),
                FOREIGN KEY (tenant, job_id) REFERENCES jobs (tenant, id)
            );
            CREATE TABLE IF NOT EXISTS deliveries (
                tenant TEXT NOT NULL,
                job_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                state TEXT NOT NULL CHECK (
                    state IN ('pending', 'acknowledged', 'unknown')
                ),
                fence INTEGER NOT NULL,
                PRIMARY KEY (tenant, job_id, seq),
                FOREIGN KEY (tenant, job_id, seq)
                    REFERENCES events (tenant, job_id, seq)
            );
            PRAGMA user_version = 1;
        """)

    def close(self) -> None:
        self.db.close()

    @contextmanager
    def _write(self) -> Iterator[None]:
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
        except BaseException:
            self.db.rollback()
            raise
        else:
            self.db.commit()

    def _job(self, scope: Scope, investigation_id: str) -> sqlite3.Row:
        row = self.db.execute(
            "SELECT * FROM jobs WHERE tenant = ? AND id = ?",
            (scope.tenant_id, investigation_id),
        ).fetchone()
        if row is None:
            raise NotFound("Investigation not found in this tenant")
        return row

    def attach(self, scope: Scope, investigation_id: str) -> Job:
        """Read only: reconnecting never starts or reruns an investigation."""
        row = self._job(scope, investigation_id)
        return Job(row["id"], row["prompt"], row["status"], row["cursor"])

    def start_or_attach(self, scope: Scope, intent_key: str, prompt: str) -> Job:
        """Retry the same explicit start with its original persisted intent key.

        The local INSERT is the entire mock start operation. This does NOT make
        an external provider's start call idempotent.
        """
        if not intent_key.strip() or not prompt.strip():
            raise ValueError("intent_key and prompt are required")
        with self._write():
            row = self.db.execute(
                "SELECT id, prompt FROM jobs WHERE tenant = ? AND intent_key = ?",
                (scope.tenant_id, intent_key),
            ).fetchone()
            if row is not None:
                if row["prompt"] != prompt:
                    raise IntentConflict("Reuse the intent key only for the same work")
                investigation_id = row["id"]
            else:
                investigation_id = "inv_" + uuid.uuid4().hex
                self.db.execute(
                    "INSERT INTO jobs (tenant, id, intent_key, prompt) VALUES (?, ?, ?, ?)",
                    (scope.tenant_id, investigation_id, intent_key, prompt),
                )
        return self.attach(scope, investigation_id)

    def ingest(self, scope: Scope, investigation_id: str, events: list[Event]) -> None:
        """Accept a contiguous stream; identical replay is harmless.

        The source sequence is scoped to this job and starts at 1. A gap must be
        recovered from the source, never silently skipped by advancing a cursor.
        """
        with self._write():
            job = self._job(scope, investigation_id)
            maximum = self.db.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM events WHERE tenant = ? AND job_id = ?",
                (scope.tenant_id, investigation_id),
            ).fetchone()[0]
            terminal = job["status"] == "completed"
            for event in events:
                if (type(event.sequence) is not int or event.sequence <= 0
                        or event.kind not in {"progress", "finding", "complete"}
                        or not isinstance(event.text, str)):
                    raise EventConflict("Invalid event sequence or kind")
                old = self.db.execute(
                    "SELECT kind, text FROM events WHERE tenant = ? AND job_id = ? AND seq = ?",
                    (scope.tenant_id, investigation_id, event.sequence),
                ).fetchone()
                if old is not None:
                    if (old["kind"], old["text"]) != (event.kind, event.text):
                        raise EventConflict("Replayed event has different content")
                    continue
                if terminal or event.sequence != maximum + 1:
                    raise EventConflict("Expected the next event of a nonterminal job")
                self.db.execute(
                    "INSERT INTO events VALUES (?, ?, ?, ?, ?)",
                    (scope.tenant_id, investigation_id, event.sequence, event.kind, event.text),
                )
                maximum = event.sequence
                terminal = event.kind == "complete"
            if terminal:
                self.db.execute(
                    "UPDATE jobs SET status = 'completed' WHERE tenant = ? AND id = ?",
                    (scope.tenant_id, investigation_id),
                )

    def claim(self, scope: Scope, investigation_id: str, owner: str,
              now: float, ttl: float = 30) -> Lease:
        """Only one unexpired owner is accepted by this SQLite store."""
        if not isinstance(owner, str) or not owner:
            raise ValueError("owner is required")
        deadline = _lease_deadline(now, ttl)
        with self._write():
            row = self._job(scope, investigation_id)
            if row["owner"] is not None and row["lease_until"] > now:
                if row["owner"] != owner:
                    raise OwnershipLost("Another polling owner is active")
                return Lease(investigation_id, owner, row["fence"])
            fence = row["fence"] + 1
            # A prior owner might have emitted before it crashed. Never assume
            # either delivery or non-delivery when no receipt was committed.
            self.db.execute(
                "UPDATE deliveries SET state = 'unknown' "
                "WHERE tenant = ? AND job_id = ? AND state = 'pending'",
                (scope.tenant_id, investigation_id),
            )
            self.db.execute(
                "UPDATE jobs SET owner = ?, lease_until = ?, fence = ? "
                "WHERE tenant = ? AND id = ?",
                (owner, deadline, fence, scope.tenant_id, investigation_id),
            )
            return Lease(investigation_id, owner, fence)

    def _assert_owner(self, scope: Scope, lease: Lease, now: float) -> sqlite3.Row:
        now = _finite_time(now, "now")
        row = self._job(scope, lease.investigation_id)
        if (row["owner"] != lease.owner or row["fence"] != lease.fence
                or row["lease_until"] <= now):
            raise OwnershipLost("Polling lease is stale or expired")
        return row

    def assert_owner(self, scope: Scope, lease: Lease, now: float) -> None:
        self._assert_owner(scope, lease, now)

    def renew(self, scope: Scope, lease: Lease, now: float, ttl: float = 30) -> None:
        deadline = _lease_deadline(now, ttl)
        with self._write():
            self._assert_owner(scope, lease, now)
            self.db.execute(
                "UPDATE jobs SET lease_until = ? WHERE tenant = ? AND id = ?",
                (deadline, scope.tenant_id, lease.investigation_id),
            )

    def prepare_next(self, scope: Scope, lease: Lease, now: float) -> Delivery | None:
        """Atomically reserve one event and checkpoint the consumed cursor.

        A process death immediately after this transaction can suppress an update
        that was never sent. Recovery exposes that uncertainty instead of making
        an exactly-once delivery claim. One in-flight update is permitted.
        """
        with self._write():
            job = self._assert_owner(scope, lease, now)
            pending = self.db.execute(
                "SELECT 1 FROM deliveries WHERE tenant = ? AND job_id = ? AND state = 'pending'",
                (scope.tenant_id, lease.investigation_id),
            ).fetchone()
            if pending:
                raise RuntimeError("Resolve or disconnect the in-flight delivery first")
            row = self.db.execute(
                "SELECT seq, kind, text FROM events WHERE tenant = ? AND job_id = ? "
                "AND seq > ? ORDER BY seq LIMIT 1",
                (scope.tenant_id, lease.investigation_id, job["cursor"]),
            ).fetchone()
            if row is None:
                return None
            self.db.execute(
                "INSERT INTO deliveries VALUES (?, ?, ?, 'pending', ?)",
                (scope.tenant_id, lease.investigation_id, row["seq"], lease.fence),
            )
            self.db.execute(
                "UPDATE jobs SET cursor = ? WHERE tenant = ? AND id = ?",
                (row["seq"], scope.tenant_id, lease.investigation_id),
            )
            return Delivery(lease.investigation_id,
                            Event(row["seq"], row["kind"], row["text"]),
                            "pending", lease.fence)

    def acknowledge(self, scope: Scope, lease: Lease, sequence: int, now: float) -> None:
        with self._write():
            self._assert_owner(scope, lease, now)
            changed = self.db.execute(
                "UPDATE deliveries SET state = 'acknowledged' WHERE tenant = ? "
                "AND job_id = ? AND seq = ? AND fence = ? AND state = 'pending'",
                (scope.tenant_id, lease.investigation_id, sequence, lease.fence),
            ).rowcount
            if changed != 1:
                raise ValueError("No matching pending delivery to acknowledge")

    def disconnect(self, scope: Scope, lease: Lease, now: float) -> None:
        with self._write():
            self._assert_owner(scope, lease, now)
            self.db.execute(
                "UPDATE deliveries SET state = 'unknown' WHERE tenant = ? "
                "AND job_id = ? AND state = 'pending'",
                (scope.tenant_id, lease.investigation_id),
            )
            self.db.execute(
                "UPDATE jobs SET owner = NULL, lease_until = 0, fence = fence + 1 "
                "WHERE tenant = ? AND id = ?",
                (scope.tenant_id, lease.investigation_id),
            )

    def deliveries(self, scope: Scope, investigation_id: str) -> list[Delivery]:
        self._job(scope, investigation_id)
        rows = self.db.execute(
            "SELECT e.seq, e.kind, e.text, d.state, d.fence FROM deliveries d "
            "JOIN events e ON (d.tenant = e.tenant AND d.job_id = e.job_id AND d.seq = e.seq) "
            "WHERE d.tenant = ? AND d.job_id = ? ORDER BY d.seq",
            (scope.tenant_id, investigation_id),
        ).fetchall()
        return [Delivery(investigation_id, Event(r["seq"], r["kind"], r["text"]),
                         r["state"], r["fence"]) for r in rows]

    def resume_status(self, scope: Scope, investigation_id: str) -> dict:
        """Read-only reconciliation, suitable for a reconnect status panel."""
        job = self.attach(scope, investigation_id)
        ambiguous = [d.event.sequence for d in self.deliveries(scope, investigation_id)
                     if d.state in {"pending", "unknown"}]
        return {
            "investigation_id": investigation_id,
            "job_status": job.status,
            "consumed_cursor": job.cursor,
            "delivery_outcome": "unknown" if ambiguous else "no_unacknowledged_attempts",
            "uncertain_sequences": ambiguous,
            "message": ("The investigation is still the same job. Delivery of the listed "
                        "updates is unknown; they will not be automatically spoken again."
                        if ambiguous else
                        "Attached to the same investigation. Application receipts are "
                        "not proof that a person heard the audio."),
        }


class Poller:
    def __init__(self, store: Store, scope: Scope, lease: Lease,
                 clock: Callable[[], float]) -> None:
        self.store, self.scope, self.lease, self.clock = store, scope, lease, clock

    def once(self, sink: Sink) -> str:
        delivery = self.store.prepare_next(self.scope, self.lease, self.clock())
        if delivery is None:
            return "idle"
        # This check narrows a race, but cannot fence an external audio sink.
        self.store.assert_owner(self.scope, self.lease, self.clock())
        try:
            received = sink.emit(delivery)
        except ConnectionError:
            received = False
        if not received:
            self.store.disconnect(self.scope, self.lease, self.clock())
            return "unknown"
        self.store.acknowledge(self.scope, self.lease, delivery.event.sequence, self.clock())
        return "acknowledged"


class MockTransport:
    """Fictional application sink. No audio, sockets, SDK, or model calls."""

    def __init__(self, fail: str | None = None) -> None:
        if fail not in {None, "before_emit", "after_emit", "crash_after_emit"}:
            raise ValueError("Unknown failure mode")
        self.fail = fail
        self.accepted: list[str] = []

    def emit(self, delivery: Delivery) -> bool:
        if self.fail == "before_emit":
            raise ConnectionError("Connection lost before mock receipt")
        self.accepted.append(delivery.delivery_id)
        if self.fail == "after_emit":
            raise ConnectionError("Mock receipt occurred but acknowledgment was lost")
        if self.fail == "crash_after_emit":
            raise RuntimeError("Simulated process crash after mock receipt, before DB ack")
        return True


def fictional_events() -> list[Event]:
    """A deterministic stand-in for a read-only investigation/model worker."""
    return [
        Event(1, "progress", "Reading fictional release and latency fixtures."),
        Event(2, "finding", "Fictional search latency rose after a cache was disabled."),
        Event(3, "complete", "Investigation complete: verify the fictional cache change."),
    ]
