# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx>=0.27,<1"]
# ///
"""Export available Agents API session traces to Braintrust."""

import argparse
import os
from itertools import islice
from urllib.parse import quote

import httpx


def session_ids(client):
    params = {"limit": 100, "order": "desc"}
    while True:
        response = client.get("sessions", params=params)
        response.raise_for_status()
        page = response.json()
        for session in page["data"]:
            yield session["id"]
        if not page["has_more"]:
            return
        after = page["last_id"]
        if not after or after == params.get("after"):
            raise ValueError("Session pagination did not advance")
        params["after"] = after


def export_session(source, destination, session_id, page_size):
    params = {"limit": page_size, "order": "asc"}
    exported = 0
    while True:
        response = source.get(
            f"sessions/{quote(session_id, safe='')}/traces", params=params
        )
        response.raise_for_status()
        page = response.json()
        resource_spans = [
            resource
            for trace in page["data"]
            for resource in trace["otlp"]["resourceSpans"]
        ]
        if resource_spans:
            response = destination.post(
                "otel/v1/traces", json={"resourceSpans": resource_spans}
            )
            response.raise_for_status()
            # OTLP can report rejected spans even with HTTP 200.
            partial = response.json().get("partialSuccess", {})
            if int(partial.get("rejectedSpans", 0)):
                raise ValueError(
                    f"Braintrust rejected {partial['rejectedSpans']} spans"
                )
            exported += len(page["data"])
        if not page["has_more"]:
            return exported
        after = page["last_id"]
        if not after or after == params.get("after"):
            raise ValueError("Trace pagination did not advance")
        params["after"] = after


def export_sessions(source, destination, ids, page_size):
    succeeded = 0
    failed = []
    for session_id in ids:
        try:
            count = export_session(source, destination, session_id, page_size)
        except (httpx.HTTPError, ValueError) as error:
            print(f"FAILED {session_id}: {error}")
            failed.append(session_id)
        else:
            print(f"Exported {session_id}: {count} traces")
            succeeded += 1
    print(f"Finished: {succeeded} sessions exported, {len(failed)} failed")
    return failed


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("Must be positive")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument(
        "--all", action="store_true", help="Export all accessible sessions"
    )
    selection.add_argument("--max-sessions", type=positive_int, default=5)
    selection.add_argument(
        "--session-id", action="append", help="Export a specific session; repeatable"
    )
    parser.add_argument(
        "--page-size",
        type=positive_int,
        default=20,
        help="Traces per request (max 100)",
    )
    args = parser.parse_args()
    if args.page_size > 100:
        parser.error("--page-size must be at most 100")

    with (
        httpx.Client(
            base_url=os.environ.get(
                "OPENAI_BASE_URL", "https://api.openai.com/v1"
            ).rstrip("/")
            + "/agents/",
            headers={
                "Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}",
                "OpenAI-Beta": "agents=v1",
            },
            timeout=60,
        ) as source,
        httpx.Client(
            base_url=os.environ.get(
                "BRAINTRUST_API_URL", "https://api.braintrust.dev"
            ).rstrip("/")
            + "/",
            headers={
                "Authorization": f"Bearer {os.environ['BRAINTRUST_API_KEY']}",
                "x-bt-parent": f"project_name:{os.environ['BRAINTRUST_PROJECT']}",
            },
            timeout=60,
        ) as destination,
    ):
        ids = args.session_id or session_ids(source)
        if not args.all and not args.session_id:
            ids = islice(ids, args.max_sessions)
        failed = export_sessions(source, destination, ids, args.page_size)
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
