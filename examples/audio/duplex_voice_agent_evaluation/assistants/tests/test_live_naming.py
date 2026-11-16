"""Canonical configuration and explicitly supported historical names."""

from __future__ import annotations

import importlib
import re
import tomllib
from pathlib import Path
from types import SimpleNamespace

import pytest

from assistants.config import ASSISTANT_ENV_DEFAULTS, LiveAgentSettings, assistant_env
from crawl_harness.evaluate import parse_args as parse_crawl_args
from run_harness.evaluate import _token_counts
from run_harness.evaluate import parse_args as parse_run_args
from shared.observability.timeline import Timeline
from shared.reporting.compat import is_live_frontend_usage
from walk_harness.evaluate import parse_args as parse_walk_args

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REMOVED_ENV_NAMES = {
    "OPENAI_LIVE_ENDPOINT": "OPENAI_BIDI_LIVE_ENDPOINT",
    "OPENAI_LIVE_MODEL": "OPENAI_BIDI_MODEL",
    "OPENAI_LIVE_VOICE": "OPENAI_BIDI_VOICE",
    "OPENAI_LIVE_BACKEND_MODEL": "OPENAI_BIDI_BACKEND_MODEL",
    "OPENAI_LIVE_BACKEND_REASONING_EFFORT": "OPENAI_BIDI_BACKEND_REASONING_EFFORT",
    "OPENAI_LIVE_BACKEND_MAX_OUTPUT_TOKENS": "OPENAI_BIDI_BACKEND_MAX_OUTPUT_TOKENS",
    "OPENAI_LIVE_BACKEND_VERBOSITY": "OPENAI_BIDI_BACKEND_VERBOSITY",
}


@pytest.fixture
def clean_live_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for canonical, legacy in REMOVED_ENV_NAMES.items():
        monkeypatch.delenv(canonical, raising=False)
        monkeypatch.delenv(legacy, raising=False)


@pytest.mark.usefixtures("clean_live_environment")
@pytest.mark.parametrize("canonical,legacy", REMOVED_ENV_NAMES.items())
def test_only_canonical_environment_settings_are_read(
    monkeypatch: pytest.MonkeyPatch, canonical: str, legacy: str
) -> None:
    assert assistant_env(canonical) == ASSISTANT_ENV_DEFAULTS[canonical]
    monkeypatch.setenv(legacy, "old-private-value")
    assert assistant_env(canonical) == ASSISTANT_ENV_DEFAULTS[canonical]
    with pytest.raises(ValueError, match="Unknown assistant setting") as caught:
        assistant_env(legacy)
    assert "old-private-value" not in str(caught.value)
    monkeypatch.setenv(canonical, "current-private-value")
    assert assistant_env(canonical) == "current-private-value"
    monkeypatch.setenv(canonical, " ")
    with pytest.raises(ValueError, match=re.escape(canonical)):
        assistant_env(canonical)


@pytest.mark.usefixtures("clean_live_environment")
@pytest.mark.parametrize("parser", [parse_crawl_args, parse_walk_args, parse_run_args])
def test_each_cli_ignores_removed_configuration(monkeypatch: pytest.MonkeyPatch, parser) -> None:
    monkeypatch.setenv(REMOVED_ENV_NAMES["OPENAI_LIVE_MODEL"], "legacy-model")
    assert parser([]).model == ASSISTANT_ENV_DEFAULTS["OPENAI_LIVE_MODEL"]
    monkeypatch.setenv("OPENAI_LIVE_MODEL", "current-model")
    assert parser([]).model == "current-model"
    assert parser(["--model", "cli-model"]).model == "cli-model"


@pytest.mark.parametrize("module_name", ["assistants", "assistants.config"])
def test_former_settings_import_is_removed(module_name: str) -> None:
    module = importlib.import_module(module_name)
    assert module.LiveAgentSettings is LiveAgentSettings
    removed_class = "BiDiAgentSettings"
    with pytest.raises(AttributeError):
        getattr(module, removed_class)


def test_usage_writer_is_canonical_and_historical_reader_still_works() -> None:
    timeline = Timeline()
    timeline.apply_event({"type": "session.closed", "usage": {"total_tokens": 12}})
    assert timeline.usage[-1]["source"] == "live_frontend"
    for source in ("live_frontend", "bidi"):
        assert is_live_frontend_usage(source)
        result = SimpleNamespace(usage=[{"source": source, "total_tokens": 12}])
        assert _token_counts(result)["frontend_total_tokens"] == 12
    assert not is_live_frontend_usage("delegated_response")


def test_distribution_and_lock_use_the_current_name() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    lock = tomllib.loads((PROJECT_ROOT / "uv.lock").read_text())
    assert project["project"]["name"] == "gpt-live-evals"
    assert [item["name"] for item in lock["package"] if item.get("source") == {"editable": "."}] == ["gpt-live-evals"]


def test_legacy_product_names_are_confined_to_migration_boundaries() -> None:
    # These are the complete, deliberately reviewable compatibility surfaces.
    allowed = {
        "assistants/tests/test_live_naming.py",
        "docs/live-naming-migration.md",
        "shared/reporting/compat.py",
    }
    roots = [
        PROJECT_ROOT / name for name in ("assistants", "crawl_harness", "walk_harness", "run_harness", "shared", "docs")
    ]
    candidates = {
        PROJECT_ROOT / name for name in ("README.md", ".env.example", ".gitignore", "pyproject.toml", "uv.lock")
    }
    for root in roots:
        candidates.update(
            path
            for path in root.rglob("*")
            if path.is_file()
            and not {"results", "__pycache__", ".audio_cache"}.intersection(path.parts)
            and path.suffix in {".py", ".md", ".toml", ".json", ".ts", ".svg", ".txt", ".js", ".css"}
        )
    retired_name = re.compile(r"bidi(?!rectional)", re.IGNORECASE)
    for path in sorted(candidates):
        relative = path.relative_to(PROJECT_ROOT).as_posix()
        assert not retired_name.search(relative), f"Legacy filename: {relative}"
        if relative not in allowed:
            assert not retired_name.search(path.read_text(encoding="utf-8")), f"Legacy product name in {relative}"
