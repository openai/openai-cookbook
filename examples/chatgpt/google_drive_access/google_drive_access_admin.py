"""Inspect shared drives and manage Google Drive access in a ChatGPT workspace."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import time
import uuid
from http.client import HTTPException
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote, unquote, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

CHATGPT_API_BASE_URL = "https://api.chatgpt.com"
GOOGLE_DRIVE_API_BASE_URL = "https://www.googleapis.com/drive/v3"
MAX_DRIVES = 1_000
POLICY_OBJECT = "workspace.google_drive.access_policy"
DRIVE_ACTIONS = {"inspect", "replace", "add", "remove"}


class NoRedirect(HTTPRedirectHandler):
    """Keep bearer credentials on the API origin selected by this script."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise HTTPError(req.full_url, code, "Unexpected API redirect", headers, fp)


def request_json(
    method: str, url: str, token: str, *, body: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Retry reads only; a failed write can have an uncertain outcome."""
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    data = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(body).encode("utf-8")
    attempts = 3 if method == "GET" else 1
    opener = build_opener(NoRedirect())
    for attempt in range(attempts):
        try:
            request = Request(url, data=data, headers=headers, method=method)
            with opener.open(request, timeout=30) as response:
                payload = json.load(response)
            if not isinstance(payload, dict):
                raise TypeError("Expected a JSON object")
            return payload
        except HTTPError as error:
            error.close()
            if error.code in {429, 502, 503, 504} and attempt + 1 < attempts:
                time.sleep(2**attempt)
                continue
            detail = f"HTTP {error.code}"
        except (OSError, HTTPException):
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
                continue
            detail = "network error or timeout"
        except (ValueError, TypeError, UnicodeError):
            detail = "invalid JSON response"
        advice = "" if method == "GET" else " Read the current policy before retrying."
        raise SystemExit(f"{method} {url} failed: {detail}.{advice}")
    raise AssertionError("unreachable")


def validate_drive_id(value: str) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{5,512}", value):
        raise SystemExit("Shared-drive IDs must contain 5–512 letters, digits, _ or -")
    return value


def parse_drive_reference(value: str) -> tuple[str, bool]:
    """Extract an ID; a URL still needs drives.get to verify it is a drive root."""
    value = value.strip()
    if "://" not in value:
        return validate_drive_id(value), False
    try:
        parsed = urlparse(value)
    except ValueError as error:
        raise SystemExit("Use a valid HTTPS shared-drive root URL") from error
    match = re.fullmatch(r"/drive/(?:u/[0-9]+/)?folders/([^/]+)/?", parsed.path)
    if parsed.scheme != "https" or parsed.netloc != "drive.google.com" or not match:
        raise SystemExit(
            "Use a shared-drive root URL: https://drive.google.com/drive/folders/ID"
        )
    return validate_drive_id(unquote(match.group(1))), True


def read_drive_references(
    drive_ids: list[str], drive_urls: list[str], drives_file: str | None
) -> list[str]:
    values = [validate_drive_id(value.strip()) for value in drive_ids]
    for value in drive_urls:
        if not parse_drive_reference(value)[1]:
            raise SystemExit("--drive-url requires a shared-drive root URL")
        values.append(value.strip())
    if drives_file:
        source = Path(drives_file)
        try:
            with source.open(encoding="utf-8-sig", newline="") as handle:
                if source.suffix.casefold() == ".csv":
                    reader = csv.DictReader(handle, strict=True)
                    columns = [
                        name
                        for name in reader.fieldnames or []
                        if name in {"drive_id", "drive_url"}
                    ]
                    if len(columns) != 1:
                        raise SystemExit(
                            "CSV must have exactly one drive_id or drive_url column"
                        )
                    for row in reader:
                        if None in row:
                            raise SystemExit("CSV row has more values than its header")
                        value = row.get(columns[0])
                        if value and value.strip():
                            value = value.strip()
                            if columns[0] == "drive_id":
                                validate_drive_id(value)
                            elif not parse_drive_reference(value)[1]:
                                raise SystemExit(
                                    "The drive_url column must contain root URLs"
                                )
                            values.append(value)
                else:
                    values.extend(
                        line.strip()
                        for line in handle
                        if line.strip() and not line.lstrip().startswith("#")
                    )
        except (OSError, UnicodeError, csv.Error) as error:
            raise SystemExit(f"Cannot read drives file: {source}") from error
    return list(dict.fromkeys(values))


def resolve_drives(
    references: list[str], *, inspect: bool = False
) -> list[dict[str, str]]:
    required: dict[str, bool] = {}
    for reference in references:
        drive_id, is_url = parse_drive_reference(reference)
        required[drive_id] = required.get(drive_id, False) or is_url or inspect
    if len(required) > MAX_DRIVES:
        raise SystemExit("A policy can contain at most 1,000 unique shared drives")
    token = os.environ.get("GOOGLE_DRIVE_TOKEN")
    if any(required.values()) and not token:
        raise SystemExit("Set GOOGLE_DRIVE_TOKEN to inspect drives or verify root URLs")
    drives = []
    for drive_id, verify in required.items():
        drive = {"id": drive_id}
        if verify:
            metadata = request_json(
                "GET",
                f"{GOOGLE_DRIVE_API_BASE_URL}/drives/{quote(drive_id, safe='')}?fields=id,name",
                token,
            )
            if metadata.get("id") != drive_id or not isinstance(
                metadata.get("name"), str
            ):
                raise SystemExit(
                    "Google Drive returned unexpected shared-drive metadata"
                )
            drive["name"] = metadata["name"]
        drives.append(drive)
    return drives


def validate_policy(policy: dict[str, Any]) -> dict[str, Any]:
    """Reject incomplete reads before using them to construct a replacement."""
    if (
        policy.get("object") != POLICY_OBJECT
        or "allow_list" not in policy
        or type(policy.get("allow_personal_drive")) is not bool
    ):
        raise SystemExit("The Admin API returned an unexpected Google Drive policy")
    allowed = policy["allow_list"]
    if allowed is not None:
        if not isinstance(allowed, list) or len(allowed) > MAX_DRIVES:
            raise SystemExit("The Admin API returned an invalid shared-drive allowlist")
        allowed = sorted({validate_drive_id(value) for value in allowed})
    return {
        "object": POLICY_OBJECT,
        "allow_list": allowed,
        "allow_personal_drive": policy["allow_personal_drive"],
    }


def plan_update(
    current: dict[str, Any], action: str, drive_ids: list[str], my_drive: str | None
) -> tuple[str, dict[str, Any] | None, dict[str, Any]]:
    """Translate CLI operations into the endpoint's full replacement contract."""
    allowed = current["allow_list"]
    if action == "reset":
        return "DELETE", None, {**current, "allow_list": None}
    if action == "replace":
        allowed = sorted(set(drive_ids))
    elif action in {"add", "remove"}:
        if allowed is None:
            raise SystemExit(
                "All shared drives are currently allowed. Use replace to choose a finite allowlist; exclude lists are unsupported."
            )
        selected = set(allowed)
        allowed = sorted(
            selected | set(drive_ids) if action == "add" else selected - set(drive_ids)
        )
    elif action == "block-all":
        allowed = []
    if allowed is not None and len(allowed) > MAX_DRIVES:
        raise SystemExit("The resulting policy exceeds 1,000 shared drives")
    body = {"drive_ids": allowed}
    proposed = {**current, "allow_list": allowed}
    if my_drive is not None:
        body["allow_personal_drive"] = my_drive == "allow"
        proposed["allow_personal_drive"] = my_drive == "allow"
    return "PUT", body, proposed


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "inspect",
            "list",
            "replace",
            "add",
            "remove",
            "reset",
            "block-all",
            "set-my-drive",
        ],
    )
    parser.add_argument("--workspace-id", help="ChatGPT workspace UUID")
    parser.add_argument(
        "--drive-id",
        action="append",
        default=[],
        help="Repeat for multiple shared-drive IDs",
    )
    parser.add_argument(
        "--drive-url",
        action="append",
        default=[],
        help="Repeat for multiple shared-drive root URLs",
    )
    parser.add_argument(
        "--drives-file",
        help="Text file of IDs/root URLs, or CSV with drive_id or drive_url",
    )
    parser.add_argument(
        "--my-drive",
        choices=["allow", "block"],
        help="Optionally update My Drive access with the shared-drive policy",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Read and preview without writing"
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirm reset or blocking every shared drive",
    )
    args = parser.parse_args(argv)

    has_input = bool(args.drive_id or args.drive_url or args.drives_file)
    if args.action not in DRIVE_ACTIONS and has_input:
        parser.error(f"{args.action} does not accept drive inputs")
    if args.action in {"inspect", "list", "reset"} and args.my_drive is not None:
        parser.error(f"{args.action} does not accept --my-drive")
    if args.action == "set-my-drive" and args.my_drive is None:
        parser.error("set-my-drive requires --my-drive allow or block")
    references = read_drive_references(args.drive_id, args.drive_url, args.drives_file)
    if args.action in DRIVE_ACTIONS and not references:
        parser.error(
            "Provide at least one --drive-id, --drive-url or nonempty --drives-file"
        )
    workspace_id = None
    admin_token = None
    if args.action != "inspect":
        try:
            workspace_id = str(uuid.UUID(args.workspace_id or ""))
        except ValueError:
            parser.error("--workspace-id must be a valid workspace UUID")
        admin_token = os.environ.get("CHATGPT_ADMIN_TOKEN")
        if not admin_token:
            parser.error("Set CHATGPT_ADMIN_TOKEN before reading or updating a policy")
    drives = resolve_drives(references, inspect=args.action == "inspect")
    if args.action == "inspect":
        print(json.dumps({"drives": drives}, indent=2))
        return

    url = f"{CHATGPT_API_BASE_URL}/v1/manage/workspaces/{workspace_id}/google-drive/drive-access/allow-list"
    current = validate_policy(request_json("GET", url, admin_token))
    if args.action == "list":
        print(json.dumps(current, indent=2))
        return
    method, body, proposed = plan_update(
        current, args.action, [drive["id"] for drive in drives], args.my_drive
    )
    preview = {
        "workspace_id": workspace_id,
        "action": args.action,
        "drives": drives,
        "current_policy": current,
        "proposed_policy": proposed,
        "method": method,
        "request_body": body,
    }
    if args.dry_run:
        print(json.dumps({"dry_run": True, **preview}, indent=2))
        return
    if proposed == current:
        print(json.dumps({"changed": False, "policy": current}, indent=2))
        return
    if not args.yes and (
        args.action in {"reset", "block-all"}
        or (proposed["allow_list"] == [] and current["allow_list"] != [])
    ):
        parser.error(
            "This change allows all shared drives or blocks every shared drive; review --dry-run, then repeat with --yes"
        )
    result = validate_policy(request_json(method, url, admin_token, body=body))
    print(
        json.dumps(
            {"workspace_id": workspace_id, "action": args.action, "policy": result},
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
