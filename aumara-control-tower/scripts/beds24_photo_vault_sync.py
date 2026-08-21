#!/usr/bin/env python3
"""Run the canonical AUMARA Beds24 photo transfer with an encrypted refresh vault.

This wrapper keeps update-beds24-photos.yml as the canonical transfer implementation,
loads the current refresh credential from the encrypted repository vault, injects it
only into the child process, captures a rotated refresh token if Beds24 returns one,
and persists only ciphertext plus sanitized evidence.
"""
from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import textwrap
import urllib.request

from cryptography.fernet import Fernet

ROOT = pathlib.Path(__file__).resolve().parents[2]
VAULT = ROOT / "aumara-control-tower/evidence/beds24-refresh-vault.json"
LAST = ROOT / "aumara-control-tower/evidence/beds24-photo-sync-last.json"
SOURCE = ROOT / ".github/workflows/update-beds24-photos.yml"
ROTATED_PATH = pathlib.Path("/tmp/beds24-rotated-refresh.txt")


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def vault_key(kek: str) -> bytes:
    digest = hashlib.sha256(("AUMARA_BEDS24_REFRESH_VAULT_V1\0" + kek).encode()).digest()
    return base64.urlsafe_b64encode(digest)


def github_call(path: str, method: str, payload: dict) -> None:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        return
    req = urllib.request.Request(
        f"https://api.github.com{path}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AUMARA-Beds24-Vault-Sync/2.0",
        },
        data=json.dumps(payload).encode(),
        method=method,
    )
    with urllib.request.urlopen(req, timeout=60):
        pass


def report_issue(result: dict) -> None:
    issue_text = (os.environ.get("ISSUE_NUMBER") or "").strip()
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if not issue_text or not repo:
        return
    issue = int(issue_text)
    body = "Beds24 vault photo-sync result (no credentials):\n\n```json\n" + json.dumps(
        result, indent=2, sort_keys=True
    ) + "\n```"
    github_call(f"/repos/{repo}/issues/{issue}/comments", "POST", {"body": body})
    github_call(
        f"/repos/{repo}/issues/{issue}",
        "PATCH",
        {"state": "closed", "state_reason": "completed"},
    )


def persist_repo_files() -> None:
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(
        ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"],
        check=True,
    )
    subprocess.run(["git", "add", str(VAULT), str(LAST)], check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], check=False).returncode != 0:
        run_id = os.environ.get("GITHUB_RUN_ID", "")
        subprocess.run(
            ["git", "commit", "-m", f"Record rotation-safe Beds24 photo sync {run_id} [skip ci]"],
            check=True,
        )
        subprocess.run(["git", "pull", "--rebase", "origin", "main"], check=True)
        subprocess.run(["git", "push", "origin", "HEAD:main"], check=True)


def main() -> int:
    kek = (os.environ.get("BEDS24_VAULT_KEK") or "").strip()
    if kek:
        print(f"::add-mask::{kek}", flush=True)

    result = {
        "checked_at_utc": now(),
        "property_id": os.environ.get("PROPERTY_ID", "324882"),
        "status": "STARTING",
        "child_returncode": None,
        "vault_loaded": False,
        "vault_refreshed": False,
        "secret_exposed": False,
    }
    rc = 1

    try:
        if not kek:
            raise RuntimeError("Production vault KEK missing")
        vault_data = json.loads(VAULT.read_text(encoding="utf-8"))
        cipher = vault_data.get("ciphertext")
        if not isinstance(cipher, str) or not cipher:
            raise RuntimeError("Encrypted refresh vault missing ciphertext")
        credential = Fernet(vault_key(kek)).decrypt(cipher.encode()).decode().strip()
        print(f"::add-mask::{credential}", flush=True)
        result["vault_loaded"] = True

        raw = SOURCE.read_text(encoding="utf-8")
        match = re.search(r"python3 - <<'PY'\n(.*?)\n\s+PY\n", raw, re.S)
        if not match:
            raise RuntimeError("Could not extract canonical photo-transfer Python from workflow")
        code = textwrap.dedent(match.group(1))

        pattern = r"(?m)^(\s*)if isinstance\(rotated, str\) and rotated:\n\1    mask\(rotated\)"
        replacement = (
            r"\1if isinstance(rotated, str) and rotated:\n"
            r"\1    mask(rotated)\n"
            r"\1    pathlib.Path(os.environ['BEDS24_ROTATED_OUT']).write_text(rotated, encoding='utf-8')"
        )
        code, count = re.subn(pattern, replacement, code, count=1)
        if count != 1:
            raise RuntimeError("Could not install rotation persistence hook into canonical transfer")

        child_env = dict(os.environ)
        child_env["BEDS24_REFRESH_CREDENTIAL"] = credential
        child_env["BEDS24_REFRESH_TOKEN"] = ""
        child_env["BEDS24_ROTATED_OUT"] = str(ROTATED_PATH)
        proc = subprocess.run([sys.executable, "-c", code], env=child_env, check=False)
        rc = int(proc.returncode)
        result["child_returncode"] = rc

        refresh_to_keep = credential
        if ROTATED_PATH.exists():
            rotated = ROTATED_PATH.read_text(encoding="utf-8").strip()
            if rotated:
                print(f"::add-mask::{rotated}", flush=True)
                refresh_to_keep = rotated
                result["vault_refreshed"] = True

        ciphertext = Fernet(vault_key(kek)).encrypt(refresh_to_keep.encode()).decode("ascii")
        VAULT.write_text(
            json.dumps(
                {
                    "version": 1,
                    "cipher": "fernet-sha256-kek",
                    "source": "rotation_safe_photo_sync",
                    "created_at_utc": now(),
                    "ciphertext": ciphertext,
                    "plaintext_stored": False,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        result["status"] = "SUCCESS" if rc == 0 else "TRANSFER_FAILED"
    except Exception as exc:
        result["status"] = "CONTROLLER_FAILED"
        result["diagnostic"] = f"{type(exc).__name__}: {str(exc)[:500]}"
        rc = 1

    result["checked_at_utc"] = now()
    LAST.parent.mkdir(parents=True, exist_ok=True)
    LAST.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    persist_repo_files()
    report_issue(result)
    print(json.dumps(result, sort_keys=True))
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
