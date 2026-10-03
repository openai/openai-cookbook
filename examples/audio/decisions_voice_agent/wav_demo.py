"""One supplied WAV through GPT Live, Luna, and local read-only MCP tools.

Checking is offline. --run opts into one paid Live attempt and at most one paid
router request. No TTS, transcription judge, reconnect, or automatic retry runs.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
import sys
import time
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# Also support Python safe-path mode and direct execution from another directory.
sys.path.insert(0, str(Path(__file__).resolve().parent))

SAMPLE_RATE = 24_000
MAX_INPUT_SECONDS = 20
WORK_SECONDS = 45
CLEANUP_SECONDS = 10
MAX_OUTPUT_BYTES = SAMPLE_RATE * 2 * (WORK_SECONDS + CLEANUP_SECONDS)
MAX_TRACE_BYTES = 8 * 1024 * 1024
LIVE_MODEL = "gpt-live-1"
LIVE_ENDPOINT = "https://api.openai.com/v1/live/sessions"
FRONTEND_PROMPT = (
    "You are a concise spoken support assistant for a synthetic shop. "
    "Delegate every user request to the application, including unclear or unsupported requests. "
    "Do not answer from memory or invent order or policy facts. "
    "When the application returns its answer, speak it once, directly and briefly. "
    "Do not add filler, a checking announcement, or a closing offer."
)


class InputError(ValueError):
    """Controlled validation text, safe to show before provider construction."""


def read_input(path: Path) -> bytes:
    """Check allocation bounds before loading exact, uncompressed PCM16 frames."""
    if path.stat().st_size > MAX_INPUT_SECONDS * SAMPLE_RATE * 2 + 64 * 1024:
        raise InputError("Input WAV exceeds the bounded file size")
    try:
        with wave.open(str(path), "rb") as recording:
            if (
                recording.getnchannels() != 1
                or recording.getsampwidth() != 2
                or recording.getframerate() != SAMPLE_RATE
                or recording.getcomptype() != "NONE"
            ):
                raise InputError("Input must be uncompressed 24,000 Hz mono PCM16 WAV")
            frames = recording.getnframes()
            if not 0 < frames <= MAX_INPUT_SECONDS * SAMPLE_RATE:
                raise InputError("Input WAV must be nonempty and at most 20 seconds long")
            pcm = recording.readframes(frames)
            if len(pcm) != frames * 2:
                raise InputError("Input WAV contains truncated PCM frames")
    except (wave.Error, EOFError) as error:
        raise InputError("Invalid PCM WAV") from error
    return pcm


def explicit_config():
    from assistants.config import LiveAgentSettings

    return LiveAgentSettings.model_validate(
        {
            "endpoint": LIVE_ENDPOINT,
            "model": LIVE_MODEL,
            "voice": "marin",
            "assistant_mode": "client",
            "client_endpoint": "",
            "backend_model": "gpt-6-luna",
            "backend_reasoning_effort": "none",
            "backend_max_output_tokens": 64,
            "backend_verbosity": "low",
        },
        context={"load_environment": False},
    )


def plan(input_path: Path, output_dir: Path) -> tuple[bytes, dict[str, Any]]:
    """No credential read, provider client construction, or output creation."""
    pcm = read_input(input_path)
    if output_dir.exists() or output_dir.is_symlink():
        raise InputError("Output directory must not already exist; preserve earlier attempts")
    from assistants.frontend.bounded import check_transport_support

    from mcp_tools import (
        MCPExecutor,  # noqa: F401 - fail before admission if optional dependencies are missing
    )

    check_transport_support()
    explicit_config()
    return pcm, {
        "status": "checked",
        "input_seconds": len(pcm) / (2 * SAMPLE_RATE),
        "input_pcm_sha256": hashlib.sha256(pcm).hexdigest(),
        "max_live_attempts": 1,
        "max_router_requests": 1,
        "max_mcp_calls": 1,
        "work_seconds": WORK_SECONDS,
        "cleanup_seconds": CLEANUP_SECONDS,
        "output_directory": str(output_dir),
    }


class Capture:
    """Bounded, private evidence and exact received PCM, including partial audio."""

    def __init__(self, stream):
        self.stream = stream
        self.started_at = time.monotonic()
        self.index = {"value": 0}
        self.bytes_written = 0
        self.audio = bytearray()

    def write(self, text: str) -> int:
        size = len(text.encode("utf-8"))
        if self.bytes_written + size > MAX_TRACE_BYTES:
            raise ValueError("Trace byte limit reached")
        self.bytes_written += size
        return self.stream.write(text)

    def flush(self) -> None:
        self.stream.flush()

    def observe(self, event: dict[str, Any], direction: str) -> None:
        from shared.observability.trace import record_event

        event = dict(event)
        if direction == "server_to_client" and event.get("type") == "session.output_audio.delta":
            encoded = event.get("delta")
            if not isinstance(encoded, str) or len(encoded) > (MAX_OUTPUT_BYTES * 4 // 3 + 4):
                raise ValueError("Output audio exceeds the byte limit")
            pcm = base64.b64decode(encoded, validate=True)
            if len(pcm) % 2 or len(self.audio) + len(pcm) > MAX_OUTPUT_BYTES:
                raise ValueError("Invalid or oversized output PCM")
            self.audio.extend(pcm)
            event["pcm_bytes"] = len(pcm)
            event["pcm_sha256"] = hashlib.sha256(pcm).hexdigest()
        record_event(
            self,
            event,
            started_at=self.started_at,
            event_index_state=self.index,
            source="live_transport",
            direction=direction,
        )


class RouteReceipt:
    def __init__(self):
        self.data: dict[str, Any] = {"attempted": False, "usage_known": False}

    def dispatch(self) -> None:
        if self.data["attempted"]:
            raise RuntimeError("The single router request was already attempted")
        self.data["attempted"] = True

    def response(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        counts = {name: getattr(usage, name, None) for name in ("input_tokens", "output_tokens")}
        self.data.update(
            response_id=getattr(response, "id", None),
            model=getattr(response, "model", None),
            status=getattr(response, "status", None),
            usage=counts,
            usage_known=all(type(value) is int and value >= 0 for value in counts.values()),
        )


def owned_router(api_key: str, receipt: RouteReceipt):
    from openai import AsyncOpenAI

    from luna_router import LunaRouter

    class OwnedRouter(LunaRouter):
        def __init__(self):
            self.owner = AsyncOpenAI(api_key=api_key, max_retries=0, timeout=5)
            super().__init__(
                self.owner,
                complete_history=True,
                on_request=receipt.dispatch,
                on_response=receipt.response,
            )

        async def close(self):
            await self.owner.close()

    return OwnedRouter()


async def run_once(
    pcm: bytes,
    output_dir: Path,
    api_key: str,
    *,
    router_factory=owned_router,
    assistant_factory=None,
    executor_factory=None,
) -> dict[str, Any]:
    """Dependency injection is for offline tests; the CLI always uses real adapters."""
    from assistants.client.assistant import ClientDelegatedAssistant
    from shared.audio.pcm import write_mono_wav
    from shared.observability.trace import sanitize_trace_value
    from shared.private_files import private_directory, private_open, private_write_text
    from shared.single_turn.runtime import (
        CallerAudioCompletion,
        collect_live_response,
        stream_audio_to_connection,
    )

    from mcp_tools import MCPExecutor
    from voice_service import SupersedingController, SupportBackend

    private_directory(output_dir, exist_ok=False)
    route = RouteReceipt()
    executor = (executor_factory or MCPExecutor)()
    router = backend = assistant = None

    async def execute(name, arguments, call_id):
        return await executor.execute(name, arguments, call_id=call_id)

    settings = SimpleNamespace(
        agent_instructions=FRONTEND_PROMPT, backend_instructions="", delegation_tools=[]
    )
    failures: list[str] = []
    response: dict[str, Any] = {}
    with private_open(output_dir / "events.jsonl", "x") as stream:
        capture = Capture(stream)
        try:
            async with asyncio.timeout(WORK_SECONDS):
                router = router_factory(api_key, route)
                backend = SupportBackend(router, execute, owned_executor=executor)
                assistant = (assistant_factory or ClientDelegatedAssistant)(
                    scenario=object(),
                    settings=settings,
                    api_key=api_key,
                    config=explicit_config(),
                    backend=backend,
                    tool_executor=executor,
                    controller_factory=SupersedingController,
                    max_pending=1,
                    max_delegations=1,
                    work_timeout=15,
                    bounded=True,
                    raw_observer=capture.observe,
                )
                await assistant.start()
                completion = CallerAudioCompletion()
                async with asyncio.TaskGroup() as group:
                    group.create_task(
                        stream_audio_to_connection(
                            assistant,
                            pcm,
                            20,
                            SAMPLE_RATE,
                            True,
                            log_file=capture,
                            started_at=capture.started_at,
                            event_index_state=capture.index,
                            caller_audio_completion=completion,
                        )
                    )
                    collected = group.create_task(
                        collect_live_response(
                            assistant,
                            capture,
                            chunk_ms=20,
                            sample_rate_hz=SAMPLE_RATE,
                            timeout_seconds=WORK_SECONDS,
                            trace_started_at=capture.started_at,
                            event_index_state=capture.index,
                            tool_observer=executor,
                            caller_audio_completion=completion,
                            tool_source="mcp_stdio",
                        )
                    )
                response = collected.result()
        except (Exception, asyncio.CancelledError) as error:
            failures.append(type(error).__name__)
        finally:
            # Ownership exists before the next constructor can fail. One cleanup
            # deadline covers every owner, including a failed assistant setup.
            deadline = asyncio.get_running_loop().time() + CLEANUP_SECONDS
            owners = [assistant] if assistant else [backend] if backend else [executor, router]
            for owner in owners:
                if owner is None:
                    continue
                try:
                    async with asyncio.timeout_at(deadline):
                        await owner.close()
                except (Exception, asyncio.CancelledError) as error:
                    failures.append(f"cleanup:{type(error).__name__}")

    audio = bytes(capture.audio)
    if audio:
        write_mono_wav(output_dir / "output.wav", audio, SAMPLE_RATE)
    final_known = assistant is not None and assistant.finalization_confirmed
    route_unknown = route.data["attempted"] and not route.data["usage_known"]
    cleanup_errors = getattr(assistant, "cleanup_errors", [])
    transport_closed = getattr(assistant, "transport_closed", True)
    if not audio:
        failures.append("NoOutputAudio")
    if not response:
        failures.append("NoCompletedResponse")
    if not route.data["attempted"]:
        failures.append("MissingDelegation")
    if route.data.get("model") not in {None, "gpt-6-luna"}:
        failures.append("UnexpectedRouterModel")
    status = (
        "unknown"
        if (assistant is not None and not final_known) or route_unknown
        else ("failed" if failures or cleanup_errors or not transport_closed else "completed")
    )
    result = {
        "status": status,
        "errors": failures,
        "tool_transport": "mcp_stdio",
        "input_pcm_sha256": hashlib.sha256(pcm).hexdigest(),
        "input_seconds": len(pcm) / (SAMPLE_RATE * 2),
        "output_audio_bytes": len(audio),
        "output_pcm_sha256": hashlib.sha256(audio).hexdigest(),
        "live": {
            "model": LIVE_MODEL,
            "start_sent": getattr(assistant, "start_sent", False),
            "started": getattr(assistant, "start_event", None),
            "closed": getattr(assistant, "final_event", None),
            "usage_known": final_known,
        },
        "route": route.data,
        "tool_executions": executor.executions,
        "application_state": executor.snapshot(),
        "assistant_text": response.get("assistant_text", ""),
        "cleanup": {
            "errors": cleanup_errors,
            "warnings": getattr(assistant, "cleanup_warnings", []),
            "transport_closed": transport_closed,
        },
        "transport_observations": getattr(assistant, "transport_observations", {}),
        "retry_policy": "one attempt; SDK and HTTP retries disabled; no reconnect",
        "device_playback_verified": False,
    }
    private_write_text(
        output_dir / "result.json", json.dumps(sanitize_trace_value(result), indent=2) + "\n"
    )
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Supplied 24 kHz mono PCM16 WAV, at most 20 seconds",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        required=True,
        help="New private directory; existing attempts are preserved",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="Validate offline (the default)")
    mode.add_argument(
        "--run", action="store_true", help="Make one paid Live attempt and at most one Luna request"
    )
    args = parser.parse_args(argv)
    try:
        pcm, checked = plan(args.input, args.output_dir)
    except InputError as error:
        print(f"Cannot run: {error}", file=sys.stderr)
        return 2
    except (ValueError, OSError, ImportError, RuntimeError) as error:
        print(
            f"Cannot validate input or optional dependencies ({type(error).__name__}).",
            file=sys.stderr,
        )
        return 2
    if not args.run:
        print(json.dumps(checked, indent=2))
        return 0
    try:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            print("Set OPENAI_API_KEY in the environment before --run", file=sys.stderr)
            return 2
        result = asyncio.run(run_once(pcm, args.output_dir, api_key))
    except Exception as error:
        # SDK/proxy/filesystem messages can contain credential-bearing URLs.
        print(
            f"Run setup or artifact writing failed ({type(error).__name__}); "
            "preserve the attempt directory.",
            file=sys.stderr,
        )
        return 2
    print(f"{result['status']}: {args.output_dir / 'result.json'}")
    if result["status"] == "unknown":
        print(
            "Final provider usage is unknown. Preserve this attempt; "
            "do not replay it automatically.",
            file=sys.stderr,
        )
    return 0 if result["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
