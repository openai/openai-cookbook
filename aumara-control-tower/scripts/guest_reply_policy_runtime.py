#!/usr/bin/env python3
"""Load and render verified guest-reply policy fragments from the registry."""

from __future__ import annotations

import json
import pathlib
import re
from typing import Any

DEFAULT_POLICY_ROOT = pathlib.Path(__file__).resolve().parents[1] / "policies"
EXPECTED_POLICY_VERSION = "2026.07.27.1"
EXPECTED_SNAPSHOT_VERSION = "2026.08.02.1"
SNAPSHOT_FILE = "guest_reply_runtime.json"


class GuestReplyPolicyError(ValueError):
    """Raised when the policy registry cannot safely produce a reply."""


def _load(path: pathlib.Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GuestReplyPolicyError(f"cannot load {path.name}") from exc
    if not isinstance(value, dict):
        raise GuestReplyPolicyError(f"{path.name} is not an object")
    return value


def _policy_map(root: pathlib.Path = DEFAULT_POLICY_ROOT) -> dict[str, dict[str, Any]]:
    root = pathlib.Path(root)
    snapshot = _load(root / SNAPSHOT_FILE)
    if snapshot.get("snapshot_version") != EXPECTED_SNAPSHOT_VERSION:
        raise GuestReplyPolicyError("guest reply snapshot version mismatch")
    if snapshot.get("property") != "elcid":
        raise GuestReplyPolicyError("guest reply snapshot property mismatch")
    if snapshot.get("registry_policy_version") != EXPECTED_POLICY_VERSION:
        raise GuestReplyPolicyError("guest reply registry version mismatch")
    approved_ids = snapshot.get("policy_ids")
    if not isinstance(approved_ids, list) or not approved_ids:
        raise GuestReplyPolicyError("guest reply snapshot has no policies")

    index = _load(root / "registry.yaml")
    if index.get("policy_version") != EXPECTED_POLICY_VERSION:
        raise GuestReplyPolicyError("policy version mismatch")
    document = _load(root / index["registries"]["elcid"])
    if document.get("policy_version") != EXPECTED_POLICY_VERSION:
        raise GuestReplyPolicyError("EL CID policy version mismatch")
    policies = document.get("policies")
    if not isinstance(policies, list):
        raise GuestReplyPolicyError("EL CID policies are missing")

    result: dict[str, dict[str, Any]] = {}
    for policy in policies:
        if isinstance(policy, dict) and policy.get("policy_id") in approved_ids:
            result[str(policy["policy_id"])] = policy
    missing = sorted(set(approved_ids) - set(result))
    if missing:
        raise GuestReplyPolicyError(
            "guest reply snapshot policies are missing: " + ", ".join(missing)
        )
    return result


def _normalize_language(language: str) -> str:
    value = (language or "en").strip().lower()
    aliases = {
        "ee": "et",
        "est": "et",
        "estonian": "et",
        "es-es": "es",
        "spanish": "es",
        "english": "en",
    }
    return aliases.get(value, value.split("-", 1)[0] or "en")


def _fragment(policy_id: str, language: str, root: pathlib.Path) -> str:
    policy = _policy_map(root).get(policy_id)
    if not policy:
        raise GuestReplyPolicyError(f"missing policy {policy_id}")
    if policy.get("property") != "elcid":
        raise GuestReplyPolicyError("cross-property policy rejected")
    if policy.get("policy_version") != EXPECTED_POLICY_VERSION:
        raise GuestReplyPolicyError(f"policy {policy_id} has version drift")
    if policy.get("status") != "verified" or not policy.get("allowed_auto_reply"):
        raise GuestReplyPolicyError(f"policy {policy_id} is not enabled")
    templates = policy.get("response_templates")
    if not isinstance(templates, dict):
        raise GuestReplyPolicyError(f"policy {policy_id} lacks templates")
    normalized = _normalize_language(language)
    template = templates.get(normalized) or templates.get("en")
    if not isinstance(template, str) or not template.strip():
        raise GuestReplyPolicyError(f"policy {policy_id} lacks a usable template")
    return template.strip()


def _contains(text: str, patterns: tuple[str, ...]) -> bool:
    folded = text.casefold()
    return any(pattern in folded for pattern in patterns)


def detect_elcid_intents(text: str) -> set[str]:
    intents: set[str] = set()
    if _contains(
        text,
        (
            "extra-large double",
            "large double bed",
            "cama doble",
            "cama de matrimonio",
            "matrimonial",
            "kaheinimesevoodi",
            "двуспальн",
        ),
    ):
        intents.add("bed")
    if _contains(
        text,
        (
            "parking",
            "car park",
            "aparcamiento",
            "estacionamiento",
            "parkimis",
            "парков",
        ),
    ):
        intents.add("parking")
    if _contains(
        text,
        (
            "non-smoking",
            "nonsmoking",
            "smoke-free",
            "no fumadores",
            "no fumador",
            "mittesuitset",
            "некурящ",
        ),
    ):
        intents.add("non_smoking")
    return intents


def build_elcid_reply(
    text: str,
    language: str = "en",
    name: str = "Guest",
    root: pathlib.Path = DEFAULT_POLICY_ROOT,
) -> str | None:
    """Return a policy-rendered EL CID reply for supported safe intents."""
    intents = detect_elcid_intents(text)
    if not intents:
        return None

    normalized = _normalize_language(language)
    fragments: list[str] = []
    if "bed" in intents:
        fragments.append(_fragment("elcid.bed-request-reply-fragment", normalized, root))
    if "parking" in intents:
        fragments.append(_fragment("elcid.parking-request-reply-fragment", normalized, root))
    if "non_smoking" in intents:
        fragments.append(
            _fragment("elcid.non-smoking-room-reply-fragment", normalized, root)
        )

    safe_name = re.sub(r"[\r\n]+", " ", (name or "Guest").strip()) or "Guest"
    body = " ".join(fragments)
    if normalized == "es":
        return (
            f"Hola {safe_name},\n\n{body}\n\n"
            "Un cordial saludo,\nEl Cid Country Club"
        )
    if normalized == "et":
        return (
            f"Tere {safe_name}!\n\n{body}\n\n"
            "Parimate soovidega,\nEl Cid Country Club"
        )
    return (
        f"Hello {safe_name},\n\n{body}\n\n"
        "Kind regards,\nEl Cid Country Club"
    )
