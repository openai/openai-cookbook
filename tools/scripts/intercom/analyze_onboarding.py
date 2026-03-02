#!/usr/bin/env python3
"""
Analyze onboarding conversations filtered by user type (accountant vs SMB).

Supports two analysis modes:
  1. Keyword matching (default): scans for first-invoice keywords (factura, comprobante, etc.)
  2. LLM classification (--llm): uses llm_classify.mjs with any topic config JSON.
     Default topic: topic_first_invoice.json. Use --topic to switch to broader topics
     like topic.json (Setup / Onboarding) for full category breakdowns.

User type segmentation:
  - accountant: es_contador=true or rol_wizard contains 'contador'
  - smb: es_contador=false (business owners)
  - all: no filter

User type data comes from Intercom contact custom_attributes (synced with HubSpot).
When cache lacks contact_es_contador (legacy caches), falls back to HubSpot API lookup.

Usage:
  python analyze_onboarding.py --cache path/to/conversations.json --user-type accountant
  python analyze_onboarding.py --cache path/to/conversations.json --user-type smb --llm
  python analyze_onboarding.py --cache path/to/conversations.json --user-type all --llm
  python analyze_onboarding.py --cache path/to/conversations.json --user-type accountant --llm \\
    --topic plugins/colppy-customer-success/skills/intercom-onboarding-setup/topic.json

Requires:
  - Intercom cache JSON with contact_email (from export_cache_for_local_scan.mjs --team 2334166)
  - When --llm: OPENAI_API_KEY, Node.js, and plugins/colppy-customer-success/scripts/llm_classify.mjs
"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

# Load .env from repo root (script is in tools/scripts/intercom/)
_REPO_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_REPO_ROOT / ".env")
load_dotenv()  # Also current dir

# First-time-to-value (first invoice) keywords - Spanish
FIRST_INVOICE_KEYWORDS = [
    "primera factura",
    "primer comprobante",
    "cómo facturo",
    "cómo facturar",
    "emitir factura",
    "generar factura",
    "generar comprobante",
    "crear factura",
    "crear comprobante",
    "primer comprobante de venta",
    "comprobante de venta",
    "factura electrónica",
    "facturación",
    "no puedo facturar",
    "no puedo generar",
    "cómo emito",
    "cómo genero",
    "alta de factura",
    "alta de comprobante",
    "talonario",
    "punto de venta",
    "punto de venta afip",
    "alta talonario",
]

USER_TYPE_LABELS = {
    "accountant": "Accountants (es_contador=true)",
    "smb": "SMB / Business owners (es_contador=false)",
    "all": "All users",
}


def _is_accountant(es_contador, rol_wizard: str | None) -> bool:
    """Accountant if es_contador=true or rol_wizard contains 'contador'."""
    if es_contador and str(es_contador).lower() in ("true", "1", "yes"):
        return True
    if rol_wizard and "conta" in str(rol_wizard).lower():
        return True
    return False


def fetch_hubspot_es_contador(emails: list[str], batch_delay: float = 0.15, quiet: bool = False) -> dict[str, dict]:
    """Fetch es_contador and rol_wizard from HubSpot for each email."""
    api_key = (
        os.getenv("HUBSPOT_API_KEY")
        or os.getenv("HUBSPOT_ACCESS_TOKEN")
        or os.getenv("HUBSPOT_TOKEN")
        or os.getenv("COLPPY_CRM_AUTOMATIONS")
        or os.getenv("ColppyCRMAutomations")
    )
    if not api_key:
        return {e: {"es_contador": None, "rol_wizard": None, "is_accountant": False, "found": False} for e in emails if e and str(e).strip()}

    base_url = "https://api.hubapi.com"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    result = {}
    for idx, email in enumerate(emails):
        if not email or not str(email).strip():
            continue
        email = str(email).strip().lower()
        try:
            payload = {
                "filterGroups": [{"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}],
                "properties": ["es_contador", "rol_wizard", "email"],
                "limit": 1,
            }
            resp = requests.post(
                f"{base_url}/crm/v3/objects/contacts/search",
                headers=headers,
                json=payload,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                results = data.get("results", [])
                if results:
                    props = results[0].get("properties", {})
                    ec = props.get("es_contador")
                    rw = props.get("rol_wizard")
                    is_accountant = _is_accountant(ec, rw)
                    result[email] = {"es_contador": ec, "rol_wizard": rw, "is_accountant": is_accountant, "found": True}
                else:
                    result[email] = {"es_contador": None, "rol_wizard": None, "is_accountant": False, "found": False}
            else:
                result[email] = {"es_contador": None, "rol_wizard": None, "is_accountant": False, "found": False}
        except Exception as e:
            result[email] = {"es_contador": None, "rol_wizard": None, "is_accountant": False, "found": False, "error": str(e)}
        if not quiet and (idx + 1) % 20 == 0:
            print(f"   HubSpot: {idx + 1}/{len(emails)} emails queried...")
        time.sleep(batch_delay)
    return result


def is_first_invoice_related(text: str) -> tuple[bool, list[str]]:
    """Check if conversation text is related to first invoice / first time to value."""
    if not text:
        return False, []
    text_lower = text.lower()
    matched = []
    for kw in FIRST_INVOICE_KEYWORDS:
        if kw.lower() in text_lower:
            matched.append(kw)
    return len(matched) > 0, matched


def build_conversation_text(conv: dict) -> str:
    """Build full text from conversation parts."""
    parts = conv.get("parts", [])
    return " ".join(p.get("body", "") or "" for p in parts)


def _is_accountant_from_conv(conv: dict) -> bool | None:
    """Get is_accountant from Intercom cache (contact_es_contador, contact_rol_wizard). Returns None if not in cache."""
    ec = conv.get("contact_es_contador")
    rw = conv.get("contact_rol_wizard")
    if ec is None and rw is None:
        return None  # Not in cache
    return _is_accountant(ec, rw)


def run_llm_classify(
    filtered_convs: list[dict],
    cache_meta: dict,
    repo_root: Path,
    topic_override: str | None = None,
    quiet: bool = False,
) -> dict | None:
    """
    Run llm_classify.mjs on filtered conversations.
    topic_override: path to a topic JSON config (relative to repo root or absolute).
    Defaults to topic_first_invoice.json when not specified.
    Returns parsed result dict or None on failure.
    """
    script_path = repo_root / "plugins" / "colppy-customer-success" / "scripts" / "llm_classify.mjs"
    if topic_override:
        topic_path = Path(topic_override) if Path(topic_override).is_absolute() else repo_root / topic_override
    else:
        topic_path = repo_root / "plugins" / "colppy-customer-success" / "skills" / "intercom-onboarding-setup" / "topic_first_invoice.json"
    if not script_path.exists() or not topic_path.exists():
        if not quiet:
            missing = script_path if not script_path.exists() else topic_path
            print(f"Warning: not found: {missing}")
        return None
    temp_cache = {
        "conversations": filtered_convs,
        "from_date": cache_meta.get("from_date", ""),
        "to_date": cache_meta.get("to_date", ""),
        "team_assignee_id": cache_meta.get("team_assignee_id"),
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as fc:
        json.dump(temp_cache, fc, ensure_ascii=False, indent=2)
        temp_cache_path = fc.name
    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False, encoding="utf-8") as fo:
            temp_output_path = fo.name
        cmd = [
            "node",
            str(script_path),
            "--cache", temp_cache_path,
            "--topic", str(topic_path),
            "--all",
            "--output", temp_output_path,
        ]
        if not quiet:
            print(f"\nRunning LLM classifier ({topic_path.name})...")
        proc = subprocess.run(
            cmd,
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=300,
        )
        if proc.returncode != 0:
            if not quiet:
                print(f"llm_classify stderr: {proc.stderr}")
            return None
        with open(temp_output_path, "r", encoding="utf-8") as f:
            result = json.load(f)
        return result
    finally:
        try:
            os.unlink(temp_cache_path)
        except OSError:
            pass
        try:
            os.unlink(temp_output_path)
        except (OSError, NameError):
            pass


def _matches_user_type_from_conv(conv: dict, user_type: str) -> bool | None:
    """True if conversation belongs to requested user type. Returns None if cache lacks user-type data."""
    is_acc = _is_accountant_from_conv(conv)
    if is_acc is None:
        return None
    if user_type == "all":
        return True
    if user_type == "accountant":
        return is_acc
    if user_type == "smb":
        return not is_acc
    return False


def main():
    parser = argparse.ArgumentParser(
        description="Analyze onboarding conversations by user type (accountant|smb|all) with keyword or LLM classification"
    )
    parser.add_argument("--cache", required=True, help="Path to Intercom cache JSON (with contact_email)")
    parser.add_argument("--user-type", choices=["accountant", "smb", "all"], default="accountant", help="Filter: accountant (es_contador=true), smb (es_contador=false), or all")
    parser.add_argument("--llm", action="store_true", help="Run LLM classifier on filtered conversations (requires OPENAI_API_KEY)")
    parser.add_argument("--topic", help="Topic config JSON for LLM classifier (default: topic_first_invoice.json). E.g. plugins/colppy-customer-success/skills/intercom-onboarding-setup/topic.json for broader onboarding analysis")
    parser.add_argument("--output", help="Output report path (default: print to stdout)")
    parser.add_argument("--json", action="store_true", help="Output report as JSON for MCP (suppresses progress)")
    args = parser.parse_args()
    quiet = args.json

    cache_path = Path(args.cache)
    if not cache_path.is_absolute():
        cache_path = _REPO_ROOT / args.cache
    if not cache_path.exists():
        print(f"Error: Cache file not found: {cache_path}")
        return 1

    with open(cache_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    conversations = data.get("conversations", [])
    if not conversations:
        print("No conversations in cache.")
        return 0

    user_type = args.user_type
    user_label = USER_TYPE_LABELS[user_type]

    # Collect unique emails
    emails = []
    for c in conversations:
        em = c.get("contact_email")
        if em and str(em).strip():
            emails.append(str(em).strip().lower())
    unique_emails = list(dict.fromkeys(emails))

    # Prefer Intercom cache (contact_es_contador) — user level = contact level, synced with HubSpot
    has_intercom_user_type = any(
        c.get("contact_es_contador") is not None or c.get("contact_rol_wizard") is not None
        for c in conversations
    )

    if not quiet:
        print(f"Loaded {len(conversations)} conversations from {cache_path.name}")
        print(f"Unique contact emails: {len(unique_emails)}")
        print(f"User type filter: {user_label}")
        print(f"User type source: {'Intercom (contact_es_contador)' if has_intercom_user_type else 'HubSpot (fallback)'}")

    # HubSpot fallback only when cache lacks contact_es_contador (legacy caches)
    hubspot_filtered_emails = set()
    if user_type != "all" and not has_intercom_user_type:
        if not quiet:
            print("\nFetching HubSpot es_contador (cache lacks contact_es_contador, re-export with latest script)...")
        hubspot_data = fetch_hubspot_es_contador(unique_emails, quiet=quiet)
        if user_type == "accountant":
            hubspot_filtered_emails = {e for e, d in hubspot_data.items() if d.get("is_accountant")}
        else:
            hubspot_filtered_emails = {e for e, d in hubspot_data.items() if d.get("found") and not d.get("is_accountant")}
        if not quiet:
            print(f"   {user_label}: {len(hubspot_filtered_emails)} contacts")

    # Filter conversations and classify for first invoice
    filtered_convs = []
    first_invoice_convs = []
    all_first_invoice = []

    for conv in conversations:
        if user_type != "all":
            if has_intercom_user_type:
                match = _matches_user_type_from_conv(conv, user_type)
                if match is not True:  # False or None (no data)
                    continue
            else:
                em_lower = str(conv.get("contact_email") or "").strip().lower()
                if em_lower not in hubspot_filtered_emails:
                    continue
        filtered_convs.append(conv)
        text = build_conversation_text(conv)
        is_ftv, matched_kw = is_first_invoice_related(text)
        if is_ftv:
            all_first_invoice.append({**conv, "matched_keywords": matched_kw})
            first_invoice_convs.append({**conv, "matched_keywords": matched_kw})

    # LLM classification (when --llm)
    llm_result = None
    llm_matches = []
    if args.llm and filtered_convs:
        llm_result = run_llm_classify(filtered_convs, data, _REPO_ROOT, topic_override=args.topic, quiet=quiet)
        if llm_result:
            llm_matches = llm_result.get("classified", [])
            if not quiet:
                llm_topic = llm_result.get("topic", "first-invoice")
                print(f"   LLM ({llm_topic}): {llm_result.get('matches', 0)} matches of {llm_result.get('total_classified', 0)} classified")

    # When --llm and LLM ran successfully: use LLM matches as primary match set
    if args.llm and llm_matches:
        conv_by_id = {str(c["conversation_id"]): c for c in filtered_convs}
        first_invoice_convs = []
        for m in llm_matches:
            cid = m.get("conversation_id")
            conv = conv_by_id.get(str(cid))
            if conv:
                first_invoice_convs.append({
                    **conv,
                    "llm_category": m.get("llm", {}).get("category"),
                    "llm_confidence": m.get("llm", {}).get("confidence"),
                    "llm_reasoning": m.get("llm", {}).get("reasoning"),
                    "matched_keywords": m.get("matched_keywords", []),
                })

    # Report
    llm_topic_name = llm_result.get("topic", "First Invoice") if llm_result else "First Invoice"
    classifier_label = f"LLM ({llm_topic_name})" if args.llm and llm_result else "Keywords"
    report_title = llm_topic_name if args.llm and llm_result else "First Time to Value (First Invoice)"
    lines = [
        f"# Onboarding: {report_title} — {user_label}",
        "",
        f"**Source:** {cache_path.name}",
        f"**Date range:** {data.get('from_date', '?')} to {data.get('to_date', '?')}",
        f"**Team inbox:** {data.get('team_assignee_id') or 'All'} (Primeros 90 días)",
        f"**Classifier:** {classifier_label}",
        "",
        "## Summary",
        "",
        f"| Metric | Count |",
        f"|--------|-------|",
        f"| Total conversations in cache | {len(conversations)} |",
        f"| With contact_email | {sum(1 for c in conversations if c.get('contact_email'))} |",
        f"| {user_label} conversations | {len(filtered_convs)} |",
        f"| **{report_title} matches** | **{len(first_invoice_convs)}** |",
        "",
    ]

    if len(filtered_convs) == 0 and user_type != "all":
        src = "Intercom contact_es_contador (sync with HubSpot)" if has_intercom_user_type else "HUBSPOT_API_KEY"
        lines.append(f"**Note:** No contacts matched the requested user type. Verify {src}.")
        lines.append("")
    elif first_invoice_convs:
        pct = (len(first_invoice_convs) / len(filtered_convs) * 100) if filtered_convs else 0
        lines.append(f"**Of {user_label} onboarding conversations, {len(first_invoice_convs)} ({pct:.1f}%) match '{report_title}'.**")
        lines.append("")
        lines.append(f"## Matching conversations ({user_label})")
        lines.append("")
        for i, c in enumerate(first_invoice_convs[:30], 1):
            kw = ", ".join(c.get("matched_keywords", []))
            preview = (build_conversation_text(c)[:300] + "...") if len(build_conversation_text(c)) > 300 else build_conversation_text(c)
            lines.append(f"### {i}. {c.get('conversation_id', '')} ({c.get('created_at', '')[:10]})")
            lines.append(f"- **Keywords:** {kw}")
            if c.get("llm_category"):
                lines.append(f"- **LLM:** {c.get('llm_category')} ({int((c.get('llm_confidence') or 0) * 100)}%) — {c.get('llm_reasoning', '')[:150]}")
            lines.append(f"- **Preview:** {preview[:200]}...")
            lines.append("")
        if len(first_invoice_convs) > 30:
            lines.append(f"... and {len(first_invoice_convs) - 30} more.")
    else:
        lines.append(f"No '{report_title}' conversations found.")

    report = "\n".join(lines)

    if args.json:
        out = {
            "success": True,
            "user_type": user_type,
            "user_type_label": user_label,
            "used_llm": bool(args.llm and llm_result),
            "topic": llm_topic_name if args.llm and llm_result else "First Invoice",
            "topic_config": args.topic or "topic_first_invoice.json",
            "report": report,
            "summary": {
                "total_conversations": len(conversations),
                "with_contact_email": sum(1 for c in conversations if c.get("contact_email")),
                "filtered_conversations": len(filtered_convs),
                "match_count": len(first_invoice_convs),
                "match_pct": round(len(first_invoice_convs) / len(filtered_convs) * 100, 1) if filtered_convs else 0,
            },
            "matched_conversations": [
                {
                    "conversation_id": c["conversation_id"],
                    "created_at": c.get("created_at", "")[:10],
                    "matched_keywords": c.get("matched_keywords", []),
                    "llm_category": c.get("llm_category"),
                    "llm_confidence": c.get("llm_confidence"),
                }
                for c in first_invoice_convs[:50]
            ],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.output:
        Path(args.output).write_text(report, encoding="utf-8")
        print(f"\nReport saved to {args.output}")
    else:
        print("\n" + report)

    return 0


if __name__ == "__main__":
    exit(main())
