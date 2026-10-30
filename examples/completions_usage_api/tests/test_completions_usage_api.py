"""Offline regression tests for the Usage API Cookbook pagination helper.

Run from the repository root with:
    python -m pytest examples/completions_usage_api/tests -q
"""

import json
from pathlib import Path

import pytest
import requests


NOTEBOOK_PATH = (
    Path(__file__).resolve().parents[2] / "completions_usage_api.ipynb"
)
URL = "https://example.test/usage"


@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    def unexpected_request(*args, **kwargs):
        raise AssertionError("Network requests are disabled in these tests")

    monkeypatch.setattr(
        requests.sessions.Session, "request", unexpected_request
    )


@pytest.fixture
def get_data():
    """Load the actual helper without executing the rest of the notebook."""
    notebook = json.loads(NOTEBOOK_PATH.read_text(encoding="utf-8"))
    source = next(
        "".join(cell["source"])
        for cell in notebook["cells"]
        if cell["cell_type"] == "code"
        and "def get_data(" in "".join(cell["source"])
    )
    namespace = {"requests": requests}
    exec(compile(source, str(NOTEBOOK_PATH), "exec"), namespace)
    return namespace["get_data"]


def make_response(status_code, payload):
    """Use Requests' real JSON parsing and HTTPError behavior."""
    response = requests.Response()
    response.status_code = status_code
    response.url = URL
    response._content = json.dumps(payload).encode("utf-8")
    return response


@pytest.fixture
def mock_pages(monkeypatch):
    def install(*responses):
        pending = iter(responses)
        seen_params = []

        def fake_get(url, headers, params):
            assert url == URL
            seen_params.append(params.copy())
            return next(pending)

        monkeypatch.setattr(requests, "get", fake_get)
        return seen_params

    return install


@pytest.mark.parametrize("status_code", [429, 500])
def test_second_page_failure_raises(get_data, mock_pages, capsys, status_code):
    failed_response = make_response(status_code, {"error": "request failed"})
    seen_params = mock_pages(
        make_response(
            200, {"data": [{"start_time": 1}], "next_page": "page-2"}
        ),
        failed_response,
    )

    with pytest.raises(requests.HTTPError) as exc_info:
        get_data(URL, {"start_time": 0})

    assert exc_info.value.response is failed_response
    assert seen_params == [
        {"start_time": 0},
        {"start_time": 0, "page": "page-2"},
    ]
    assert "Data retrieved successfully!" not in capsys.readouterr().out


def test_successful_pages_preserve_all_data(get_data, mock_pages, capsys):
    first_bucket = {"start_time": 1}
    last_bucket = {"start_time": 3}
    seen_params = mock_pages(
        make_response(200, {"data": [first_bucket], "next_page": "page-2"}),
        make_response(200, {"data": [], "next_page": "page-3"}),
        make_response(200, {"data": [last_bucket], "next_page": None}),
    )

    assert get_data(URL, {"start_time": 0}) == [first_bucket, last_bucket]
    assert seen_params == [
        {"start_time": 0},
        {"start_time": 0, "page": "page-2"},
        {"start_time": 0, "page": "page-3"},
    ]
    assert capsys.readouterr().out == "Data retrieved successfully!\n"


@pytest.mark.parametrize("payload", [{}, {"data": [], "next_page": None}])
def test_empty_result_is_preserved(get_data, mock_pages, capsys, payload):
    seen_params = mock_pages(make_response(200, payload))

    assert get_data(URL, {"start_time": 0}) == []
    assert seen_params == [{"start_time": 0}]
    assert capsys.readouterr().out == "Issue: No data available to retrieve.\n"
