#!/usr/bin/env python3
"""
Fix Deal–Company Associations (Groups 1 & 2)
============================================
Fixes closedwon deals where billing company is missing or not PRIMARY.
Updates local deal_associations after each batch (no full populate needed).

Rule: We do not accept companies without a valid CUIT as PRIMARY. When a company
lacks CUIT, the script fixes it: (1) PATCH the company with customer_cuit from
facturacion, or (2) find another company with that CUIT in HubSpot and use that.

HubSpot allows only one primary company per deal. Before adding PRIMARY to the
billing company, the script removes PRIMARY from any other company on the deal.

Groups:
  1. Missing billing: billing company not associated at all → add association (PRIMARY)
  2. Billing not PRIMARY: billing associated but not type 5 → add PRIMARY
  3. Accountant not associated: accountant company (Cuenta Contador, etc.) matches customer_cuit
     but is not associated with deal (type 5 or 8) → add type 8 (Estudio Contable). Considers ALL
     companies per CUIT (not just one).
  5. MISMATCH: HubSpot primary CUIT ≠ Colppy DB CUIT → remove PRIMARY from wrong company,
     add PRIMARY to company with Colppy CUIT. Requires --colppy-db --year --month.
     When multiple companies share the same CUIT, disambiguates by id_empresa in name,
     then razon_social/empresa_nombre.

Usage:
    python tools/scripts/hubspot/fix_deal_associations.py --group 1 --batch 5
    python tools/scripts/hubspot/fix_deal_associations.py --group 2 --batch 5
    python tools/scripts/hubspot/fix_deal_associations.py --group 3 --batch 10
    python tools/scripts/hubspot/fix_deal_associations.py --status   # show counts only
    python tools/scripts/hubspot/fix_deal_associations.py --dry-run  # show what would be fixed
    # Group 1 with Colppy DB (fixes NO_PRIMARY deals not in billing):
    python tools/scripts/hubspot/fix_deal_associations.py --group 1 --colppy-db --year 2026 --month 2 --dry-run
    python tools/scripts/hubspot/fix_deal_associations.py --group 2 --batch 10  # logs to edit_logs by default; use --no-log to skip

    # Group 1 with Colppy DB (fix NO_PRIMARY deals not in billing):
    python tools/scripts/hubspot/fix_deal_associations.py --group 1 --colppy-db --year 2026 --month 2 --dry-run
    # Group 5 (MISMATCH: wrong primary CUIT → swap to Colppy DB company):
    python tools/scripts/hubspot/fix_deal_associations.py --group 5 --colppy-db --year 2026 --month 2 --dry-run

Fix association label (change type 11 → 8 for accountant company):
    python tools/scripts/hubspot/fix_deal_associations.py --fix-label 9424153860 9019047084 --remove 11 --add 8

Rule for accountant (type 8): Company type ∈ Cuenta Contador | Cuenta Contador y Reseller | Contador Robado,
or Empresa Administrada + industria contabilidad, or (fallback) name suggests accountant when type/industria empty.
When inferred from name, the script also enriches the company: type=Cuenta Contador, industria=Contabilidad, impuestos, legales.
After each fix batch, an audit corrects type 8/11 labels when company.type is null or inconsistent.
See tools/docs/HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md section 0.1.
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))
from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "tools" / ".env")

DEFAULT_DB = str(REPO_ROOT / "tools" / "data" / "facturacion_hubspot.db")
DEFAULT_COLPPY_DB = str(REPO_ROOT / "tools" / "data" / "colppy_export.db")

EXCLUDE_CUITS = {"12345678911", "12345678901", "00000000000"}

# Company types that identify accountant firms → association type 8 (Estudio Contable)
ACCOUNTANT_COMPANY_TYPES = {"Cuenta Contador", "Cuenta Contador y Reseller", "Contador Robado"}

# Empresa Administrada + industria contabilidad → treat as accountant (type 8)
INDUSTRIA_CONTABILIDAD = "Contabilidad, impuestos, legales"

# Name patterns to infer accountant when type/industria are empty (fallback only)
ACCOUNTANT_NAME_PATTERNS = (
    "estudio contable",
    "estudio de contabilidad",
    "contador",
    "contadores",
    "asesor impositivo",
    "contaduría",
    "contadoría",
    "asesoramiento contable",
    "servicios contables",
)


def _normalize_cuit(raw: str) -> str | None:
    """Normalize CUIT to 11 digits. Returns None if invalid."""
    if not raw or str(raw).strip().upper() in ("#N/A", "N/A", ""):
        return None
    digits = re.sub(r"[^\d]", "", str(raw).strip())
    if len(digits) != 11 or not digits.isdigit() or digits in EXCLUDE_CUITS:
        return None
    return digits


def _format_cuit_display(digits: str) -> str:
    """Format 11 digits as XX-XXXXXXXX-X."""
    if not digits or len(digits) != 11:
        return str(digits)
    return f"{digits[:2]}-{digits[2:10]}-{digits[10]}"


def _format_amount(raw: str | float) -> str:
    """Format amount for Argentina: $ with dot as thousand sep, comma as decimal."""
    if raw is None or raw == "":
        return ""
    s = str(raw).strip().replace(",", ".")
    try:
        n = float(s)
        int_part = int(n)
        dec_part = round((n - int_part) * 100)
        formatted = f"{int_part:,}".replace(",", ".") if int_part else "0"
        return f"${formatted},{dec_part:02d}" if dec_part else f"${formatted}"
    except (ValueError, TypeError):
        return str(raw)


def _verify_and_fix_companies(
    client,
    batch: list[dict],
    cuit_by_deal: dict[str, str],
) -> tuple[list[dict], list[dict]]:
    """
    Verify each billing company has CUIT in HubSpot. If not, fix it:
    1. PATCH company with customer_cuit from facturacion
    2. If PATCH fails, search for another company with that CUIT and use it
    Returns (to_fix, outcomes) where outcomes is list of {deal_id, outcome, detail} for logging.
    """
    company_ids = list(dict.fromkeys(r["billing_id"] for r in batch))
    valid_ids = set()
    batch_size = 100
    for i in range(0, len(company_ids), batch_size):
        chunk = company_ids[i : i + batch_size]
        try:
            resp = client.post(
                "crm/v3/objects/companies/batch/read",
                json_data={"inputs": [{"id": cid} for cid in chunk], "properties": ["cuit"]},
            )
            for r in resp.get("results", []):
                cid = r.get("id")
                if _normalize_cuit((r.get("properties") or {}).get("cuit") or ""):
                    valid_ids.add(cid)
        except Exception as e:
            print(f"  Warning: Could not verify CUIT ({e})", file=sys.stderr)

    to_fix: list[dict] = []
    outcomes: list[dict] = []  # {deal_id, deal_name, billing_id, billing_name, customer_cuit, outcome, detail}

    for r in batch:
        bid = r["billing_id"]
        deal_id = r["deal_id"]
        customer_cuit = cuit_by_deal.get(deal_id) or ""
        cuit_norm = _normalize_cuit(customer_cuit)
        base_outcome = {**r, "outcome": "", "detail": ""}

        if bid in valid_ids:
            to_fix.append(r)
            outcomes.append({**base_outcome, "outcome": "to_fix", "detail": "cuit_ok"})
            continue

        if not cuit_norm:
            print(f"  Skip {deal_id}: no customer_cuit in facturacion for deal")
            outcomes.append({**base_outcome, "outcome": "skipped", "detail": "no_customer_cuit"})
            continue

        cuit_display = _format_cuit_display(cuit_norm)

        try:
            client.patch(
                f"crm/v3/objects/companies/{bid}",
                json_data={"properties": {"cuit": cuit_display}},
            )
            print(f"  Fixed CUIT on company {bid} ({r['billing_name'][:35]}) → {cuit_display}")
            to_fix.append(r)
            outcomes.append({**base_outcome, "outcome": "to_fix", "detail": "cuit_patched"})
            continue
        except Exception:
            pass

        found_alt = False
        try:
            for cuit_val in [cuit_display, cuit_norm]:
                resp = client.search_objects(
                    object_type="companies",
                    filter_groups=[{"filters": [{"propertyName": "cuit", "operator": "EQ", "value": cuit_val}]}],
                    properties=["name", "cuit"],
                    limit=5,
                )
                results = resp.get("results", [])
                if results:
                    alt_id = results[0].get("id")
                    if alt_id and alt_id != bid:
                        print(f"  Using alternative company {alt_id} (has CUIT) for deal {deal_id} instead of {bid}")
                        to_fix.append({**r, "billing_id": alt_id, "billing_name": results[0].get("properties", {}).get("name", "")})
                        outcomes.append({
                            **base_outcome,
                            "billing_id": alt_id,
                            "billing_name": results[0].get("properties", {}).get("name", ""),
                            "outcome": "to_fix",
                            "detail": "cuit_alternative",
                        })
                        found_alt = True
                        break
        except Exception:
            pass

        if not found_alt:
            print(f"  Skip {deal_id}: could not fix CUIT on {bid} and no alternative company found")
            outcomes.append({**base_outcome, "outcome": "skipped", "detail": "cuit_unfixable"})

    return to_fix, outcomes


def _remove_primary_from_wrong_companies(
    client, to_fix: list[dict], conn: sqlite3.Connection | None = None
) -> None:
    """
    HubSpot allows only one primary per deal. Remove PRIMARY (type 5) from any
    company that is not our billing company, so we can add PRIMARY to the correct one.
    Updates local deal_associations to remove stale PRIMARY rows.
    """
    deal_to_billing = {r["deal_id"]: r["billing_id"] for r in to_fix}
    deal_ids = list(deal_to_billing.keys())

    # Batch read deal→company associations
    try:
        resp = client.post(
            "crm/v4/associations/deals/companies/batch/read",
            json_data={"inputs": [{"id": did} for did in deal_ids]},
        )
    except Exception as e:
        print(f"  Warning: Could not fetch associations ({e})", file=sys.stderr)
        return

    archive_inputs = []
    for r in resp.get("results", []):
        deal_id = r.get("from", {}).get("id")
        billing_id = deal_to_billing.get(deal_id)
        if not billing_id:
            continue
        for to_obj in r.get("to", []) or []:
            company_id = str(to_obj.get("toObjectId", ""))
            if not company_id or company_id == billing_id:
                continue
            types = to_obj.get("associationTypes", [])
            if any(t.get("typeId") == 5 for t in types):
                archive_inputs.append({
                    "from": {"id": deal_id},
                    "to": {"id": company_id},
                    "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 5}],
                })

    if not archive_inputs:
        return

    # Archive PRIMARY from deal→company (type 5)
    try:
        client.post(
            "crm/v4/associations/deals/companies/batch/labels/archive",
            json_data={"inputs": archive_inputs},
        )
        if archive_inputs:
            print(f"  Removed PRIMARY from {len(archive_inputs)} wrong company/deal pair(s)")
    except Exception as e:
        print(f"  Warning: Could not remove PRIMARY labels ({e})", file=sys.stderr)

    # Archive type 6 (Company→Deal "Deal with Primary Company") for same pairs
    company_archive = [
        {"from": {"id": inp["to"]["id"]}, "to": {"id": inp["from"]["id"]}, "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 6}]}
        for inp in archive_inputs
    ]
    try:
        client.post(
            "crm/v4/associations/companies/deals/batch/labels/archive",
            json_data={"inputs": company_archive},
        )
    except Exception as e:
        print(f"  Warning: Could not remove company-side PRIMARY labels ({e})", file=sys.stderr)

    # Remove stale PRIMARY from local deal_associations
    if conn:
        for inp in archive_inputs:
            delete_association_local(
                conn, inp["from"]["id"], inp["to"]["id"], type_id=5
            )

    # Set correct association label (8 or 11) for each company that lost PRIMARY
    pairs = [(inp["from"]["id"], inp["to"]["id"]) for inp in archive_inputs]
    _fix_secondary_company_labels(client, pairs, conn)


def _audit_deal_association_labels(
    client,
    deal_ids: list[str],
    billing_id_by_deal: dict[str, str],
    conn: sqlite3.Connection | None = None,
) -> None:
    """
    Audit all non-primary companies on deals. Fix type 8/11 when inconsistent with company.type/industria/name.

    Rule: type 8 (Estudio Contable) only if company.type ∈ accountant types, Empresa Administrada + industria contabilidad,
    or (fallback) type/industria empty and name suggests accountant (e.g. "Estudio Contable X").
    Otherwise → type 11 (Múltiples Negocios).
    """
    if not deal_ids:
        return
    try:
        resp = client.post(
            "crm/v4/associations/deals/companies/batch/read",
            json_data={"inputs": [{"id": did} for did in deal_ids]},
        )
    except Exception as e:
        print(f"  Warning: Could not fetch associations for audit ({e})", file=sys.stderr)
        return

    to_fix: list[tuple[str, str, bool, bool]] = []  # (deal_id, company_id, has_type_8, has_type_11)
    company_ids = set()
    for r in resp.get("results", []):
        deal_id = r.get("from", {}).get("id")
        billing_id = billing_id_by_deal.get(deal_id)
        for to_obj in r.get("to", []) or []:
            company_id = str(to_obj.get("toObjectId", ""))
            if not company_id or company_id == billing_id:
                continue
            types = to_obj.get("associationTypes", []) or []
            has_8 = any(t.get("typeId") == 8 for t in types)
            has_11 = any(t.get("typeId") == 11 for t in types)
            if has_8 or has_11:
                to_fix.append((deal_id, company_id, has_8, has_11))
                company_ids.add(company_id)

    if not to_fix:
        return

    # Batch fetch company type, industria, and name (name used for fallback inference)
    type_by_company: dict[str, str] = {}
    industria_by_company: dict[str, str] = {}
    name_by_company: dict[str, str] = {}
    for i in range(0, len(company_ids), 100):
        chunk = list(company_ids)[i : i + 100]
        try:
            r = client.post(
                "crm/v3/objects/companies/batch/read",
                json_data={"inputs": [{"id": cid} for cid in chunk], "properties": ["type", "industria", "name"]},
            )
            for res in r.get("results", []):
                cid = str(res.get("id", ""))
                props = res.get("properties") or {}
                type_by_company[cid] = str(props.get("type") or "").strip()
                industria_by_company[cid] = str(props.get("industria") or "").strip()
                name_by_company[cid] = str(props.get("name") or "").strip()
        except Exception as e:
            print(f"  Warning: Could not fetch company types for audit ({e})", file=sys.stderr)
            return

    corrections = 0
    inferred_from_name: list[tuple[str, str, str]] = []  # (deal_id, company_id, company_name)
    for deal_id, company_id, has_8, has_11 in to_fix:
        ctype = type_by_company.get(company_id, "")
        industria = industria_by_company.get(company_id, "")
        name = name_by_company.get(company_id, "")
        is_accountant = _is_accountant_company(ctype, industria, name)

        if is_accountant and has_11:
            remove_ids, add_ids = [11], [8]
            # Enrich company when inferred from name (type/industria empty)
            if not ctype and not industria and name:
                if _enrich_company_as_accountant(client, company_id, name, quiet=True):
                    inferred_from_name.append((deal_id, company_id, name))
        elif not is_accountant and has_8:
            remove_ids, add_ids = [8], [11]
        else:
            continue

        success, msg = fix_association_label(
            client, deal_id, company_id, remove_ids, add_ids, dry_run=False, quiet=True
        )
        if success:
            corrections += 1
            if conn:
                for tid in remove_ids:
                    delete_association_local(conn, deal_id, company_id, type_id=tid)
                for tid in add_ids:
                    cat = "USER_DEFINED" if tid in USER_DEFINED_TYPES else "HUBSPOT_DEFINED"
                    conn.execute(
                        "INSERT OR REPLACE INTO deal_associations (deal_hubspot_id, company_hubspot_id, association_type_id, association_category) VALUES (?, ?, ?, ?)",
                        (deal_id, company_id, tid, cat),
                    )
                    conn.commit()
        else:
            print(f"  Warning: Audit fix failed deal {deal_id} → company {company_id}: {msg}", file=sys.stderr)

    if corrections:
        print(f"  Audit: corrected {corrections} association label(s) (type 8↔11 by company.type/name)")
    if inferred_from_name:
        print(f"  Audit inferred from name ({len(inferred_from_name)}): enriched type=Cuenta Contador, industria={INDUSTRIA_CONTABILIDAD}")
        for deal_id, company_id, cname in inferred_from_name:
            print(f"    → deal {deal_id} | company {company_id} ({cname[:45]})")
    elif to_fix:
        print(f"  Audit inferred from name: 0")


def _is_accountant_by_name(name: str) -> bool:
    """
    Infer accountant from company name when type/industria are empty.
    Used as fallback only. Returns True if name contains any ACCOUNTANT_NAME_PATTERNS.
    """
    if not name or not str(name).strip():
        return False
    lower = str(name).strip().lower()
    return any(p in lower for p in ACCOUNTANT_NAME_PATTERNS)


def _enrich_company_as_accountant(
    client, company_id: str, company_name: str = "", quiet: bool = True
) -> bool:
    """
    PATCH company with type=Cuenta Contador and industria=Contabilidad, impuestos, legales.
    Used when we inferred accountant from name (type/industria were empty).
    Returns True on success.
    """
    try:
        client.patch(
            f"crm/v3/objects/companies/{company_id}",
            json_data={
                "properties": {
                    "type": "Cuenta Contador",
                    "industria": INDUSTRIA_CONTABILIDAD,
                }
            },
        )
        if not quiet:
            print(f"  Enriched company {company_id} ({company_name[:40]}) → type=Cuenta Contador, industria={INDUSTRIA_CONTABILIDAD}")
        return True
    except Exception as e:
        if not quiet:
            print(f"  Warning: Could not enrich company {company_id}: {e}", file=sys.stderr)
        return False


def _is_accountant_company(ctype: str, industria: str, name: str = "") -> bool:
    """
    True if company is accountant:
    1. type in ACCOUNTANT_COMPANY_TYPES, or
    2. Empresa Administrada + industria contabilidad, or
    3. (Fallback) type and industria empty AND name suggests accountant (e.g. 'Estudio Contable X').
    """
    if ctype in ACCOUNTANT_COMPANY_TYPES:
        return True
    if ctype == "Empresa Administrada" and industria and "contabilidad" in industria.lower():
        return True
    # Fallback: when type/industria are empty, infer from name
    if not ctype and not industria and name:
        return _is_accountant_by_name(name)
    return False


def _fix_secondary_company_labels(
    client, pairs: list[tuple[str, str]], conn: sqlite3.Connection | None = None
) -> None:
    """
    Set correct association label for non-primary companies based on Company type/industria/name.

    Rule: company.type ∈ Cuenta Contador | Cuenta Contador y Reseller | Contador Robado
    → type 8 (Estudio Contable). Empresa Administrada + industria contabilidad → type 8.
    Fallback: when type and industria are empty, infer from name (e.g. "Estudio Contable X").
    Otherwise → type 11 (Múltiples Negocios).
    Updates local deal_associations with the new label (8 or 11).
    """
    if not pairs:
        return
    print(f"  Setting association labels for {len(pairs)} secondary company/deal pair(s) (type 8 or 11 by company.type/industria/name)")
    company_ids = list(dict.fromkeys(cid for _, cid in pairs))
    type_by_company: dict[str, str] = {}
    industria_by_company: dict[str, str] = {}
    name_by_company: dict[str, str] = {}
    for i in range(0, len(company_ids), 100):
        chunk = company_ids[i : i + 100]
        try:
            resp = client.post(
                "crm/v3/objects/companies/batch/read",
                json_data={"inputs": [{"id": cid} for cid in chunk], "properties": ["type", "industria", "name"]},
            )
            for r in resp.get("results", []):
                cid = str(r.get("id", ""))
                props = r.get("properties") or {}
                type_by_company[cid] = str(props.get("type") or "").strip()
                industria_by_company[cid] = str(props.get("industria") or "").strip()
                name_by_company[cid] = str(props.get("name") or "").strip()
        except Exception as e:
            print(f"  Warning: Could not fetch company types ({e})", file=sys.stderr)
            return

    inferred_from_name: list[tuple[str, str, str]] = []  # (deal_id, company_id, company_name)
    for deal_id, company_id in pairs:
        ctype = type_by_company.get(company_id, "")
        industria = industria_by_company.get(company_id, "")
        name = name_by_company.get(company_id, "")
        is_accountant = _is_accountant_company(ctype, industria, name)
        if is_accountant:
            remove_ids, add_ids = [11], [8]
            # Enrich company when inferred from name (type/industria empty)
            if not ctype and not industria and name:
                if _enrich_company_as_accountant(client, company_id, name, quiet=True):
                    inferred_from_name.append((deal_id, company_id, name))
        else:
            remove_ids, add_ids = [8], [11]
        success, msg = fix_association_label(
            client, deal_id, company_id, remove_ids, add_ids, dry_run=False, quiet=True
        )
        if not success:
            print(f"  Warning: Could not set label for deal {deal_id} → company {company_id}: {msg}", file=sys.stderr)
        elif conn:
            # Update local deal_associations: remove old label, add new
            for tid in remove_ids:
                delete_association_local(conn, deal_id, company_id, type_id=tid)
            for tid in add_ids:
                cat = "USER_DEFINED" if tid in USER_DEFINED_TYPES else "HUBSPOT_DEFINED"
                conn.execute(
                    "INSERT OR REPLACE INTO deal_associations (deal_hubspot_id, company_hubspot_id, association_type_id, association_category) VALUES (?, ?, ?, ?)",
                    (deal_id, company_id, tid, cat),
                )
                conn.commit()
    if inferred_from_name:
        print(f"  Inferred from name ({len(inferred_from_name)}): enriched type=Cuenta Contador, industria={INDUSTRIA_CONTABILIDAD}")
        for deal_id, company_id, cname in inferred_from_name:
            print(f"    → deal {deal_id} | company {company_id} ({cname[:45]})")
    else:
        print(f"  Inferred from name: 0")


# Active deal stages (in facturacion): closedwon + Cerrado Ganado Recupero
ACTIVE_DEAL_STAGES = ("closedwon", "34692158")

# Group 1: billing company (any with that CUIT) not associated as PRIMARY
# Facturacion is master: deal must have a company with customer_cuit as PRIMARY
SQL_GROUP1 = """
SELECT d.hubspot_id, d.deal_name, d.amount, d.id_empresa,
  (SELECT c2.hubspot_id FROM companies c2
   WHERE c2.cuit = f.customer_cuit AND c2.hubspot_id != ''
   ORDER BY c2.hubspot_id LIMIT 1) as billing_id,
  (SELECT c2.name FROM companies c2
   WHERE c2.cuit = f.customer_cuit AND c2.hubspot_id != ''
   ORDER BY c2.hubspot_id LIMIT 1) as billing_name,
  f.customer_cuit
FROM facturacion f
JOIN deals d ON f.id_empresa = d.id_empresa
WHERE d.deal_stage IN ('closedwon', '34692158')
AND d.hubspot_id != ''
AND f.customer_cuit IN (SELECT cuit FROM companies WHERE hubspot_id != '')
AND NOT EXISTS (
  SELECT 1 FROM deal_associations da
  JOIN companies c ON da.company_hubspot_id = c.hubspot_id
  WHERE da.deal_hubspot_id = d.hubspot_id AND c.cuit = f.customer_cuit AND da.association_type_id = 5
)
GROUP BY d.hubspot_id
ORDER BY CAST(d.amount AS INTEGER) DESC
"""

# Group 2: deal has company with customer_cuit but not as PRIMARY
SQL_GROUP2 = """
SELECT d.hubspot_id, d.deal_name, d.amount, d.id_empresa,
  (SELECT c2.hubspot_id FROM companies c2
   WHERE c2.cuit = f.customer_cuit AND c2.hubspot_id != ''
   ORDER BY c2.hubspot_id LIMIT 1) as billing_id,
  (SELECT c2.name FROM companies c2
   WHERE c2.cuit = f.customer_cuit AND c2.hubspot_id != ''
   ORDER BY c2.hubspot_id LIMIT 1) as billing_name,
  f.customer_cuit
FROM facturacion f
JOIN deals d ON f.id_empresa = d.id_empresa
WHERE d.deal_stage IN ('closedwon', '34692158')
AND d.hubspot_id != ''
AND f.customer_cuit IN (SELECT cuit FROM companies WHERE hubspot_id != '')
AND EXISTS (
  SELECT 1 FROM deal_associations da
  JOIN companies c ON da.company_hubspot_id = c.hubspot_id
  WHERE da.deal_hubspot_id = d.hubspot_id AND c.cuit = f.customer_cuit
)
AND NOT EXISTS (
  SELECT 1 FROM deal_associations da
  JOIN companies c ON da.company_hubspot_id = c.hubspot_id
  WHERE da.deal_hubspot_id = d.hubspot_id AND c.cuit = f.customer_cuit AND da.association_type_id = 5
)
GROUP BY d.hubspot_id
ORDER BY CAST(d.amount AS INTEGER) DESC
"""


def _date_filter_sql(year: int | None, month: int | None) -> tuple[str, list]:
    """Return (date_sql, params) for close_date filter. Empty if year/month not provided."""
    if year is None or month is None:
        return "", []
    import calendar
    start = f"{year}-{month:02d}-01"
    last_day = calendar.monthrange(year, month)[1]
    end = f"{year}-{month:02d}-{last_day}"
    return " AND d.close_date >= ? AND d.close_date <= ?", [start, end]


def _load_colppy_cuit_map(colppy_db_path: Path) -> dict[str, dict]:
    """
    Load id_empresa → {cuit, cuit_display, razon_social, empresa_nombre} from colppy_export.db.
    Primary: facturacion.CUIT. Fallback: empresa.CUIT.
    empresa_nombre (empresa.Nombre) is used for disambiguation when multiple HubSpot companies share the same CUIT.
    """
    if not colppy_db_path.exists():
        return {}
    with sqlite3.connect(colppy_db_path) as conn:
        conn.row_factory = sqlite3.Row
        by_facturacion: dict[str, dict] = {}
        cur = conn.execute(
            """
            SELECT f.IdEmpresa AS id_empresa, f.CUIT AS cuit_raw, f.razonSocial
            FROM facturacion f
            WHERE (f.fechaBaja IS NULL OR f.fechaBaja = '' OR f.fechaBaja = '0000-00-00')
              AND f.IdEmpresa IS NOT NULL AND f.IdEmpresa != 0 AND f.IdEmpresa != ''
            """
        )
        for r in cur.fetchall():
            ie = str(r["id_empresa"] or "").strip()
            if not ie:
                continue
            cuit = _normalize_cuit(r["cuit_raw"] or "")
            if cuit and len(cuit) == 11:
                by_facturacion[ie] = {
                    "cuit": cuit,
                    "cuit_display": _format_cuit_display(cuit),
                    "razon_social": (r["razonSocial"] or "").strip()[:80],
                    "empresa_nombre": "",
                }
        # Enrich with empresa.Nombre for disambiguation (same id_empresa can have different names)
        cur2 = conn.execute(
            """
            SELECT e.IdEmpresa AS id_empresa, e.Nombre AS empresa_nombre
            FROM empresa e
            WHERE e.IdEmpresa IS NOT NULL AND e.IdEmpresa != 0 AND e.IdEmpresa != ''
            """
        )
        empresa_by_ie: dict[str, str] = {}
        for r in cur2.fetchall():
            ie = str(r["id_empresa"] or "").strip()
            if ie:
                empresa_by_ie[ie] = (r["empresa_nombre"] or "").strip()[:80]
        for ie, data in by_facturacion.items():
            data["empresa_nombre"] = empresa_by_ie.get(ie, "")
        # Fallback: id_empresa not in facturacion
        cur3 = conn.execute(
            """
            SELECT e.IdEmpresa AS id_empresa, e.CUIT AS cuit_raw, e.Nombre AS empresa_nombre
            FROM empresa e
            WHERE e.IdEmpresa IS NOT NULL AND e.IdEmpresa != 0 AND e.IdEmpresa != ''
            """
        )
        for r in cur3.fetchall():
            ie = str(r["id_empresa"] or "").strip()
            if not ie or ie in by_facturacion:
                continue
            cuit = _normalize_cuit(r["cuit_raw"] or "")
            if cuit and len(cuit) == 11:
                by_facturacion[ie] = {
                    "cuit": cuit,
                    "cuit_display": _format_cuit_display(cuit),
                    "razon_social": (r["empresa_nombre"] or "").strip()[:80],
                    "empresa_nombre": (r["empresa_nombre"] or "").strip()[:80],
                }
    return by_facturacion


def _pick_target_company_by_cuit(
    conn: sqlite3.Connection,
    cuit_norm: str,
    id_empresa: str,
    razon_social: str,
    empresa_nombre: str,
) -> tuple[str | None, str]:
    """
    When multiple HubSpot companies share the same CUIT, pick the one for this deal.
    Tiebreaker: (1) company name starts with "{id_empresa} - ", (2) name contains razon_social or empresa_nombre.
    Returns (hubspot_id, name) or (None, "") if no match or ambiguous.
    """
    rows = conn.execute(
        """
        SELECT hubspot_id, name FROM companies
        WHERE (REPLACE(REPLACE(REPLACE(COALESCE(cuit,''),'-',''),' ',''),'.','') = ?)
          AND hubspot_id != ''
        """,
        (cuit_norm,),
    ).fetchall()
    if not rows:
        return None, ""
    if len(rows) == 1:
        return rows[0][0], (rows[0][1] or "")
    # Multiple companies with same CUIT: use tiebreaker
    id_prefix = f"{id_empresa} - "
    rs_lower = (razon_social or "").strip().lower()
    en_lower = (empresa_nombre or "").strip().lower()
    for hubspot_id, name in rows:
        name_str = (name or "").strip()
        if name_str.startswith(id_prefix):
            return hubspot_id, name_str
    for hubspot_id, name in rows:
        name_lower = (name or "").strip().lower()
        if rs_lower and rs_lower in name_lower:
            return hubspot_id, (name or "")
        if en_lower and en_lower in name_lower:
            return hubspot_id, (name or "")
    return None, ""  # ambiguous


def _get_group5_mismatch_candidates(
    conn: sqlite3.Connection,
    colppy_db_path: Path,
    year: int | None = None,
    month: int | None = None,
) -> list[dict]:
    """
    Group 5 (MISMATCH): Deals where HubSpot primary company CUIT ≠ Colppy DB CUIT.
    Fix: remove PRIMARY from wrong company, add PRIMARY to company with Colppy CUIT.
    When multiple companies share the same CUIT, uses id_empresa/razon_social/empresa_nombre to disambiguate.
    Returns list of {deal_id, deal_name, amount, id_empresa, billing_id, billing_name, customer_cuit}.
    Skips when target company not found or ambiguous.
    """
    colppy_cuit = _load_colppy_cuit_map(colppy_db_path)
    if not colppy_cuit:
        return []
    import calendar

    sql = """
        SELECT d.hubspot_id, d.deal_name, d.amount, d.id_empresa, d.close_date,
               da.company_hubspot_id AS primary_company_hs_id,
               c.cuit AS hubspot_primary_cuit
        FROM deals d
        JOIN deal_associations da ON da.deal_hubspot_id = d.hubspot_id AND da.association_type_id = 5
        JOIN companies c ON c.hubspot_id = da.company_hubspot_id
        WHERE d.deal_stage IN ('closedwon', '34692158')
          AND d.hubspot_id != ''
          AND d.id_empresa IS NOT NULL AND d.id_empresa != ''
    """
    params: list = []
    if year is not None and month is not None:
        start = f"{year}-{month:02d}-01"
        last_day = calendar.monthrange(year, month)[1]
        end = f"{year}-{month:02d}-{last_day}"
        sql += " AND d.close_date >= ? AND d.close_date <= ?"
        params = [start, end]
    sql += " ORDER BY CAST(d.amount AS INTEGER) DESC"

    rows = conn.execute(sql, params).fetchall()
    result: list[dict] = []
    for r in rows:
        ie = str(r[3] or "").strip()
        colppy_row = colppy_cuit.get(ie)
        if not colppy_row:
            continue
        colppy_cuit_norm = colppy_row.get("cuit", "")
        hs_cuit_norm = _normalize_cuit(r[6])
        if not colppy_cuit_norm or colppy_cuit_norm in EXCLUDE_CUITS:
            continue
        if hs_cuit_norm == colppy_cuit_norm:
            continue  # MATCH, not MISMATCH
        target_id, target_name = _pick_target_company_by_cuit(
            conn,
            colppy_cuit_norm,
            ie,
            colppy_row.get("razon_social", ""),
            colppy_row.get("empresa_nombre", ""),
        )
        if not target_id:
            continue
        result.append({
            "deal_id": r[0],
            "deal_name": r[1],
            "amount": r[2],
            "id_empresa": ie,
            "billing_id": target_id,
            "billing_name": target_name or "",
            "customer_cuit": colppy_row.get("cuit_display", ""),
        })
    return result


def _find_company_by_name(
    conn: sqlite3.Connection,
    id_empresa: str,
    razon_social: str,
    empresa_nombre: str,
    client=None,
) -> tuple[str | None, str]:
    """
    Fallback when no company found by CUIT: search by name.
    1. DB: name starts with "{id_empresa} - " or contains empresa_nombre/razon_social key part.
    2. HubSpot API: text search by id_empresa or empresa_nombre (if client provided).
    Returns (hubspot_id, name) or (None, "").
    """
    id_prefix = f"{id_empresa} - "
    en = (empresa_nombre or "").strip()
    rs = (razon_social or "").strip()
    # Prefer short distinctive name for search (empresa_nombre often matches deal)
    search_term = en if len(en) > 3 else (rs.split()[0] if rs else id_empresa)

    # 1. Search our DB by name
    rows = conn.execute(
        """
        SELECT hubspot_id, name FROM companies
        WHERE hubspot_id != '' AND (
          name LIKE ? OR name LIKE ?
        )
        ORDER BY CASE WHEN name LIKE ? THEN 0 ELSE 1 END
        LIMIT 1
        """,
        (id_prefix + "%", "%" + (search_term or "") + "%", id_prefix + "%"),
    ).fetchall()
    if rows:
        return rows[0][0], (rows[0][1] or "")

    # 2. HubSpot API text search (query param does full-text search)
    if client and search_term:
        try:
            resp = client.search_objects(
                object_type="companies",
                query=search_term[:50],
                properties=["name", "cuit"],
                limit=5,
            )
            results = resp.get("results", [])
            for obj in results:
                name = (obj.get("properties") or {}).get("name", "")
                if not name:
                    continue
                # Prefer name starting with id_empresa
                if name.strip().startswith(id_prefix):
                    return str(obj.get("id", "")), name
                # Or contains search term
                if search_term.lower() in (name or "").lower():
                    return str(obj.get("id", "")), name
            if results:
                r0 = results[0]
                return str(r0.get("id", "")), (r0.get("properties") or {}).get("name", "")
        except Exception:
            pass
    return None, ""


def _get_group1_colppy_db(
    conn: sqlite3.Connection,
    colppy_db_path: Path,
    year: int | None = None,
    month: int | None = None,
    client=None,
) -> list[dict]:
    """
    Group 1 (Colppy DB source): Deals with NO_PRIMARY (no type 5 association).
    Uses Colppy DB for CUIT mapping instead of facturacion (billing CSV).
    When no company with CUIT in DB, falls back to search by name (DB then HubSpot API if client).
    Returns list of {deal_id, deal_name, amount, id_empresa, billing_id, billing_name, customer_cuit}.
    """
    colppy_cuit = _load_colppy_cuit_map(colppy_db_path)
    if not colppy_cuit:
        return []

    # NO_PRIMARY deals: no type 5 association
    sql = """
        SELECT d.hubspot_id, d.deal_name, d.amount, d.id_empresa, d.close_date
        FROM deals d
        LEFT JOIN deal_associations da ON da.deal_hubspot_id = d.hubspot_id AND da.association_type_id = 5
        WHERE d.deal_stage IN ('closedwon', '34692158')
          AND d.hubspot_id != ''
          AND d.id_empresa IS NOT NULL AND d.id_empresa != ''
          AND da.company_hubspot_id IS NULL
    """
    params: list = []
    if year is not None and month is not None:
        start = f"{year}-{month:02d}-01"
        import calendar
        last_day = calendar.monthrange(year, month)[1]
        end = f"{year}-{month:02d}-{last_day}"
        sql += " AND d.close_date >= ? AND d.close_date <= ?"
        params = [start, end]
    sql += " ORDER BY CAST(d.amount AS INTEGER) DESC"

    rows = conn.execute(sql, params).fetchall()
    result: list[dict] = []
    for r in rows:
        ie = str(r[3] or "").strip()
        colppy_row = colppy_cuit.get(ie)
        if not colppy_row:
            continue
        cuit = colppy_row["cuit"]
        cuit_display = colppy_row["cuit_display"]
        if not cuit or cuit in EXCLUDE_CUITS:
            continue
        # 1. Find by CUIT in our DB
        company_row = conn.execute(
            """
            SELECT hubspot_id, name FROM companies
            WHERE (cuit = ? OR REPLACE(REPLACE(REPLACE(COALESCE(cuit,''),'-',''),' ',''),'.','') = ?)
              AND hubspot_id != ''
            ORDER BY hubspot_id LIMIT 1
            """,
            (cuit, cuit),
        ).fetchone()
        if not company_row:
            # 2. Fallback: search by name (DB then HubSpot API)
            billing_id, billing_name = _find_company_by_name(
                conn, ie,
                colppy_row.get("razon_social", ""),
                colppy_row.get("empresa_nombre", ""),
                client,
            )
            if not billing_id:
                continue
        else:
            billing_id, billing_name = company_row[0], company_row[1]
        result.append({
            "deal_id": r[0],
            "deal_name": r[1],
            "amount": r[2],
            "id_empresa": ie,
            "billing_id": billing_id,
            "billing_name": billing_name or "",
            "customer_cuit": cuit_display,
        })
    return result


def _get_group3_candidates(
    conn: sqlite3.Connection,
    year: int | None = None,
    month: int | None = None,
) -> list[dict]:
    """
    Group 3: Deals where facturacion.customer_cuit matches an accountant company
    (Cuenta Contador, etc.) that is NOT associated with the deal (type 5 or 8).
    Considers ALL companies per CUIT (not just one).
    Skips when deal already has ANY company with that customer_cuit as PRIMARY (redundant).
    Returns list of {deal_id, deal_name, accountant_id, accountant_name, amount, customer_cuit}.
    When year/month provided, filter to deals closed in that month.
    """
    accountants = conn.execute("""
        SELECT hubspot_id, name, cuit FROM companies
        WHERE type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
        AND cuit IS NOT NULL AND TRIM(cuit) != '' AND hubspot_id != ''
    """).fetchall()
    cuit_to_accs: dict[str, list[tuple[str, str]]] = {}
    for r in accountants:
        c = _normalize_cuit(r[2])
        if c and len(c) == 11:
            cuit_to_accs.setdefault(c, []).append((r[0], r[1]))
    date_sql, date_params = _date_filter_sql(year, month)
    rows = conn.execute(
        f"""
        SELECT f.customer_cuit, f.id_empresa, f.amount, d.hubspot_id, d.deal_name
        FROM facturacion f
        JOIN deals d ON f.id_empresa = d.id_empresa
        WHERE d.deal_stage IN ('closedwon', '34692158')
        AND d.hubspot_id != '' AND f.customer_cuit != ''
        {date_sql}
        """,
        date_params,
    ).fetchall()
    candidates: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for r in rows:
        c = _normalize_cuit(r[0])
        if not c or len(c) != 11:
            continue
        # Skip if deal already has ANY company with this CUIT as PRIMARY (redundant)
        has_primary_same_cuit = conn.execute(
            """
            SELECT 1 FROM deal_associations da
            JOIN companies c ON da.company_hubspot_id = c.hubspot_id
            WHERE da.deal_hubspot_id = ? AND da.association_type_id = 5
            AND (REPLACE(REPLACE(c.cuit,'-',''),' ','') = ? OR c.cuit = ?)
            """,
            (r[3], c, r[0]),
        ).fetchone()
        if has_primary_same_cuit:
            continue
        for acc_id, acc_name in cuit_to_accs.get(c, []):
            if (r[3], acc_id) in seen:
                continue
            assoc = conn.execute(
                "SELECT 1 FROM deal_associations WHERE deal_hubspot_id=? AND company_hubspot_id=? AND association_type_id IN (5, 8)",
                (r[3], acc_id),
            ).fetchone()
            if assoc is None:
                seen.add((r[3], acc_id))
                candidates.append({
                    "deal_id": r[3],
                    "deal_name": r[4],
                    "billing_id": acc_id,
                    "billing_name": acc_name,
                    "amount": r[2],
                    "id_empresa": r[1],
                    "customer_cuit": r[0],
                })
    candidates.sort(key=lambda x: float(x.get("amount") or 0), reverse=True)
    return candidates


def _get_redundant_type8(
    conn: sqlite3.Connection,
    year: int | None = None,
    month: int | None = None,
) -> list[dict]:
    """
    Type 8 associations that are redundant: the SAME company record has both PRIMARY (5) and
    type 8 (Estudio Contable). A company cannot be both the customer and their own accountant.

    IMPORTANT: We only remove when it's the SAME company (same hubspot_id). We do NOT remove
    type 8 from a different company record, even if it shares the same CUIT as the Primary.
    A deal can have multiple accountants (multiple type 8 associations); if the association
    exists, the company is an actual accountant (not Primary). Different company records
    with same CUIT may be valid (e.g. Cuenta Pyme vs Cuenta Contador views).

    When year/month provided, filter to deals closed in that month.
    """
    date_sql, date_params = _date_filter_sql(year, month)
    join_deals = " JOIN deals d ON dp.deal_hubspot_id = d.hubspot_id " if date_params else ""
    rows = conn.execute(
        f"""
        WITH deal_primary AS (
            SELECT da.deal_hubspot_id, da.company_hubspot_id
            FROM deal_associations da
            WHERE da.association_type_id = 5
        ),
        deal_type8 AS (
            SELECT da.deal_hubspot_id, da.company_hubspot_id
            FROM deal_associations da
            WHERE da.association_type_id = 8
        )
        SELECT dp.deal_hubspot_id, dp.company_hubspot_id
        FROM deal_primary dp
        JOIN deal_type8 dt ON dp.deal_hubspot_id = dt.deal_hubspot_id
            AND dp.company_hubspot_id = dt.company_hubspot_id
        {join_deals}
        WHERE 1=1 {date_sql}
        """,
        date_params,
    ).fetchall()
    result = []
    for r in rows:
        deal_name = conn.execute("SELECT deal_name FROM deals WHERE hubspot_id = ?", (r[0],)).fetchone()
        company = conn.execute("SELECT name, cuit FROM companies WHERE hubspot_id = ?", (r[1],)).fetchone()
        result.append({
            "deal_id": r[0],
            "deal_name": (deal_name[0] if deal_name else "")[:60],
            "company_id": r[1],
            "company_name": (company[0] if company and company[0] else r[1])[:60],
            "cuit": company[1] if company and company[1] else "",
        })
    return result


def _get_group4_candidates(
    conn: sqlite3.Connection,
    year: int | None = None,
    month: int | None = None,
) -> list[dict]:
    """
    Group 4: Non-primary companies that are accountants (type Cuenta Contador, etc.) and
    associated with a deal, but missing type 8 (Estudio Contable). Add type 8 to them.

    Example: RPA Consulting (Cuenta Contador) associated with deal 66535 - PICNIC
    with only type 341 — should have type 8.

    When year/month provided, filter to deals closed in that month.
    """
    date_sql, date_params = _date_filter_sql(year, month)
    rows = conn.execute(
        f"""
        SELECT DISTINCT da.deal_hubspot_id, da.company_hubspot_id, c.name,
               d.deal_name, CAST(d.amount AS INTEGER)
        FROM deal_associations da
        JOIN companies c ON da.company_hubspot_id = c.hubspot_id
        JOIN deals d ON da.deal_hubspot_id = d.hubspot_id
        WHERE c.type IN ('Cuenta Contador', 'Cuenta Contador y Reseller', 'Contador Robado')
        AND d.deal_stage IN ('closedwon', '34692158')
        {date_sql}
        AND NOT EXISTS (
            SELECT 1 FROM deal_associations da2
            WHERE da2.deal_hubspot_id = da.deal_hubspot_id
              AND da2.company_hubspot_id = da.company_hubspot_id
              AND da2.association_type_id = 5
        )
        AND NOT EXISTS (
            SELECT 1 FROM deal_associations da2
            WHERE da2.deal_hubspot_id = da.deal_hubspot_id
              AND da2.company_hubspot_id = da.company_hubspot_id
              AND da2.association_type_id = 8
        )
        ORDER BY CAST(d.amount AS INTEGER) DESC
    """,
        date_params,
    ).fetchall()
    return [
        {
            "deal_id": r[0],
            "deal_name": (r[3] or "")[:60],
            "billing_id": r[1],
            "billing_name": (r[2] or "")[:60],
            "amount": r[4],
            "customer_cuit": "",
        }
        for r in rows
    ]


def get_group_batch(
    conn: sqlite3.Connection,
    group: int,
    limit: int,
    offset: int,
    *,
    colppy_db_path: Path | None = None,
    year: int | None = None,
    month: int | None = None,
    client=None,
) -> list[dict]:
    """Get next batch of deals to fix for given group."""
    if group in (3, 4):
        candidates = (
            _get_group3_candidates(conn, year=year, month=month)
            if group == 3
            else _get_group4_candidates(conn, year=year, month=month)
        )
        return candidates[offset : offset + limit]
    if group == 1 and colppy_db_path and colppy_db_path.exists():
        all_rows = _get_group1_colppy_db(conn, colppy_db_path, year, month, client)
        return all_rows[offset : offset + limit]
    if group == 5 and colppy_db_path and colppy_db_path.exists():
        all_rows = _get_group5_mismatch_candidates(conn, colppy_db_path, year, month)
        return all_rows[offset : offset + limit]
    sql = SQL_GROUP1 if group == 1 else SQL_GROUP2
    date_sql, date_params = _date_filter_sql(year, month)
    if date_sql and date_params:
        sql = sql.replace("GROUP BY", date_sql + " GROUP BY")
    sql += f" LIMIT {limit} OFFSET {offset}"
    rows = conn.execute(sql, date_params).fetchall() if date_params else conn.execute(sql).fetchall()
    return [
        {
            "deal_id": r[0],
            "deal_name": r[1],
            "amount": r[2],
            "id_empresa": r[3],
            "billing_id": r[4],
            "billing_name": r[5],
            "customer_cuit": r[6] if len(r) > 6 else "",
        }
        for r in rows
    ]


def get_group_count(
    conn: sqlite3.Connection,
    group: int,
    *,
    colppy_db_path: Path | None = None,
    year: int | None = None,
    month: int | None = None,
) -> int:
    """Get total count for group."""
    if group == 3:
        return len(_get_group3_candidates(conn, year=year, month=month))
    if group == 4:
        return len(_get_group4_candidates(conn, year=year, month=month))
    if group == 1 and colppy_db_path and colppy_db_path.exists():
        return len(_get_group1_colppy_db(conn, colppy_db_path, year, month, client=None))
    if group == 5 and colppy_db_path and colppy_db_path.exists():
        return len(_get_group5_mismatch_candidates(conn, colppy_db_path, year, month))
    sql = SQL_GROUP1 if group == 1 else SQL_GROUP2
    date_sql, date_params = _date_filter_sql(year, month)
    if date_sql and date_params:
        sql = sql.replace("GROUP BY", date_sql + " GROUP BY")
    sql = "SELECT COUNT(*) FROM (" + sql.replace("\n", " ") + ")"
    row = conn.execute(sql, date_params).fetchone() if date_params else conn.execute(sql).fetchone()
    return row[0]


def insert_association_local(conn: sqlite3.Connection, deal_id: str, company_id: str, type_id: int = 5):
    """Insert association locally after successful API call."""
    cat = "USER_DEFINED" if type_id in USER_DEFINED_TYPES else "HUBSPOT_DEFINED"
    conn.execute(
        "INSERT OR REPLACE INTO deal_associations (deal_hubspot_id, company_hubspot_id, association_type_id, association_category) VALUES (?, ?, ?, ?)",
        (deal_id, company_id, type_id, cat),
    )
    conn.commit()


def delete_association_local(
    conn: sqlite3.Connection, deal_id: str, company_id: str, type_id: int = 5
) -> None:
    """Remove association from local DB to keep in sync with HubSpot."""
    conn.execute(
        "DELETE FROM deal_associations WHERE deal_hubspot_id = ? AND company_hubspot_id = ? AND association_type_id = ?",
        (deal_id, company_id, type_id),
    )
    conn.commit()


# Association type 8 = Estudio Contable, 11 = Compañía con Múltiples Negocios (USER_DEFINED)
USER_DEFINED_TYPES = {2, 8, 11, 39}


def fix_association_label(
    client,
    deal_id: str,
    company_id: str,
    remove_type_ids: list[int],
    add_type_ids: list[int],
    dry_run: bool = False,
    quiet: bool = False,
) -> tuple[bool, str]:
    """
    Change deal–company association labels via HubSpot API.

    Archives specified association types and adds new ones. Uses v4 batch/labels/archive
    and batch/create per HubSpot docs (developers.hubspot.com/docs/api/crm/associations).

    Args:
        client: HubSpot API client
        deal_id: Deal HubSpot ID
        company_id: Company HubSpot ID
        remove_type_ids: Type IDs to archive (e.g. [11] for "Compañía con Múltiples Negocios")
        add_type_ids: Type IDs to add (e.g. [8] for "Estudio Contable")
        dry_run: If True, only print planned actions
        quiet: If True, suppress per-call logging (for batch use)

    Returns:
        (success, message)
    """
    deal_id = str(deal_id)
    company_id = str(company_id)

    if dry_run:
        if not quiet:
            print(f"  [DRY-RUN] Would archive types {remove_type_ids} from deal {deal_id} → company {company_id}")
            print(f"  [DRY-RUN] Would add types {add_type_ids} to deal {deal_id} → company {company_id}")
        return True, "dry_run"

    # Step 1: Archive remove_type_ids from deal→company
    for tid in remove_type_ids:
        cat = "USER_DEFINED" if tid in USER_DEFINED_TYPES else "HUBSPOT_DEFINED"
        try:
            client.post(
                "crm/v4/associations/deals/companies/batch/labels/archive",
                json_data={
                    "inputs": [{
                        "from": {"id": deal_id},
                        "to": {"id": company_id},
                        "types": [{"associationCategory": cat, "associationTypeId": tid}],
                    }],
                },
            )
            if not quiet:
                print(f"  Archived type {tid} ({cat}) from deal {deal_id} → company {company_id}")
        except Exception as e:
            return False, f"Archive type {tid}: {e}"

    # Step 2: Add add_type_ids via batch create (adds labels to existing association)
    if add_type_ids:
        types_payload = []
        for tid in add_type_ids:
            cat = "USER_DEFINED" if tid in USER_DEFINED_TYPES else "HUBSPOT_DEFINED"
            types_payload.append({"associationCategory": cat, "associationTypeId": tid})
        try:
            client.post(
                "crm/v4/associations/deals/companies/batch/create",
                json_data={
                    "inputs": [{
                        "from": {"id": deal_id},
                        "to": {"id": company_id},
                        "types": types_payload,
                    }],
                },
            )
            if not quiet:
                print(f"  Added types {add_type_ids} to deal {deal_id} → company {company_id}")
        except Exception as e:
            return False, f"Batch create types {add_type_ids}: {e}"

    return True, "ok"


HUBSPOT_PORTAL = "19877595"


def _hubspot_deal_url(deal_id: str) -> str:
    """Return HubSpot deal record URL for clickable links."""
    return f"https://app.hubspot.com/contacts/{HUBSPOT_PORTAL}/deal/{deal_id}"


def _hubspot_company_url(company_id: str) -> str:
    """Return HubSpot company record URL for clickable links."""
    return f"https://app.hubspot.com/contacts/{HUBSPOT_PORTAL}/company/{company_id}"


def _print_batch_preview(batch: list[dict], group: int, offset: int) -> None:
    """Print batch as table with direct HubSpot links for deal and company."""
    if not batch:
        return
    n = len(batch)
    print(f"\nNext {n} Group {group} Deals (offset {offset})")
    print("-" * 100)
    print(f"{'#':<4} {'Deal ID':<14} {'Deal Name':<45} {'Amount':<12} {'id_empresa':<10} {'Billing Company':<40} {'Billing CUIT'}")
    print("-" * 100)
    for i, r in enumerate(batch, start=offset + 1):
        deal_id = str(r.get("deal_id", ""))
        billing_id = str(r.get("billing_id", ""))
        deal_url = _hubspot_deal_url(deal_id)
        company_url = _hubspot_company_url(billing_id) if billing_id else ""
        amount = _format_amount(r.get("amount", ""))
        cuit = r.get("customer_cuit", "")
        cuit_display = _format_cuit_display(_normalize_cuit(cuit) or cuit) if cuit else ""
        print(f"{i:<4} {deal_id:<14} {(r.get('deal_name') or '')[:40]:<45} {amount:<12} {r.get('id_empresa',''):<10} {(r.get('billing_name') or '')[:35]:<40} {cuit_display}")
        print(f"      Deal: {deal_url}")
        if company_url:
            print(f"      Company: {company_url}")
    print("-" * 100)


def _log_outcomes_to_db(conn: sqlite3.Connection, group: int, outcomes: list[dict]) -> int:
    """
    Append all deal outcomes to edit_logs table in DB.

    Args:
        conn: SQLite connection
        group: Group number (1, 2, 3, or 4)
        outcomes: List of {deal_id, deal_name, billing_id, billing_name, customer_cuit, outcome, detail}

    Returns:
        Number of rows inserted
    """
    from tools.scripts.hubspot.edit_log_db import log_edits_batch

    action = f"group_{group}"
    return log_edits_batch(conn, "fix_deal_associations", action, outcomes)


def _show_log_result(conn: sqlite3.Connection, limit: int = 50) -> None:
    """Print the last N entries from edit_logs with clickable HubSpot URLs."""
    try:
        rows = conn.execute(
            """
            SELECT deal_id, deal_name, deal_url, company_id, company_url, outcome
            FROM edit_logs
            WHERE script = 'fix_deal_associations'
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    except sqlite3.OperationalError:
        return
    if not rows:
        return
    print("\n" + "=" * 60)
    print("LOG RESULT (last entries) — click links below")
    print("=" * 60)
    for r in rows:
        deal_id, deal_name, deal_url, company_id, company_url, outcome = r
        deal_url = deal_url or _hubspot_deal_url(deal_id or "")
        company_url = company_url or _hubspot_company_url(company_id or "")
        print(f"  {(deal_name or '')[:40]} | {outcome}")
        print(f"    Deal: {deal_url}")
        print(f"    Company: {company_url}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Fix deal–company associations (Groups 1 & 2)")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite database path")
    parser.add_argument("--group", type=int, choices=[1, 2, 3, 4, 5], help="Group to fix: 1=missing, 2=not PRIMARY, 3=accountant type 8, 4=accountant missing type 8, 5=MISMATCH (Colppy CUIT)")
    parser.add_argument("--batch", type=int, default=5, help="Batch size (default 5)")
    parser.add_argument("--offset", type=int, default=0, help="Offset for pagination")
    parser.add_argument("--status", action="store_true", help="Show group counts only")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fixed, no API calls")
    parser.add_argument("--no-log", action="store_true", help="Skip logging to edit_logs (default: always log)")
    parser.add_argument("--fix-label", nargs=2, metavar=("DEAL_ID", "COMPANY_ID"), help="Fix association labels: deal_id company_id")
    parser.add_argument("--remove", type=int, nargs="+", default=[], help="Type IDs to archive (e.g. 11)")
    parser.add_argument("--add", type=int, nargs="+", default=[], help="Type IDs to add (e.g. 8)")
    parser.add_argument("--remove-redundant-type8", action="store_true", help="Remove type 8 only when SAME company has both Primary and type 8 (redundant). Use --dry-run to preview.")
    parser.add_argument("--colppy-db", action="store_true", help="[Group 1 & 5] Use Colppy DB for CUIT mapping. Group 1: NO_PRIMARY. Group 5: MISMATCH (wrong primary CUIT).")
    parser.add_argument("--colppy-db-path", default=DEFAULT_COLPPY_DB, help=f"Path to colppy_export.db (default: {DEFAULT_COLPPY_DB})")
    parser.add_argument("--year", type=int, help="Filter deals by close_date year (e.g. 2026). Applies to Group 1/5 with --colppy-db, Group 2, and --remove-redundant-type8.")
    parser.add_argument("--month", type=int, help="Filter deals by close_date month (e.g. 2). Use with --year.")
    args = parser.parse_args()

    # --fix-label mode: change association label (e.g. type 11 → 8)
    if args.fix_label:
        deal_id, company_id = args.fix_label
        if not args.remove and not args.add:
            print("ERROR: Use --remove and/or --add with --fix-label (e.g. --remove 11 --add 8)", file=sys.stderr)
            return 1
        from tools.hubspot_api.client import get_hubspot_client
        client = get_hubspot_client()
        print(f"Fix association label: deal {deal_id} → company {company_id}")
        print(f"  Remove: {args.remove or 'none'} | Add: {args.add or 'none'}")
        success, msg = fix_association_label(
            client, deal_id, company_id,
            remove_type_ids=args.remove or [],
            add_type_ids=args.add or [],
            dry_run=args.dry_run,
        )
        # Log to edit_logs (default: always)
        db_path = Path(args.db)
        if success and not args.no_log and db_path.exists():
            conn = sqlite3.connect(str(db_path))
            try:
                from tools.scripts.hubspot.edit_log_db import log_edit
                log_edit(
                    conn,
                    script="fix_deal_associations",
                    action="fix_label",
                    outcome="dry_run" if args.dry_run else "fixed",
                    detail=f"remove={args.remove} add={args.add}",
                    deal_id=str(deal_id),
                    company_id=str(company_id),
                )
            finally:
                conn.close()
        if success:
            print(f"  Result: {msg}")
            return 0
        print(f"  Failed: {msg}", file=sys.stderr)
        return 1

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: Database not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))

    if args.status:
        colppy_path = Path(args.colppy_db_path) if args.colppy_db else None
        year_month = (args.year, args.month) if (args.year is not None and args.month is not None) else (None, None)
        c1 = get_group_count(
            conn, 1,
            colppy_db_path=colppy_path,
            year=year_month[0],
            month=year_month[1],
        )
        c2 = get_group_count(conn, 2, year=year_month[0], month=year_month[1])
        c3 = get_group_count(conn, 3, year=year_month[0], month=year_month[1])
        redundant = len(_get_redundant_type8(conn, year=year_month[0], month=year_month[1]))
        print("DEAL ASSOCIATION FIX STATUS")
        print("=" * 50)
        c4 = get_group_count(conn, 4, year=year_month[0], month=year_month[1])
        c5 = get_group_count(
            conn, 5,
            colppy_db_path=colppy_path,
            year=year_month[0],
            month=year_month[1],
        ) if colppy_path and year_month[0] and year_month[1] else 0
        g1_label = "Group 1 (Colppy DB, NO_PRIMARY)" if colppy_path else "Group 1 (billing NOT associated)"
        print(f"  {g1_label}:  {c1:,}")
        print(f"  Group 2 (billing not PRIMARY):    {c2:,}")
        print(f"  Group 3 (accountant not type 8):  {c3:,}")
        print(f"  Group 4 (accountant missing type 8): {c4:,}")
        print(f"  Group 5 (MISMATCH, Colppy CUIT):  {c5:,}" + (" (requires --colppy-db --year --month)" if c5 == 0 and not colppy_path else ""))
        print(f"  Redundant type 8 (same company Primary+8): {redundant:,}")
        print(f"  Total to fix:                     {c1 + c2 + c3 + c4 + c5:,}")
        conn.close()
        return 0

    # --remove-redundant-type8: remove type 8 where same CUIT is already PRIMARY
    if args.remove_redundant_type8:
        year_month = (args.year, args.month) if (args.year is not None and args.month is not None) else (None, None)
        redundant = _get_redundant_type8(conn, year=year_month[0], month=year_month[1])
        print("=" * 90)
        period = f" ({year_month[0]}-{year_month[1]:02d})" if year_month[0] is not None and year_month[1] is not None else ""
        print(f"REDUNDANT TYPE 8 ASSOCIATIONS{period} (same company has both Primary + type 8 — would remove)")
        print("=" * 90)
        print(f"\nTotal: {len(redundant)}")
        print(f"\n{'#':<4} {'Deal ID':<14} {'Deal Name':<45} {'Company ID':<14} {'Company Name':<35} {'CUIT'}")
        print("-" * 90)
        portal = HUBSPOT_PORTAL
        for i, r in enumerate(redundant[:25], 1):
            print(f"{i:<4} {r['deal_id']:<14} {(r['deal_name'] or '')[:42]:<45} {r['company_id']:<14} {(r['company_name'] or '')[:32]:<35} {r.get('cuit','')}")
        if len(redundant) > 25:
            print(f"... and {len(redundant) - 25} more")
        print("\n--- HUBSPOT LINKS (first 5) ---")
        for i, r in enumerate(redundant[:5]):
            print(f"  Deal: https://app.hubspot.com/contacts/{portal}/deal/{r['deal_id']}")
            print(f"  Company (type 8 to remove): https://app.hubspot.com/contacts/{portal}/company/{r['company_id']}")
        if args.dry_run:
            print("\n[DRY-RUN] No changes made. Run without --dry-run to remove these associations.")
            if not args.no_log and redundant:
                from tools.scripts.hubspot.edit_log_db import log_edits_batch
                outcomes = [
                    {"deal_id": r["deal_id"], "deal_name": r["deal_name"], "billing_id": r["company_id"],
                     "billing_name": r["company_name"], "customer_cuit": r.get("cuit", ""),
                     "outcome": "dry_run", "detail": "redundant_type8_remove"}
                    for r in redundant
                ]
                n = log_edits_batch(conn, "fix_deal_associations", "remove_redundant_type8", outcomes)
                print(f"  Logged {n} to edit_logs (dry-run)")
        else:
            from tools.hubspot_api.client import get_hubspot_client
            client = get_hubspot_client()
            ok, fail = 0, 0
            outcomes = []
            for r in redundant:
                success, msg = fix_association_label(
                    client, r["deal_id"], r["company_id"],
                    remove_type_ids=[8], add_type_ids=[],
                    dry_run=False, quiet=True,
                )
                if success:
                    delete_association_local(conn, r["deal_id"], r["company_id"], 8)
                    ok += 1
                    outcomes.append({"deal_id": r["deal_id"], "deal_name": r["deal_name"], "billing_id": r["company_id"], "billing_name": r["company_name"], "customer_cuit": r.get("cuit", ""), "outcome": "fixed", "detail": "redundant_type8_removed"})
                else:
                    print(f"  Failed deal {r['deal_id']} → company {r['company_id']}: {msg}", file=sys.stderr)
                    fail += 1
                    outcomes.append({"deal_id": r["deal_id"], "deal_name": r["deal_name"], "billing_id": r["company_id"], "billing_name": r["company_name"], "customer_cuit": r.get("cuit", ""), "outcome": "failed", "detail": str(msg)[:500]})
            if not args.no_log and outcomes:
                from tools.scripts.hubspot.edit_log_db import log_edits_batch
                n = log_edits_batch(conn, "fix_deal_associations", "remove_redundant_type8", outcomes)
                print(f"  Logged {n} to edit_logs")
            print(f"\nRemoved type 8 from {ok} associations. Failed: {fail}. Local DB updated.")
        conn.close()
        return 0

    if not args.group:
        print("ERROR: Use --group 1, 2, 3, 4, or 5 (or --status for counts)", file=sys.stderr)
        return 1

    if args.colppy_db and args.group not in (1, 5):
        print("ERROR: --colppy-db is only supported with --group 1 or 5", file=sys.stderr)
        return 1

    if args.group == 5 and not args.colppy_db:
        print("ERROR: Group 5 (MISMATCH) requires --colppy-db", file=sys.stderr)
        return 1

    if args.group == 5 and (args.year is None or args.month is None):
        print("ERROR: Group 5 (MISMATCH) requires --year and --month", file=sys.stderr)
        return 1

    colppy_path = Path(args.colppy_db_path) if args.colppy_db else None
    year_month = (args.year, args.month) if (args.year is not None and args.month is not None) else (None, None)
    total = get_group_count(
        conn, args.group,
        colppy_db_path=colppy_path,
        year=year_month[0],
        month=year_month[1],
    )
    # Group 1 with Colppy DB may need HubSpot API for name fallback; create client early
    from tools.hubspot_api.client import get_hubspot_client
    client = get_hubspot_client() if (args.group == 1 and colppy_path) else None
    batch = get_group_batch(
        conn, args.group, args.batch, args.offset,
        colppy_db_path=colppy_path,
        year=year_month[0],
        month=year_month[1],
        client=client,
    )
    if not client:
        client = get_hubspot_client()

    if not batch:
        print(f"Group {args.group}: No deals to fix (offset {args.offset})")
        conn.close()
        return 0

    print(f"Group {args.group}: fixing {len(batch)} deals (offset {args.offset}, {total - args.offset} remaining)")
    print("-" * 60)

    _print_batch_preview(batch, args.group, args.offset)

    # Group 3 & 4: Add accountant as type 8 (Estudio Contable) — different flow from Group 1/2
    if args.group in (3, 4):
        if args.dry_run:
            print(f"\nDRY-RUN: Would add type 8 (Estudio Contable) to these deal–accountant pairs (Group {args.group}):")
            for r in batch:
                print(f"  {r['deal_id']} {r['deal_name'][:45]} → {r['billing_id']} {r['billing_name'][:35]}")
            conn.close()
            return 0
        inputs = [
            {
                "from": {"id": r["deal_id"]},
                "to": {"id": r["billing_id"]},
                "types": [{"associationCategory": "USER_DEFINED", "associationTypeId": 8}],
            }
            for r in batch
        ]
        failed = []
        try:
            client.post(
                "crm/v4/associations/deals/companies/batch/create",
                json_data={"inputs": inputs},
            )
            for r in batch:
                insert_association_local(conn, r["deal_id"], r["billing_id"], 8)
            print(f"Fixed {len(batch)} deal–accountant associations (type 8). Local DB updated.")
        except Exception as e:
            print(f"  Failed batch create: {e}", file=sys.stderr)
            failed = [(r["deal_id"], str(e)) for r in batch]
        if not args.no_log and batch:
            failed_by_deal = {d: err for d, err in failed}
            outcomes = [
                {"deal_id": r["deal_id"], "deal_name": r["deal_name"], "billing_id": r["billing_id"],
                 "billing_name": r["billing_name"], "customer_cuit": r.get("customer_cuit", ""),
                 "outcome": "failed" if r["deal_id"] in failed_by_deal else "fixed",
                 "detail": failed_by_deal.get(r["deal_id"], "type_8_added")[:500]}
                for r in batch
            ]
            n = _log_outcomes_to_db(conn, 3, outcomes)
            print(f"  Logged {n} outcomes to edit_logs")
            _show_log_result(conn)
        conn.close()
        return 0

    # Verify CUIT on each company; fix (PATCH or find alternative) when missing
    cuit_by_deal = {r["deal_id"]: (r.get("customer_cuit") or "") for r in batch}
    to_fix, verify_outcomes = _verify_and_fix_companies(client, batch, cuit_by_deal)
    if not to_fix:
        print("  No deals to fix (all skipped or unfixable).")
        if not args.no_log and verify_outcomes:
            n = _log_outcomes_to_db(conn, args.group, verify_outcomes)
            print(f"  Logged {n} outcomes to edit_logs")
            _show_log_result(conn)
        conn.close()
        return 0

    if args.dry_run:
        print("\nDRY-RUN: Would add PRIMARY to these deals:")
        for r in to_fix:
            deal_id = str(r.get("deal_id", ""))
            billing_id = str(r.get("billing_id", ""))
            deal_url = _hubspot_deal_url(deal_id)
            company_url = _hubspot_company_url(billing_id) if billing_id else ""
            print(f"  {r['deal_id']} {r['deal_name'][:45]} → {r['billing_id']} {r['billing_name'][:35]}")
            print(f"    Deal: {deal_url}")
            if company_url:
                print(f"    Company: {company_url}")
        if not args.no_log and verify_outcomes:
            dry_outcomes = [
                {**o, "outcome": "dry_run" if o.get("outcome") == "to_fix" else o.get("outcome")}
                for o in verify_outcomes
            ]
            n = _log_outcomes_to_db(conn, args.group, dry_outcomes)
            print(f"  Logged {n} outcomes to edit_logs (dry-run)")
            _show_log_result(conn)
        conn.close()
        return 0

    # Remove PRIMARY from wrong companies first (HubSpot allows only one primary per deal)
    _remove_primary_from_wrong_companies(client, to_fix, conn)

    # Add PRIMARY to billing company.
    # - If already associated: use PUT to add PRIMARY label (preserves existing labels)
    # - If not associated: use batch create
    failed = []
    deal_ids = list({r["deal_id"] for r in to_fix})
    assoc_resp = client.post(
        "crm/v4/associations/deals/companies/batch/read",
        json_data={"inputs": [{"id": did} for did in deal_ids]},
    )
    associated_pairs = set()  # (deal_id, company_id) that exist
    for res in assoc_resp.get("results", []):
        deal_id = res.get("from", {}).get("id")
        for to_obj in res.get("to", []) or []:
            associated_pairs.add((str(deal_id), str(to_obj.get("toObjectId", ""))))

    to_put = [r for r in to_fix if (str(r["deal_id"]), str(r["billing_id"])) in associated_pairs]
    to_create = [r for r in to_fix if (str(r["deal_id"]), str(r["billing_id"])) not in associated_pairs]

    for r in to_put:
        deal_id, billing_id = r["deal_id"], r["billing_id"]
        try:
            for res in assoc_resp.get("results", []):
                if str(res.get("from", {}).get("id")) != str(deal_id):
                    continue
                existing_types = []
                for to_obj in res.get("to", []) or []:
                    if str(to_obj.get("toObjectId")) == str(billing_id):
                        existing_types = [
                            {"associationCategory": t.get("category", "HUBSPOT_DEFINED"), "associationTypeId": t.get("typeId")}
                            for t in to_obj.get("associationTypes", [])
                        ]
                        break
                labels = [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 5}]
                seen = {5}
                for t in existing_types:
                    tid = t.get("associationTypeId")
                    if tid and tid not in seen:
                        labels.append(t)
                        seen.add(tid)
                client.put(
                    f"crm/v4/objects/deals/{deal_id}/associations/companies/{billing_id}",
                    json_data=labels,
                )
                insert_association_local(conn, deal_id, billing_id, 5)
                break
        except Exception as e:
            failed.append((deal_id, str(e)))
            print(f"  Failed {deal_id} (PUT): {e}", file=sys.stderr)

    if to_create:
        try:
            inputs = [
                {
                    "from": {"id": r["deal_id"]},
                    "to": {"id": r["billing_id"]},
                    "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 5}],
                }
                for r in to_create
            ]
            client.post(
                "crm/v4/associations/deals/companies/batch/create",
                json_data={"inputs": inputs},
            )
            for r in to_create:
                insert_association_local(conn, r["deal_id"], r["billing_id"], 5)
        except Exception as e:
            print(f"  Failed batch create: {e}", file=sys.stderr)
            for r in to_create:
                failed.append((r["deal_id"], str(e)))

    fixed_count = len(to_fix) - len(failed)
    failed_ids = {str(f[0]) for f in failed}
    failed_errors = {str(f[0]): f[1] for f in failed}

    # Audit: fix type 8/11 labels when company.type is null or inconsistent with association
    fixed_deal_ids = [str(r["deal_id"]) for r in to_fix if str(r["deal_id"]) not in failed_ids]
    if fixed_deal_ids:
        billing_by_deal = {str(r["deal_id"]): str(r["billing_id"]) for r in to_fix}
        _audit_deal_association_labels(client, fixed_deal_ids, billing_by_deal, conn)

    # Build final outcomes: update to_fix entries to fixed/failed, keep skipped as-is
    to_fix_ids = {str(r["deal_id"]) for r in to_fix}
    final_outcomes = []
    for o in verify_outcomes:
        did = str(o.get("deal_id", ""))
        if o.get("outcome") != "to_fix":
            final_outcomes.append(o)
            continue
        if did in failed_ids:
            final_outcomes.append({**o, "outcome": "failed", "detail": failed_errors.get(did, "unknown")[:500]})
        else:
            final_outcomes.append({**o, "outcome": "fixed"})  # detail kept: cuit_ok|cuit_patched|cuit_alternative

    if not args.no_log and final_outcomes:
        n = _log_outcomes_to_db(conn, args.group, final_outcomes)
        print(f"  Logged {n} outcomes to edit_logs")
        _show_log_result(conn)
    if failed:
        print(f"Fixed {fixed_count} deals. {len(failed)} failed. Local DB updated.")
    else:
        print(f"Fixed {fixed_count} deals. Local DB updated.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
