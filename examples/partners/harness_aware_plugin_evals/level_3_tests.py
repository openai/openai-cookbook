from pathlib import Path

import yaml


CONFIG_PATH = Path(__file__).with_name("promptfooconfig.yaml")


def generate_tests(_config: dict | None = None) -> list[dict]:
    """Reuse the shared corpus for the Codex provider."""
    return yaml.safe_load(CONFIG_PATH.read_text())["tests"]
