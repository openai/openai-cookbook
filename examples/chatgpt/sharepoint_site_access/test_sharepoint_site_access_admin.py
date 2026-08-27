"""Offline tests for the SharePoint site-collection allowlist example."""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock
from urllib.error import HTTPError

import sharepoint_site_access_admin as site_access

WORKSPACE_ID = "2a171a87-9cc8-453c-b7c4-0e0316903eb3"
COLLECTION_GUID = "da60e844-ba1d-49bc-b4d4-d5e36bae9019"
WEB_GUID = "712a596e-90a1-49e3-9b48-bfa80bee8740"
SITE_URL = "https://contoso.sharepoint.com/sites/Finance"
IDEMPOTENCY_KEY = "3b5e9666-f01e-4f8b-9336-e70b67c07cf5"
ALLOWLIST_URL = (
    f"https://api.chatgpt.com/v1/manage/workspaces/{WORKSPACE_ID}"
    "/sharepoint/site-access/allow-list"
)


def graph_site(*, web_guid: str = WEB_GUID) -> dict[str, str]:
    return {
        "id": f"contoso.sharepoint.com,{COLLECTION_GUID},{web_guid}",
        "webUrl": SITE_URL,
    }


class RequestJsonTests(unittest.TestCase):
    @mock.patch.object(site_access, "urlopen")
    def test_sends_idempotency_header_only_when_provided(
        self, urlopen: mock.Mock
    ) -> None:
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok":true}'
        urlopen.return_value = response

        site_access.request_json(
            "PUT",
            "https://api.chatgpt.com/example",
            "admin-token",
            body={"collection_guids": [COLLECTION_GUID]},
            idempotency_key=IDEMPOTENCY_KEY,
        )

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Idempotency-key"), IDEMPOTENCY_KEY)

        site_access.request_json(
            "GET", "https://api.chatgpt.com/example", "admin-token"
        )

        request_without_key = urlopen.call_args.args[0]
        self.assertFalse(request_without_key.has_header("Idempotency-key"))

    @mock.patch.object(site_access.time, "sleep")
    @mock.patch.object(site_access, "urlopen")
    def test_retries_temporary_rate_limit(
        self, urlopen: mock.Mock, sleep: mock.Mock
    ) -> None:
        throttled = HTTPError(
            "https://api.chatgpt.com/example",
            429,
            "Too Many Requests",
            None,
            io.BytesIO(b'{"error":"rate limited"}'),
        )
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b'{"ok":true}'
        urlopen.side_effect = [throttled, response]

        result = site_access.request_json(
            "GET", "https://api.chatgpt.com/example", "admin-token"
        )

        self.assertEqual(result, {"ok": True})
        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(1)

    @mock.patch.object(site_access.time, "sleep")
    @mock.patch.object(site_access, "urlopen")
    def test_does_not_retry_authorization_failures(
        self, urlopen: mock.Mock, sleep: mock.Mock
    ) -> None:
        urlopen.side_effect = HTTPError(
            "https://api.chatgpt.com/example",
            403,
            "Forbidden",
            None,
            io.BytesIO(b'{"error":"permission denied"}'),
        )

        with self.assertRaisesRegex(SystemExit, "HTTP 403"):
            site_access.request_json(
                "GET", "https://api.chatgpt.com/example", "admin-token"
            )

        urlopen.assert_called_once()
        sleep.assert_not_called()


class ResolveSharePointUrlTests(unittest.TestCase):
    @mock.patch.object(site_access, "request_json")
    def test_resolves_and_normalizes_collection_guid(
        self, request_json: mock.Mock
    ) -> None:
        request_json.return_value = graph_site()

        result = site_access.resolve_sharepoint_url(SITE_URL, "graph-token")

        self.assertEqual(result["collection_guid"], COLLECTION_GUID)
        self.assertEqual(
            result["site_id"], f"contoso.sharepoint.com,{COLLECTION_GUID},{WEB_GUID}"
        )
        request_json.assert_called_once_with(
            "GET",
            "https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com:/sites/Finance"
            "?%24select=id%2CwebUrl",
            "graph-token",
        )

    @mock.patch.object(site_access, "request_json")
    def test_preserves_percent_encoded_sharepoint_paths(
        self, request_json: mock.Mock
    ) -> None:
        request_json.return_value = graph_site()

        site_access.resolve_sharepoint_url(
            "https://contoso.sharepoint.com/sites/Finance%20Team", "graph-token"
        )

        request_json.assert_called_once_with(
            "GET",
            "https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com:"
            "/sites/Finance%20Team?%24select=id%2CwebUrl",
            "graph-token",
        )

    @mock.patch.object(site_access, "request_json")
    def test_uses_by_path_syntax_for_tenant_root_site(
        self, request_json: mock.Mock
    ) -> None:
        request_json.return_value = graph_site()

        site_access.resolve_sharepoint_url(
            "https://contoso.sharepoint.com/", "graph-token"
        )

        request_json.assert_called_once_with(
            "GET",
            "https://graph.microsoft.com/v1.0/sites/contoso.sharepoint.com:/"
            "?%24select=id%2CwebUrl",
            "graph-token",
        )

    def test_rejects_non_https_urls(self) -> None:
        with self.assertRaisesRegex(SystemExit, "valid HTTPS URLs"):
            site_access.resolve_sharepoint_url(
                "http://contoso.sharepoint.com/sites/Finance", "token"
            )

    @mock.patch.object(site_access, "request_json")
    def test_rejects_mismatched_graph_hostname(self, request_json: mock.Mock) -> None:
        request_json.return_value = {
            "id": f"other.sharepoint.com,{COLLECTION_GUID},{WEB_GUID}"
        }

        with self.assertRaisesRegex(SystemExit, "unexpected site ID"):
            site_access.resolve_sharepoint_url(SITE_URL, "graph-token")

    @mock.patch.object(site_access, "request_json")
    def test_rejects_invalid_graph_guids(self, request_json: mock.Mock) -> None:
        request_json.return_value = {
            "id": f"contoso.sharepoint.com,not-a-guid,{WEB_GUID}"
        }

        with self.assertRaisesRegex(SystemExit, "invalid site ID"):
            site_access.resolve_sharepoint_url(SITE_URL, "graph-token")


class ReadSiteUrlsTests(unittest.TestCase):
    def test_reads_csv_and_deduplicates_inline_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sites_file = Path(directory) / "sites.csv"
            sites_file.write_text(
                "site_url\nhttps://contoso.sharepoint.com/sites/Finance\n"
                "https://contoso.sharepoint.com/sites/Research\n",
                encoding="utf-8",
            )

            result = site_access.read_site_urls([SITE_URL], str(sites_file))

        self.assertEqual(
            result, [SITE_URL, "https://contoso.sharepoint.com/sites/Research"]
        )

    def test_reads_text_and_skips_comments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sites_file = Path(directory) / "sites.txt"
            sites_file.write_text(f"# Approved sites\n\n{SITE_URL}\n", encoding="utf-8")

            result = site_access.read_site_urls([], str(sites_file))

        self.assertEqual(result, [SITE_URL])

    def test_skips_csv_rows_with_missing_or_empty_site_urls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sites_file = Path(directory) / "sites.csv"
            sites_file.write_text(
                f"name,site_url\nFinance\nEmpty,\nResearch,{SITE_URL}\n",
                encoding="utf-8",
            )

            result = site_access.read_site_urls([], str(sites_file))

        self.assertEqual(result, [SITE_URL])

    def test_rejects_csv_without_site_url_column(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            sites_file = Path(directory) / "sites.csv"
            sites_file.write_text("name\nFinance\n", encoding="utf-8")

            with self.assertRaisesRegex(SystemExit, "site_url or url column"):
                site_access.read_site_urls([], str(sites_file))


class AllowlistCommandTests(unittest.TestCase):
    def run_command(
        self,
        arguments: list[str],
        *,
        responses: list[dict[str, object]],
    ) -> tuple[dict[str, object], mock.Mock]:
        output = io.StringIO()
        environment = {
            "MICROSOFT_GRAPH_TOKEN": "graph-token",
            "CHATGPT_ADMIN_TOKEN": "admin-token",
        }
        with (
            mock.patch("sys.argv", ["sharepoint_site_access_admin.py", *arguments]),
            mock.patch.dict(site_access.os.environ, environment, clear=True),
            mock.patch.object(
                site_access, "request_json", side_effect=responses
            ) as request_json,
            mock.patch("sys.stdout", output),
        ):
            site_access.main()

        return json.loads(output.getvalue()), request_json

    def test_inspect_does_not_call_chatgpt_admin_api(self) -> None:
        result, request_json = self.run_command(
            ["inspect", "--site-url", SITE_URL], responses=[graph_site()]
        )

        self.assertEqual(result["collection_guids"], [COLLECTION_GUID])
        self.assertEqual(request_json.call_count, 1)

    def test_add_deduplicates_collections_and_uses_one_put(self) -> None:
        research_url = "https://contoso.sharepoint.com/sites/Research"
        second_web_guid = "4318127b-8167-42de-82f3-e4e41a6e5c1a"
        result, request_json = self.run_command(
            [
                "add",
                "--workspace-id",
                WORKSPACE_ID,
                "--site-url",
                SITE_URL,
                "--site-url",
                research_url,
            ],
            responses=[
                graph_site(),
                graph_site(web_guid=second_web_guid),
                {"allow_list": {}},
                {"allow_list": {COLLECTION_GUID: {}}},
            ],
        )

        self.assertEqual(result["processed_count"], 1)
        self.assertEqual(
            request_json.call_args,
            mock.call(
                "PUT",
                ALLOWLIST_URL,
                "admin-token",
                body={"collection_guids": [COLLECTION_GUID]},
                idempotency_key=None,
            ),
        )

    def test_add_forwards_optional_idempotency_key(self) -> None:
        result, request_json = self.run_command(
            [
                "add",
                "--workspace-id",
                WORKSPACE_ID,
                "--site-url",
                SITE_URL,
                "--idempotency-key",
                IDEMPOTENCY_KEY,
            ],
            responses=[graph_site(), {"allow_list": {}}, {"allow_list": {}}],
        )

        self.assertEqual(result["processed_count"], 1)
        self.assertEqual(
            request_json.call_args,
            mock.call(
                "PUT",
                ALLOWLIST_URL,
                "admin-token",
                body={"collection_guids": [COLLECTION_GUID]},
                idempotency_key=IDEMPOTENCY_KEY,
            ),
        )

    def test_dry_run_reads_policy_without_writing(self) -> None:
        result, request_json = self.run_command(
            [
                "add",
                "--workspace-id",
                WORKSPACE_ID,
                "--site-url",
                SITE_URL,
                "--dry-run",
            ],
            responses=[graph_site(), {"allow_list": {}}],
        )

        self.assertTrue(result["dry_run"])
        self.assertEqual(result["collection_guids"], [COLLECTION_GUID])
        self.assertEqual(
            [call.args[0] for call in request_json.call_args_list], ["GET", "GET"]
        )

    def test_add_rejects_empty_input_before_any_request(self) -> None:
        with (
            mock.patch("sys.argv", ["script", "add", "--workspace-id", WORKSPACE_ID]),
            mock.patch.object(site_access, "request_json") as request_json,
            self.assertRaisesRegex(SystemExit, "Provide at least one"),
        ):
            site_access.main()

        request_json.assert_not_called()

    def test_list_does_not_require_graph_token(self) -> None:
        output = io.StringIO()
        with (
            mock.patch("sys.argv", ["script", "list", "--workspace-id", WORKSPACE_ID]),
            mock.patch.dict(
                site_access.os.environ,
                {"CHATGPT_ADMIN_TOKEN": "admin-token"},
                clear=True,
            ),
            mock.patch.object(
                site_access, "request_json", return_value={"allow_list": {}}
            ),
            mock.patch("sys.stdout", output),
        ):
            site_access.main()

        self.assertEqual(json.loads(output.getvalue()), {"allow_list": {}})

    def test_remove_deletes_the_collection_guid(self) -> None:
        result, request_json = self.run_command(
            ["remove", "--workspace-id", WORKSPACE_ID, "--site-url", SITE_URL],
            responses=[
                graph_site(),
                {"allow_list": {COLLECTION_GUID: {}}},
                {"allow_list": {}},
            ],
        )

        self.assertEqual(result["processed_count"], 1)
        self.assertEqual(
            request_json.call_args,
            mock.call(
                "DELETE",
                f"{ALLOWLIST_URL}/{COLLECTION_GUID}",
                "admin-token",
                idempotency_key=None,
            ),
        )

    def test_remove_derives_distinct_stable_keys_for_each_collection(self) -> None:
        other_collection_guid = "b70d36d6-06d8-4591-964a-848f46c56b40"
        other_url = "https://contoso.sharepoint.com/sites/Research"
        other_site = {
            "id": f"contoso.sharepoint.com,{other_collection_guid},{WEB_GUID}",
            "webUrl": other_url,
        }
        result, request_json = self.run_command(
            [
                "remove",
                "--workspace-id",
                WORKSPACE_ID,
                "--site-url",
                SITE_URL,
                "--site-url",
                other_url,
                "--idempotency-key",
                IDEMPOTENCY_KEY,
            ],
            responses=[
                graph_site(),
                other_site,
                {"allow_list": {}},
                {"allow_list": {}},
                {"allow_list": {}},
            ],
        )

        self.assertEqual(result["processed_count"], 2)
        delete_calls = request_json.call_args_list[-2:]
        self.assertEqual(
            [call.kwargs["idempotency_key"] for call in delete_calls],
            [
                str(
                    uuid.uuid5(uuid.UUID(IDEMPOTENCY_KEY), f"remove:{COLLECTION_GUID}")
                ),
                str(
                    uuid.uuid5(
                        uuid.UUID(IDEMPOTENCY_KEY), f"remove:{other_collection_guid}"
                    )
                ),
            ],
        )

    def test_clear_requires_explicit_confirmation(self) -> None:
        with (
            mock.patch("sys.argv", ["script", "clear", "--workspace-id", WORKSPACE_ID]),
            mock.patch.dict(
                site_access.os.environ,
                {"CHATGPT_ADMIN_TOKEN": "admin-token"},
                clear=True,
            ),
            mock.patch.object(
                site_access, "request_json", return_value={"allow_list": {}}
            ) as request_json,
            self.assertRaisesRegex(SystemExit, "repeat with --yes"),
        ):
            site_access.main()

        request_json.assert_called_once_with("GET", ALLOWLIST_URL, "admin-token")

    def test_clear_with_confirmation_deletes_allowlist(self) -> None:
        result, request_json = self.run_command(
            ["clear", "--workspace-id", WORKSPACE_ID, "--yes"],
            responses=[{"allow_list": {COLLECTION_GUID: {}}}, {"allow_list": {}}],
        )

        self.assertEqual(result["action"], "clear")
        self.assertEqual(
            request_json.call_args,
            mock.call("DELETE", ALLOWLIST_URL, "admin-token", idempotency_key=None),
        )

    def test_clear_forwards_optional_idempotency_key(self) -> None:
        result, request_json = self.run_command(
            [
                "clear",
                "--workspace-id",
                WORKSPACE_ID,
                "--yes",
                "--idempotency-key",
                IDEMPOTENCY_KEY,
            ],
            responses=[{"allow_list": {COLLECTION_GUID: {}}}, {"allow_list": {}}],
        )

        self.assertEqual(result["action"], "clear")
        self.assertEqual(
            request_json.call_args,
            mock.call(
                "DELETE", ALLOWLIST_URL, "admin-token", idempotency_key=IDEMPOTENCY_KEY
            ),
        )

    def test_clear_dry_run_does_not_require_confirmation_or_write(self) -> None:
        result, request_json = self.run_command(
            ["clear", "--workspace-id", WORKSPACE_ID, "--dry-run"],
            responses=[{"allow_list": {COLLECTION_GUID: {}}}],
        )

        self.assertTrue(result["dry_run"])
        request_json.assert_called_once_with("GET", ALLOWLIST_URL, "admin-token")

    def test_rejects_invalid_workspace_uuid_before_admin_request(self) -> None:
        with (
            mock.patch("sys.argv", ["script", "list", "--workspace-id", "not-a-uuid"]),
            mock.patch.dict(
                site_access.os.environ,
                {"CHATGPT_ADMIN_TOKEN": "admin-token"},
                clear=True,
            ),
            mock.patch.object(site_access, "request_json") as request_json,
            self.assertRaisesRegex(SystemExit, "valid UUID"),
        ):
            site_access.main()

        request_json.assert_not_called()


class MutationKeyTests(unittest.TestCase):
    def test_omitted_key_leaves_existing_behavior_unchanged(self) -> None:
        self.assertIsNone(site_access.mutation_key(None, "add"))

    def test_rejects_invalid_idempotency_uuid(self) -> None:
        with self.assertRaisesRegex(
            SystemExit, "--idempotency-key must be a valid UUID"
        ):
            site_access.mutation_key("not-a-uuid", "add")

    def test_remove_keys_are_stable_and_unique_per_identifier(self) -> None:
        first = site_access.mutation_key(IDEMPOTENCY_KEY, "remove", COLLECTION_GUID)
        repeated = site_access.mutation_key(IDEMPOTENCY_KEY, "remove", COLLECTION_GUID)
        second = site_access.mutation_key(IDEMPOTENCY_KEY, "remove", WEB_GUID)

        self.assertEqual(first, repeated)
        self.assertNotEqual(first, second)


if __name__ == "__main__":
    unittest.main()
