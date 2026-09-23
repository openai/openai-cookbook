from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default="8732")
    parser.add_argument("--log-file", required=True)
    parser.add_argument("--pid-file", required=True)
    args = parser.parse_args()

    log_path = Path(args.log_file)
    pid_path = Path(args.pid_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.parent.mkdir(parents=True, exist_ok=True)

    handle = log_path.open("ab")
    process = subprocess.Popen(
        [
            "uv",
            "run",
            "python",
            "-m",
            "app.main",
        ],
        env={
            **os.environ,
            "HOST": args.host,
            "PORT": str(args.port),
        },
        stdout=handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    pid_path.write_text(str(process.pid), encoding="utf-8")


if __name__ == "__main__":
    main()
