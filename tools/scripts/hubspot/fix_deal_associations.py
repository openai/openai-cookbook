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

Usage:
    python tools/scripts/hubspot/fix_deal_associations.py --group 1 --batch 5
    python tools/scripts/hubspot/fix_deal_associations.py --group 2 --batch 5
    python tools/scripts/hubspot/fix_deal_associations.py --status   # show counts only
    python tools/scripts/hubspot/fix_deal_associations.py --dry-run  # show what would be fixed
    python tools/scripts/hubspot/fix_deal_associations.py --group 2 --batch 10 --log-fixed  # log all outcomes

Fix association label (change type 11 → 8 for accountant company):
    python tools/scripts/hubspot/fix_deal_associations.py --fix-label 9424153860 9019047084 --remove 11 --add 8

Rule for accountant (type 8): Company type ∈ Cuenta Contador | Cuenta Contador y Reseller | Contador Robado,
or Empresa Administrada + industria contabilidad, or (fallback) name suggests accountant when type/industria empty.
When inferred from name, the script also enriches the company: type=Cuenta Contador, industria=Contabilidad, impuestos, legales.
After each fix batch, an audit corrects type 8/11 labels when company.type is null or inconsistent.
See tools/docs/HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md section 0.1.
"""
import argparse
import csv
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB = "tools/outputs/facturacion_hubspot.db"
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_LOG = str(_PROJECT_ROOT / "tools" / "outputs" / "fix_deal_associations_log.csv")

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


def get_group_batch(conn: sqlite3.Connection, group: int, limit: int, offset: int) -> list[dict]:
    """Get next batch of deals to fix for given group."""
    sql = SQL_GROUP1 if group == 1 else SQL_GROUP2
    sql += f" LIMIT {limit} OFFSET {offset}"
    rows = conn.execute(sql).fetchall()
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


def get_group_count(conn: sqlite3.Connection, group: int) -> int:
    """Get total count for group."""
    sql = SQL_GROUP1 if group == 1 else SQL_GROUP2
    sql = "SELECT COUNT(*) FROM (" + sql.replace("\n", " ") + ")"
    return conn.execute(sql).fetchone()[0]


def insert_association_local(conn: sqlite3.Connection, deal_id: str, company_id: str, type_id: int = 5):
    """Insert association locally after successful API call."""
    conn.execute(
        "INSERT OR REPLACE INTO deal_associations (deal_hubspot_id, company_hubspot_id, association_type_id, association_category) VALUES (?, ?, ?, ?)",
        (deal_id, company_id, type_id, "HUBSPOT_DEFINED"),
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
LOG_HEADER = [
    "timestamp", "group", "deal_id", "deal_name", "deal_url", "billing_id", "billing_name",
    "company_url", "customer_cuit", "outcome", "detail",
]


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


def _log_outcomes(
    log_path: Path,
    group: int,
    outcomes: list[dict],
) -> None:
    """
    Append all deal outcomes to a CSV log file.

    Args:
        log_path: Path to CSV log file
        group: Group number (1 or 2)
        outcomes: List of {deal_id, deal_name, billing_id, billing_name, customer_cuit, outcome, detail}
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_exists = log_path.exists()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(LOG_HEADER)
        for r in outcomes:
            deal_id = str(r.get("deal_id", ""))
            billing_id = str(r.get("billing_id", ""))
            writer.writerow([
                ts,
                group,
                deal_id,
                (r.get("deal_name") or "")[:200],
                _hubspot_deal_url(deal_id) if deal_id else "",
                billing_id,
                (r.get("billing_name") or "")[:200],
                _hubspot_company_url(billing_id) if billing_id else "",
                (r.get("customer_cuit") or ""),
                r.get("outcome", ""),
                (r.get("detail") or "")[:500],
            ])


def _show_log_result(log_path: Path, limit: int = 50) -> None:
    """Print the last N lines of the log file with clickable HubSpot URLs."""
    if not log_path.exists():
        return
    with open(log_path, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        return
    print("\n" + "=" * 60)
    print("LOG RESULT (last entries) — click links below")
    print("=" * 60)
    to_show = rows[-limit:] if len(rows) > limit else rows
    for r in to_show:
        deal_id = str(r.get("deal_id", ""))
        billing_id = str(r.get("billing_id", ""))
        # Guard: billing_id may be misaligned in old-format files (no deal_url column)
        if billing_id.startswith("http"):
            billing_id = ""
        deal_url = r.get("deal_url") or (_hubspot_deal_url(deal_id) if deal_id else "")
        company_url = r.get("company_url") or (_hubspot_company_url(billing_id) if billing_id and not billing_id.startswith("http") else "")
        outcome = r.get("outcome", "")
        deal_name = (r.get("deal_name") or "")[:40]
        print(f"  {deal_name} | {outcome}")
        print(f"    Deal: {deal_url}")
        print(f"    Company: {company_url}")
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Fix deal–company associations (Groups 1 & 2)")
    parser.add_argument("--db", default=DEFAULT_DB, help="SQLite database path")
    parser.add_argument("--group", type=int, choices=[1, 2], help="Group to fix: 1=missing, 2=not PRIMARY")
    parser.add_argument("--batch", type=int, default=5, help="Batch size (default 5)")
    parser.add_argument("--offset", type=int, default=0, help="Offset for pagination")
    parser.add_argument("--status", action="store_true", help="Show group counts only")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be fixed, no API calls")
    parser.add_argument("--log-fixed", action="store_true", help="Log all outcomes (fixed, failed, skipped) to CSV and show result")
    parser.add_argument("--log-path", default=DEFAULT_LOG, help=f"Log file path (default: {DEFAULT_LOG})")
    parser.add_argument("--fix-label", nargs=2, metavar=("DEAL_ID", "COMPANY_ID"), help="Fix association labels: deal_id company_id")
    parser.add_argument("--remove", type=int, nargs="+", default=[], help="Type IDs to archive (e.g. 11)")
    parser.add_argument("--add", type=int, nargs="+", default=[], help="Type IDs to add (e.g. 8)")
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
        c1 = get_group_count(conn, 1)
        c2 = get_group_count(conn, 2)
        print("DEAL ASSOCIATION FIX STATUS")
        print("=" * 50)
        print(f"  Group 1 (billing NOT associated):  {c1:,}")
        print(f"  Group 2 (billing not PRIMARY):    {c2:,}")
        print(f"  Total to fix:                     {c1 + c2:,}")
        conn.close()
        return 0

    if not args.group:
        print("ERROR: Use --group 1 or --group 2 (or --status for counts)", file=sys.stderr)
        return 1

    from tools.hubspot_api.client import get_hubspot_client

    client = get_hubspot_client()
    total = get_group_count(conn, args.group)
    batch = get_group_batch(conn, args.group, args.batch, args.offset)

    if not batch:
        print(f"Group {args.group}: No deals to fix (offset {args.offset})")
        conn.close()
        return 0

    print(f"Group {args.group}: fixing {len(batch)} deals (offset {args.offset}, {total - args.offset} remaining)")
    print("-" * 60)

    _print_batch_preview(batch, args.group, args.offset)

    # Verify CUIT on each company; fix (PATCH or find alternative) when missing
    cuit_by_deal = {r["deal_id"]: (r.get("customer_cuit") or "") for r in batch}
    to_fix, verify_outcomes = _verify_and_fix_companies(client, batch, cuit_by_deal)
    if not to_fix:
        print("  No deals to fix (all skipped or unfixable).")
        if args.log_fixed and verify_outcomes:
            log_path = Path(args.log_path)
            _log_outcomes(log_path, args.group, verify_outcomes)
            _show_log_result(log_path)
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
        if args.log_fixed and verify_outcomes:
            dry_outcomes = [
                {**o, "outcome": "dry_run" if o.get("outcome") == "to_fix" else o.get("outcome")}
                for o in verify_outcomes
            ]
            log_path = Path(args.log_path)
            _log_outcomes(log_path, args.group, dry_outcomes)
            _show_log_result(log_path)
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

    if args.log_fixed and final_outcomes:
        log_path = Path(args.log_path)
        _log_outcomes(log_path, args.group, final_outcomes)
        print(f"  Logged {len(final_outcomes)} outcomes to {log_path}")
        _show_log_result(log_path)
    if failed:
        print(f"Fixed {fixed_count} deals. {len(failed)} failed. Local DB updated.")
    else:
        print(f"Fixed {fixed_count} deals. Local DB updated.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
