import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from vision_harness import storage
from vision_harness.storage import OutputStore


def test_new_basename_is_unique_within_same_millisecond(tmp_path: Path) -> None:
    original_time = storage.time.time
    try:
        storage.time.time = lambda: 1234.567
        store = OutputStore(tmp_path)
        first = store.new_basename("case-model")
        second = store.new_basename("case-model")
    finally:
        storage.time.time = original_time

    assert first != second
    assert first.startswith("case-model_1234567_")
    assert second.startswith("case-model_1234567_")
