"""Fault injection at participant I/O; runner, client controller, and batch stay real."""

from __future__ import annotations

import asyncio
import base64
import json
import socket
import time
import wave

import pytest

from assistants.client.delegation import ClientDelegationController
from assistants.errors import LiveResponseError
from assistants.resources import assistant_resources
from run_harness import evaluate
from run_harness.evaluate import DEFAULT_DATA_JSON, load_run_scenarios, parse_args, run_evals
from run_harness.simulation import gpt_live
from run_harness.simulation.gpt_live_participants import SimulatorControlTools
from run_harness.simulation.gpt_live_runner import DualGptLiveRunner

WORK_GRACE = 0.025
CLEANUP_TIMEOUT = 0.035
WATCHDOG = 1.0
SPEECH = (1800).to_bytes(2, byteorder="little", signed=True) * 480


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Shutdown fault tests must never open a network connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)


class StalledBackend:
    """Actual client delegation work that never completes without cancellation."""

    def __init__(self):
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()
        self.closed = asyncio.Event()

    async def run(self, handoff, emit):
        self.started.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled.set()

    async def close(self):
        self.closed.set()


class FaultParticipant:
    """Transport-only peer; optional real client controller and injected hangs."""

    def __init__(self, role, *, backend=None, stubborn_wait=False, stubborn_close=False):
        self.agent_id = f"offline-shutdown-{role}"
        self.role = role
        self.events = asyncio.Queue()
        self.close_started = asyncio.Event()
        self.closed = asyncio.Event()
        self.wait_started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancellation_seen = asyncio.Event()
        self.stubborn_wait = stubborn_wait
        self.stubborn_close = stubborn_close
        self.operations = set()
        self.backend = backend
        self.controller = (
            ClientDelegationController(backend=backend, send_live=self.events.put, emit=self.events.put)
            if backend is not None
            else None
        )

    async def start(self):
        if self.controller is not None:
            event = {"type": "session.delegation.created", "delegation": {"id": "stalled", "target": "client"}}
            await self.events.put(event)
            await self.controller.observe(event)
            await self.backend.started.wait()

    async def trigger_opening(self, text):
        await self.events.put({"type": "session.output_audio.delta", "delta": base64.b64encode(SPEECH).decode()})

    async def send_audio(self, pcm):
        pass

    async def incoming(self):
        while (event := await self.events.get()) is not None:
            yield event

    async def _ignore_cancellation_until_released(self):
        task = asyncio.current_task()
        self.operations.add(task)
        try:
            while not self.release.is_set():
                try:
                    await self.release.wait()
                except asyncio.CancelledError:
                    self.cancellation_seen.set()
        finally:
            self.operations.discard(task)

    async def wait_for_tools(self):
        self.wait_started.set()
        if self.stubborn_wait:
            await self._ignore_cancellation_until_released()
        if self.controller is not None:
            await self.controller.wait()

    async def close(self):
        self.close_started.set()
        if self.stubborn_close:
            await self._ignore_cancellation_until_released()
        if self.controller is not None:
            await self.controller.close()
        await self.events.put({"type": "session.closed", "reason": "client_request", "usage": {"seconds": 0.02}})
        await self.events.put(None)
        self.closed.set()


def runner_for(caller, assistant, *, tmp_path=None):
    scenario = load_run_scenarios(DEFAULT_DATA_JSON, max_examples=1)[0]
    resources = assistant_resources()
    executor = resources.create_executor(scenario.application.initial_state, resources.load_facts())
    runner = DualGptLiveRunner(
        scenario,
        caller=caller,
        assistant=assistant,
        caller_tools=SimulatorControlTools(),
        application_tools=executor,
        offline=True,
        real_time=False,
        tick_ms=20,
        max_duration_s=0.02,
        save_conversations=tmp_path,
        event_log_path=tmp_path / "events.jsonl" if tmp_path else None,
        debug_artifacts=tmp_path is not None,
    )
    # Assign after construction so the old runner reaches the real hang in the red run,
    # rather than failing only because a new constructor keyword does not exist yet.
    runner.work_grace_seconds = WORK_GRACE
    runner.cleanup_timeout_seconds = CLEANUP_TIMEOUT
    return runner


async def release_faults(task, peers):
    for peer in peers:
        peer.release.set()
    if not task.done():
        task.cancel()
    outstanding = {task, *(operation for peer in peers for operation in peer.operations)}
    done, pending = await asyncio.wait(outstanding, timeout=WATCHDOG)
    for completed in done:
        if not completed.cancelled():
            completed.exception()
    assert not pending, "Fault fixture failed to release its test-owned tasks"


async def bounded_run(runner, peers):
    task = asyncio.create_task(runner.run())
    try:
        done, _ = await asyncio.wait({task}, timeout=WATCHDOG)
        assert task in done, "Runner exceeded watchdog; pending work or cleanup is unbounded"
        return task.result()
    finally:
        await release_faults(task, peers)


@pytest.mark.asyncio
async def test_actual_client_controller_stall_has_finite_work_grace(tmp_path):
    backend = StalledBackend()
    caller = FaultParticipant("caller")
    assistant = FaultParticipant("assistant", backend=backend)
    runner = runner_for(caller, assistant, tmp_path=tmp_path)

    with pytest.raises(LiveResponseError) as error:
        await bounded_run(runner, [caller, assistant])

    assert error.value.failure_stage == "pending_work_timeout"
    assert backend.started.is_set() and backend.cancelled.is_set() and backend.closed.is_set()
    assert caller.closed.is_set() and assistant.closed.is_set()
    assert runner.event_log is not None and runner.event_log.closed
    assert runner.recorder.user, "The fixture must have captured speech before the stall"
    assert any(tmp_path.rglob("*.wav")), "A failed run must retain its captured audio"


@pytest.mark.asyncio
async def test_cancellation_resistant_work_wait_cannot_defeat_deadline():
    caller = FaultParticipant("caller")
    assistant = FaultParticipant("assistant", stubborn_wait=True)
    runner = runner_for(caller, assistant)

    with pytest.raises(LiveResponseError) as error:
        await bounded_run(runner, [caller, assistant])

    assert error.value.failure_stage == "pending_work_timeout"
    assert assistant.cancellation_seen.is_set()
    assert caller.closed.is_set() and assistant.closed.is_set()
    assert "assistant_pending_work" in error.value.partial_result.run_metadata["cleanup"]["unfinished_tasks"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stuck_role", ["caller", "assistant"])
async def test_one_stuck_close_does_not_block_other_close(stuck_role):
    caller = FaultParticipant("caller", stubborn_close=stuck_role == "caller")
    assistant = FaultParticipant("assistant", stubborn_close=stuck_role == "assistant")
    stuck, healthy = (caller, assistant) if stuck_role == "caller" else (assistant, caller)
    runner = runner_for(caller, assistant)
    task = asyncio.create_task(runner.run())
    try:
        done, _ = await asyncio.wait({task}, timeout=WATCHDOG)
        assert task in done, "A cancellation-resistant close exceeded the harness cleanup deadline"
        with pytest.raises(LiveResponseError) as error:
            task.result()
        assert error.value.failure_stage == "cleanup_timeout"
        assert healthy.closed.is_set(), "Both closes must be attempted independently"
        assert stuck.close_started.is_set() and stuck.cancellation_seen.is_set()
        assert not stuck.release.is_set(), "The test must not release the fault before checking the deadline"
        cleanup = error.value.partial_result.run_metadata["cleanup"]
        assert cleanup["status"] == "timed_out"
        assert f"{stuck_role}_close" in cleanup["unfinished_tasks"]
    finally:
        await release_faults(task, [caller, assistant])


@pytest.mark.asyncio
async def test_external_cancellation_still_closes_both_participants():
    backend = StalledBackend()
    caller = FaultParticipant("caller")
    assistant = FaultParticipant("assistant", backend=backend)
    runner = runner_for(caller, assistant)
    runner.work_grace_seconds = 20
    task = asyncio.create_task(runner.run())
    try:
        await asyncio.wait_for(assistant.wait_started.wait(), timeout=WATCHDOG)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=WATCHDOG)
        assert task in done, "External cancellation must not wait for the pending-work grace"
        with pytest.raises(asyncio.CancelledError):
            task.result()
        assert caller.closed.is_set() and assistant.closed.is_set()
        assert backend.cancelled.is_set() and backend.closed.is_set()
    finally:
        await release_faults(task, [caller, assistant])


@pytest.mark.asyncio
async def test_work_timeout_remains_primary_when_cleanup_also_times_out():
    backend = StalledBackend()
    caller = FaultParticipant("caller", stubborn_close=True)
    assistant = FaultParticipant("assistant", backend=backend)
    runner = runner_for(caller, assistant)

    with pytest.raises(LiveResponseError) as error:
        await bounded_run(runner, [caller, assistant])

    assert error.value.failure_stage == "pending_work_timeout"
    assert assistant.closed.is_set() and backend.closed.is_set()
    assert caller.cancellation_seen.is_set()


@pytest.mark.asyncio
async def test_all_resistant_components_share_one_cleanup_budget():
    caller = FaultParticipant("caller", stubborn_wait=True, stubborn_close=True)
    assistant = FaultParticipant("assistant", stubborn_wait=True, stubborn_close=True)
    runner = runner_for(caller, assistant)
    runner.cleanup_timeout_seconds = 0.15
    observer_task = asyncio.create_task(caller._ignore_cancellation_until_released())
    await asyncio.sleep(0)
    runner._completion_task = observer_task
    started = time.monotonic()

    with pytest.raises(LiveResponseError) as error:
        await bounded_run(runner, [caller, assistant])

    elapsed = time.monotonic() - started
    assert error.value.failure_stage == "pending_work_timeout"
    assert caller.close_started.is_set() and assistant.close_started.is_set()
    cleanup = error.value.partial_result.run_metadata["cleanup"]
    assert set(cleanup["unfinished_tasks"]) >= {
        "caller_pending_work",
        "assistant_pending_work",
        "completion_observer",
        "caller_close",
        "assistant_close",
    }
    # One 150 ms budget, plus work grace and 100 ms for scheduler/test overhead.
    # Separate 150 ms budgets per component would exceed this by a wide margin.
    assert elapsed < WORK_GRACE + runner.cleanup_timeout_seconds + 0.1


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["event_drain", "monitor_close"])
async def test_cleanup_errors_preserve_work_timeout_and_close_remaining_resources(tmp_path, monkeypatch, fault):
    class ProbeMonitor:
        closed = False

        def start(self):
            pass

        def push(self, *args, **kwargs):
            pass

        def close(self):
            self.closed = True
            if fault == "monitor_close":
                raise RuntimeError("Injected monitor close failure")

    backend = StalledBackend()
    caller = FaultParticipant("caller")
    assistant = FaultParticipant("assistant", backend=backend)
    runner = runner_for(caller, assistant, tmp_path=tmp_path)
    runner.monitor = ProbeMonitor()
    real_drain = runner._drain_events

    async def fail_only_during_cleanup():
        if fault == "event_drain" and runner._shutting_down:
            raise RuntimeError("Injected cleanup event drain failure")
        await real_drain()

    monkeypatch.setattr(runner, "_drain_events", fail_only_during_cleanup)
    with pytest.raises(LiveResponseError) as error:
        await bounded_run(runner, [caller, assistant])

    assert error.value.failure_stage == "pending_work_timeout"
    assert caller.closed.is_set() and assistant.closed.is_set() and backend.closed.is_set()
    assert runner.monitor.closed
    assert runner.event_log is not None and runner.event_log.closed
    expected_component = "event_drain" if fault == "event_drain" else "monitor"
    cleanup_errors = error.value.partial_result.run_metadata["cleanup"]["errors"]
    assert any(item["component"] == expected_component for item in cleanup_errors)
    assert any(tmp_path.rglob("*.wav")), "Secondary cleanup errors must not discard captured evidence"


@pytest.mark.asyncio
async def test_external_cancellation_is_not_replaced_by_cleanup_timeout():
    backend = StalledBackend()
    caller = FaultParticipant("caller", stubborn_close=True)
    assistant = FaultParticipant("assistant", backend=backend)
    runner = runner_for(caller, assistant)
    runner.work_grace_seconds = 20
    task = asyncio.create_task(runner.run())
    try:
        await asyncio.wait_for(assistant.wait_started.wait(), timeout=WATCHDOG)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=WATCHDOG)
        assert task in done, "Cancellation must not wait indefinitely for a resistant close"
        with pytest.raises(asyncio.CancelledError):
            task.result()
        assert assistant.closed.is_set() and backend.closed.is_set()
        assert caller.cancellation_seen.is_set()
    finally:
        await release_faults(task, [caller, assistant])


@pytest.mark.asyncio
async def test_repeated_external_cancellation_still_allows_healthy_closes():
    class DelayedClose(FaultParticipant):
        async def close(self):
            self.close_started.set()
            await asyncio.sleep(0.03)
            await super().close()

    backend = StalledBackend()
    caller = DelayedClose("caller")
    assistant = DelayedClose("assistant", backend=backend)
    runner = runner_for(caller, assistant)
    runner.work_grace_seconds = 20
    runner.cleanup_timeout_seconds = 0.2
    task = asyncio.create_task(runner.run())
    try:
        await asyncio.wait_for(assistant.wait_started.wait(), timeout=WATCHDOG)
        task.cancel()
        await asyncio.wait_for(caller.close_started.wait(), timeout=WATCHDOG)
        await asyncio.sleep(0.005)
        task.cancel()
        done, _ = await asyncio.wait({task}, timeout=WATCHDOG)
        assert task in done
        with pytest.raises(asyncio.CancelledError):
            task.result()
        assert caller.closed.is_set() and assistant.closed.is_set(), "Repeated cancellation interrupted healthy cleanup"
        assert backend.cancelled.is_set() and backend.closed.is_set()
    finally:
        await release_faults(task, [caller, assistant])


@pytest.mark.asyncio
async def test_completion_observer_cancellation_is_inside_cleanup_budget():
    caller = FaultParticipant("caller")
    assistant = FaultParticipant("assistant")
    runner = runner_for(caller, assistant)
    observer_task = asyncio.create_task(caller._ignore_cancellation_until_released())
    await asyncio.sleep(0)
    runner._completion_task = observer_task

    with pytest.raises(LiveResponseError) as error:
        await bounded_run(runner, [caller, assistant])

    assert error.value.failure_stage == "cleanup_timeout"
    assert caller.cancellation_seen.is_set()
    assert caller.closed.is_set() and assistant.closed.is_set()
    assert observer_task.done(), "Test fixture must release the resistant observer afterward"
    assert "completion_observer" in error.value.partial_result.run_metadata["cleanup"]["unfinished_tasks"]


@pytest.mark.asyncio
async def test_receiver_pump_is_inside_cleanup_budget_and_late_evidence_is_sealed(tmp_path):
    class StubbornReceiver(FaultParticipant):
        async def incoming(self):
            async for event in super().incoming():
                yield event
            await self._ignore_cancellation_until_released()
            yield {"type": "error", "error": {"code": "late_failure", "message": "After the result was returned"}}
            yield {"type": "session.output_audio.delta", "delta": base64.b64encode(SPEECH).decode()}

    caller = FaultParticipant("caller")
    assistant = StubbornReceiver("assistant")
    runner = runner_for(caller, assistant, tmp_path=tmp_path)
    task = asyncio.create_task(runner.run())
    try:
        done, _ = await asyncio.wait({task}, timeout=WATCHDOG)
        assert task in done, "A receiver must not outlive the harness cleanup deadline"
        with pytest.raises(LiveResponseError) as error:
            task.result()
        assert error.value.failure_stage == "cleanup_timeout"
        result = error.value.partial_result
        assert "assistant_receiver" in result.run_metadata["cleanup"]["unfinished_tasks"]
        assert caller.closed.is_set() and assistant.closed.is_set()
        assert assistant.cancellation_seen.is_set()
        saved_result = json.dumps(result.model_dump(), sort_keys=True)
        saved_files = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
        evidence_version = runner.timeline.version
        queued_events = runner.events.qsize()
        failure = runner.failure

        assistant.release.set()
        await asyncio.wait_for(asyncio.gather(*runner._pumps, return_exceptions=True), timeout=WATCHDOG)

        assert json.dumps(result.model_dump(), sort_keys=True) == saved_result
        assert {path: path.read_bytes() for path in saved_files} == saved_files
        assert runner.timeline.version == evidence_version
        assert runner.events.qsize() == queued_events
        assert runner.failure is failure
    finally:
        await release_faults(task, [caller, assistant])


@pytest.mark.asyncio
async def test_work_finishing_within_grace_is_not_an_infrastructure_failure():
    class BriefWork(FaultParticipant):
        async def wait_for_tools(self):
            await asyncio.sleep(0.005)

    caller = FaultParticipant("caller")
    assistant = BriefWork("assistant")
    result = await bounded_run(runner_for(caller, assistant), [caller, assistant])

    assert result.termination_reason == "duration_limit"
    assert caller.closed.is_set() and assistant.closed.is_set()


@pytest.mark.asyncio
@pytest.mark.parametrize("fault", ["stalled_backend", "stubborn_close"])
async def test_failed_first_case_retains_evidence_and_releases_batch_slot(tmp_path, monkeypatch, fault):
    peers = []
    backends = []
    graded_scenarios = []
    real_grade_procedure = evaluate.grade_procedure

    def record_grade(scenario, *args, **kwargs):
        graded_scenarios.append(scenario.id)
        return real_grade_procedure(scenario, *args, **kwargs)

    def caller_factory(*args, **kwargs):
        peer = FaultParticipant("caller")
        peers.append(peer)
        return peer

    def assistant_factory(*args, **kwargs):
        first_case = not backends
        backend = StalledBackend() if first_case and fault == "stalled_backend" else None
        backends.append(backend)
        peer = FaultParticipant("assistant", backend=backend, stubborn_close=first_case and fault == "stubborn_close")
        peers.append(peer)
        return peer

    # Only transport participants are substituted: settings, runner, controller,
    # semaphore, deterministic grading, artifact persistence, and report are real.
    monkeypatch.setattr(gpt_live, "OfflineCallerParticipant", caller_factory)
    monkeypatch.setattr(gpt_live, "OfflineRestaurantParticipant", assistant_factory)
    monkeypatch.setattr(evaluate, "grade_procedure", record_grade)
    args = parse_args(
        [
            "--offline",
            "--no-judge",
            "--max-examples",
            "2",
            "--concurrency",
            "1",
            "--tick-ms",
            "20",
            "--max-duration-seconds",
            "0.02",
            "--debug-artifacts",
            "--results-dir",
            str(tmp_path),
        ]
    )
    args.work_grace_seconds = WORK_GRACE
    args.cleanup_timeout_seconds = CLEANUP_TIMEOUT
    task = asyncio.create_task(run_evals(args))
    try:
        done, _ = await asyncio.wait({task}, timeout=WATCHDOG)
        assert task in done, "A failed first scenario held the sole batch slot forever"
        run_dir = task.result()
        report = json.loads((run_dir / "results.json").read_text())
        first, second = report["results"]
        assert first["status"] == "infrastructure_error"
        assert first["error"]["stage"] == ("pending_work_timeout" if fault == "stalled_backend" else "cleanup_timeout")
        assert second["status"] != "infrastructure_error"
        assert len(peers) == 4
        assert all(peer.closed.is_set() for peer in peers if not peer.stubborn_close)
        assert graded_scenarios == [second["scenario_id"]], "The infrastructure failure must bypass target grading"
        assert report["summary"]["total"] == 2
        assert report["summary"]["infrastructure_errors"] == 1
        assert report["summary"]["passed"] + report["summary"]["failed"] == 1
        assert first["artifacts"], "The failure row must link retained evidence"
        referenced = [run_dir / value for value in first["artifacts"].values() if isinstance(value, str)]
        assert all(path.is_file() for path in referenced)
        recordings = [path for path in referenced if path.suffix == ".wav"]
        assert recordings, "Captured speech must remain reachable from the failed result"
        with wave.open(str(recordings[0]), "rb") as recording:
            assert recording.getnframes() > 0
    finally:
        await release_faults(task, peers)
