from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class OutputStore:
    """
    Simple artifact store that writes directly to the root folder.
    Note: This implementation writes directly to `root` (no per-test subfolders),
    which keeps site-relative image paths stable for cookbook rendering.
    """

    root: Path

    def run_dir(self, test_id: str, model_label: str) -> Path:
        # Ignore test/model subfolders; write everything to the root.
        self.root.mkdir(parents=True, exist_ok=True)
        return self.root

    def new_basename(self, prefix: str) -> str:
        created_ms = int(time.time() * 1000)
        return f"{prefix}_{created_ms}"

    def save_png(self, run_dir: Path, basename: str, idx: int, png_bytes: bytes) -> Path:
        out = run_dir / f"{basename}_{idx}.png"
        out.write_bytes(png_bytes)
        return out
