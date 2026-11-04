"""Offline, synthetic behavioral and secret-echo regression tests."""

import copy
import json
import socket
import unittest
from unittest.mock import patch

from oauth_doctor import diagnose, diagnose_json
from safe_fixtures import matching_evidence


def check(report, check_id):
    return next(item for item in report["checks"] if item["id"] == check_id)


class Comparisons(unittest.TestCase):
    def setUp(self):
        self.data = matching_evidence()

    def test_match_does_not_verify_authentication_or_tool_access(self):
        report = diagnose(self.data)
        self.assertEqual(report["status"], "settings_match")
        self.assertEqual(report["authentication"], "not_verified")
        self.assertEqual(report["tool_access"], "not_verified")
        self.assertEqual(report["network_activity"], "none")
        self.assertTrue(all(x["status"] == "match" for x in report["checks"]))

    def test_input_is_not_mutated(self):
        before = copy.deepcopy(self.data)
        diagnose(self.data)
        self.assertEqual(self.data, before)

    def test_issuer_is_exact_even_host_case(self):
        self.data["discovered"]["issuer"] = "https://AUTH.example.test"
        report = diagnose(self.data)
        self.assertEqual(check(report, "issuer.metadata")["status"], "mismatch")
        self.assertEqual(check(report, "endpoint.token")["status"], "unknown")

    def test_issuer_trailing_slash_is_not_equivalent(self):
        self.data["discovered"]["issuer"] += "/"
        self.assertEqual(diagnose(self.data)["status"], "mismatch")

    def test_selected_issuer_mismatch(self):
        self.data["observed"]["selected_issuer"] = "https://other.example.test"
        self.assertEqual(check(diagnose(self.data), "issuer.selected")["status"], "mismatch")

    def test_resource_scheme_and_host_case_are_equivalent(self):
        self.data["observed"]["authorization_resource"] = "HTTPS://MCP.EXAMPLE.TEST/mcp"
        self.assertEqual(diagnose(self.data)["status"], "settings_match")

    def test_resource_path_case_slash_port_and_escape_not_collapsed(self):
        for url in ["https://mcp.example.test/MCP", "https://mcp.example.test/mcp/",
                    "https://mcp.example.test:443/mcp", "https://mcp.example.test/%6dcp",
                    "https://mcp.example.test/a/../mcp"]:
            with self.subTest(url=url):
                self.data["observed"]["token_resource"] = url
                self.assertEqual(check(diagnose(self.data), "resource.token")["status"], "mismatch")

    def test_metadata_resource_mismatch(self):
        self.data["discovered"]["resource"] = "https://other.example.test/mcp"
        self.assertEqual(check(diagnose(self.data), "resource.metadata")["status"], "mismatch")

    def test_endpoint_differences_are_not_normalized(self):
        self.data["discovered"]["token_endpoint"] += "/"
        self.assertEqual(check(diagnose(self.data), "endpoint.token")["status"], "mismatch")

    def test_callback_requires_exact_effective_uri(self):
        for uri in ["https://APP.example.test/callback", "https://app.example.test/callback/",
                    "https://app.example.test:443/callback", "https://app.example.test/Callback"]:
            with self.subTest(uri=uri):
                self.data["observed"]["authorization_redirect_uri"] = uri
                self.assertEqual(check(diagnose(self.data), "redirect.authorization")["status"], "mismatch")

    def test_token_callback_drift(self):
        self.data["observed"]["token_redirect_uri"] = "https://app.example.test/other"
        report = diagnose(self.data)
        self.assertEqual(check(report, "redirect.token")["status"], "mismatch")
        self.assertEqual(check(report, "redirect.consistency")["status"], "mismatch")

    def test_loopback_effective_callback_supported_without_probing(self):
        for uri in ["http://localhost:3000/callback", "http://127.0.0.1:3000/callback",
                    "http://[::1]:3000/callback"]:
            with self.subTest(uri=uri):
                self.data["configured"]["redirect_uri"] = uri
                self.data["observed"]["authorization_redirect_uri"] = uri
                self.data["observed"]["token_redirect_uri"] = uri
                self.assertEqual(diagnose(self.data)["status"], "settings_match")

    def test_scope_order_and_duplicates_are_equivalent(self):
        self.data["observed"]["requested_scopes"] = ["files:write", "files:read", "files:read"]
        self.data["observed"]["granted_scopes"] = ["files:write", "files:write", "files:read"]
        self.assertEqual(diagnose(self.data)["status"], "settings_match")

    def test_scope_case_is_significant(self):
        self.data["observed"]["requested_scopes"] = ["Files:read", "files:write"]
        self.assertEqual(check(diagnose(self.data), "scope.requested")["status"], "mismatch")

    def test_missing_granted_scope_is_mismatch_not_auth_failure(self):
        self.data["observed"]["granted_scopes"] = ["files:read"]
        report = diagnose(self.data)
        self.assertEqual(check(report, "scope.granted")["status"], "mismatch")
        self.assertEqual(report["authentication"], "not_verified")

    def test_unadvertised_scope_requires_review_not_unsupported_claim(self):
        self.data["discovered"]["scopes_supported"] = ["files:read"]
        report = diagnose(self.data)
        self.assertEqual(check(report, "scope.advertised")["status"], "review")
        self.assertEqual(report["status"], "review_required")

    def test_extra_advertised_scopes_are_not_a_mismatch(self):
        self.data["discovered"]["scopes_supported"].append("admin:read")
        self.assertEqual(diagnose(self.data)["status"], "settings_match")

    def test_client_type_mismatch(self):
        self.data["observed"]["client_type"] = "confidential"
        self.assertEqual(check(diagnose(self.data), "client.type")["status"], "mismatch")

    def test_client_auth_method_mismatch(self):
        self.data["observed"]["token_endpoint_auth_method"] = "client_secret_basic"
        self.assertEqual(check(diagnose(self.data), "client.auth_method")["status"], "mismatch")

    def test_unsupported_client_auth_method(self):
        self.data["discovered"]["token_endpoint_auth_methods_supported"] = ["client_secret_basic"]
        self.assertEqual(check(diagnose(self.data), "client.auth_supported")["status"], "mismatch")

    def test_public_client_secret_method_is_configuration_mismatch(self):
        self.data["configured"]["token_endpoint_auth_method"] = "client_secret_basic"
        self.assertEqual(check(diagnose(self.data), "client.configured_mode")["status"], "mismatch")

    def test_missing_observations_are_unknown_not_match(self):
        del self.data["observed"]
        report = diagnose(self.data)
        self.assertEqual(report["status"], "evidence_incomplete")
        self.assertEqual(check(report, "scope.granted")["status"], "unknown")
        self.assertEqual(report["tool_access"], "not_verified")

    def test_each_missing_field_prevents_fully_matching_report(self):
        for section, fields in matching_evidence().items():
            for field in fields:
                with self.subTest(section=section, field=field):
                    payload = matching_evidence()
                    del payload[section][field]
                    self.assertEqual(diagnose(payload)["status"], "evidence_incomplete")

    def test_confidential_client_profile(self):
        for section in ["configured", "observed"]:
            self.data[section]["client_type"] = "confidential"
            self.data[section]["token_endpoint_auth_method"] = "client_secret_basic"
        self.assertEqual(diagnose(self.data)["status"], "settings_match")

    def test_explicit_empty_scope_set_is_not_missing(self):
        self.data["configured"]["scopes"] = []
        self.data["observed"]["requested_scopes"] = []
        self.data["observed"]["granted_scopes"] = []
        self.assertEqual(diagnose(self.data)["status"], "settings_match")

    def test_empty_input_is_unknown(self):
        report = diagnose({})
        self.assertEqual(report["status"], "evidence_incomplete")
        self.assertTrue(all(x["status"] == "unknown" for x in report["checks"]))

    def test_missing_metadata_issuer_blocks_dependent_comparisons(self):
        del self.data["discovered"]["issuer"]
        report = diagnose(self.data)
        for name in ["endpoint.token", "endpoint.authorization", "scope.advertised", "client.auth_supported"]:
            self.assertEqual(check(report, name)["status"], "unknown")

    def test_no_network_calls(self):
        with patch.object(socket, "socket", side_effect=AssertionError("network forbidden")), \
             patch.object(socket, "getaddrinfo", side_effect=AssertionError("DNS forbidden")):
            self.assertEqual(diagnose(self.data)["status"], "settings_match")


class Validation(unittest.TestCase):
    def assert_rejected(self, value):
        report = diagnose(value)
        self.assertEqual(report["status"], "invalid_input")
        self.assertEqual(report["checks"], [])
        self.assertEqual(report["authentication"], "not_verified")
        return report

    def test_unknown_keys_rejected_at_each_level_without_echo(self):
        secret = "SYNTHETIC_DO_NOT_ECHO"
        for payload in [{secret: secret}, {"observed": {secret: {"access_token": secret}}},
                        {"configured": {"access_token": secret}},
                        {"discovered": {"raw_headers": {"Authorization": secret}}}]:
            with self.subTest():
                self.assertNotIn(secret, json.dumps(self.assert_rejected(payload)))

    def test_nested_objects_rejected_in_allowed_fields(self):
        for value in [{"access_token": "SYNTHETIC_SECRET"}, ["https://example.test"], 1, True, None]:
            with self.subTest():
                self.assert_rejected({"configured": {"issuer": value}})

    def test_non_plain_types_rejected_without_running_methods(self):
        class Evil(dict):
            def items(self):
                raise AssertionError("must not execute")
        self.assert_rejected(Evil())
        self.assert_rejected({"configured": Evil()})

    def test_unknown_section_and_invalid_container(self):
        for value in [[], None, "trace", {"configured": []}, {"observed": None}, {1: "bad"}]:
            with self.subTest():
                self.assert_rejected(value)

    def test_secret_like_strings_in_allowlisted_fields_rejected(self):
        for value in ["Bearer SYNTHETIC", "client_secret=SYNTHETIC", "access_token=SYNTHETIC",
                      "eyJhbGciOiJub25lIn0.eyJzdWIiOiJ0ZXN0In0.c2ln", "sk-SYNTHETIC123456789"]:
            with self.subTest():
                report = self.assert_rejected({"configured": {"scopes": [value]}})
                self.assertNotIn(value, json.dumps(report))

    def test_urls_reject_query_fragment_userinfo_and_bad_syntax(self):
        for uri in ["https://example.test?code=SYNTHETIC", "https://example.test?", "https://example.test#",
                    "https://user:SYNTHETIC@example.test/mcp", "https://example.test/mcp#SYNTHETIC",
                    "https://example.test/\nSYNTHETIC", " https://example.test", "https://example.test\\mcp",
                    "https://example.test:bad/mcp", "https://example.test:99999/mcp", "https://example.test:/mcp",
                    "https://example.test/%zz", "https://example.test/%0a", "https://example.test/%250a",
                    "https://example.test/[", "https://bad_host.example/mcp", "https:///mcp", "file:///tmp/a",
                    "https://[::1]evil/mcp", "https://[::1]%25/mcp"]:
            with self.subTest(uri=uri):
                self.assert_rejected({"configured": {"resource": uri}})

    def test_plain_http_is_rejected_except_exact_loopback_callback_hosts(self):
        for field, uri in [("issuer", "http://localhost/issuer"), ("resource", "http://localhost/mcp"),
                           ("redirect_uri", "http://localhost.evil.test/callback"),
                           ("redirect_uri", "http://127.0.0.2/callback")]:
            with self.subTest():
                self.assert_rejected({"configured": {field: uri}})

    def test_invalid_scopes_and_enums(self):
        for field, value in [("scopes", "files:read"), ("scopes", ["two scopes"]),
                             ("scopes", ["bad\\scope"]), ("scopes", ["bad\"scope"]),
                             ("scopes", ["é"]), ("scopes", [None]), ("scopes", ["x"] * 129),
                             ("client_type", "PUBLIC"), ("token_endpoint_auth_method", "custom")]:
            with self.subTest():
                self.assert_rejected({"configured": {field: value}})

    def test_null_is_invalid_instead_of_absent(self):
        self.assert_rejected({"observed": {"granted_scopes": None}})

    def test_untrusted_authentication_claim_does_not_override_status(self):
        payload = matching_evidence()
        payload["observed"]["authentication"] = "verified"
        self.assert_rejected(payload)

    def test_output_never_contains_valid_input_values(self):
        payload = matching_evidence()
        payload["observed"]["requested_scopes"] = ["opaque-value-only-caller-knows"]
        report = json.dumps(diagnose(payload))
        self.assertNotIn("opaque-value-only-caller-knows", report)
        self.assertNotIn("example.test", report)
        self.assertNotIn("files:read", report)

    def test_json_parser_rejects_duplicate_keys_and_invalid_json_without_echo(self):
        for text in ['{"observed": {}, "observed": {}}', '{"configured":{"issuer":"a","issuer":"b"}}',
                     '{"access_token": "SYNTHETIC', "NaN", "[" * 10000, "x" * 65537]:
            with self.subTest():
                result = diagnose_json(text)
                self.assertEqual(result["status"], "invalid_input")
                self.assertNotIn("SYNTHETIC", json.dumps(result))

    def test_json_parser_accepts_valid_document(self):
        self.assertEqual(diagnose_json(json.dumps(matching_evidence()))["status"], "settings_match")

    def test_no_input_exception_text_is_exposed(self):
        self.assertNotIn("SYNTHETIC", json.dumps(self.assert_rejected({"configured": {"issuer": "https://[SYNTHETIC"}})))


if __name__ == "__main__":
    unittest.main()
