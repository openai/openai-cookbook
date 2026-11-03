"""Connect Blossom Store to GPT-Live over WebRTC and record the call."""

from __future__ import annotations

import asyncio
from array import array
from collections import deque
import copy
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import time

from .audio import AudioBuffer, Recorder
from .config import save

RATE = 24000
SAMPLES = 480
SILENCE = bytes(2 * SAMPLES)
LIVE_ENDPOINT = "https://api.openai.com/v1/live/sessions"


def rms(pcm):
    v = array("h", pcm)
    return math.sqrt(sum(x * x for x in v) / len(v)) if v else 0.0


def public_event(value):
    if isinstance(value, dict):
        if value.get("type") == "error" and isinstance(value.get("error"), dict):
            # Provider error text can echo submitted credentials or request data.
            value = {
                **value,
                "error": {
                    k: v
                    for k, v in value["error"].items()
                    if k in {"code", "type", "param", "event_id"}
                },
            }
        return {
            k: public_event(v)
            for k, v in value.items()
            if str(k).lower()
            not in {"authorization", "api_key", "client_secret", "access_token", "ice_pwd", "sdp"}
        }
    if isinstance(value, list):
        return [public_event(v) for v in value]
    return value


def rtc_session(start):
    if start.get("type") != "session.start" or "session" not in start:
        raise ValueError("A session.start configuration is required")
    session = copy.deepcopy(start["session"])
    audio = session.get("audio", {})
    audio.pop("format", None)
    return session


class Bundle:
    def __init__(self, directory, audio_source):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=False)
        self.directory.chmod(0o700)
        self.origin = time.monotonic()
        self.source = audio_source
        self.source_started = False
        self.source_error = None
        self.render_sizes = deque()
        self.receiver_bytes_played = 0
        self.recorder = Recorder()
        self.raw = bytearray()
        self.last_native_voiced_end = 0
        self.media_ms = 0
        self.adapter = None
        self.frames = (self.directory / "frames.jsonl").open("x")
        self.events = (self.directory / "events.jsonl").open("x")
        self.tool_rows = []
        self.requests = []
        self.finalized = False
        self.app_closed = False
        self.receipt = {
            "status": "starting",
            "transport": "webrtc",
            "case": "blossom-store",
            "session_started": False,
            "session_finalized": False,
            "model": "gpt-live-1",
            "voice": "marin",
            "input_mode": audio_source.mode,
            "playout_mode": "current_native_receiver_only",
            "human_listening": False,
        }
        self.source.output = AudioBuffer(on_render=self.render_sizes.append)

    def elapsed(self):
        return round((time.monotonic() - self.origin) * 1000, 3)

    def record(self, direction, event):
        safe = public_event(event)
        row = {
            "elapsed_ms": self.elapsed(),
            "media_ms": self.media_ms,
            "direction": direction,
            "event": safe,
        }
        self.events.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.events.flush()
        if safe.get("type") == "app.tool":
            self.tool_rows.append(row)
        return row

    def emit(self, event_type, **data):
        return self.record("application", {"type": event_type, **data})

    def enqueue(self, pcm):
        count = len(self.raw) // 2
        for i in range(0, len(pcm), len(SILENCE)):
            slot = pcm[i : i + len(SILENCE)]
            if rms(slot) > 120:
                self.last_native_voiced_end = count + (i + len(slot)) // 2
        self.raw.extend(pcm)
        self.source.output.append(pcm)

    @property
    def remaining_native_voice(self):
        # RTP keeps delivering silent frames. Count buffered samples only up to
        # the last decoded voiced block, not later packets of digital silence.
        return max(0, self.last_native_voiced_end - self.receiver_bytes_played // 2)

    async def source_frame(self):
        if not self.source_started:
            # WebRTC can request a packet before the data channel announces session.started.
            return self.paired_frame(SILENCE, SILENCE, 0)
        try:
            incoming, played = await self.source.read_frame()
            if len(incoming) != len(SILENCE) or len(played) != len(SILENCE):
                raise ValueError("The audio device must return a 20 ms mono PCM16 frame")
            # This count belongs to this exact device callback, even if capture ran ahead of RTP.
            size = self.render_sizes.popleft()
            self.receiver_bytes_played += size
            return self.paired_frame(incoming, played, size)
        except Exception as error:
            self.source_error = (
                error  # aiortc stops a broken sender internally; surface it to the call.
            )
            raise

    def paired_frame(self, incoming, played, size):
        self.recorder.append(incoming, played)
        elapsed = self.elapsed()
        self.frames.write(
            json.dumps(
                {
                    "slot": self.recorder.frame_count - 1,
                    "elapsed_ms": elapsed,
                    "media_ms": self.media_ms,
                    "input_rms": round(rms(incoming), 2),
                    "output_rms": round(rms(played), 2),
                    "receiver_bytes": size,
                    "queue_samples": (len(self.raw) - self.receiver_bytes_played) // 2,
                    "queued_samples_through_last_voice": self.remaining_native_voice,
                }
            )
            + "\n"
        )
        if self.adapter is not None and not self.finalized and not self.app_closed:
            self.adapter.frame(incoming, played, elapsed)
        self.media_ms += 20
        return incoming

    def finish(self):
        try:
            self.save_recording()
        finally:
            self.frames.close()
            self.events.close()

    def save_recording(self):
        self.recorder.save(self.directory)
        Recorder.save_mono(self.directory / "raw-receiver.wav", self.raw)
        self.receipt.update(
            self.recorder.receipt(),
            raw_receiver_samples=len(self.raw) // 2,
            receiver_queued_samples_at_close=(len(self.raw) - self.receiver_bytes_played) // 2,
        )
        save(self.directory / "tool-calls.json", self.tool_rows)
        save(self.directory / "model-requests.json", self.requests)
        save(self.directory / "receipt.json", self.receipt)


def create_mic(bundle):
    from aiortc import MediaStreamTrack
    from av import AudioFrame

    class ClockedMicrophone(MediaStreamTrack):
        kind = "audio"

        def __init__(self):
            super().__init__()
            self.sample = 0
            self.due = None

        async def recv(self):
            if self.due is None:
                self.due = time.monotonic()
            await asyncio.sleep(max(0, self.due - time.monotonic()))
            pcm = await bundle.source_frame()
            frame = AudioFrame(format="s16", layout="mono", samples=SAMPLES)
            frame.planes[0].update(pcm)
            frame.sample_rate, frame.pts, frame.time_base = RATE, self.sample, Fraction(1, RATE)
            self.sample += SAMPLES
            # No catch-up burst after a stalled observer or event loop.
            self.due = max(self.due + 0.02, time.monotonic())
            return frame

    return ClockedMicrophone()


async def receive_track(track, bundle):
    from av import AudioResampler
    from aiortc.mediastreams import MediaStreamError

    resampler = AudioResampler(format="s16", layout="mono", rate=RATE)
    try:
        while True:
            frame = await track.recv()
            for out in resampler.resample(frame):
                bundle.enqueue(bytes(out.planes[0])[: out.samples * 2])
    except MediaStreamError:
        for out in resampler.resample(None):
            bundle.enqueue(bytes(out.planes[0])[: out.samples * 2])


async def run(directory, *, api_key, duration, audio_source, adapter_factory, stop, on_ready):
    import aiohttp
    from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription

    bundle = Bundle(directory, audio_source)
    tasks = []
    peer = adapter = dc = None
    send_wire = None
    ready, closed = asyncio.Event(), asyncio.Event()
    queue = asyncio.Queue()
    read_task = None
    protocol_error = None
    headers = {"Authorization": "Bearer " + api_key}
    running_task = asyncio.current_task()

    async def stop_call():
        await stop.wait()
        running_task.cancel()

    async def send(event):
        if send_wire is None:
            raise RuntimeError("Data transport is not ready")
        await send_wire(event)
        bundle.record("sent", event)

    async def consume():
        nonlocal protocol_error
        pending_events = []
        while True:
            event = await queue.get()
            row = bundle.record("received", event)
            kind = event.get("type")
            if kind == "session.closed":
                bundle.finalized = True
                bundle.receipt.update(
                    session_finalized=True,
                    final_usage=event.get("usage"),
                    close_reason=event.get("reason"),
                )
                closed.set()
                return
            if kind == "error":
                protocol_error = (event.get("error") or {}).get("code") or "unclassified_api_error"
                continue
            if kind == "session.started":
                bundle.receipt.update(
                    session_started=True,
                    session_id=event["session"]["id"],
                    returned_model=event["session"].get("model"),
                )
                await adapter.opening(event["session"]["id"])
                if not bundle.app_closed:
                    audio_source.open()
                    bundle.source_started = True
                    if on_ready is not None:
                        on_ready()
                for older, receipt in pending_events:
                    adapter.observe(older, receipt["elapsed_ms"])
                pending_events.clear()
                ready.set()
                continue
            if not ready.is_set():
                pending_events.append((event, row))
            elif not bundle.finalized and not bundle.app_closed:
                adapter.observe(event, row["elapsed_ms"])

    async def watch(seconds, predicate):
        end = time.monotonic() + seconds
        while not predicate() and time.monotonic() < end:
            if protocol_error:
                raise RuntimeError("Live returned a protocol error")
            if bundle.source_error is not None:
                raise bundle.source_error
            if read_task.done():
                read_task.result()
                if not closed.is_set():
                    raise RuntimeError("Live receiver exited before graceful close")
                break
            for task in tasks:
                if task.done():
                    task.result()
            if peer is not None and peer.connectionState == "failed":
                raise RuntimeError("WebRTC peer connection failed")
            await asyncio.sleep(0.035)
        return predicate()

    async with aiohttp.ClientSession(
        headers=headers, trust_env=True, timeout=aiohttp.ClientTimeout(total=45)
    ) as http:
        stop_watcher = asyncio.create_task(stop_call()) if stop is not None else None
        try:
            adapter = adapter_factory(bundle, send, http)
            bundle.adapter = adapter
            start = adapter.start_event
            save(bundle.directory / "initial-state.json", adapter.snapshot())
            read_task = asyncio.create_task(consume())
            peer = RTCPeerConnection(RTCConfiguration(iceServers=[]))
            dc = peer.createDataChannel("oai-events")

            @dc.on("message")
            def message(data):
                queue.put_nowait(json.loads(data))

            @peer.on("track")
            def track(track):
                if track.kind == "audio":
                    tasks.append(asyncio.create_task(receive_track(track, bundle)))

            @peer.on("connectionstatechange")
            def connection_changed():
                if not bundle.events.closed:
                    bundle.record(
                        "transport", {"type": "transport.peer_state", "state": peer.connectionState}
                    )

            async def data_send(event):
                if dc.readyState != "open":
                    raise RuntimeError("WebRTC data channel is not open")
                dc.send(json.dumps(event))

            send_wire = data_send
            peer.addTrack(create_mic(bundle))
            await asyncio.wait_for(peer.setLocalDescription(await peer.createOffer()), 15)
            session = rtc_session(start)
            sdp = peer.localDescription.sdp
            # SDP contains ephemeral ICE credentials. Preserve configuration and a digest only.
            shape = {
                "session": session,
                "transport": {
                    "type": "webrtc",
                    "sdp_sha256": hashlib.sha256(sdp.encode()).hexdigest(),
                },
            }
            save(bundle.directory / "session-payload.json", shape)
            async with http.post(
                LIVE_ENDPOINT,
                headers=headers,
                json={"session": session, "transport": {"type": "webrtc", "sdp": sdp}},
            ) as res:
                bundle.receipt.update(
                    http_status=res.status, request_id=res.headers.get("x-request-id")
                )
                answer = await res.json()
                if res.status != 201:
                    bundle.receipt["http_error_code"] = (answer.get("error") or {}).get("code")
                    raise RuntimeError("Live did not return a WebRTC session")
            bundle.receipt["negotiated_session_id"] = answer["session"]["id"]
            if answer.get("transport", {}).get("type") != "webrtc":
                raise RuntimeError("Unexpected session transport")
            await peer.setRemoteDescription(
                RTCSessionDescription(sdp=answer["transport"]["sdp"], type="answer")
            )
            if not await watch(30, ready.is_set):
                raise TimeoutError("No session.started")
            bundle.receipt["status"] = "running"

            async def app_ticks():
                while not closed.is_set() and not bundle.app_closed:
                    await adapter.tick()
                    await asyncio.sleep(0.05)

            tasks.append(asyncio.create_task(app_ticks()))
            await watch(duration, closed.is_set)
            bundle.receipt["termination"] = "server_closed" if closed.is_set() else "duration_limit"
        except (Exception, asyncio.CancelledError) as error:
            if isinstance(error, asyncio.CancelledError) and stop is not None and stop.is_set():
                bundle.receipt["termination"] = "user_stop"
            else:
                bundle.receipt.update(
                    status="failed",
                    termination="error",
                    error_type=type(error).__name__,
                    protocol_error=protocol_error,
                )
            # Application-generated errors can be identified without saving arbitrary network messages.
            if isinstance(
                error,
                (RuntimeError, ValueError, TimeoutError, ImportError, AttributeError, TypeError),
            ):
                detail = str(error)
                bundle.receipt["error_detail"] = (
                    "redacted" if api_key in detail or "Bearer " in detail else detail[:300]
                )
        finally:
            if stop_watcher is not None:
                stop_watcher.cancel()
                tasks.append(stop_watcher)
            if adapter is not None:
                bundle.app_closed = True
                try:
                    state = adapter.snapshot()
                    save(bundle.directory / "final-state.json", state)
                except Exception as error:
                    bundle.receipt["final_snapshot_error"] = type(error).__name__
                finally:
                    try:
                        await adapter.close()
                    except Exception as error:
                        bundle.receipt["app_close_error"] = type(error).__name__
            if bundle.receipt["session_started"] and not closed.is_set():
                try:
                    await send({"type": "session.close", "event_id": "close"})
                    await asyncio.wait_for(closed.wait(), 15)
                except Exception as error:
                    bundle.receipt["close_error"] = type(error).__name__
            if peer is not None:
                try:
                    await peer.close()
                except Exception as error:
                    bundle.receipt["peer_close_error"] = type(error).__name__
            if bundle.source_started:
                try:
                    audio_source.close()
                except Exception as error:
                    bundle.receipt.update(status="failed", device_close_error=type(error).__name__)
            if read_task is not None:
                tasks.append(read_task)
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            if bundle.receipt["status"] != "failed":
                bundle.receipt["status"] = (
                    "complete" if bundle.receipt["session_finalized"] else "incomplete"
                )
                if any(
                    key in bundle.receipt
                    for key in ("final_snapshot_error", "app_close_error", "peer_close_error")
                ):
                    bundle.receipt["status"] = "failed"
            bundle.finish()
    return bundle.receipt
