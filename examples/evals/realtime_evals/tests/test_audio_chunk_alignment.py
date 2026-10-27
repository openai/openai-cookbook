import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from shared.realtime_harness_utils import compute_bytes_per_chunk


def test_pcm16_chunk_size_stays_sample_aligned() -> None:
    bytes_per_chunk = compute_bytes_per_chunk(
        sample_rate_hz=44_100,
        chunk_ms=15,
        bytes_per_sample=2,
    )

    assert bytes_per_chunk == 1_322
    assert bytes_per_chunk % 2 == 0


def test_single_byte_formats_keep_expected_chunk_size() -> None:
    assert compute_bytes_per_chunk(8_000, 15, 1) == 120
