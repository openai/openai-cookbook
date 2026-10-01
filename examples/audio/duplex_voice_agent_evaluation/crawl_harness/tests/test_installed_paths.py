"""Writable installed defaults, explicit environment discovery, and optional audio."""

from __future__ import annotations

import builtins
import importlib
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from assistants.config import LiveAgentSettings
from run_harness.visualization.export_viewer import export_viewer
from shared import environment, paths
from shared.audio.conversation import LiveMonitor
from walk_harness.generate_audio import _derived_dataset_path, generate, parse_args

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("phase", paths.PHASES)
def test_source_defaults_preserve_existing_locations(phase: str) -> None:
    assert paths.source_checkout_root() == ROOT
    assert paths.default_results_dir(phase) == ROOT / f"{phase}_harness/results"
    assert paths.default_audio_cache_dir() == ROOT / "crawl_harness/.audio_cache"


@pytest.mark.parametrize("phase", paths.PHASES)
def test_installed_defaults_and_explicit_overrides(phase: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "source_checkout_root", lambda: None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    module = importlib.import_module(f"{phase}_harness.evaluate")
    args = module.parse_args([])
    assert args.results_dir == tmp_path / "results" / phase
    assert args.data.is_file()
    if phase == "crawl":
        assert args.audio_cache_dir == tmp_path / "cache/gpt-live-evals/crawl-audio"
    config = tmp_path / "custom.toml"
    config.write_text('[execution]\nresults_dir="output"\n[audio]\ncache_dir="cache-custom"\n')
    configured = module.parse_args(["--config", str(config)])
    assert configured.results_dir == tmp_path / "output"
    overridden = module.parse_args(["--config", str(config), "--results-dir", "explicit"])
    assert overridden.results_dir == Path("explicit")
    if phase == "crawl":
        assert configured.audio_cache_dir == tmp_path / "cache-custom"
        assert module.parse_args(
            ["--config", str(config), "--audio-cache-dir", "explicit-cache"]
        ).audio_cache_dir == Path("explicit-cache")


@pytest.mark.parametrize(
    "platform,suffix", [("darwin", "Library/Caches"), ("linux", ".cache"), ("win32", "AppData/Local")]
)
def test_user_cache_fallback(platform: str, suffix: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "source_checkout_root", lambda: None)
    monkeypatch.setattr(paths.sys, "platform", platform)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    assert paths.default_audio_cache_dir() == tmp_path / suffix / "gpt-live-evals/crawl-audio"


@pytest.mark.parametrize("package", paths.PACKAGES)
def test_installed_package_outputs_are_rejected(package: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "source_checkout_root", lambda: None)
    with pytest.raises(ValueError, match="outside installed"):
        paths.require_external_output(paths.package_path(package) / "output")
    assert paths.require_external_output(tmp_path) == tmp_path


def test_installed_generator_uses_external_derived_dataset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "source_checkout_root", lambda: None)
    monkeypatch.chdir(tmp_path)
    args = parse_args(["--condition", "noisy"])
    assert _derived_dataset_path(args) == tmp_path / "data/walk/scenarios.noisy.json"
    assert _derived_dataset_path(parse_args(["--output-data", "custom.json"])) == tmp_path / "custom.json"


async def test_generator_rejects_explicit_installed_output_before_api_use(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "source_checkout_root", lambda: None)
    output = paths.package_path("walk_harness", "data", "forbidden.json")
    args = parse_args(["--example", "restaurant_001", "--output-data", str(output)])
    with pytest.raises(ValueError, match="outside installed"):
        await generate(args, client=object())
    assert not output.exists()


def test_viewer_rejects_installed_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paths, "source_checkout_root", lambda: None)
    with pytest.raises(ValueError, match="outside installed"):
        export_viewer(tmp_path / "results.json", paths.package_path("run_harness", "viewer.html"))


def test_environment_discovery_is_explicit_and_does_not_walk_parents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GPT_LIVE_EVALS_ENV_FILE", raising=False)
    monkeypatch.setattr(environment, "source_checkout_root", lambda: None)
    parent = tmp_path / "parent"
    child = parent / "child"
    child.mkdir(parents=True)
    (parent / ".env").write_text("UNUSED_PARENT_SECRET=not-loaded\n")
    monkeypatch.chdir(child)
    assert environment.environment_file() is None
    local = child / ".env"
    local.write_text("F08_TEST_SETTING=local\n")
    assert environment.environment_file() == local
    explicit = tmp_path / "selected.env"
    explicit.write_text("F08_TEST_SETTING=selected\n")
    monkeypatch.setenv("GPT_LIVE_EVALS_ENV_FILE", str(explicit))
    monkeypatch.setenv("F08_TEST_SETTING", "shell")
    assert environment.load_environment() == explicit
    assert os.environ["F08_TEST_SETTING"] == "shell"
    monkeypatch.delenv("F08_TEST_SETTING")
    environment.load_environment()
    assert os.environ["F08_TEST_SETTING"] == "selected"
    monkeypatch.delenv("F08_TEST_SETTING")


def test_source_env_fallback_and_missing_explicit_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / ".env").write_text("OPENAI_LIVE_MODEL=from-selected-file\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(environment, "source_checkout_root", lambda: checkout)
    monkeypatch.delenv("GPT_LIVE_EVALS_ENV_FILE", raising=False)
    monkeypatch.delenv("OPENAI_LIVE_MODEL", raising=False)
    assert environment.environment_file() == checkout / ".env"
    assert LiveAgentSettings().model == "from-selected-file"
    monkeypatch.delenv("OPENAI_LIVE_MODEL")
    for value in ("", str(tmp_path / "missing.env")):
        monkeypatch.setenv("GPT_LIVE_EVALS_ENV_FILE", value)
        with pytest.raises(ValueError):
            environment.load_environment()


def test_importing_configuration_does_not_load_environment(tmp_path: Path) -> None:
    selected = tmp_path / "selected.env"
    selected.write_text("F08_IMPORT_SENTINEL=unexpected\n")
    env = {**os.environ, "GPT_LIVE_EVALS_ENV_FILE": str(selected), "PYTHONPATH": str(ROOT)}
    env.pop("F08_IMPORT_SENTINEL", None)
    subprocess.run(
        [
            sys.executable,
            "-c",
            "import os, assistants.config, run_harness.simulation.models; "
            "assert 'F08_IMPORT_SENTINEL' not in os.environ",
        ],
        cwd=tmp_path,
        env=env,
        check=True,
    )


def test_missing_playback_extra_has_actionable_error(monkeypatch: pytest.MonkeyPatch) -> None:
    original = builtins.__import__

    def without_sounddevice(name, *args, **kwargs):
        if name == "sounddevice":
            raise ModuleNotFoundError("No module named 'sounddevice'")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", without_sounddevice)
    with pytest.raises(RuntimeError, match=r"uv sync --extra playback"):
        LiveMonitor(24_000).start()


def test_playback_is_optional_and_entrypoints_do_not_modify_import_paths() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert not any(item.startswith("sounddevice") for item in project["dependencies"])
    assert project["optional-dependencies"]["playback"] == ["sounddevice>=0.5"]
    for module in project["scripts"].values():
        source = (ROOT / (module.split(":")[0].replace(".", "/") + ".py")).read_text()
        assert "sys.path.insert" not in source and "noqa: E402" not in source
