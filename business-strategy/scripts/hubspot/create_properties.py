"""Idempotently create/update the tps_* contact property groups + properties in HubSpot.

Usage:
    export HUBSPOT_PRIVATE_APP_TOKEN=pat-na1-...
    python create_properties.py            # apply changes
    python create_properties.py --dry-run  # show what would change, no writes

Requires a HubSpot Private App with these scopes:
    crm.schemas.contacts.read
    crm.schemas.contacts.write

Safe to re-run. Existing groups/properties are PATCHed with current definitions;
new ones are POSTed. The script never deletes — remove properties manually in HubSpot.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any
from urllib import error, request

from properties import ALL_PROPERTIES, GROUPS

API_BASE = "https://api.hubapi.com"
GROUPS_URL = f"{API_BASE}/crm/v3/properties/contacts/groups"
PROPS_URL = f"{API_BASE}/crm/v3/properties/contacts"


def _token() -> str:
    token = os.environ.get("HUBSPOT_PRIVATE_APP_TOKEN")
    if not token:
        sys.exit("HUBSPOT_PRIVATE_APP_TOKEN not set.")
    return token


def _req(method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = request.Request(
        url,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {_token()}",
            "Content-Type": "application/json",
        },
    )
    try:
        with request.urlopen(req) as resp:
            payload = resp.read().decode() or "{}"
            return resp.status, json.loads(payload)
    except error.HTTPError as e:
        payload = e.read().decode() or "{}"
        try:
            parsed = json.loads(payload)
        except json.JSONDecodeError:
            parsed = {"raw": payload}
        return e.code, parsed


def _get_existing_groups() -> set[str]:
    status, body = _req("GET", GROUPS_URL)
    if status != 200:
        sys.exit(f"Failed to list groups: {status} {body}")
    return {g["name"] for g in body.get("results", [])}


def _get_existing_properties() -> set[str]:
    status, body = _req("GET", PROPS_URL)
    if status != 200:
        sys.exit(f"Failed to list properties: {status} {body}")
    return {p["name"] for p in body.get("results", [])}


def upsert_group(group: dict[str, str], existing: set[str], dry_run: bool) -> None:
    name = group["name"]
    payload = {"name": name, "label": group["label"], "displayOrder": -1}
    if name in existing:
        if dry_run:
            print(f"  [dry-run] PATCH group {name}")
            return
        status, body = _req("PATCH", f"{GROUPS_URL}/{name}", {"label": group["label"]})
        _check(status, body, f"PATCH group {name}")
    else:
        if dry_run:
            print(f"  [dry-run] CREATE group {name}")
            return
        status, body = _req("POST", GROUPS_URL, payload)
        _check(status, body, f"CREATE group {name}")


def upsert_property(prop: dict[str, Any], existing: set[str], dry_run: bool) -> None:
    name = prop["name"]
    if name in existing:
        if dry_run:
            print(f"  [dry-run] PATCH property {name}")
            return
        # PATCH cannot change `name` or `type`; HubSpot ignores them on update.
        status, body = _req("PATCH", f"{PROPS_URL}/{name}", prop)
        _check(status, body, f"PATCH property {name}")
    else:
        if dry_run:
            print(f"  [dry-run] CREATE property {name}")
            return
        status, body = _req("POST", PROPS_URL, prop)
        _check(status, body, f"CREATE property {name}")


def _check(status: int, body: dict, action: str) -> None:
    if status >= 300:
        print(f"  ERROR {action}: {status} {body}", file=sys.stderr)
    else:
        print(f"  OK    {action}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Print planned changes without writing to HubSpot.")
    args = parser.parse_args()

    print("Fetching existing groups + properties...")
    existing_groups = _get_existing_groups()
    existing_props = _get_existing_properties()
    print(f"  found {len(existing_groups)} groups, {len(existing_props)} properties")

    print("\nUpserting property groups:")
    for g in GROUPS:
        upsert_group(g, existing_groups, args.dry_run)

    print("\nUpserting properties:")
    for prop in ALL_PROPERTIES:
        upsert_property(prop, existing_props, args.dry_run)
        if not args.dry_run:
            time.sleep(0.1)  # gentle rate-limit; HubSpot allows 100/10s

    print(f"\nDone. {len(ALL_PROPERTIES)} properties processed.")


if __name__ == "__main__":
    main()
