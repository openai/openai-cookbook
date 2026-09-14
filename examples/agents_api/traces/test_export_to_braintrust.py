import json

import httpx
import pytest
from export_to_braintrust import export_sessions, session_ids


def trace_page(name, has_more=False):
    return {
        "data": [
            {"otlp": {"resourceSpans": [{"scopeSpans": [{"spans": [{"name": name}]}]}]}}
        ],
        "last_id": name,
        "has_more": has_more,
    }


def test_export_pages_sessions_and_traces():
    requested = []
    uploaded = []

    def source(request):
        assert request.headers["authorization"] == "Bearer source-only"
        requested.append((request.url.path, dict(request.url.params)))
        if request.url.path.endswith("/sessions"):
            second = request.url.params.get("cursor") == "next"
            return httpx.Response(
                200,
                json={
                    "page": [{"id": "sess_two" if second else "sess_one"}],
                    "has_more": not second,
                    "next_cursor": None if second else "next",
                },
            )
        if "sess_two" in request.url.path:
            return httpx.Response(200, json={"data": [], "has_more": False})
        second = request.url.params.get("after") == "one"
        return httpx.Response(
            200, json=trace_page("two" if second else "one", not second)
        )

    def destination(request):
        assert request.url.path == "/otel/v1/traces"
        assert request.headers["authorization"] == "Bearer destination-only"
        uploaded.append(json.loads(request.content))
        return httpx.Response(200, json={})

    with (
        httpx.Client(
            base_url="https://source.test/v1/agents/",
            headers={"Authorization": "Bearer source-only"},
            transport=httpx.MockTransport(source),
        ) as source_client,
        httpx.Client(
            base_url="https://destination.test/",
            headers={"Authorization": "Bearer destination-only"},
            transport=httpx.MockTransport(destination),
        ) as destination_client,
    ):
        assert (
            export_sessions(
                source_client, destination_client, session_ids(source_client), 20
            )
            == []
        )
    assert uploaded == [
        {"resourceSpans": trace_page(name)["data"][0]["otlp"]["resourceSpans"]}
        for name in ("one", "two")
    ]
    assert requested == [
        ("/v1/agents/sessions", {"limit": "100", "order": "desc"}),
        ("/v1/agents/sessions/sess_one/traces", {"limit": "20", "order": "asc"}),
        (
            "/v1/agents/sessions/sess_one/traces",
            {"limit": "20", "order": "asc", "after": "one"},
        ),
        ("/v1/agents/sessions", {"limit": "100", "order": "desc", "cursor": "next"}),
        ("/v1/agents/sessions/sess_two/traces", {"limit": "20", "order": "asc"}),
    ]


@pytest.mark.parametrize(
    "status,body", [(503, {}), (200, {"partialSuccess": {"rejectedSpans": "1"}})]
)
def test_upload_failure_reports_session_and_continues(status, body):
    uploads = []

    def destination(request):
        uploads.append(json.loads(request.content))
        return httpx.Response(
            status if len(uploads) == 1 else 200, json=body if len(uploads) == 1 else {}
        )

    with (
        httpx.Client(
            base_url="https://source.test/",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json=trace_page(request.url.path))
            ),
        ) as source_client,
        httpx.Client(
            base_url="https://destination.test/",
            transport=httpx.MockTransport(destination),
        ) as destination_client,
    ):
        assert export_sessions(
            source_client, destination_client, ["sess_bad", "sess_good"], 20
        ) == ["sess_bad"]
    assert len(uploads) == 2
