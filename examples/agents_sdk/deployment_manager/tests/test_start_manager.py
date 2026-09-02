import argparse
import importlib.util
from pathlib import Path
from unittest import TestCase


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "start_manager.py"
SPEC = importlib.util.spec_from_file_location("start_manager_script", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
start_manager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(start_manager)


class StartManagerTests(TestCase):
    def test_valid_port_accepts_tcp_boundaries(self) -> None:
        self.assertEqual(start_manager._valid_port("1"), 1)
        self.assertEqual(start_manager._valid_port("65535"), 65535)

    def test_valid_port_rejects_out_of_range_and_non_numeric_values(self) -> None:
        for value in ("0", "65536", "not-a-port"):
            with self.subTest(value=value):
                with self.assertRaises(argparse.ArgumentTypeError):
                    start_manager._valid_port(value)
