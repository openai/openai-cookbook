import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import unittest
from unittest import mock


SCRIPTS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "beds24_auth_check",
    SCRIPTS / "beds24_auth_check.py",
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class Beds24AuthCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp_dir.name)
        self.evidence_path = self.root / "beds24-auth-check.json"
        self.token_path = self.root / "beds24-access-token"
        self.path_patches = [
            mock.patch.object(MODULE, "EVIDENCE_PATH", self.evidence_path),
            mock.patch.object(MODULE, "ACCESS_TOKEN_FILE", self.token_path),
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

    @mock.patch.dict("os.environ", {"B24_TOKEN_CREDENTIAL": "refresh-secret"}, clear=True)
    @mock.patch.object(
        MODULE,
        "request_json",
        return_value=(
            401,
            {
                "message": "Credential [REDACTED] is invalid",
                "code": "unauthorized",
            },
        ),
    )
    def test_exchange_failure_persists_safe_diagnostics(self, _request_json):
        with mock.patch("sys.stderr", new_callable=io.StringIO):
            result = MODULE.command_exchange()

        evidence = self.load_evidence()
        self.assertEqual(result, 1)
        self.assertEqual(evidence["status"], "AUTH_FAILED")
        self.assertEqual(evidence["failure_stage"], "exchange")
        self.assertEqual(evidence["token_exchange_http_status"], 401)
        diagnostics = evidence["token_exchange_diagnostics"]
        self.assertEqual(diagnostics["code"], "unauthorized")
        self.assertNotIn("refresh-secret", diagnostics["message"])
        self.assertIn(MODULE.REDACTED, diagnostics["message"])

    @mock.patch.object(
        MODULE,
        "request_json",
        return_value=(403, {"detail": "Access token [REDACTED] rejected"}),
    )
    def test_probe_failure_persists_safe_diagnostics_and_cleans_up(self, _request_json):
        self.token_path.write_text("access-secret", encoding="utf-8")

        result = MODULE.command_probe()

        evidence = self.load_evidence()
        self.assertEqual(result, 1)
        self.assertEqual(evidence["status"], "AUTH_FAILED")
        self.assertEqual(evidence["failure_stage"], "probe")
        self.assertEqual(evidence["readonly_probe_http_status"], 403)
        diagnostics = evidence["readonly_probe_diagnostics"]
        self.assertNotIn("access-secret", diagnostics["detail"])
        self.assertIn(MODULE.REDACTED, diagnostics["detail"])
        self.assertFalse(self.token_path.exists())

    def test_request_json_parses_http_error_body(self):
        error_response = mock.Mock()
        error_response.read.return_value = b'{"message":"Denied refresh-secret","status":401}'
        error = MODULE.urllib.error.HTTPError(
            url="https://example.test",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=error_response,
        )

        with mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=error):
            status, body = MODULE.request_json(
                "https://example.test",
                {"refreshToken": "refresh-secret"},
                secrets=("refresh-secret",),
            )

        self.assertEqual(status, 401)
        self.assertEqual(body["status"], 401)
        self.assertEqual(body["message"], "Denied [REDACTED]")

    def test_report_failure_summarizes_exchange_diagnostics(self):
        MODULE.save_evidence(
            {
                "status": "AUTH_FAILED",
                "failure_stage": "exchange",
                "token_exchange_http_status": 401,
                "token_exchange_diagnostics": {
                    "message": "Credential [REDACTED] is invalid",
                    "code": "unauthorized",
                },
                "readonly_probe_http_status": None,
                "readonly_probe_diagnostics": {},
                "credential_source": "B24_TOKEN_CREDENTIAL",
                "secret_present": True,
                "secret_length": 16,
                "secret_exposed": False,
            }
        )

        with mock.patch("sys.stderr", new_callable=io.StringIO) as stderr:
            result = MODULE.command_report()

        self.assertEqual(result, 1)
        output = stderr.getvalue()
        self.assertIn("failed during exchange", output)
        self.assertIn("HTTP status: 401", output)
        self.assertIn('code="unauthorized"', output)


if __name__ == "__main__":
    unittest.main()
