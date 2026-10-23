"""All tests use fictional data and local SQLite; no paid or network calls."""

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest

from continuity import (
    Event, EventConflict, IntentConflict, MockTransport, NotFound,
    OwnershipLost, Poller, Scope, Store, fictional_events,
)


ROOT = Path(__file__).resolve().parent


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "jobs.sqlite3"
        self.store = Store(self.path)
        self.addCleanup(self.store.close)
        self.scope = Scope("fictional-tenant-a")
        self.job = self.store.start_or_attach(self.scope, "intent-17", "Investigate latency")
        self.job_id = self.job.investigation_id
        self.now = 100.0

    def lease(self, owner="voice-session-a", ttl=30):
        return self.store.claim(self.scope, self.job_id, owner, self.now, ttl)

    def source(self):
        self.store.ingest(self.scope, self.job_id, fictional_events())

    def test_duplicate_start_and_reconnect_do_not_create_another_job(self):
        retried = self.store.start_or_attach(self.scope, "intent-17", "Investigate latency")
        self.assertEqual(retried.investigation_id, self.job_id)
        for _ in range(4):
            self.assertEqual(self.store.attach(self.scope, self.job_id).investigation_id, self.job_id)
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 1)

    def test_reconnect_unknown_id_never_starts_a_job(self):
        with self.assertRaises(NotFound):
            self.store.attach(self.scope, "inv_nonexistent")
        self.assertEqual(self.store.db.execute("SELECT COUNT(*) FROM jobs").fetchone()[0], 1)

    def test_reused_intent_key_cannot_silently_change_work(self):
        with self.assertRaises(IntentConflict):
            self.store.start_or_attach(self.scope, "intent-17", "Different work")

    def test_new_intent_key_is_an_explicit_new_job(self):
        new = self.store.start_or_attach(self.scope, "intent-18", "Investigate latency")
        self.assertNotEqual(new.investigation_id, self.job_id)

    def test_concurrent_duplicate_starts_use_database_uniqueness(self):
        barrier = threading.Barrier(2)

        def start():
            store = Store(self.path)
            try:
                barrier.wait(timeout=5)
                return store.start_or_attach(self.scope, "concurrent-intent", "Same work").investigation_id
            finally:
                store.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(start) for _ in range(2)]
            ids = [f.result(timeout=10) for f in futures]
        self.assertEqual(ids[0], ids[1])

    def test_start_key_is_scoped_to_tenant(self):
        other = self.store.start_or_attach(Scope("fictional-tenant-b"), "intent-17", "Different work")
        self.assertNotEqual(other.investigation_id, self.job_id)

    def test_all_job_operations_enforce_tenant_scope(self):
        other = Scope("fictional-tenant-b")
        lease = self.lease()
        calls = [
            lambda: self.store.attach(other, self.job_id),
            lambda: self.store.ingest(other, self.job_id, fictional_events()),
            lambda: self.store.claim(other, self.job_id, "b", self.now),
            lambda: self.store.prepare_next(other, lease, self.now),
            lambda: self.store.acknowledge(other, lease, 1, self.now),
            lambda: self.store.renew(other, lease, self.now),
            lambda: self.store.disconnect(other, lease, self.now),
            lambda: self.store.deliveries(other, self.job_id),
            lambda: self.store.resume_status(other, self.job_id),
        ]
        for call in calls:
            with self.subTest(call=call), self.assertRaises(NotFound):
                call()

    def test_source_replay_is_deduplicated_and_delivered_in_order(self):
        self.source()
        self.source()
        self.store.ingest(self.scope, self.job_id, [fictional_events()[1]])
        sink = MockTransport()
        poller = Poller(self.store, self.scope, self.lease(), lambda: self.now)
        self.assertEqual([poller.once(sink) for _ in range(4)],
                         ["acknowledged", "acknowledged", "acknowledged", "idle"])
        self.assertEqual(sink.accepted, [f"{self.job_id}:{n}" for n in (1, 2, 3)])
        self.assertEqual(self.store.attach(self.scope, self.job_id).cursor, 3)

    def test_changed_replay_rejected(self):
        self.source()
        with self.assertRaises(EventConflict):
            self.store.ingest(self.scope, self.job_id, [Event(1, "progress", "Changed")])

    def test_source_gap_rolls_back_entire_batch(self):
        with self.assertRaises(EventConflict):
            self.store.ingest(self.scope, self.job_id, [Event(1, "progress", "First"),
                                                       Event(3, "finding", "Missing second")])
        self.assertIsNone(self.store.prepare_next(self.scope, self.lease(), self.now))
        self.assertEqual(self.store.attach(self.scope, self.job_id).cursor, 0)

    def test_source_reordering_rejected(self):
        with self.assertRaises(EventConflict):
            self.store.ingest(self.scope, self.job_id, [fictional_events()[1], fictional_events()[0]])

    def test_source_sequence_requires_a_strict_positive_integer(self):
        for sequence in [True, False, 1.0, "1", 0, -1]:
            with self.subTest(sequence=sequence), self.assertRaises(EventConflict):
                self.store.ingest(self.scope, self.job_id, [Event(sequence, "progress", "Invalid")])
        self.assertEqual(self.store.attach(self.scope, self.job_id).cursor, 0)

    def test_terminal_job_rejects_new_events_but_accepts_identical_replay(self):
        self.source()
        self.source()
        with self.assertRaises(EventConflict):
            self.store.ingest(self.scope, self.job_id, [Event(4, "progress", "Too late")])

    def test_single_current_owner_and_expired_owner_fencing(self):
        first = self.lease(ttl=5)
        self.assertEqual(self.lease(ttl=5), first)
        with self.assertRaises(OwnershipLost):
            self.lease("voice-session-b")
        self.now = 105
        second = self.lease("voice-session-b")
        self.assertGreater(second.fence, first.fence)
        for call in [lambda: self.store.prepare_next(self.scope, first, self.now),
                     lambda: self.store.renew(self.scope, first, self.now),
                     lambda: self.store.disconnect(self.scope, first, self.now),
                     lambda: self.store.acknowledge(self.scope, first, 1, self.now)]:
            with self.assertRaises(OwnershipLost):
                call()

    def test_concurrent_owner_claims_have_one_winner(self):
        barrier = threading.Barrier(2)

        def claim(owner):
            store = Store(self.path)
            try:
                barrier.wait(timeout=5)
                try:
                    store.claim(self.scope, self.job_id, owner, self.now)
                    return "won"
                except OwnershipLost:
                    return "lost"
            finally:
                store.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(claim, name) for name in ("a", "b")]
            self.assertCountEqual([f.result(timeout=10) for f in futures], ["won", "lost"])

    def test_owner_name_reuse_does_not_revive_stale_fence(self):
        first = self.lease(ttl=1)
        self.now += 1
        second = self.lease()
        self.assertGreater(second.fence, first.fence)
        with self.assertRaises(OwnershipLost):
            self.store.prepare_next(self.scope, first, self.now)

    def test_lease_renewal_and_expiry_boundary(self):
        lease = self.lease(ttl=2)
        self.store.renew(self.scope, lease, now=101, ttl=10)
        self.store.assert_owner(self.scope, lease, now=110.9)
        with self.assertRaises(OwnershipLost):
            self.store.assert_owner(self.scope, lease, now=111)

    def test_nonfinite_clock_rejected_at_all_ownership_seams(self):
        lease = self.lease()
        for now in [float("nan"), float("inf"), -float("inf"), True, "100"]:
            calls = [
                lambda: self.store.claim(self.scope, self.job_id, "new", now),
                lambda: self.store.assert_owner(self.scope, lease, now),
                lambda: self.store.renew(self.scope, lease, now),
                lambda: self.store.prepare_next(self.scope, lease, now),
                lambda: self.store.acknowledge(self.scope, lease, 1, now),
                lambda: self.store.disconnect(self.scope, lease, now),
            ]
            for call in calls:
                with self.subTest(now=now, call=call), self.assertRaises(ValueError):
                    call()
        self.store.assert_owner(self.scope, lease, self.now)

    def test_nonfinite_or_nonpositive_ttl_rejected(self):
        lease = self.lease()
        for ttl in [0, -1, True, "30", float("nan"), float("inf")]:
            for call in [lambda: self.store.claim(self.scope, self.job_id, "new", self.now, ttl),
                         lambda: self.store.renew(self.scope, lease, self.now, ttl)]:
                with self.subTest(ttl=ttl), self.assertRaises(ValueError):
                    call()
        for now, ttl in [(1e308, 1e308), (1e308, 1.0)]:
            with self.subTest(now=now, ttl=ttl), self.assertRaises(ValueError):
                self.store.claim(self.scope, self.job_id, "new", now, ttl)

    def test_cursor_and_job_survive_real_process_restart(self):
        self.source()
        lease = self.lease()
        self.assertEqual(Poller(self.store, self.scope, lease, lambda: self.now).once(MockTransport()),
                         "acknowledged")
        code = """
import sys
from continuity import Scope, Store
store = Store(sys.argv[1])
scope = Scope('fictional-tenant-a')
job = store.start_or_attach(scope, 'intent-17', 'Investigate latency')
assert job.investigation_id == sys.argv[2]
assert job.cursor == 1
assert store.deliveries(scope, job.investigation_id)[0].state == 'acknowledged'
lease = store.claim(scope, job.investigation_id, 'restarted-process', now=131)
assert store.prepare_next(scope, lease, now=131).event.sequence == 2
store.close()
"""
        result = subprocess.run([sys.executable, "-c", code, str(self.path), self.job_id],
                                cwd=ROOT, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_disconnect_before_or_after_emit_is_unknown_not_replayed(self):
        for mode, expected_receipts in [("before_emit", 0), ("after_emit", 1)]:
            with self.subTest(mode=mode):
                job = self.store.start_or_attach(self.scope, mode, "Test ambiguity")
                job_id = job.investigation_id
                self.store.ingest(self.scope, job_id, fictional_events())
                first = self.store.claim(self.scope, job_id, "first", self.now)
                sink = MockTransport(mode)
                self.assertEqual(Poller(self.store, self.scope, first, lambda: self.now).once(sink), "unknown")
                self.assertEqual(len(sink.accepted), expected_receipts)
                self.assertEqual(self.store.resume_status(self.scope, job_id)["uncertain_sequences"], [1])
                new = self.store.claim(self.scope, job_id, "reconnected", self.now)
                fresh_sink = MockTransport()
                Poller(self.store, self.scope, new, lambda: self.now).once(fresh_sink)
                self.assertEqual(fresh_sink.accepted, [f"{job_id}:2"])

    def test_crash_between_emit_and_ack_remains_unknown_after_takeover(self):
        self.source()
        lease = self.lease(ttl=1)
        sink = MockTransport("crash_after_emit")
        with self.assertRaisesRegex(RuntimeError, "Simulated process crash"):
            Poller(self.store, self.scope, lease, lambda: self.now).once(sink)
        self.assertEqual(sink.accepted, [f"{self.job_id}:1"])
        self.assertEqual(self.store.deliveries(self.scope, self.job_id)[0].state, "pending")
        self.assertEqual(self.store.resume_status(self.scope, self.job_id)["delivery_outcome"], "unknown")
        self.now += 1
        next_lease = self.lease("reconnected")
        self.assertEqual(self.store.deliveries(self.scope, self.job_id)[0].state, "unknown")
        next_sink = MockTransport()
        Poller(self.store, self.scope, next_lease, lambda: self.now).once(next_sink)
        self.assertEqual(next_sink.accepted, [f"{self.job_id}:2"])

    def test_crash_after_reservation_before_emit_is_also_unknown(self):
        self.source()
        self.store.prepare_next(self.scope, self.lease(ttl=1), self.now)
        self.now += 1
        new = self.lease("new")
        self.assertEqual(self.store.resume_status(self.scope, self.job_id)["uncertain_sequences"], [1])
        self.assertEqual(self.store.prepare_next(self.scope, new, self.now).event.sequence, 2)

    def test_one_inflight_update_and_no_ack_without_matching_attempt(self):
        self.source()
        lease = self.lease()
        self.store.prepare_next(self.scope, lease, self.now)
        with self.assertRaises(RuntimeError):
            self.store.prepare_next(self.scope, lease, self.now)
        with self.assertRaises(ValueError):
            self.store.acknowledge(self.scope, lease, 2, self.now)
        self.store.acknowledge(self.scope, lease, 1, self.now)
        with self.assertRaises(ValueError):
            self.store.acknowledge(self.scope, lease, 1, self.now)

    def test_late_old_owner_emission_is_not_prevented_by_database_fencing(self):
        # Deliberately documents the guarantee boundary rather than concealing it.
        self.source()
        reserved = self.store.prepare_next(self.scope, self.lease(ttl=1), self.now)
        self.now += 1
        self.lease("new")
        late_sink = MockTransport()
        late_sink.emit(reserved)
        self.assertEqual(len(late_sink.accepted), 1)
        self.assertEqual(self.store.resume_status(self.scope, self.job_id)["delivery_outcome"], "unknown")

    def test_read_only_reconnect_does_not_change_cursor_or_ownership(self):
        self.source()
        lease = self.lease()
        before = self.store.db.total_changes
        self.store.attach(self.scope, self.job_id)
        self.store.resume_status(self.scope, self.job_id)
        self.assertEqual(self.store.db.total_changes, before)
        self.store.assert_owner(self.scope, lease, self.now)


if __name__ == "__main__":
    unittest.main(verbosity=2)
