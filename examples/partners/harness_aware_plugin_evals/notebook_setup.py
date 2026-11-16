import atexit
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

PLACEHOLDERS = ("", "your-api-key")
STARTUP_TIMEOUT_S = 30

fixture_server = None


def serving(host: str, port: int) -> bool:
    with socket.socket() as probe:
        return probe.connect_ex((host, port)) == 0


def start_server(host: str, port: int) -> subprocess.Popen:
    process = subprocess.Popen([sys.executable, "server.py"], start_new_session=True)
    atexit.register(stop_server)
    deadline = time.time() + STARTUP_TIMEOUT_S
    while not serving(host, port):
        if process.poll() is not None:
            raise RuntimeError(f"server.py exited with {process.returncode}")
        if time.time() > deadline:
            process.kill()
            raise RuntimeError(f"the fixture server did not answer on {host}:{port}")
        time.sleep(1)
    return process


def stop_server() -> None:
    process = fixture_server
    if process is None or process.poll() is not None:
        return
    process.terminate()
    process.wait(timeout=5)


def prepare() -> bool:
    """Load `.env`, point Codex and promptfoo at this example, and in live mode start the server."""
    global fixture_server
    load_dotenv()
    run_live = os.environ.get("RUN_LIVE") == "1"

    os.environ["CODEX_HOME"] = str(Path(".codex-home").resolve())
    os.environ["PROMPTFOO_PYTHON"] = sys.executable
    mcp_url = os.environ.setdefault("MCP_URL", "http://127.0.0.1:8000/mcp")
    host, port = urlsplit(mcp_url).hostname, urlsplit(mcp_url).port

    if run_live:
        missing = [n for n in ("OPENAI_API_KEY", "EVAL_MODEL") if os.environ.get(n, "") in PLACEHOLDERS]
        if missing:
            raise RuntimeError(f"live mode needs a real value for {', '.join(missing)}")
        if not shutil.which("npx"):
            raise RuntimeError("live mode needs Node.js on PATH")
        shutil.rmtree("outputs", ignore_errors=True)
        Path("outputs").mkdir()
        marketplace = Path(os.environ["CODEX_HOME"]) / "marketplaces" / "cookbook-plugins"
        config = Path(os.environ["CODEX_HOME"]) / "config.toml"
        config.write_text(
            re.sub(
                r"^source = .*",
                lambda _: f'source = "{marketplace}"',
                config.with_suffix(".toml.example").read_text(),
                flags=re.M,
            )
        )
        if not serving(host, port):
            fixture_server = start_server(host, port)
    return run_live
