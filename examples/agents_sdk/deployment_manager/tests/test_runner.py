import importlib
import os
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
_is_running = importlib.import_module("app.runner")._is_running


def test_is_running_matches_managed_process() -> None:
    deployment_id = "deployment-pid-guard-test"
    env = os.environ.copy()
    env["AGENTS_SDK_DEPLOYMENT_ID"] = deployment_id
    process = subprocess.Popen(
        ["sleep", "30"],
        env=env,
        start_new_session=True,
    )
    try:
        assert _is_running(process.pid, deployment_id)
        assert not _is_running(process.pid, "different-deployment")
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=5)

    assert not _is_running(process.pid, deployment_id)
