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
    "beds24_auth_check",
    SCRIPTS_DIR / "beds24_auth_check.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class Beds24AuthCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp_dir.name)
        self.evidence_path = self.root / "beds24-auth-check.json"
        self.path_patches = [
            mock.patch.object(MODULE, "EVIDENCE_PATH", self.evidence_path),
        ]
        for patcher in self.path_patches:
            patcher.start()
        self.addCleanup(self.temp_dir.cleanup)
        self.addCleanup(self.stop_patches)

    def stop_patches(self):
        for patcher in reversed(self.path_patches):
            patcher.stop()

    def load_evidence(self) -> dict[str, object]:
        return json.loads(self.evidence_path.read_text(encoding="utf-8"))

    @mock.patch.dict("os.environ", {"BEDS24_TOKEN_CREDENTIAL": " access-secret \n"})
    def test_validate_records_normalized_credential_presence(self):
        result = MODULE.command_validate()

        evidence = self.load_evidence()
        self.assertEqual(result, 0)
        self.assertEqual(evidence["status"], "CREDENTIAL_PRESENT")
        self.assertEqual(evidence["credential_source"], MODULE.CREDENTIAL_SOURCE)
        self.assertTrue(evidence["secret_present"])
        self.assertEqual(evidence["secret_length"], len("access-secret"))

    @mock.patch.object(
        MODULE,
        "request_json",
        return_value=(403, {"detail": "Access token access-secret rejected"}),
    )
    @mock.patch.dict("os.environ", {"BEDS24_TOKEN_CREDENTIAL": "access-secret"})
    def test_probe_failure_persists_safe_diagnostics(self, request_json):
        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            result = MODULE.command_probe()

        evidence = self.load_evidence()
        self.assertEqual(result, 1)
        self.assertEqual(evidence["status"], "AUTH_FAILED")
        self.assertEqual(evidence["failure_stage"], "probe")
        self.assertEqual(evidence["readonly_probe_http_status"], 403)
        self.assertIsNone(evidence["token_exchange_http_status"])
        self.assertEqual(evidence["token_exchange_diagnostics"], {})
        diagnostics = evidence["readonly_probe_diagnostics"]
        self.assertNotIn("access-secret", diagnostics["detail"])
        self.assertIn(MODULE.REDACTED, diagnostics["detail"])
        self.assertIn("HTTP status 403", stderr.getvalue())
        request_json.assert_called_once_with(
            f"{MODULE.API_BASE}/authentication/details",
            {"token": "access-secret"},
            secrets=("access-secret",),
        )

    def test_request_json_parses_http_error_body(self):
        test_secret = "test-access-token"
        error_response = mock.Mock()
        error_response.read.return_value = json.dumps(
            {"message": f"Denied {test_secret}", "status": 403}
        ).encode("utf-8")
        error = MODULE.urllib.error.HTTPError(
            url="https://example.test",
            code=403,
            msg="Forbidden",
            hdrs=None,
            fp=error_response,
        )

        with mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=error):
            status, body = MODULE.request_json(
                "https://example.test",
                {"token": test_secret},
                secrets=(test_secret,),
            )

        self.assertEqual(status, 403)
        self.assertEqual(body["status"], 403)
        self.assertEqual(body["message"], "Denied [REDACTED]")

    def test_parse_args_rejects_removed_exchange_command(self):
        with (
            mock.patch.object(sys, "argv", ["beds24_auth_check.py", "exchange"]),
            mock.patch("sys.stderr", new_callable=io.StringIO),
        ):
            with self.assertRaises(SystemExit) as exc:
                MODULE.parse_args()

        self.assertEqual(exc.exception.code, 2)

    def test_parse_args_accepts_supported_commands(self):
        for command in ("validate", "probe", "report"):
            with self.subTest(command=command):
                with mock.patch.object(sys, "argv", ["beds24_auth_check.py", command]):
                    args = MODULE.parse_args()
                self.assertEqual(args.command, command)

    @mock.patch.dict("os.environ", {"BEDS24_TOKEN_CREDENTIAL": "access-secret"})
    def test_probe_success_persists_auth_ok_without_token_exchange(self):
        observed_headers: list[dict[str, str]] = []

        class FakeResponse:
            def __init__(self, status: int, payload: dict[str, object]):
                self.status = status
                self._payload = payload

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return json.dumps(self._payload).encode("utf-8")

        def fake_urlopen(request, timeout=45):
            self.assertEqual(timeout, 45)
            self.assertEqual(
                request.full_url,
                f"{MODULE.API_BASE}/authentication/details",
            )
            headers = {key.lower(): value for key, value in request.header_items()}
            observed_headers.append(headers)
            self.assertEqual(headers["token"], "access-secret")
            self.assertNotIn("refreshtoken", headers)
            return FakeResponse(200, {"status": "ok"})

        with mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = MODULE.command_probe()

        evidence = self.load_evidence()
        self.assertEqual(result, 0)
        self.assertEqual(len(observed_headers), 1)
        self.assertEqual(evidence["status"], "AUTH_OK")
        self.assertIsNone(evidence["failure_stage"])
        self.assertEqual(evidence["readonly_probe_http_status"], 200)
        self.assertIsNone(evidence["token_exchange_http_status"])
        self.assertEqual(evidence["token_exchange_diagnostics"], {})
        self.assertNotIn("access-secret", json.dumps(evidence))

    def test_report_failure_summarizes_probe_diagnostics(self):
        MODULE.save_evidence(
            {
                "status": "AUTH_FAILED",
                "failure_stage": "probe",
                "token_exchange_http_status": None,
                "token_exchange_diagnostics": {},
                "readonly_probe_http_status": 403,
                "readonly_probe_diagnostics": {
                    "detail": "Access token [REDACTED] rejected",
                    "type": "error",
                },
                "credential_source": MODULE.CREDENTIAL_SOURCE,
                "secret_present": True,
                "secret_length": 16,
                "secret_exposed": False,
            }
        )

        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            result = MODULE.command_report()

        self.assertEqual(result, 1)
        output = stderr.getvalue()
        self.assertIn("failed during probe", output)
        self.assertIn("HTTP status: 403", output)
        self.assertIn('type="error"', output)


if __name__ == "__main__":
    unittest.main()
