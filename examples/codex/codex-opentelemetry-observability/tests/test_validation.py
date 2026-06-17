#!/usr/bin/env python3
"""Unit tests for example-local static validation and OTLP fixtures."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check_otlp_response  # noqa: E402
import validate_assets  # noqa: E402


class CodexProfileTests(unittest.TestCase):
    def test_local_profile_enables_private_otlp_exports(self) -> None:
        path = ROOT / "local-otel.config.toml.example"
        with path.open("rb") as file_handle:
            config = validate_assets.tomllib.load(file_handle)

        self.assertTrue(config["analytics"]["enabled"])
        otel = config["otel"]
        self.assertFalse(otel["log_user_prompt"])
        self.assertEqual(otel["environment"], "local-demo")

        expected_endpoints = {
            "exporter": "http://127.0.0.1:4318/v1/logs",
            "trace_exporter": "http://127.0.0.1:4318/v1/traces",
            "metrics_exporter": "http://127.0.0.1:4318/v1/metrics",
        }
        for exporter, endpoint in expected_endpoints.items():
            with self.subTest(exporter=exporter):
                self.assertEqual(
                    otel[exporter]["otlp-http"],
                    {"endpoint": endpoint, "protocol": "binary"},
                )


class FixtureTests(unittest.TestCase):
    def test_otlp_fixtures_are_json_with_environment_placeholder(self) -> None:
        expected_roots = {
            "otlp-logs.json": "resourceLogs",
            "otlp-traces.json": "resourceSpans",
            "otlp-metrics.json": "resourceMetrics",
        }
        for filename, root_key in expected_roots.items():
            with self.subTest(filename=filename):
                path = ROOT / "tests" / "fixtures" / filename
                text = path.read_text(encoding="utf-8")
                payload = json.loads(text)
                self.assertIn(root_key, payload)
                self.assertIn("__SMOKE_ENVIRONMENT__", text)
                self.assertIn("__PRIVACY_SENTINEL__", text)

    def test_metrics_fixture_covers_descriptor_and_scope_privacy(self) -> None:
        path = ROOT / "tests" / "fixtures" / "otlp-metrics.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        scope_metrics = payload["resourceMetrics"][0]["scopeMetrics"][0]
        self.assertEqual(scope_metrics["scope"]["name"], "__PRIVACY_SENTINEL__")
        self.assertEqual(scope_metrics["scope"]["version"], "__PRIVACY_SENTINEL__")

        native_metric = scope_metrics["metrics"][0]
        self.assertEqual(native_metric["description"], "__PRIVACY_SENTINEL__")
        self.assertEqual(native_metric["unit"], "__PRIVACY_SENTINEL__")
        self.assertIn(
            "__PRIVACY_SENTINEL__",
            scope_metrics["metrics"][1]["name"],
        )


class OtlpResponseTests(unittest.TestCase):
    def test_accepts_empty_and_empty_object_responses(self) -> None:
        for response_text in ("", "{}"):
            with self.subTest(response_text=response_text):
                self.assertIsNone(
                    check_otlp_response.validation_error("logs", response_text)
                )

    def test_rejects_partial_success_counts(self) -> None:
        rejected_counts = {
            "logs": "rejectedLogRecords",
            "traces": "rejectedSpans",
            "metrics": "rejectedDataPoints",
        }
        for signal, count_key in rejected_counts.items():
            with self.subTest(signal=signal):
                response_text = json.dumps(
                    {"partialSuccess": {count_key: "1"}}
                )
                error = check_otlp_response.validation_error(signal, response_text)
                self.assertIsNotNone(error)
                self.assertIn("rejected 1", error)


class DashboardValidationTests(unittest.TestCase):
    def test_rejects_raw_logs_and_sensitive_fields(self) -> None:
        dashboard = {
            "title": "Unsafe",
            "panels": [
                {
                    "type": "logs",
                    "title": "Request details",
                    "targets": [{"expr": "{request_id=~\".+\"}"}],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "dashboard.json"
            path.write_text(json.dumps(dashboard), encoding="utf-8")
            errors = validate_assets.validate_dashboard(path)
        self.assertTrue(any("raw log panel" in error for error in errors))
        self.assertTrue(any("request identifier" in error for error in errors))

    def test_rejects_unsupported_loki_and_tempo_queries(self) -> None:
        dashboard = {
            "title": "Unsupported queries",
            "panels": [
                {
                    "type": "timeseries",
                    "datasource": {"type": "loki"},
                    "targets": [
                        {
                            "expr": (
                                "count_over_time({service_name=~\".+\"}"
                                "[$__rate_interval])"
                            )
                        }
                    ],
                },
                {
                    "type": "traces",
                    "datasource": {"type": "tempo"},
                    "targets": [{"queryType": "traceql", "query": "{}"}],
                },
            ],
        }
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "dashboard.json"
            path.write_text(json.dumps(dashboard), encoding="utf-8")
            errors = validate_assets.validate_dashboard(path)
        self.assertTrue(any("Loki targets" in error for error in errors))
        self.assertTrue(any("Tempo search queries" in error for error in errors))


class ComposeValidationTests(unittest.TestCase):
    def validate(self, compose: str) -> list[str]:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "docker-compose.yml"
            path.write_text(compose, encoding="utf-8")
            return validate_assets.validate_compose_source(path)

    def test_accepts_pinned_local_services(self) -> None:
        service = """
    image: example/service:1.0@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
"""
        compose = "services:\n" + "".join(
            f"  {name}:{service}" for name in sorted(validate_assets.EXPECTED_LOCAL_SERVICES)
        )
        compose += """
    ports:
      - "127.0.0.1:${CODEX_OTEL_HTTP_PORT:-4318}:4318"
      - "127.0.0.1:${CODEX_OTEL_HEALTH_PORT:-13133}:13133"
      - "127.0.0.1:${CODEX_OTEL_GRAFANA_PORT:-3001}:3000"
      - "127.0.0.1:${CODEX_OTEL_LOKI_PORT:-3100}:3100"
      - "127.0.0.1:${CODEX_OTEL_PROMETHEUS_PORT:-9090}:9090"
      - "127.0.0.1:${CODEX_OTEL_TEMPO_PORT:-3200}:3200"
    environment:
      GF_AUTH_ANONYMOUS_ORG_ROLE: Viewer
"""
        self.assertEqual(self.validate(compose), [])

    def test_rejects_unpinned_and_elevated_services(self) -> None:
        compose = """
services:
  grafana:
    image: grafana/grafana:latest
    privileged: true
    network_mode: host
    cap_add:
      - SYS_ADMIN
    security_opt:
      - seccomp=unconfined
"""
        errors = self.validate(compose)
        self.assertTrue(any("not pinned" in error for error in errors))
        self.assertTrue(any("privileged" in error for error in errors))
        self.assertTrue(any("host network" in error for error in errors))
        self.assertTrue(any("capability" in error for error in errors))
        self.assertTrue(any("seccomp" in error for error in errors))


class CollectorSourceValidationTests(unittest.TestCase):
    def test_rejects_debug_exporter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "collector.yaml"
            path.write_text("exporters:\n  debug:\n", encoding="utf-8")
            errors = validate_assets.validate_collector_source(path)
        self.assertTrue(any("debug exporter" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
