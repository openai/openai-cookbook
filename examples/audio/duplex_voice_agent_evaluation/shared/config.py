"""Small, standard-library configuration for independent evaluation harnesses."""

from __future__ import annotations

import argparse
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from shared.environment import load_environment


@dataclass(frozen=True, slots=True)
class HarnessConfig:
    """A module-owned TOML file with paths relative to that module."""

    path: Path
    values: Mapping[str, Any]

    def get(self, section: str, name: str, default: Any) -> Any:
        group = self.values.get(section, {})
        if not isinstance(group, dict):
            raise ValueError(f"Configuration section [{section}] must be a table: {self.path}")
        value = group.get(name, default)
        if isinstance(default, bool) and not isinstance(value, bool):
            raise ValueError(f"Configuration {section}.{name} must be a boolean: {self.path}")
        if (
            isinstance(default, int)
            and not isinstance(default, bool)
            and (not isinstance(value, int) or isinstance(value, bool))
        ):
            raise ValueError(f"Configuration {section}.{name} must be an integer: {self.path}")
        if isinstance(default, float) and (not isinstance(value, int | float) or isinstance(value, bool)):
            raise ValueError(f"Configuration {section}.{name} must be a number: {self.path}")
        if isinstance(default, str) and not isinstance(value, str):
            raise ValueError(f"Configuration {section}.{name} must be a string: {self.path}")
        return value

    def path_for(self, section: str, name: str, default: Path) -> Path:
        group = self.values.get(section, {})
        if not isinstance(group, dict):
            raise ValueError(f"Configuration section [{section}] must be a table: {self.path}")
        value = group.get(name)
        if value is None:
            return default
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Configuration {section}.{name} must be a nonempty path: {self.path}")
        candidate = Path(value).expanduser()
        return candidate if candidate.is_absolute() else (self.path.parent / candidate).resolve()


def load_harness_config(argv: Sequence[str] | None, default: Path) -> HarnessConfig:
    """Read ``--config`` early while leaving all other CLI flags untouched."""

    load_environment()
    bootstrap = argparse.ArgumentParser(add_help=False)
    bootstrap.add_argument("--config", type=Path, default=default)
    selected, _ = bootstrap.parse_known_args(argv)
    path = selected.config.expanduser().resolve()
    try:
        with path.open("rb") as stream:
            values = tomllib.load(stream)
    except FileNotFoundError as exc:
        raise ValueError(f"Harness configuration does not exist: {path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise ValueError(f"Invalid harness configuration: {path}: {exc}") from exc
    return HarnessConfig(path=path, values=values)
