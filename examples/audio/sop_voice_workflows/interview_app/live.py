"""Handle GPT-Live handoffs and transcript triggers for one interview."""

from __future__ import annotations

import asyncio
import base64
from array import array
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import time
from uuid import uuid4

import aiohttp

from voice.audio import Recorder
from voice.config import save
from .meaning import read_proposal, request, start_event
from .store import ATS
from .script import INTERPRET_FAILED
from .summary_capture import summary_captions
from .workflow import Interview, Step

LIVE_URL = "wss://api.openai.com/v1/live/sessions"


def rms(pcm):
    samples = array("h", pcm)[::8]
    return math.sqrt(sum(v * v for v in samples) / len(samples)) if samples else 0


def queued_voice_samples(output):
    """Samples through the last voiced block still waiting for local playback."""
    with output.lock:
        chunks = tuple(output.chunks)
    offset = 0
    last_voiced = 0
    for chunk in chunks:
        for start in range(0, len(chunk), 960):
            block = chunk[start : start + 960]
            offset += len(block) // 2
            if rms(block) > 120:
                last_voiced = offset
    return last_voiced


def prepare_interview(store, run_id, emit, *, voice="marin"):
    """Look up the first official line before creating the Live session."""
    opening = Interview(store, emit).opening(run_id)
    _, step = opening
    emit(
        "app.interview_seed",
        kind=step.kind,
        content=step.content,
        operation_id=opening[0]["source_event_id"] + "/initial",
    )
    return start_event(voice, opening=step.content), opening


@dataclass
class Turn:
    number: int
    start_ms: int
    last_voice: float
    last_delta: float
    speech_before: str
    summary_ready: bool
    preceding_step: str | None
    fragments: list = field(default_factory=list)
    labels: dict = field(default_factory=dict)
    owners: list = field(default_factory=list)
    closed: bool = False
    jobs: set = field(default_factory=set)
    backchannels: set = field(default_factory=set)
    done: str | None = None

    @property
    def source(self):
        return self.fragments[-1]["event_id"] if self.fragments else None

    @property
    def text(self):
        return "".join(e["delta"] for e in self.fragments).strip()


class Controller:
    def __init__(
        self,
        store,
        session_id,
        emit,
        send,
        interpret,
        *,
        before_delegation=None,
        after_interpret=None,
    ):
        self.store, self.session_id = store, session_id
        self.emit, self.send, self.interpret = emit, send, interpret
        self.before_delegation, self.after_interpret = before_delegation, after_interpret
        self.workflow = Interview(store, emit)
        self.turns, self.guidance, self.captions = [], [], []
        self.tasks, self.errors, self.delegations = set(), [], set()
        self.source_turns = {}
        self.media_ms, self.last_played_voice, self.now = 0, -1, 0
        self.stopping = False
        self.playout_loud = False
        self.context_acks = {}

    @property
    def current(self):
        return self.turns[-1] if self.turns else None

    def start(self, coro):
        task = asyncio.create_task(coro)
        self.tasks.add(task)

        def finished(t):
            self.tasks.discard(t)
            if not t.cancelled() and t.exception() is not None:
                self.errors.append(t.exception())

        task.add_done_callback(finished)

    def by_offset(self, offset):
        return next((t for t in reversed(self.turns) if offset >= t.start_ms - 120), None)

    async def opening(self, prepared=None):
        if prepared is None:
            scope, step = self.workflow.opening(self.session_id)
        else:
            lookup_scope, step = prepared
            scope = {
                **lookup_scope,
                "source_event_id": self.session_id + "/open",
                "seed_lookup_operation_id": lookup_scope["source_event_id"] + "/initial",
            }
            self.workflow.paused = step.kind in {"unknown", "lookup_unavailable"}
        await self.release(scope, step, None)

    async def release(self, scope, step, owner):
        if self.stopping:
            return
        if scope["turn"] and (
            self.current.number != scope["turn"] or scope["source_event_id"] != self.current.source
        ):
            self.emit("app.stale", reason="obsolete_guidance", **scope)
            return
        self.workflow.step = step
        sid = "step_" + str(len(self.guidance) + 1)
        row = {
            "step_id": sid,
            "kind": step.kind,
            "content": step.content,
            "revision": self.store.snapshot()["revision"],
            "turn": scope["turn"],
            "source_event_id": scope["source_event_id"],
            "release_elapsed_ms": self.now,
            "release_media_ms": self.media_ms,
            "delegation_id": owner,
        }
        if "seed_lookup_operation_id" in scope:
            row["seed_lookup_operation_id"] = scope["seed_lookup_operation_id"]
        if step.kind == "summary":
            row["caption_index_at_release"] = len(self.captions)
        self.guidance.append(row)
        self.emit("app.guidance", **row)
        await self.send(
            {
                "type": "session.commentary.append",
                "event_id": sid,
                "delegation_id": owner,
                "content": step.content,
            }
        )

    def summary_before_reply(self, step, start_ms, remaining_output_samples):
        ack = self.context_acks.get(step["step_id"])
        frames = summary_captions(self.captions, step["caption_index_at_release"], ack)
        speech = "".join(frame["delta"] for frame in frames)
        quiet_ms = start_ms - self.last_played_voice
        ready = (
            bool(speech.strip())
            and step["revision"] == self.store.snapshot()["revision"]
            and self.last_played_voice > step["release_media_ms"]
            and quiet_ms >= 600
            and remaining_output_samples == 0
        )
        evidence = {
            "step_id": step["step_id"],
            "revision": step["revision"],
            "context_ack_id": ack["event_id"] if ack else None,
            "context_end_session_ms": ack["end_ms"] if ack else None,
            "caption_event_ids": [frame["event_id"] for frame in frames],
            "quiet_receiver_ms": quiet_ms,
            "remaining_voiced_output_samples": remaining_output_samples,
        }
        return speech, ready, evidence

    def frame(self, incoming, played, now, *, remaining_output_samples=None):
        self.now = now
        start = self.media_ms
        self.media_ms += len(incoming) // 48
        input_rms, output_rms = rms(incoming), rms(played)
        if output_rms > 120:
            self.last_played_voice = self.media_ms
            if not self.playout_loud:
                self.emit(
                    "app.playout_started",
                    media_ms=start,
                    latest_guidance_id=self.guidance[-1]["step_id"] if self.guidance else None,
                )
                self.playout_loud = True
        elif self.playout_loud and self.media_ms - self.last_played_voice >= 400:
            self.emit(
                "app.playout_quiet",
                last_voiced_media_ms=self.last_played_voice,
                media_ms=self.media_ms,
                latest_guidance_id=self.guidance[-1]["step_id"] if self.guidance else None,
            )
            self.playout_loud = False
        t = self.current
        caller_started = input_rms > 120 and (t is None or t.closed)
        if input_rms > 120:
            if caller_started:
                prior = self.guidance[-1] if self.guidance else None
                speech = "".join(
                    x["delta"]
                    for x in self.captions
                    if prior and x["elapsed_ms"] >= prior["release_elapsed_ms"]
                )
                summary_ready = False
                summary_evidence = None
                if prior and prior["kind"] == "summary":
                    speech, summary_ready, summary_evidence = self.summary_before_reply(
                        prior, start, remaining_output_samples
                    )
                t = Turn(
                    len(self.turns) + 1,
                    start,
                    now,
                    now,
                    speech,
                    summary_ready,
                    prior["step_id"] if prior else None,
                )
                self.turns.append(t)
                self.emit(
                    "app.turn_started",
                    turn=t.number,
                    media_ms=start,
                    previous_step_id=t.preceding_step,
                    summary_playout_ready=summary_ready,
                    assistant_speech_before=speech,
                    summary_evidence=summary_evidence,
                    speech_provenance="live_output_captions",
                )
            t.last_voice = now
        elif t and not t.closed and now - t.last_voice >= 750:
            t.closed = True
            self.emit("app.turn_quiet", turn=t.number, media_ms=self.media_ms)
        self.tick(now)
        return input_rms, output_rms

    def observe(self, event, now):
        self.now = now
        kind = event["type"]
        if kind == "session.input_transcript.delta":
            t = self.by_offset(event["end_ms"])
            if t and event["event_id"] not in self.source_turns:
                t.fragments.append(event)
                t.last_delta = now
                self.source_turns[event["event_id"]] = t
                self.emit(
                    "app.transcript_bound",
                    turn=t.number,
                    source_event_id=event["event_id"],
                    start_ms=event.get("start_ms"),
                    end_ms=event.get("end_ms"),
                )
        elif kind == "session.output_transcript.delta":
            self.captions.append(dict(elapsed_ms=now, **event))
        elif (
            kind == "session.commentary.appended"
            and isinstance(event.get("end_ms"), int)
            and event.get("client_event_id")
        ):
            self.context_acks[event["client_event_id"]] = event
        elif (
            kind == "decision.event" and event.get("event", {}).get("type") == "decision.completed"
        ):
            sid = event.get("source_event_id")
            t = self.source_turns.get(sid)
            if t:
                t.labels[sid] = {
                    x["name"]: x.get("choice") for x in event["event"]["decision"]["answers"]
                }
        elif kind == "session.delegation.created" and event["delegation"].get("target") == "client":
            # Match the handoff to its caller before waiting for delivery.
            t = self.by_offset(event.get("offset_ms", -1))
            self.start(self.native(event, t))

    async def native(self, event, turn):
        owner = event["delegation"]["id"]
        if self.before_delegation:
            self.emit(
                "app.delivery_wait",
                delegation_id=owner,
                turn=turn.number if turn else None,
                event_id=event.get("event_id"),
            )
            await self.before_delegation(event)
            self.emit(
                "app.delivery_released",
                delegation_id=owner,
                turn=turn.number if turn else None,
                event_id=event.get("event_id"),
            )
        if self.stopping:
            return
        if owner in self.delegations:
            self.emit(
                "app.delegation_received",
                delegation_id=owner,
                turn=turn.number if turn else None,
                disposition="repeated_delegation",
            )
            self.emit(
                "app.duplicate",
                reason="repeated_delegation",
                delegation_id=owner,
                turn=turn.number if turn else None,
            )
            return
        self.delegations.add(owner)
        if not turn or turn is not self.current:
            self.emit(
                "app.delegation_received",
                delegation_id=owner,
                turn=turn.number if turn else None,
                disposition="old_or_unknown_delegation",
            )
            self.emit(
                "app.stale",
                reason="old_or_unknown_delegation",
                delegation_id=owner,
                turn=turn.number if turn else None,
            )
            return
        if turn.done or turn.jobs or turn.owners:
            self.emit(
                "app.delegation_received",
                delegation_id=owner,
                turn=turn.number,
                source_event_id=turn.source,
                disposition="turn_already_owned",
            )
            self.emit(
                "app.duplicate", reason="turn_already_owned", delegation_id=owner, turn=turn.number
            )
            return
        self.emit(
            "app.delegation_received", delegation_id=owner, turn=turn.number, disposition="claimed"
        )
        turn.owners.append(owner)
        self.tick(self.now)

    def tick(self, now):
        t = self.current
        if (
            self.stopping
            or not t
            or not t.closed
            or not t.text
            or t.source in t.jobs
            or t.done == t.source
        ):
            return
        if self.workflow.paused or self.store.snapshot()["status"] != "active":
            return
        quiet = now - max(t.last_voice, t.last_delta)
        if quiet < 1000:
            return
        labels = t.labels.get(t.source, {})
        if labels.get("needs_backend_v1") == "no" and not t.owners:
            if t.source in t.backchannels:
                return
            t.backchannels.add(t.source)
            self.emit(
                "app.backchannel",
                turn=t.number,
                source_event_id=t.source,
                labels=labels,
                origin="input_decisions",
            )
            return
        if (not t.owners or not labels) and quiet < 1800:
            return
        t.jobs.add(t.source)
        scope = {
            "turn": t.number,
            "source_event_id": t.source,
            "revision": self.store.snapshot()["revision"],
        }
        if t.owners:
            reason = "native_delegation"
        elif labels.get("needs_backend_v1") == "yes":
            reason = "decisions_recovery"
        else:
            reason = "settled_unclassified"
        self.emit(
            "app.route",
            reason=reason,
            quiet_ms=quiet,
            labels=labels,
            delegation_id=t.owners[0] if t.owners else None,
            **scope,
        )
        self.start(self.process(t, scope, labels))

    async def process(self, t, scope, labels):
        step = self.workflow.step
        evidence = {
            "completed_caller_contribution": t.text,
            "source": scope,
            "current_step": {"kind": step.kind, "content": step.content} if step else None,
            "state": self.store.snapshot(),
            "unresolved_field": self.workflow.pending_field,
            "pending_conditions": self.store.pending_conditions(),
            "prior_caller_contributions": [
                other.text for other in self.turns if other.number < t.number
            ],
            "assistant_speech_before_this_caller_started": t.speech_before,
            "summary_playout_ready": t.summary_ready,
            "input_decisions": labels,
            "assistant_speech_provenance": "live_output_captions",
        }
        intent = await self.interpret(evidence)
        if self.after_interpret:
            self.emit("app.proposal_wait", intent=intent, **scope)
            await self.after_interpret(scope, intent)
            self.emit("app.proposal_released", intent=intent, **scope)
        # A correction may have arrived while the interpreter was running.
        if (
            self.stopping
            or self.current is not t
            or t.source != scope["source_event_id"]
            or self.store.snapshot()["revision"] != scope["revision"]
        ):
            self.emit("app.stale", reason="scope_changed_while_interpreting", **scope)
            return
        t.done = t.source
        if intent is None:
            self.workflow.paused = True
            result = Step("interpret_unavailable", INTERPRET_FAILED)
        else:
            self.emit("app.interpret", intent=intent, **scope)
            if intent["action"] == "backchannel":
                self.emit("app.backchannel", origin="interpreter", **scope)
            result = self.workflow.apply(
                scope,
                intent,
                t.labels.get(t.source, {}).get("condition_v1"),
                t.summary_ready,
                caller_text=t.text,
            )
        if result:
            await self.release(scope, result, t.owners[0] if t.owners else None)

    async def stop(self):
        self.stopping = True
        pending = list(self.tasks)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)


async def run_interview(
    source,
    directory,
    *,
    api_key,
    duration=120,
    stop=None,
    store=None,
    on_event=None,
    before_delegation=None,
    after_interpret=None,
    voice="marin",
):
    """Run one interview. on_event receives timestamped events without raw audio."""
    if not api_key or duration <= 0:
        raise ValueError("An existing API key and a positive duration are required")
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    directory.chmod(0o700)
    own_store = store is None
    store = store if store is not None else ATS(directory / "interview.sqlite")
    stop = stop or asyncio.Event()
    initial = store.snapshot()
    save(directory / "initial-state.json", initial)
    origin = time.monotonic()
    recorder = Recorder()
    received_pcm = bytearray()
    tool_rows, transcript, frames, requests = [], [], [], []
    receipt = {
        "status": "starting",
        "session_started": False,
        "session_finalized": False,
        "playout_mode": "live_output",
        "input_mode": source.mode,
        "model": "gpt-live-1",
        "voice": voice,
        "human_listening": False,
    }

    def elapsed():
        return round((time.monotonic() - origin) * 1000, 3)

    ledger = (directory / "events.jsonl").open("x")

    def record(direction, event):
        clean = event.copy()
        if event["type"] in {"session.input_audio.append", "session.output_audio.delta"}:
            key = "audio" if event["type"] == "session.input_audio.append" else "delta"
            clean["audio_bytes"] = len(base64.b64decode(clean.pop(key)))
        if event["type"] == "error":
            error = event.get("error", {})
            clean["error"] = {
                key: error.get(key) for key in ("code", "type", "param", "client_event_id")
            }
        row = {"elapsed_ms": elapsed(), "direction": direction, "event": clean}
        ledger.write(json.dumps(row, ensure_ascii=False) + "\n")
        if clean["type"] not in {"session.input_audio.append", "session.output_audio.delta"}:
            ledger.flush()
        if on_event:
            on_event(row)
        return row

    def emit(event_type, **values):
        row = record("application", {"type": event_type, **values})
        if event_type == "app.tool":
            tool_rows.append({"elapsed_ms": row["elapsed_ms"], **values})

    payload, opening = prepare_interview(store, uuid4().hex, emit, voice=voice)
    save(directory / "session-payload.json", payload)
    headers = {"Authorization": "Bearer " + api_key}
    controller = None
    ws = http = receiver = None
    opened = False
    closed = asyncio.Event()
    try:
        http = aiohttp.ClientSession(
            trust_env=True, timeout=aiohttp.ClientTimeout(total=None, sock_connect=15)
        )
        ws = await http.ws_connect(
            LIVE_URL, headers=headers, heartbeat=20, max_msg_size=4 * 1024 * 1024
        )

        async def send(event):
            await asyncio.wait_for(ws.send_json(event), 10)
            record("sent", event)

        async def interpret(evidence):
            body = request(evidence)
            row = {"request": body, "started_ms": elapsed()}
            requests.append(row)
            try:
                async with http.post(
                    "https://api.openai.com/v1/responses",
                    headers=headers,
                    json=body,
                    timeout=aiohttp.ClientTimeout(total=45),
                ) as res:
                    row.update(request_id=res.headers.get("x-request-id"), http_status=res.status)
                    if res.status != 200:
                        row["error_code"] = (await res.json()).get("error", {}).get("code")
                        return None
                    result = await res.json()
                row.update(response=result, finished_ms=elapsed())
                emit(
                    "app.model_result",
                    model=result.get("model"),
                    response_id=result.get("id"),
                    request_id=row["request_id"],
                    usage=result.get("usage"),
                    source=evidence["source"],
                )
                return read_proposal(result)
            except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
                row["error_type"] = type(exc).__name__
                return None

        await send(payload)
        msg = await ws.receive_json(timeout=20)
        record("received", msg)
        if msg.get("type") != "session.started":
            raise RuntimeError("Live session did not start")
        receipt.update(
            session_started=True,
            session_id=msg["session"]["id"],
            returned_model=msg["session"].get("model"),
        )
        controller = Controller(
            store,
            receipt["session_id"],
            emit,
            send,
            interpret,
            before_delegation=before_delegation,
            after_interpret=after_interpret,
        )

        async def receive():
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    raise RuntimeError("Live connection ended before final receipt")
                e = json.loads(msg.data)
                row = record("received", e)
                if e["type"] == "session.closed":
                    receipt.update(session_finalized=True, final_usage=e.get("usage"))
                    closed.set()
                    return
                if e["type"] == "error":
                    raise RuntimeError("Live returned an error, recorded in events.jsonl")
                if e["type"] == "session.output_audio.delta":
                    pcm = base64.b64decode(e["delta"], validate=True)
                    received_pcm.extend(pcm)
                    source.output.append(pcm)
                if e["type"] in {
                    "session.input_transcript.delta",
                    "session.output_transcript.delta",
                }:
                    transcript.append(row)
                controller.observe(e, row["elapsed_ms"])
            if not closed.is_set():
                raise RuntimeError("Live connection closed without session.closed")

        source.open()
        opened = True
        receiver = asyncio.create_task(receive())
        await controller.opening(opening)
        endpoint = time.monotonic() + duration
        while time.monotonic() < endpoint and not stop.is_set():
            if receiver.done():
                receiver.result()
                break
            if controller.errors:
                raise controller.errors[0]
            incoming, played = await asyncio.wait_for(source.read_frame(), 5)
            now = elapsed()
            recorder.append(incoming, played)
            pending = queued_voice_samples(source.output)
            input_rms, output_rms = controller.frame(
                incoming, played, now, remaining_output_samples=pending
            )
            frames.append(
                {
                    "slot": recorder.frame_count - 1,
                    "elapsed_ms": now,
                    "media_ms": controller.media_ms,
                    "input_rms": round(input_rms, 2),
                    "output_rms": round(output_rms, 2),
                }
            )
            await send(
                {"type": "session.input_audio.append", "audio": base64.b64encode(incoming).decode()}
            )
        receipt["termination"] = (
            "source_stop" if stop.is_set() else ("server_closed" if closed.is_set() else "duration")
        )
    except asyncio.CancelledError:
        receipt.update(termination="cancelled", error_type="CancelledError")
        raise
    except Exception as exc:
        receipt["termination"] = "error"
        receipt["error_type"] = type(exc).__name__
        receipt["error"] = (
            str(exc) if isinstance(exc, RuntimeError) else "Session did not finish normally"
        )
    finally:
        if controller:
            emit(
                "app.capture_end",
                reason=receipt.get("termination"),
                media_ms=controller.media_ms,
                last_voiced_output_ms=controller.last_played_voice,
                output_buffer_bytes=source.output.buffered_bytes,
            )
            await controller.stop()
        if opened:
            try:
                source.close()
            except Exception as exc:
                receipt["source_close_error"] = type(exc).__name__
        if ws and receipt["session_started"] and not receipt["session_finalized"]:
            try:
                await send({"type": "session.close", "event_id": "close"})
                if receiver and not receiver.done():
                    await asyncio.wait_for(asyncio.shield(receiver), 15)
                elif not closed.is_set():
                    async with asyncio.timeout(15):
                        while not closed.is_set():
                            event = await ws.receive_json()
                            record("received", event)
                            if event["type"] == "session.closed":
                                closed.set()
                                receipt.update(
                                    session_finalized=True, final_usage=event.get("usage")
                                )
            except Exception as exc:
                receipt["close_error"] = type(exc).__name__
        if receiver:
            receiver.cancel()
            await asyncio.gather(receiver, return_exceptions=True)
        if ws:
            await ws.close()
        if http:
            await http.close()
        recorder.save(directory)
        Recorder.save_mono(directory / "received-output.wav", bytes(received_pcm))
        save(directory / "transcript.json", transcript)
        save(directory / "tool-executions.json", tool_rows)
        save(directory / "final-state.json", store.snapshot())
        save(directory / "guidance.json", controller.guidance if controller else [])
        save(directory / "media-clock.json", frames)
        save(directory / "model-requests.json", requests)
        receipt.update(recorder.receipt(), received_output_samples=len(received_pcm) // 2)
        receipt["status"] = (
            "collected"
            if receipt["session_finalized"]
            and recorder.frame_count
            and not any(k in receipt for k in ("error_type", "close_error", "source_close_error"))
            else "incomplete"
        )
        save(directory / "receipt.json", receipt)
        ledger.close()
        if own_store:
            store.close()
    return receipt
