"""Offline tests for the Google Drive workspace content-control example."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from http.client import IncompleteRead
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError, URLError
from urllib.request import Request

import google_drive_access_admin as drive_access

WORKSPACE_ID = "2a171a87-9cc8-453c-b7c4-0e0316903eb3"
POLICY_URL = (
    f"https://api.chatgpt.com/v1/manage/workspaces/{WORKSPACE_ID}"
    "/google-drive/drive-access/allow-list"
)
GOOGLE_URL = "https://www.googleapis.com/drive/v3/drives/DriveA?fields=id,name"
ROOT_URL = "https://drive.google.com/drive/folders/DriveA"
ADMIN_TOKEN = "test-admin-token"
GOOGLE_TOKEN = "test-google-token"


def policy(allowed, personal=False):
    return {
        "object": "workspace.google_drive.access_policy",
        "allow_list": allowed,
        "allow_personal_drive": personal,
    }


class CommandTests(unittest.TestCase):
    def setUp(self):
        environment = mock.patch.dict(
            drive_access.os.environ,
            {"CHATGPT_ADMIN_TOKEN": ADMIN_TOKEN, "GOOGLE_DRIVE_TOKEN": GOOGLE_TOKEN},
            clear=True,
        )
        environment.start()
        self.addCleanup(environment.stop)
        request = mock.patch.object(drive_access, "request_json")
        self.request = request.start()
        self.addCleanup(request.stop)

    def run_command(self, action, *arguments, responses):
        self.request.reset_mock()
        self.request.side_effect = responses
        stdout = io.StringIO()
        argv = [action, *arguments]
        if action != "inspect":
            argv[1:1] = ["--workspace-id", WORKSPACE_ID]
        with mock.patch("sys.stdout", stdout), mock.patch("sys.stderr", io.StringIO()):
            drive_access.main(argv)
        return json.loads(stdout.getvalue())

    def assert_methods(self, *methods):
        self.assertEqual(
            [call.args[0] for call in self.request.call_args_list], list(methods)
        )

    def test_list_preserves_all_none_and_my_drive_false(self):
        for allowed in (None, [], ["DriveA"]):
            with self.subTest(allowed=allowed):
                result = self.run_command("list", responses=[policy(allowed)])
                self.assertEqual(result, policy(allowed))
                self.request.assert_called_once_with("GET", POLICY_URL, ADMIN_TOKEN)

    def test_replace_replaces_whole_list_and_omits_unchanged_my_drive(self):
        result = self.run_command(
            "replace",
            "--drive-id",
            "DriveB",
            responses=[policy(["DriveA"]), policy(["DriveB"])],
        )
        self.assertEqual(result["policy"], policy(["DriveB"]))
        self.assert_methods("GET", "PUT")
        self.assertEqual(
            self.request.call_args,
            mock.call("PUT", POLICY_URL, ADMIN_TOKEN, body={"drive_ids": ["DriveB"]}),
        )

    def test_explicit_my_drive_values_are_json_booleans(self):
        for choice, expected in (("allow", True), ("block", False)):
            with self.subTest(choice=choice):
                self.run_command(
                    "replace",
                    "--drive-id",
                    "DriveB",
                    "--my-drive",
                    choice,
                    responses=[
                        policy(["DriveA"], not expected),
                        policy(["DriveB"], expected),
                    ],
                )
                self.assertEqual(
                    self.request.call_args.kwargs["body"],
                    {"drive_ids": ["DriveB"], "allow_personal_drive": expected},
                )

    def test_add_and_remove_send_complete_replacements(self):
        cases = [
            ("add", ["DriveA", "drivea"], "DriveB", ["DriveA", "DriveB", "drivea"]),
            ("remove", ["DriveA", "DriveB"], "DriveA", ["DriveB"]),
        ]
        for action, current, requested, expected in cases:
            with self.subTest(action=action):
                self.run_command(
                    action,
                    "--drive-id",
                    requested,
                    responses=[policy(current), policy(expected)],
                )
                self.assert_methods("GET", "PUT")
                self.assertEqual(
                    self.request.call_args.kwargs["body"], {"drive_ids": expected}
                )

    def test_incremental_changes_reject_unrestricted_policy(self):
        for action in ("add", "remove"):
            with self.subTest(action=action):
                with self.assertRaisesRegex(
                    SystemExit, "exclude lists are unsupported"
                ):
                    self.run_command(
                        action, "--drive-id", "DriveA", responses=[policy(None)]
                    )
                self.assert_methods("GET")

    def test_removing_last_drive_requires_confirmation(self):
        with self.assertRaises(SystemExit):
            self.run_command(
                "remove", "--drive-id", "DriveA", responses=[policy(["DriveA"])]
            )
        self.assert_methods("GET")
        self.run_command(
            "remove",
            "--drive-id",
            "DriveA",
            "--yes",
            responses=[policy(["DriveA"]), policy([])],
        )
        self.assertEqual(self.request.call_args.kwargs["body"], {"drive_ids": []})

    def test_reset_allows_shared_drives_and_preserves_my_drive(self):
        result = self.run_command(
            "reset", "--yes", responses=[policy(["DriveA"]), policy(None)]
        )
        self.assertEqual(result["policy"], policy(None))
        self.assert_methods("GET", "DELETE")
        self.assertEqual(
            self.request.call_args,
            mock.call("DELETE", POLICY_URL, ADMIN_TOKEN, body=None),
        )

    def test_reset_and_block_all_require_confirmation(self):
        for action in ("reset", "block-all"):
            with self.subTest(action=action):
                with self.assertRaises(SystemExit):
                    self.run_command(action, responses=[policy(["DriveA"])])
                self.assert_methods("GET")

    def test_set_my_drive_preserves_all_shared_drive_states(self):
        for allowed in (None, [], ["DriveA"]):
            with self.subTest(allowed=allowed):
                self.run_command(
                    "set-my-drive",
                    "--my-drive",
                    "allow",
                    responses=[policy(allowed), policy(allowed, True)],
                )
                self.assertEqual(
                    self.request.call_args.kwargs["body"],
                    {"drive_ids": allowed, "allow_personal_drive": True},
                )

    def test_dry_run_previews_changes_without_write_or_confirmation(self):
        cases = [
            ("replace", ["--drive-id", "DriveB"], ["DriveB"], False),
            ("remove", ["--drive-id", "DriveA"], [], False),
            ("reset", [], None, False),
            ("block-all", [], [], False),
            ("set-my-drive", ["--my-drive", "allow"], ["DriveA"], True),
        ]
        for action, arguments, allowed, personal in cases:
            with self.subTest(action=action):
                result = self.run_command(
                    action, *arguments, "--dry-run", responses=[policy(["DriveA"])]
                )
                self.assertTrue(result["dry_run"])
                self.assertEqual(result["proposed_policy"], policy(allowed, personal))
                self.assert_methods("GET")

    def test_noops_do_not_write(self):
        cases = [
            ("replace", ["DriveA"], ["--drive-id", "DriveA"]),
            ("add", ["DriveA"], ["--drive-id", "DriveA"]),
            ("remove", ["DriveA"], ["--drive-id", "DriveB"]),
            ("reset", None, []),
            ("block-all", [], []),
            ("set-my-drive", ["DriveA"], ["--my-drive", "block"]),
        ]
        for action, allowed, arguments in cases:
            with self.subTest(action=action):
                result = self.run_command(
                    action, *arguments, responses=[policy(allowed)]
                )
                self.assertEqual(result, {"changed": False, "policy": policy(allowed)})
                self.assert_methods("GET")

    def test_incomplete_or_invalid_policy_stops_writes(self):
        invalid = [
            {},
            {"allow_list": []},
            {
                "object": "workspace.google_drive.access_policy",
                "allow_personal_drive": False,
            },
            {**policy([]), "object": "other"},
            policy([], "false"),
            policy([], 0),
            policy([], None),
            policy({}),
            policy(["root"]),
            policy(["DriveA", 123]),
            policy(["DriveA"] * 1001),
        ]
        for current in invalid:
            with self.subTest(current=current):
                with self.assertRaises(SystemExit):
                    self.run_command(
                        "replace", "--drive-id", "DriveB", responses=[current]
                    )
                self.assert_methods("GET")

    def test_add_checks_result_limit_before_writing(self):
        current = [f"Drive{i:04d}" for i in range(1000)]
        with self.assertRaisesRegex(SystemExit, "resulting policy exceeds"):
            self.run_command(
                "add", "--drive-id", "DriveExtra", responses=[policy(current)]
            )
        self.assert_methods("GET")

    def test_files_preserve_case_and_deduplicate_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            for filename, contents in (
                ("drives.txt", "# approved drives\n\n DriveA \ndrivea\nDriveB\n"),
                (
                    "drives.csv",
                    "\ufeffdrive_id,description\nDriveA,First\ndrivea,Second\nDriveB,Third\n",
                ),
            ):
                with self.subTest(filename=filename):
                    path = Path(directory) / filename
                    path.write_text(contents, encoding="utf-8")
                    self.run_command(
                        "replace",
                        "--drive-id",
                        "DriveA",
                        "--drives-file",
                        str(path),
                        responses=[policy([]), policy(["DriveA", "DriveB", "drivea"])],
                    )
                    self.assertEqual(
                        self.request.call_args.kwargs["body"],
                        {"drive_ids": ["DriveA", "DriveB", "drivea"]},
                    )

    def test_empty_files_cannot_accidentally_block_all_drives(self):
        with tempfile.TemporaryDirectory() as directory:
            for filename, contents in (
                ("empty.txt", "# nothing selected\n \n"),
                ("empty.csv", "drive_id\n\n"),
            ):
                with self.subTest(filename=filename):
                    path = Path(directory) / filename
                    path.write_text(contents, encoding="utf-8")
                    with self.assertRaises(SystemExit):
                        self.run_command(
                            "replace", "--drives-file", str(path), responses=[]
                        )
                    self.request.assert_not_called()

    def test_malformed_csv_is_rejected_before_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "drives.csv"
            for contents in (
                "name\nDriveA\n",
                "drive_id,drive_url\nDriveA,\n",
                "drive_id,drive_id\nDriveA,DriveB\n",
                "drive_id\nDriveA,DriveB\n",
                'drive_id\n"DriveA\n',
            ):
                with self.subTest(contents=contents):
                    path.write_text(contents, encoding="utf-8")
                    with self.assertRaises(SystemExit):
                        self.run_command(
                            "replace", "--drives-file", str(path), responses=[]
                        )
                    self.request.assert_not_called()

    def test_invalid_ids_and_urls_fail_before_requests(self):
        references = [
            ("--drive-id", "root"),
            ("--drive-id", "abcd"),
            ("--drive-id", "x" * 513),
            ("--drive-id", "Drive A"),
            ("--drive-id", "DrivéA"),
            ("--drive-id", ROOT_URL),
            ("--drive-url", "DriveA"),
            ("--drive-url", "http://drive.google.com/drive/folders/DriveA"),
            ("--drive-url", "https://drive.google.com.evil.test/drive/folders/DriveA"),
            ("--drive-url", "https://user@drive.google.com/drive/folders/DriveA"),
            ("--drive-url", "https://drive.google.com:443/drive/folders/DriveA"),
            ("--drive-url", "https://drive.google.com/file/d/DriveA/view"),
            ("--drive-url", "https://drive.google.com/drive/folders/root"),
            ("--drive-url", "https://drive.google.com/drive/folders/Drive%2FA"),
            ("--drive-url", "https://[drive.google.com/drive/folders/DriveA"),
        ]
        for option, value in references:
            with self.subTest(option=option, value=value):
                with self.assertRaises(SystemExit):
                    self.run_command("replace", option, value, responses=[])
                self.request.assert_not_called()

    def test_invalid_command_options_fail_before_requests(self):
        for action, arguments in (
            ("replace", []),
            ("set-my-drive", []),
            ("reset", ["--my-drive", "block"]),
            ("list", ["--drive-id", "DriveA"]),
            ("replace", ["--drive-id", "DriveA", "--workspace-id", "invalid"]),
            ("list", ["--api-base-url", "https://other.example"]),
        ):
            with self.subTest(action=action, arguments=arguments):
                with self.assertRaises(SystemExit):
                    self.run_command(action, *arguments, responses=[])
                self.request.assert_not_called()
        with mock.patch.dict(drive_access.os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                self.run_command("list", responses=[])
            self.request.assert_not_called()

    def test_all_text_references_are_validated_before_google_requests(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "drives.txt"
            path.write_text(f"{ROOT_URL}\ninvalid name\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                self.run_command("replace", "--drives-file", str(path), responses=[])
        self.request.assert_not_called()

    def test_root_urls_are_verified_once_and_tokens_stay_on_their_origins(self):
        self.run_command(
            "replace",
            "--drive-id",
            "DriveA",
            "--drive-url",
            ROOT_URL,
            responses=[
                {"id": "DriveA", "name": "Company"},
                policy([]),
                policy(["DriveA"]),
            ],
        )
        self.assertEqual(
            self.request.call_args_list,
            [
                mock.call("GET", GOOGLE_URL, GOOGLE_TOKEN),
                mock.call("GET", POLICY_URL, ADMIN_TOKEN),
                mock.call(
                    "PUT", POLICY_URL, ADMIN_TOKEN, body={"drive_ids": ["DriveA"]}
                ),
            ],
        )

    def test_url_verification_and_inspection_require_google_token(self):
        with mock.patch.dict(
            drive_access.os.environ, {"CHATGPT_ADMIN_TOKEN": ADMIN_TOKEN}, clear=True
        ):
            for action, arguments in (
                ("replace", ["--drive-url", ROOT_URL]),
                ("inspect", ["--drive-id", "DriveA"]),
            ):
                with self.subTest(action=action):
                    with self.assertRaisesRegex(SystemExit, "GOOGLE_DRIVE_TOKEN"):
                        self.run_command(action, *arguments, responses=[])
                    self.request.assert_not_called()

    def test_inspection_accepts_account_root_urls_without_admin_credentials(self):
        with mock.patch.dict(
            drive_access.os.environ, {"GOOGLE_DRIVE_TOKEN": GOOGLE_TOKEN}, clear=True
        ):
            result = self.run_command(
                "inspect",
                "--drive-url",
                "https://drive.google.com/drive/u/0/folders/DriveA?usp=sharing",
                responses=[{"id": "DriveA", "name": "Company"}],
            )
        self.assertEqual(result, {"drives": [{"id": "DriveA", "name": "Company"}]})
        self.request.assert_called_once_with("GET", GOOGLE_URL, GOOGLE_TOKEN)

    def test_bad_google_metadata_stops_before_admin_policy_read(self):
        for metadata in (
            {"id": "OtherDrive", "name": "Company"},
            {"id": "DriveA"},
            {"id": "DriveA", "name": 7},
        ):
            with self.subTest(metadata=metadata):
                with self.assertRaisesRegex(
                    SystemExit, "unexpected shared-drive metadata"
                ):
                    self.run_command(
                        "replace", "--drive-url", ROOT_URL, responses=[metadata]
                    )
                self.request.assert_called_once_with("GET", GOOGLE_URL, GOOGLE_TOKEN)

    def test_id_limits_apply_after_client_deduplication(self):
        self.assertEqual(
            drive_access.resolve_drives(["DriveA"] * 1001 + ["drivea"]),
            [{"id": "DriveA"}, {"id": "drivea"}],
        )
        thousand = [f"Drive{i:04d}" for i in range(1000)]
        self.assertEqual(len(drive_access.resolve_drives(thousand)), 1000)
        with self.assertRaisesRegex(SystemExit, "at most 1,000"):
            drive_access.resolve_drives([*thousand, "ExtraDrive"])
        self.assertEqual(drive_access.validate_drive_id("x" * 512), "x" * 512)
        self.request.assert_not_called()


class TransportTests(unittest.TestCase):
    def setUp(self):
        opener = mock.patch.object(drive_access, "build_opener")
        self.build_opener = opener.start()
        self.addCleanup(opener.stop)
        self.open = self.build_opener.return_value.open
        sleep = mock.patch.object(drive_access.time, "sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def http_error(self, code):
        return HTTPError(
            POLICY_URL, code, "Private response", {}, io.BytesIO(b"private body")
        )

    def test_reads_retry_transient_http_and_network_errors(self):
        for error in [self.http_error(code) for code in (429, 502, 503, 504)] + [
            URLError("offline"),
            TimeoutError(),
            ConnectionResetError("reset"),
            IncompleteRead(b"partial response"),
        ]:
            with self.subTest(error=error):
                self.open.reset_mock()
                self.sleep.reset_mock()
                self.open.side_effect = [error, io.BytesIO(b'{"ok": true}')]
                self.assertEqual(
                    drive_access.request_json("GET", POLICY_URL, ADMIN_TOKEN),
                    {"ok": True},
                )
                self.assertEqual(self.open.call_count, 2)
                self.sleep.assert_called_once_with(1)

    def test_read_retries_are_bounded(self):
        self.open.side_effect = [self.http_error(503) for _ in range(3)]
        with self.assertRaisesRegex(SystemExit, "HTTP 503"):
            drive_access.request_json("GET", POLICY_URL, ADMIN_TOKEN)
        self.assertEqual(self.open.call_count, 3)
        self.assertEqual(self.sleep.call_args_list, [mock.call(1), mock.call(2)])

    def test_writes_never_retry_and_explain_uncertain_outcomes(self):
        for method in ("PUT", "DELETE"):
            for error in [self.http_error(code) for code in (409, 429, 503)] + [
                URLError("offline"),
                TimeoutError(),
                ConnectionResetError("reset"),
                IncompleteRead(b"partial response"),
            ]:
                with self.subTest(method=method, error=error):
                    self.open.reset_mock()
                    self.sleep.reset_mock()
                    self.open.side_effect = error
                    with self.assertRaisesRegex(
                        SystemExit, "Read the current policy before retrying"
                    ) as caught:
                        drive_access.request_json(
                            method, POLICY_URL, ADMIN_TOKEN, body={"drive_ids": []}
                        )
                    self.open.assert_called_once()
                    self.sleep.assert_not_called()
                    self.assertNotIn(ADMIN_TOKEN, str(caught.exception))
                    self.assertNotIn("private body", str(caught.exception))

    def test_reads_do_not_retry_permanent_http_errors(self):
        for status in (400, 401, 403, 404):
            with self.subTest(status=status):
                self.open.reset_mock()
                self.sleep.reset_mock()
                self.open.side_effect = self.http_error(status)
                with self.assertRaisesRegex(SystemExit, f"HTTP {status}"):
                    drive_access.request_json("GET", POLICY_URL, ADMIN_TOKEN)
                self.open.assert_called_once()
                self.sleep.assert_not_called()

    def test_invalid_json_or_non_object_response_is_not_retried(self):
        for payload in (b"not JSON", b"[]", b"null", b'"private-token"'):
            with self.subTest(payload=payload):
                self.open.reset_mock()
                self.open.return_value = io.BytesIO(payload)
                with self.assertRaisesRegex(
                    SystemExit, "invalid JSON response"
                ) as caught:
                    drive_access.request_json("GET", POLICY_URL, ADMIN_TOKEN)
                self.open.assert_called_once()
                self.sleep.assert_not_called()
                self.assertNotIn("private-token", str(caught.exception))

    def test_request_headers_json_false_and_no_redirect_handler(self):
        self.open.return_value = io.BytesIO(b'{"ok": true}')
        body = {"drive_ids": [], "allow_personal_drive": False}
        drive_access.request_json("PUT", POLICY_URL, ADMIN_TOKEN, body=body)
        request = self.open.call_args.args[0]
        self.assertEqual(request.full_url, POLICY_URL)
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(request.get_header("Authorization"), f"Bearer {ADMIN_TOKEN}")
        self.assertEqual(request.get_header("Content-type"), "application/json")
        self.assertEqual(json.loads(request.data), body)
        self.assertFalse(request.has_header("Idempotency-key"))
        self.assertEqual(self.open.call_args.kwargs, {"timeout": 30})
        self.assertIsInstance(
            self.build_opener.call_args.args[0], drive_access.NoRedirect
        )

    def test_redirects_are_rejected_instead_of_forwarding_tokens(self):
        request = Request(
            POLICY_URL, headers={"Authorization": f"Bearer {ADMIN_TOKEN}"}
        )
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                with self.assertRaises(HTTPError) as caught:
                    drive_access.NoRedirect().redirect_request(
                        request,
                        None,
                        status,
                        "redirect",
                        {},
                        "https://other.example/policy",
                    )
                self.assertEqual(caught.exception.code, status)
                self.assertEqual(caught.exception.url, POLICY_URL)
        self.open.assert_not_called()


if __name__ == "__main__":
    unittest.main()
