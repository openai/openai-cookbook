from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest

from demo_date import DEMO_TRAVEL_DATE_TOKEN, demo_travel_date, materialize_demo_date

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("shell_override", [None, "2099-09-23"])
def test_npm_demo_date_loads_root_dotenv_and_preserves_shell_overrides(
    tmp_path: Path, shell_override: str | None
) -> None:
    if not shutil.which("npm") or not shutil.which("uv"):
        pytest.skip("The demo-date npm entrypoint requires npm and uv")
    runtime = tmp_path / "runtime-agent"
    runtime.mkdir()
    for name in ("package.json", "pyproject.toml", "uv.lock", "demo_date.py"):
        shutil.copyfile(REPOSITORY_ROOT / "runtime-agent" / name, runtime / name)
    (tmp_path / ".env").write_text("COOKBOOK_DEMO_TRAVEL_DATE=2099-09-22\n", encoding="utf-8")
    # Exercise the real npm/uv entrypoint, without cloud configuration, dependency
    # installs, or user-level uv/npm config. demo_date.py uses only the stdlib.
    environment = {
        "PATH": os.environ["PATH"],
        "UV_PYTHON": sys.executable,
        "UV_PYTHON_DOWNLOADS": "never",
        "UV_NO_SYNC": "1",
        "UV_NO_CONFIG": "1",
        "UV_OFFLINE": "1",
        "UV_CACHE_DIR": str(tmp_path / "uv-cache"),
        "UV_PROJECT_ENVIRONMENT": str(tmp_path / "venv"),
        "npm_config_userconfig": str(tmp_path / "empty-user-npmrc"),
        "npm_config_globalconfig": str(tmp_path / "empty-global-npmrc"),
    }
    if shell_override:
        environment["COOKBOOK_DEMO_TRAVEL_DATE"] = shell_override
    result = subprocess.run(
        ["npm", "--prefix", "runtime-agent", "run", "--silent", "demo-date"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == (shell_override or "2099-09-22")


def test_demo_date_defaults_to_45_days_in_the_future() -> None:
    assert demo_travel_date(environment={}, today=date(2030, 1, 10)) == "2030-02-24"


def test_demo_date_accepts_a_future_deterministic_override() -> None:
    assert (
        demo_travel_date(
            environment={"COOKBOOK_DEMO_TRAVEL_DATE": "2030-03-01"},
            today=date(2030, 1, 10),
        )
        == "2030-03-01"
    )


@pytest.mark.parametrize("value", ["not-a-date", "2030-02-30", "2030-01-10", "2029-12-31"])
def test_demo_date_rejects_an_invalid_or_non_future_override(value: str) -> None:
    with pytest.raises(RuntimeError, match="must be an ISO date|must be later than today"):
        demo_travel_date(
            environment={"COOKBOOK_DEMO_TRAVEL_DATE": value},
            today=date(2030, 1, 10),
        )


def test_materialize_demo_date_replaces_nested_fixture_tokens() -> None:
    value = {
        "request": {"travel_date": DEMO_TRAVEL_DATE_TOKEN},
        "assertions": [DEMO_TRAVEL_DATE_TOKEN],
    }

    assert materialize_demo_date(value, "2030-03-01") == {
        "request": {"travel_date": "2030-03-01"},
        "assertions": ["2030-03-01"],
    }
