import importlib.util
import io
import json
import pathlib
import stat
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
        self.token_path = self.root / "beds24-access-token"
        self.vault_path = self.root / "vault" / "beds24-refresh-token.enc"
        self.path_patches = [
            mock.patch.object(MODULE, "EVIDENCE_PATH", self.evidence_path),
            mock.patch.object(MODULE, "ACCESS_TOKEN_FILE", self.token_path),
            mock.patch.object(MODULE, "ENCRYPTED_REFRESH_FILE", self.vault_path),
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

    @mock.patch.dict("os.environ", {"B24_TOKEN_CREDENTIAL": "refresh-secret"})
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

    @mock.patch.dict("os.environ", {"B24_TOKEN_CREDENTIAL": "refresh-secret"})
    def test_exchange_probe_success_persists_auth_ok_and_cleans_up(self):
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
            headers = {key.lower(): value for key, value in request.header_items()}
            observed_headers.append(headers)
            if request.full_url.endswith("/authentication/token"):
                self.assertEqual(headers["refreshtoken"], "refresh-secret")
                return FakeResponse(200, {"token": "access-secret", "expiresIn": 3600})
            self.assertEqual(request.full_url, f"{MODULE.API_BASE}/authentication/details")
            self.assertEqual(headers["token"], "access-secret")
            return FakeResponse(200, {"status": "ok"})

        with mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=fake_urlopen):
            exchange_result = MODULE.command_exchange()
            self.assertEqual(exchange_result, 0)
            self.assertTrue(self.token_path.exists())
            self.assertEqual(
                stat.S_IMODE(self.token_path.stat().st_mode),
                stat.S_IRUSR | stat.S_IWUSR,
            )
            self.assertEqual(
                self.token_path.read_text(encoding="utf-8"),
                "access-secret",
            )

            probe_result = MODULE.command_probe()

        evidence = self.load_evidence()
        exchange_headers, probe_headers = observed_headers
        self.assertEqual(probe_result, 0)
        self.assertEqual(exchange_headers["refreshtoken"], "refresh-secret")
        self.assertEqual(probe_headers["token"], "access-secret")
        self.assertEqual(evidence["status"], "AUTH_OK")
        self.assertIsNone(evidence["failure_stage"])
        self.assertEqual(evidence["token_exchange_http_status"], 200)
        self.assertEqual(evidence["readonly_probe_http_status"], 200)
        self.assertFalse(self.token_path.exists())
        self.assertNotIn("access-secret", json.dumps(evidence))

    @mock.patch.dict("os.environ", {"B24_TOKEN_CREDENTIAL": "vault-passphrase"})
    def test_exchange_uses_decrypted_vault_refresh_token(self):
        observed_headers: list[dict[str, str]] = []
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        self.vault_path.write_text("encrypted", encoding="utf-8")

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

        def fake_run(args, env, capture_output, text):
            self.assertEqual(env["BEDS24_VAULT_PASSPHRASE"], "vault-passphrase")
            self.assertEqual(
                args[:10],
                [
                    "openssl",
                    "enc",
                    "-d",
                    "-aes-256-cbc",
                    "-pbkdf2",
                    "-iter",
                    "200000",
                    "-pass",
                    "env:BEDS24_VAULT_PASSPHRASE",
                    "-in",
                ],
            )
            self.assertEqual(args[10], str(self.vault_path))
            self.assertEqual(args[11], "-out")
            out_path = pathlib.Path(args[args.index("-out") + 1])
            out_path.write_text("  refresh-from-vault \n", encoding="utf-8")
            return mock.Mock(returncode=0)

        def fake_urlopen(request, timeout=45):
            self.assertEqual(timeout, 45)
            headers = {key.lower(): value for key, value in request.header_items()}
            observed_headers.append(headers)
            if request.full_url.endswith("/authentication/token"):
                self.assertEqual(headers["refreshtoken"], "refresh-from-vault")
                return FakeResponse(200, {"token": "access-secret", "expiresIn": 3600})
            self.assertEqual(request.full_url, f"{MODULE.API_BASE}/authentication/details")
            self.assertEqual(headers["token"], "access-secret")
            return FakeResponse(200, {"status": "ok"})

        with (
            mock.patch.object(MODULE.subprocess, "run", side_effect=fake_run),
            mock.patch.object(MODULE.urllib.request, "urlopen", side_effect=fake_urlopen),
        ):
            exchange_result = MODULE.command_exchange()
            probe_result = MODULE.command_probe()

        evidence = self.load_evidence()
        self.assertEqual(exchange_result, 0)
        self.assertEqual(probe_result, 0)
        self.assertEqual(observed_headers[0]["refreshtoken"], "refresh-from-vault")
        self.assertTrue(evidence["credential_source"].endswith("vault/beds24-refresh-token.enc"))
        self.assertEqual(evidence["status"], "AUTH_OK")
        self.assertFalse(self.token_path.exists())

    @mock.patch.dict("os.environ", {"B24_TOKEN_CREDENTIAL": "vault-passphrase"})
    def test_exchange_fails_with_decrypt_stage_when_vault_decrypts_empty(self):
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        self.vault_path.write_text("encrypted", encoding="utf-8")

        def fake_run(args, env, capture_output, text):
            out_path = pathlib.Path(args[args.index("-out") + 1])
            out_path.write_text(" \n\t ", encoding="utf-8")
            return mock.Mock(returncode=0)

        with (
            mock.patch.object(MODULE.subprocess, "run", side_effect=fake_run),
            mock.patch.object(MODULE.urllib.request, "urlopen") as urlopen,
            mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            result = MODULE.command_exchange()

        evidence = self.load_evidence()
        self.assertEqual(result, 1)
        self.assertEqual(evidence["status"], "AUTH_FAILED")
        self.assertEqual(evidence["failure_stage"], "decrypt")
        self.assertEqual(
            evidence["token_exchange_diagnostics"]["message"],
            "Beds24 refresh token vault decrypted to an empty value.",
        )
        self.assertIn("decrypted to an empty value", stderr.getvalue())
        urlopen.assert_not_called()

    @mock.patch.dict("os.environ", {"B24_TOKEN_CREDENTIAL": "vault-passphrase"})
    def test_exchange_fails_with_decrypt_stage_when_vault_command_fails(self):
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        self.vault_path.write_text("encrypted", encoding="utf-8")

        with (
            mock.patch.object(
                MODULE.subprocess,
                "run",
                return_value=mock.Mock(returncode=1, stderr="bad decrypt vault-passphrase"),
            ),
            mock.patch.object(MODULE.urllib.request, "urlopen") as urlopen,
            mock.patch("sys.stderr", new_callable=io.StringIO) as stderr,
        ):
            result = MODULE.command_exchange()

        evidence = self.load_evidence()
        self.assertEqual(result, 1)
        self.assertEqual(evidence["status"], "AUTH_FAILED")
        self.assertEqual(evidence["failure_stage"], "decrypt")
        self.assertEqual(
            evidence["token_exchange_diagnostics"]["message"],
            MODULE.DECRYPT_FAILED_MESSAGE,
        )
        self.assertEqual(
            evidence["token_exchange_diagnostics"]["detail"],
            "bad decrypt [REDACTED]",
        )
        self.assertEqual(stderr.getvalue().strip(), MODULE.DECRYPT_FAILED_MESSAGE)
        urlopen.assert_not_called()

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
