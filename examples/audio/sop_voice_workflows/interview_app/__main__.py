"""Run the interview using a microphone or a caller's paced WAV recording."""

import argparse
import asyncio
import json
from pathlib import Path
import signal
import sqlite3
import sys

from voice.config import api_key
from voice.audio import MicrophoneAudio, WavAudio
from .live import prepare_interview, run_interview
from .store import ATS


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--mic", action="store_true")
    source.add_argument("--input-wav", type=Path)
    source.add_argument(
        "--describe",
        action="store_true",
        help="Print the exact Live session.start without connecting",
    )
    parser.add_argument("--output", type=Path, default=Path("runs/interview"))
    parser.add_argument("--duration", type=float, default=120, help="Conversation time in seconds")
    parser.add_argument("--database", type=Path, help="Resume an interview from this SQLite file")
    parser.add_argument("--voice", default="marin")
    args = parser.parse_args()
    if args.describe:
        # Build the example in memory so --describe leaves the caller's database alone.
        store = ATS()
        try:
            if args.database:
                db = sqlite3.connect(args.database.resolve().as_uri() + "?mode=ro", uri=True)
                try:
                    db.backup(store.db)
                finally:
                    db.close()
            payload, _ = prepare_interview(
                store, "describe", lambda *a, **kw: None, voice=args.voice
            )
            print(json.dumps(payload, indent=2))
        finally:
            store.close()
        return 0
    if args.duration <= 0:
        parser.error("Choose a positive duration")
    source = MicrophoneAudio() if args.mic else WavAudio(args.input_wav)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    store = ATS(args.database) if args.database else None
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        result = await run_interview(
            source,
            args.output,
            api_key=api_key(),
            duration=args.duration,
            voice=args.voice,
            stop=stop,
            store=store,
        )
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)
        if store:
            store.close()
    print(json.dumps(result, indent=2))
    return int(result["status"] != "collected")


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except (OSError, ValueError) as exc:
        print(
            f"Interview could not start ({type(exc).__name__}). Check the input, configuration, and output path.",
            file=sys.stderr,
        )
        raise SystemExit(1)
