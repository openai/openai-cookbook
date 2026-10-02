from __future__ import annotations

import unittest
from unittest.mock import patch

from scripts.local_deploy import api_ok


class ManagerHealthProbeTests(unittest.TestCase):
    @patch("scripts.local_deploy.request", return_value=b'{"ok":"true"}')
    def test_api_ok_uses_short_probe_timeout(self, request_mock) -> None:
        self.assertTrue(api_ok("http://127.0.0.1:8732"))
        request_mock.assert_called_once_with(
            "http://127.0.0.1:8732/api/health", timeout=1
        )

    @patch("scripts.local_deploy.request", side_effect=TimeoutError)
    def test_api_ok_returns_false_on_timeout(self, _request_mock) -> None:
        self.assertFalse(api_ok("http://127.0.0.1:8732"))

    @patch("scripts.local_deploy.request", return_value=b"not-json")
    def test_api_ok_returns_false_on_invalid_json(self, _request_mock) -> None:
        self.assertFalse(api_ok("http://127.0.0.1:8732"))


if __name__ == "__main__":
    unittest.main()
