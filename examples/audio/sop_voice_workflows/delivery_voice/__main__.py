"""Talk to Blossom Store about a late delivery or a damaged desk lamp."""

import argparse
import asyncio
from datetime import datetime
from functools import partial
import json
import math
from pathlib import Path
import signal
import sys

from voice.audio import MicrophoneAudio, WavAudio, preflight
from delivery import backend
from voice import webrtc
from .application import Application, session_start


def make_application(bundle, send, http):
    return Application(
        bundle, backend.DEFAULT_BACKEND_MODEL, send, partial(backend.http_sender, http)
    )


async def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--mic",
        action="store_true",
        help="Use your default microphone and speaker. Wear headphones.",
    )
    mode.add_argument(
        "--input-wav",
        type=Path,
        metavar="CALLER.wav",
        help="Use a mono 24 kHz PCM16 caller WAV and record the current reply without audio hardware.",
    )
    mode.add_argument(
        "--describe",
        action="store_true",
        help="Print the Live configuration and store tools offline.",
    )
    parser.add_argument(
        "--duration", type=float, default=120, help="Conversation length in seconds (default 120)."
    )
    parser.add_argument(
        "--output", type=Path, help="New directory for audio, events, tool calls, and store state."
    )
    parser.add_argument(
        "--preflight-audio",
        action="store_true",
        help="Exercise capture and playout offline with a tone.",
    )
    args = parser.parse_args(argv)
    if args.describe:
        print(
            json.dumps(
                {
                    "session": webrtc.rtc_session(session_start()),
                    "backend_model": backend.DEFAULT_BACKEND_MODEL,
                    "tools": [tool["name"] for tool in backend.FUNCTIONS],
                },
                indent=2,
            )
        )
        return 0
    if not math.isfinite(args.duration) or args.duration <= 0:
        parser.error("--duration must be a positive number of seconds")
    directory = args.output or Path("runs") / datetime.now().strftime("blossom-%Y%m%d-%H%M%S-%f")
    if directory.exists():
        parser.error(f"Choose a new output directory. {directory} already exists.")
    if args.mic:
        source = MicrophoneAudio()
    else:
        try:
            source = WavAudio(args.input_wav)
        except (OSError, ValueError, EOFError) as error:
            parser.error(
                f"Cannot load caller WAV ({type(error).__name__}). Use uncompressed mono PCM16 at 24 kHz."
            )
    if args.preflight_audio:
        result = await preflight(source, directory, seconds=min(2, args.duration))
    else:
        from voice.config import api_key

        key = api_key()
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        try:

            def ready():
                print(
                    "Connected. Speak now." if args.mic else "Connected. Sending caller audio.",
                    file=sys.stderr,
                )

            print(
                f"Connecting to Blossom Store. Ctrl-C closes the call. Saving to {directory}",
                file=sys.stderr,
            )
            result = await webrtc.run(
                directory,
                api_key=key,
                duration=args.duration,
                audio_source=source,
                adapter_factory=make_application,
                stop=stop,
                on_ready=ready,
            )
        finally:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.remove_signal_handler(sig)
    print(json.dumps({"directory": str(directory), **result}, indent=2))
    return int(result.get("status", "complete") != "complete")


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except Exception as error:
        # Network errors can contain credentials or private request data.
        print(
            f"Could not run Blossom Store ({type(error).__name__}). Check the inputs, dependencies, and receipt.",
            file=sys.stderr,
        )
        raise SystemExit(1)
