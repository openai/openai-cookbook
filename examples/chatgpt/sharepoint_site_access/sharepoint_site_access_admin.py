#!/usr/bin/env python3
"""Resolve SharePoint URLs and manage a ChatGPT workspace site allowlist."""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

CHATGPT_API_BASE_URL = "https://api.chatgpt.com"
MICROSOFT_GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"
MAX_COLLECTIONS_PER_REQUEST = 10_000


def request_json(
    method: str,
    url: str,
    token: str,
    *,
    body: dict[str, Any] | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Send an authenticated JSON request and retry temporary failures."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key

    for attempt in range(3):
        try:
            request = Request(url, data=data, headers=headers, method=method)
            with urlopen(request, timeout=30) as response:
                payload = response.read()
            return json.loads(payload) if payload else {}
        except HTTPError as error:
            details = error.read().decode("utf-8", errors="replace")
            if error.code in {429, 503} and attempt < 2:
                time.sleep(2**attempt)
                continue
            raise SystemExit(
                f"{method} {url} failed: HTTP {error.code}: {details}"
            ) from error
        except URLError as error:
            if attempt < 2:
                time.sleep(2**attempt)
                continue
            raise SystemExit(f"{method} {url} failed: {error.reason}") from error

    raise AssertionError("unreachable")


def resolve_sharepoint_url(site_url: str, graph_token: str) -> dict[str, str]:
    """Resolve a SharePoint site URL to its canonical site-collection GUID."""
    parsed = urlparse(site_url.strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username:
        raise SystemExit(f"SharePoint URLs must be valid HTTPS URLs: {site_url!r}")

    site_path = unquote(parsed.path.rstrip("/") or "/")
    site_resource = f"{parsed.hostname}:{quote(site_path, safe='/')}"
    graph_url = f"{MICROSOFT_GRAPH_BASE_URL}/sites/{site_resource}?" + urlencode(
        {"$select": "id,webUrl"}
    )
    site = request_json("GET", graph_url, graph_token)
    site_id = str(site.get("id", ""))
    components = [component.strip() for component in site_id.split(",")]
    if len(components) != 3 or components[0].casefold() != parsed.hostname.casefold():
        raise SystemExit(
            f"Microsoft Graph returned an unexpected site ID for {site_url!r}"
        )

    try:
        collection_guid = str(uuid.UUID(components[1]))
        web_guid = str(uuid.UUID(components[2]))
    except ValueError as error:
        raise SystemExit(
            f"Microsoft Graph returned an invalid site ID: {site_id!r}"
        ) from error

    return {
        "requested_url": site_url,
        "resolved_url": str(site.get("webUrl", site_url)),
        "site_id": f"{components[0].casefold()},{collection_guid},{web_guid}",
        "collection_guid": collection_guid,
    }


def read_site_urls(inline_urls: list[str], sites_file: str | None) -> list[str]:
    """Read unique site URLs from command-line arguments or a text/CSV file."""
    values = list(inline_urls)
    if sites_file:
        source = Path(sites_file)
        with source.open(encoding="utf-8-sig", newline="") as handle:
            if source.suffix.casefold() == ".csv":
                reader = csv.DictReader(handle)
                if not reader.fieldnames:
                    raise SystemExit(
                        "The CSV file must contain a site_url or url column"
                    )
                field = next(
                    (name for name in reader.fieldnames if name in {"site_url", "url"}),
                    None,
                )
                if field is None:
                    raise SystemExit(
                        "The CSV file must contain a site_url or url column"
                    )
                for row in reader:
                    site_url = row.get(field)
                    if site_url and site_url.strip():
                        values.append(site_url.strip())
            else:
                values.extend(
                    line.strip()
                    for line in handle
                    if line.strip() and not line.lstrip().startswith("#")
                )

    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def mutation_key(
    seed: str | None, action: str, identifier: str | None = None
) -> str | None:
    """Return a stable optional key, unique for each multi-site deletion."""
    if seed is None:
        return None

    try:
        root = uuid.UUID(seed)
    except ValueError as error:
        raise SystemExit("--idempotency-key must be a valid UUID") from error

    return str(uuid.uuid5(root, f"{action}:{identifier}")) if identifier else str(root)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["inspect", "list", "add", "remove", "clear"])
    parser.add_argument("--workspace-id", help="ChatGPT workspace UUID")
    parser.add_argument(
        "--site-url",
        action="append",
        default=[],
        help="Repeat for multiple HTTPS SharePoint URLs",
    )
    parser.add_argument(
        "--sites-file",
        help="Text file with one URL per line or CSV with a site_url column",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Resolve and inspect without changing the allowlist",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm that clearing the allowlist restores access",
    )
    parser.add_argument(
        "--idempotency-key",
        help="Optional UUID for safe write retries when workspace support is enabled",
    )
    args = parser.parse_args()

    site_urls = read_site_urls(args.site_url, args.sites_file)
    if args.action in {"inspect", "add", "remove"} and not site_urls:
        raise SystemExit("Provide at least one --site-url or --sites-file")
    if args.action in {"list", "clear"} and site_urls:
        raise SystemExit(f"The {args.action} action does not accept site URLs")

    sites: list[dict[str, str]] = []
    if site_urls:
        graph_token = os.environ.get("MICROSOFT_GRAPH_TOKEN")
        if not graph_token:
            raise SystemExit(
                "Set MICROSOFT_GRAPH_TOKEN before resolving SharePoint URLs"
            )
        sites = [
            resolve_sharepoint_url(site_url, graph_token) for site_url in site_urls
        ]

    collection_guids = list(dict.fromkeys(site["collection_guid"] for site in sites))
    if len(collection_guids) > MAX_COLLECTIONS_PER_REQUEST:
        raise SystemExit(
            "A policy request cannot contain more than 10,000 unique site collections"
        )

    if args.action == "inspect":
        print(
            json.dumps({"sites": sites, "collection_guids": collection_guids}, indent=2)
        )
        return

    if not args.workspace_id:
        raise SystemExit("--workspace-id is required for allowlist operations")
    try:
        workspace_id = str(uuid.UUID(args.workspace_id))
    except ValueError as error:
        raise SystemExit("--workspace-id must be a valid UUID") from error

    admin_token = os.environ.get("CHATGPT_ADMIN_TOKEN")
    if not admin_token:
        raise SystemExit(
            "Set CHATGPT_ADMIN_TOKEN before inspecting or updating the allowlist"
        )

    allowlist_url = (
        f"{CHATGPT_API_BASE_URL}/v1/manage/workspaces/{workspace_id}"
        "/sharepoint/site-access/allow-list"
    )
    current_policy = request_json("GET", allowlist_url, admin_token)
    if args.action == "list":
        print(json.dumps(current_policy, indent=2))
        return

    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "workspace_id": workspace_id,
                    "action": args.action,
                    "sites": sites,
                    "collection_guids": collection_guids,
                    "current_policy": current_policy,
                },
                indent=2,
            )
        )
        return

    if args.action == "clear":
        if not args.yes:
            raise SystemExit(
                "Clearing the allowlist restores access to all permitted SharePoint sites; "
                "repeat with --yes to confirm"
            )
        response = request_json(
            "DELETE",
            allowlist_url,
            admin_token,
            idempotency_key=mutation_key(args.idempotency_key, "clear"),
        )
    elif args.action == "add":
        response = request_json(
            "PUT",
            allowlist_url,
            admin_token,
            body={"collection_guids": collection_guids},
            idempotency_key=mutation_key(args.idempotency_key, "add"),
        )
    else:
        response = current_policy
        for collection_guid in collection_guids:
            response = request_json(
                "DELETE",
                f"{allowlist_url}/{quote(collection_guid, safe='')}",
                admin_token,
                idempotency_key=mutation_key(
                    args.idempotency_key, "remove", collection_guid
                ),
            )

    print(
        json.dumps(
            {
                "workspace_id": workspace_id,
                "action": args.action,
                "processed_count": len(collection_guids),
                "policy": response,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
