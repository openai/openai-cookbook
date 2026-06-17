#!/usr/bin/env python3
"""Send synthetic Codex OTLP signals through the local Docker stack."""

from __future__ import annotations

import json
import os
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures"

COLLECTOR_URL = os.environ.get(
    "CODEX_OTEL_COLLECTOR_URL", "http://127.0.0.1:4318"
).rstrip("/")
LOKI_URL = os.environ.get(
    "CODEX_OTEL_LOKI_URL", "http://127.0.0.1:3100"
).rstrip("/")
PROMETHEUS_URL = os.environ.get(
    "CODEX_OTEL_PROMETHEUS_URL", "http://127.0.0.1:9090"
).rstrip("/")
TEMPO_URL = os.environ.get(
    "CODEX_OTEL_TEMPO_URL", "http://127.0.0.1:3200"
).rstrip("/")

ATTEMPTS = int(os.environ.get("CODEX_OTEL_SMOKE_ATTEMPTS", "20"))
INTERVAL_SECONDS = float(os.environ.get("CODEX_OTEL_SMOKE_INTERVAL", "1"))


def http_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
) -> tuple[int, str]:
    body = None
    headers: dict[str, str] = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")


def render_fixture(
    filename: str,
    *,
    environment: str,
    sentinel: str,
    trace_id: str,
    span_id: str,
    timestamp_ns: int,
) -> dict[str, Any]:
    text = (FIXTURES / filename).read_text(encoding="utf-8")
    replacements = {
        "__SMOKE_ENVIRONMENT__": environment,
        "__PRIVACY_SENTINEL__": sentinel,
        "__TRACE_ID__": trace_id,
        "__SPAN_ID__": span_id,
        "__START_TIME_UNIX_NANO__": str(timestamp_ns),
        "__END_TIME_UNIX_NANO__": str(timestamp_ns + 1_000_000),
        "__TIME_UNIX_NANO__": str(timestamp_ns + 1_000_000),
    }
    for source, destination in replacements.items():
        text = text.replace(source, destination)
    return json.loads(text)


def validate_otlp_response(signal: str, response_text: str) -> None:
    if not response_text.strip():
        return
    response = json.loads(response_text)
    partial = response.get("partialSuccess", {})
    rejected_keys = {
        "logs": "rejectedLogRecords",
        "traces": "rejectedSpans",
        "metrics": "rejectedDataPoints",
    }
    rejected = int(partial.get(rejected_keys[signal], 0))
    if rejected:
        raise RuntimeError(f"Collector rejected {rejected} {signal}")


def post_signal(signal: str, payload: dict[str, Any]) -> None:
    status, response_text = http_json(
        f"{COLLECTOR_URL}/v1/{signal}",
        method="POST",
        payload=payload,
    )
    if status < 200 or status >= 300:
        raise RuntimeError(f"Collector returned HTTP {status} for {signal}")
    validate_otlp_response(signal, response_text)
    print(f"PASS - Collector accepted synthetic {signal}")


def wait_for(label: str, predicate: Callable[[], bool]) -> None:
    for attempt in range(1, ATTEMPTS + 1):
        if predicate():
            print(f"PASS - {label} on attempt {attempt}")
            return
        if attempt < ATTEMPTS:
            time.sleep(INTERVAL_SECONDS)
    raise RuntimeError(f"Timed out waiting for {label}")


def query_prometheus(query: str) -> dict[str, Any] | None:
    encoded = urllib.parse.urlencode({"query": query})
    status, response_text = http_json(
        f"{PROMETHEUS_URL}/api/v1/query?{encoded}"
    )
    if status != 200:
        return None
    response = json.loads(response_text)
    if response.get("status") != "success":
        return None
    return response


def prometheus_has_results(query: str) -> bool:
    response = query_prometheus(query)
    if response is None:
        return False
    return bool(response.get("data", {}).get("result", []))


def query_loki(query: str, start_ns: int, end_ns: int) -> dict[str, Any] | None:
    encoded = urllib.parse.urlencode(
        {
            "query": query,
            "start": str(start_ns),
            "end": str(end_ns),
            "limit": "20",
        }
    )
    status, response_text = http_json(
        f"{LOKI_URL}/loki/api/v1/query_range?{encoded}"
    )
    if status != 200:
        return None
    return json.loads(response_text)


def loki_has_results(query: str, start_ns: int, end_ns: int) -> bool:
    response = query_loki(query, start_ns, end_ns)
    if response is None:
        return False
    return bool(response.get("data", {}).get("result", []))


def tempo_trace(trace_id: str) -> str | None:
    status, response_text = http_json(f"{TEMPO_URL}/api/traces/{trace_id}")
    return response_text if status == 200 else None


def main() -> int:
    timestamp_ns = time.time_ns()
    environment = f"local-smoke-{int(time.time())}"
    sentinel = f"CODEX_OTEL_PRIVACY_SENTINEL_{secrets.token_hex(6)}"
    trace_id = secrets.token_hex(16)
    span_id = secrets.token_hex(8)

    post_signal(
        "logs",
        render_fixture(
            "otlp-logs.json",
            environment=environment,
            sentinel=sentinel,
            trace_id=trace_id,
            span_id=span_id,
            timestamp_ns=timestamp_ns,
        ),
    )
    post_signal(
        "traces",
        render_fixture(
            "otlp-traces.json",
            environment=environment,
            sentinel=sentinel,
            trace_id=trace_id,
            span_id=span_id,
            timestamp_ns=timestamp_ns,
        ),
    )
    post_signal(
        "metrics",
        render_fixture(
            "otlp-metrics.json",
            environment=environment,
            sentinel=sentinel,
            trace_id=trace_id,
            span_id=span_id,
            timestamp_ns=timestamp_ns,
        ),
    )

    query_start = timestamp_ns - 60_000_000_000
    query_end = time.time_ns() + 60_000_000_000
    log_query = (
        '{service_name=~"codex.*"}'
        f' | env="{environment}" | event_name="codex.api_request"'
    )
    wait_for(
        "Loki stored the sanitized log",
        lambda: loki_has_results(log_query, query_start, query_end),
    )
    wait_for(
        "Tempo stored the sanitized trace",
        lambda: tempo_trace(trace_id) is not None,
    )
    wait_for(
        "Prometheus stored the sanitized metric",
        lambda: prometheus_has_results(
            f'codex_api_request_total{{env="{environment}"}}'
        ),
    )

    sentinel_query = f'{{service_name=~"codex.*"}} |= "{sentinel}"'
    if loki_has_results(sentinel_query, query_start, query_end):
        raise RuntimeError("Privacy sentinel reached Loki")
    tool_result_query = (
        '{service_name=~"codex.*"}'
        f' | env="{environment}" | event_name="codex.tool_result"'
    )
    if loki_has_results(tool_result_query, query_start, query_end):
        raise RuntimeError("codex.tool_result reached Loki")
    print("PASS - Loki contains neither the sentinel nor codex.tool_result")

    trace_text = tempo_trace(trace_id)
    if trace_text is None or sentinel in trace_text:
        raise RuntimeError("Privacy sentinel reached Tempo")
    print("PASS - Tempo trace does not contain the sentinel")

    status, metric_names = http_json(
        f"{PROMETHEUS_URL}/api/v1/label/__name__/values"
    )
    if status != 200 or sentinel in metric_names:
        raise RuntimeError("Privacy sentinel reached Prometheus metric names")
    print("PASS - Prometheus metric names do not contain the sentinel")

    print(
        "Smoke test complete - "
        f"environment {environment} - trace {trace_id} - sentinel {sentinel}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
