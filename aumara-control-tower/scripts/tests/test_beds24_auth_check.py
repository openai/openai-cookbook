import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

SCRIPTS_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))
SPEC = importlib.util.spec_from_file_location(
    "beds24_auth_check", SCRIPTS_DIR / "beds24_auth_check.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class Beds24AuthCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.evidence_path = pathlib.Path(self.temp_dir.name) / "evidence.json"
        self.patch = mock.patch.object(MODULE, "EVIDENCE_PATH", self.evidence_path)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.addCleanup(self.temp_dir.cleanup)

    def evidence(self):
        return json.loads(self.evidence_path.read_text(encoding="utf-8"))

    @mock.patch.dict("os.environ", {"BEDS24_REFRESH_TOKEN": " secret \n"})
    def test_validate_present(self):
        self.assertEqual(MODULE.command_validate(), 0)
        self.assertEqual(self.evidence()["status"], "CREDENTIAL_PRESENT")

    def test_validate_missing_fails_closed(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            with mock.patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(MODULE.command_validate(), 1)
        self.assertEqual(self.evidence()["failure_stage"], "validate")

    @mock.patch.dict("os.environ", {"BEDS24_REFRESH_TOKEN": "access-secret"})
    def test_access_token_mode_succeeds_without_exchange(self):
        with mock.patch.object(
            MODULE,
            "request_json",
            return_value=(200, {"validToken": True, "token": "access-secret"}),
        ) as request:
            self.assertEqual(MODULE.command_authenticate(), 0)
        evidence = self.evidence()
        self.assertEqual(evidence["credential_mode"], "access_token")
        self.assertEqual(evidence["status"], "AUTH_OK")
        self.assertNotIn("access-secret", json.dumps(evidence))
        request.assert_called_once()

    @mock.patch.dict("os.environ", {"BEDS24_REFRESH_TOKEN": "refresh-secret"})
    def test_refresh_token_mode_exchanges_then_probes(self):
        responses = [
            (401, {"error": "Token not valid"}),
            (200, {"token": "temporary-access"}),
            (200, {"validToken": True}),
        ]
        with mock.patch.object(MODULE, "request_json", side_effect=responses) as request:
            self.assertEqual(MODULE.command_authenticate(), 0)
        evidence = self.evidence()
        self.assertEqual(evidence["credential_mode"], "refresh_token")
        self.assertEqual(evidence["status"], "AUTH_OK")
        self.assertNotIn("refresh-secret", json.dumps(evidence))
        self.assertNotIn("temporary-access", json.dumps(evidence))
        self.assertEqual(request.call_count, 3)
        self.assertEqual(request.call_args_list[0].args[1], {"token": "refresh-secret"})
        self.assertEqual(
            request.call_args_list[1].args[1], {"refreshToken": "refresh-secret"}
        )
        self.assertEqual(
            request.call_args_list[2].args[1], {"token": "temporary-access"}
        )

    @mock.patch.dict("os.environ", {"BEDS24_REFRESH_TOKEN": "invalid-access"})
    def test_http_200_with_valid_token_false_is_not_auth_ok(self):
        responses = [
            (200, {"validToken": False, "diagnostics": {"requestIp": "127.0.0.1"}}),
            (401, {"error": "Token not valid", "code": 401}),
        ]
        with mock.patch.object(MODULE, "request_json", side_effect=responses):
            with mock.patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(MODULE.command_authenticate(), 1)
        evidence = self.evidence()
        self.assertEqual(evidence["status"], "AUTH_FAILED")
        self.assertFalse(evidence["direct_probe_valid_token"])
        self.assertEqual(evidence["failure_stage"], "credential")

    @mock.patch.dict("os.environ", {"BEDS24_REFRESH_TOKEN": "bad-secret"})
    def test_both_modes_invalid_fail_honestly_and_redacted(self):
        responses = [
            (401, {"error": "Token bad-secret not valid"}),
            (401, {"error": "Token bad-secret not valid", "code": 401}),
        ]
        with mock.patch.object(MODULE, "request_json", side_effect=responses):
            with mock.patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(MODULE.command_authenticate(), 1)
        evidence = self.evidence()
        self.assertEqual(evidence["status"], "AUTH_FAILED")
        self.assertEqual(evidence["failure_stage"], "credential")
        self.assertEqual(evidence["direct_probe_http_status"], 401)
        self.assertEqual(evidence["token_exchange_http_status"], 401)
        self.assertNotIn("bad-secret", json.dumps(evidence))
        self.assertIn(MODULE.REDACTED, json.dumps(evidence))

    @mock.patch.dict("os.environ", {"BEDS24_REFRESH_TOKEN": "refresh-secret"})
    def test_exchanged_access_token_probe_failure_is_redacted(self):
        responses = [
            (401, {"error": "not access"}),
            (200, {"token": "temporary-access"}),
            (403, {"detail": "temporary-access rejected"}),
        ]
        with mock.patch.object(MODULE, "request_json", side_effect=responses):
            with mock.patch("sys.stderr", new_callable=io.StringIO):
                self.assertEqual(MODULE.command_authenticate(), 1)
        evidence = self.evidence()
        self.assertEqual(evidence["failure_stage"], "probe")
        self.assertNotIn("temporary-access", json.dumps(evidence))

    def test_request_json_redacts_http_error(self):
        response = mock.Mock()
        response.read.return_value = b'{"message":"Denied test-secret"}'
        error = MODULE.urllib.error.HTTPError(
            "https://example.test", 401, "Unauthorized", None, response
        )
        with mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=error):
            status, body = MODULE.request_json(
                "https://example.test",
                {"token": "test-secret"},
                secrets=("test-secret",),
            )
        self.assertEqual(status, 401)
        self.assertEqual(body["message"], "Denied [REDACTED]")

    def test_extracts_beds24_diagnostics(self):
        self.assertEqual(
            MODULE.extract_diagnostics({"diagnostics": ["bookingsRead missing"]}),
            {"diagnostics": ["bookingsRead missing"]},
        )

    def test_cli_commands(self):
        for command in ("validate", "authenticate", "report"):
            with mock.patch.object(sys, "argv", ["beds24_auth_check.py", command]):
                self.assertEqual(MODULE.parse_args().command, command)


if __name__ == "__main__":
    unittest.main()
