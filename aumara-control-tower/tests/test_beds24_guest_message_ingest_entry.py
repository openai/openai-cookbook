from __future__ import annotations

import pathlib
import sys
import unittest
from unittest import mock

SCRIPTS = pathlib.Path(__file__).resolve().parents[1] / "scripts"
REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(SCRIPTS))

import beds24_guest_message_ingest_entry as entry  # noqa: E402


class EntryTests(unittest.TestCase):
    def test_workflow_keeps_secret_out_of_pull_request_and_push_jobs(self):
        workflow = (
            REPOSITORY_ROOT
            / ".github"
            / "workflows"
            / "beds24-guest-message-ingest.yml"
        ).read_text(encoding="utf-8")
        live_job = workflow.split("  live-readonly-proof:\n", 1)[1]

        self.assertIn(
            "github.event_name == 'workflow_dispatch'",
            live_job,
        )
        self.assertIn(
            "RUN_BEDS24_READONLY_PROOF",
            live_job,
        )
        self.assertNotIn("github.event_name == 'push'", live_job)
        self.assertNotIn("github.event_name == 'pull_request'", live_job)
        self.assertEqual(
            workflow.count(
                "BEDS24_TOKEN_CREDENTIAL: "
                "${{ secrets.BEDS24_TOKEN_CREDENTIAL }}"
            ),
            1,
        )

    def test_scope_names_are_extracted_without_other_diagnostics(self):
        details = {
            "diagnostics": {
                "scopes": ["bookings", "bookings-personal", "unknown-scope"],
                "note": "properties inventory",
                "account": "private-value",
            }
        }
        self.assertEqual(
            entry.extract_scope_names(details),
            ["bookings", "bookings-personal", "inventory", "properties"],
        )

    def test_existing_access_token_is_reused_after_readonly_probe(self):
        calls = []

        def request(url, headers, secrets=(), redact=True):
            calls.append((url, headers, secrets, redact))
            return 200, {"diagnostics": {"scopes": ["bookings-personal"]}}

        with mock.patch.object(entry.auth, "get_credential", return_value="access"), \
             mock.patch.object(entry.auth, "request_json", side_effect=request):
            (
                token,
                mode,
                api_base,
                source,
                scopes,
                redaction_key,
            ) = entry.resolve_access_token()

        self.assertEqual(token, "access")
        self.assertEqual(mode, "access_token")
        self.assertEqual(api_base, entry.auth.API_BASE)
        self.assertEqual(source, entry.auth.CREDENTIAL_SOURCE)
        self.assertEqual(scopes, ["bookings-personal"])
        self.assertEqual(redaction_key, "access")
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0][0].endswith("/authentication/details"))
        self.assertEqual(calls[0][1], {"token": "access"})

    def test_refresh_credential_is_exchanged_and_probed(self):
        responses = [
            (401, {"message": "not access"}),
            (200, {"token": " temporary-token "}),
            (200, {"diagnostics": {"scopes": ["bookings-personal"]}}),
        ]
        calls = []

        def request(url, headers, secrets=(), redact=True):
            calls.append((url, headers, secrets, redact))
            return responses.pop(0)

        with mock.patch.object(entry.auth, "get_credential", return_value="refresh"), \
             mock.patch.object(entry.auth, "request_json", side_effect=request):
            token, mode, _, _, scopes, redaction_key = (
                entry.resolve_access_token()
            )

        self.assertEqual(token, "temporary-token")
        self.assertEqual(mode, "refresh_token")
        self.assertEqual(scopes, ["bookings-personal"])
        self.assertEqual(redaction_key, "refresh")
        self.assertEqual(len(calls), 3)
        self.assertTrue(calls[1][0].endswith("/authentication/token"))
        self.assertEqual(calls[1][1], {"refreshToken": "refresh"})
        self.assertFalse(calls[1][3])
        self.assertTrue(calls[2][0].endswith("/authentication/details"))
        self.assertEqual(calls[2][1], {"token": "temporary-token"})

    def test_invalid_credential_fails_without_setup_or_write_endpoint(self):
        calls = []

        def request(url, headers, secrets=(), redact=True):
            calls.append(url)
            return 401, {}

        with mock.patch.object(entry.auth, "get_credential", return_value="bad"), \
             mock.patch.object(entry.auth, "request_json", side_effect=request):
            with self.assertRaisesRegex(entry.ingest.IngestError, "HTTP 401/401"):
                entry.resolve_access_token()

        self.assertEqual(len(calls), 2)
        self.assertFalse(any("/authentication/setup" in url for url in calls))
        self.assertFalse(any(url.endswith("/bookings") for url in calls))

    def test_missing_credential_fails_before_network(self):
        with mock.patch.object(entry.auth, "get_credential", return_value=""), \
             mock.patch.object(entry.auth, "request_json") as request:
            with self.assertRaisesRegex(entry.ingest.IngestError, "is missing"):
                entry.resolve_access_token()
        request.assert_not_called()

    def test_build_report_adds_only_redacted_auth_metadata(self):
        report = {
            "summary": {"messagesScanned": 0},
            "safety": {"bookingMutations": 0},
        }
        with mock.patch.object(
            entry,
            "resolve_access_token",
            return_value=(
                "secret-access-token",
                "access_token",
                "https://api.beds24.com/v2",
                "BEDS24_TOKEN_CREDENTIAL",
                ["bookings", "bookings-personal"],
                "stable-redaction-key",
            ),
        ), mock.patch.object(entry.ingest, "run", return_value=report) as run:
            result = entry.build_report(3)

        run.assert_called_once()
        self.assertEqual(
            run.call_args.kwargs["redaction_key"],
            "stable-redaction-key",
        )
        self.assertEqual(result["status"], "OK")
        self.assertEqual(result["authentication"]["mode"], "access_token")
        self.assertEqual(result["authentication"]["source"], "BEDS24_TOKEN_CREDENTIAL")
        self.assertEqual(result["authentication"]["apiHost"], "api.beds24.com")
        self.assertEqual(
            result["authentication"]["scopes"],
            ["bookings", "bookings-personal"],
        )
        self.assertTrue(result["authentication"]["bookingsPersonalScopePresent"])
        self.assertFalse(result["authentication"]["secretLogged"])
        self.assertNotIn("secret-access-token", str(result))
        self.assertNotIn("stable-redaction-key", str(result))

    def test_401_message_access_creates_exact_blocker_report(self):
        with mock.patch.object(
            entry,
            "resolve_access_token",
            return_value=(
                "secret-access-token",
                "access_token",
                "https://api.beds24.com/v2",
                "BEDS24_TOKEN_CREDENTIAL",
                ["bookings"],
                "stable-redaction-key",
            ),
        ), mock.patch.object(
            entry.ingest,
            "run",
            side_effect=entry.ingest.IngestError(
                "Guest-message lookup failed with HTTP 401"
            ),
        ):
            result = entry.build_report(3)

        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["blocker"]["code"], "MISSING_BOOKINGS_PERSONAL_SCOPE")
        self.assertEqual(result["blocker"]["requiredScope"], "bookings-personal")
        self.assertEqual(result["blocker"]["httpStatus"], 401)
        self.assertFalse(
            result["authentication"]["bookingsPersonalScopePresent"]
        )
        self.assertEqual(result["safety"]["guestMessagesSent"], 0)
        self.assertEqual(result["safety"]["bookingMutations"], 0)
        self.assertNotIn("secret-access-token", str(result))

    def test_unknown_scope_list_reports_access_denied_not_missing(self):
        report = entry.blocked_report(
            error="Guest-message lookup failed with HTTP 401",
            auth_mode="access_token",
            api_base="https://api.beds24.com/v2",
            auth_source="BEDS24_TOKEN_CREDENTIAL",
            scopes=[],
            max_age_days=3,
        )
        self.assertEqual(
            report["blocker"]["code"], "BOOKINGS_PERSONAL_ACCESS_DENIED"
        )
        self.assertIsNone(
            report["authentication"]["bookingsPersonalScopePresent"]
        )


if __name__ == "__main__":
    unittest.main()
