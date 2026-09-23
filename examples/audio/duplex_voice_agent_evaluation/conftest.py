"""Keep offline tests from loading a developer's private environment file."""

from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def empty_environment_file(tmp_path_factory: pytest.TempPathFactory) -> Path:
    selected = tmp_path_factory.mktemp("test-environment") / "empty-test.env"
    selected.write_text("", encoding="utf-8")
    return selected


@pytest.fixture(autouse=True)
def isolated_environment_file(empty_environment_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GPT_LIVE_EVALS_ENV_FILE", str(empty_environment_file))
