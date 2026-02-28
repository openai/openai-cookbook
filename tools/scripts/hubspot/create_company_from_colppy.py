#!/usr/bin/env python3
"""
Create HubSpot company from Colppy DB and associate as primary with deal.
============================================
For NO_PRIMARY deals where no company with Colppy CUIT exists in HubSpot.
Creates company with name, CUIT, address, type, industria from Colppy facturacion/empresa,
then associates it with the deal as PRIMARY (type 5).

Sets: type=Cuenta Pyme, industria (inferred from actividad_economica/razon_social).
tipo_icp_contador left empty for Pyme (used for accountant subtypes).

Usage:
  python tools/scripts/hubspot/create_company_from_colppy.py --id-empresa 93946
  python tools/scripts/hubspot/create_company_from_colppy.py --id-empresa 93946 --dry-run
  python tools/scripts/hubspot/create_company_from_colppy.py --id-empresa 93946 --patch-company 52110611591
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")
load_dotenv(REPO_ROOT / "tools" / ".env")

DEFAULT_COLPPY_DB = REPO_ROOT / "tools/data/colppy_export.db"
DEFAULT_HUBSPOT_DB = REPO_ROOT / "tools/data/facturacion_hubspot.db"


# Default company type for SMB deals created from Colppy (closed-won = paying customer)
DEFAULT_COMPANY_TYPE = "Cuenta Pyme"

# ICP: tipo_icp_contador is for accountant subtypes (Operador, Asesor, Híbrido). Leave empty for Pyme.
# industria: Colppy custom property (enum). Must use exact HubSpot enum values.
INDUSTRIA_CONTABILIDAD = "Contabilidad, impuestos, legales"
INDUSTRIA_ENTRETENIMIENTO = "Entretenimiento y recreación"
INDUSTRIA_SERVICIOS_DEPORTIVOS = "Servicios deportivos"

# Map keywords to valid industria enum values (from HubSpot companies property)
INDUSTRIA_KEYWORDS = (
    (("CONTADOR", "CONTABLE", "CONTABILIDAD"), INDUSTRIA_CONTABILIDAD),
    (("DEPORTIV", "DEPORTE", "CLUB"), INDUSTRIA_SERVICIOS_DEPORTIVOS),
    (("ASOC", "ASOCIACION", "CULTURAL", "RECREACION"), INDUSTRIA_ENTRETENIMIENTO),
)


def _infer_industria(actividad_economica: str, razon_social: str) -> str:
    """
    Infer HubSpot industria from Colppy actividad_economica or razon_social.
    Returns only valid HubSpot enum values. Empty if no match.
    """
    text = f"{(actividad_economica or '').upper()} {(razon_social or '').upper()}"
    for keywords, value in INDUSTRIA_KEYWORDS:
        if any(kw in text for kw in keywords):
            return value
    return ""


def load_colppy_company(colppy_db_path: Path, id_empresa: str) -> dict | None:
    """
    Load company data from Colppy DB (facturacion + empresa).
    Returns dict with name, cuit, razon_social, domicilio, localidad, provincia, codigo_postal, pais,
    email, actividad_economica, id_plan.
    """
    if not colppy_db_path.exists():
        return None
    ie = int(id_empresa) if str(id_empresa).isdigit() else id_empresa
    with sqlite3.connect(colppy_db_path) as conn:
        conn.row_factory = sqlite3.Row
        # Prefer facturacion (billing), fallback empresa
        row = conn.execute(
            """
            SELECT f.IdEmpresa AS id_empresa, f.CUIT AS cuit, f.razonSocial,
                   f.domicilio, f.localidad, f.provincia, f.email
            FROM facturacion f
            WHERE f.IdEmpresa = ? AND (COALESCE(f.fechaBaja,'') = '' OR f.fechaBaja = '0000-00-00')
            """,
            (ie,),
        ).fetchone()
        if row:
            emp = conn.execute(
                """SELECT Nombre, domicilio, codigoPostal, localidad, provincia, pais, email,
                          actividad_economica, idPlan FROM empresa WHERE IdEmpresa = ?""",
                (ie,),
            ).fetchone()
            return {
                "id_empresa": str(row["id_empresa"]),
                "cuit": (row["cuit"] or "").strip(),
                "razon_social": (row["razonSocial"] or "").strip(),
                "nombre": (emp["Nombre"] or row["razonSocial"] or "").strip() if emp else (row["razonSocial"] or "").strip(),
                "domicilio": (row["domicilio"] or (emp["domicilio"] if emp else "") or "").strip(),
                "localidad": (row["localidad"] or (emp["localidad"] if emp else "") or "").strip(),
                "provincia": (row["provincia"] or (emp["provincia"] if emp else "") or "").strip(),
                "codigo_postal": (emp["codigoPostal"] or "").strip() if emp else "",
                "pais": (emp["pais"] or "ARGENTINA").strip() if emp else "ARGENTINA",
                "email": (row["email"] or (emp["email"] if emp else "") or "").strip(),
                "actividad_economica": (emp["actividad_economica"] or "").strip() if emp else "",
                "id_plan": emp["idPlan"] if emp else None,
            }
        row = conn.execute(
            """
            SELECT IdEmpresa, CUIT, Nombre AS nombre, domicilio, codigoPostal AS codigo_postal,
                   localidad, provincia, pais, email, actividad_economica, idPlan
            FROM empresa WHERE IdEmpresa = ?
            """,
            (ie,),
        ).fetchone()
        if row:
            return {
                "id_empresa": str(row["IdEmpresa"]),
                "cuit": (row["CUIT"] or "").strip(),
                "razon_social": (row["nombre"] or "").strip(),
                "nombre": (row["nombre"] or "").strip(),
                "domicilio": (row["domicilio"] or "").strip(),
                "localidad": (row["localidad"] or "").strip(),
                "provincia": (row["provincia"] or "").strip(),
                "codigo_postal": (row["codigo_postal"] or "").strip(),
                "pais": (row["pais"] or "ARGENTINA").strip(),
                "email": (row["email"] or "").strip(),
                "actividad_economica": (row["actividad_economica"] or "").strip(),
                "id_plan": row["idPlan"],
            }
    return None


def get_deal_hubspot_id(hubspot_db_path: Path, id_empresa: str) -> str | None:
    """Get deal HubSpot ID for id_empresa."""
    if not hubspot_db_path.exists():
        return None
    row = __import__("sqlite3").connect(str(hubspot_db_path)).execute(
        "SELECT hubspot_id FROM deals WHERE id_empresa = ? AND deal_stage IN ('closedwon','34692158')",
        (id_empresa,),
    ).fetchone()
    return row[0] if row else None


def main() -> int:
    parser = argparse.ArgumentParser(description="Create HubSpot company from Colppy DB and associate with deal")
    parser.add_argument("--id-empresa", required=True, help="Colppy id_empresa (e.g. 93946)")
    parser.add_argument("--colppy-db", type=Path, default=DEFAULT_COLPPY_DB)
    parser.add_argument("--hubspot-db", type=Path, default=DEFAULT_HUBSPOT_DB)
    parser.add_argument("--dry-run", action="store_true", help="Print what would be done, no API calls")
    parser.add_argument(
        "--patch-company",
        metavar="HUBSPOT_COMPANY_ID",
        help="PATCH existing company with type, industria (no create, no associate)",
    )
    args = parser.parse_args()

    data = load_colppy_company(args.colppy_db, args.id_empresa)
    if not data:
        print(f"Error: No Colppy data for id_empresa {args.id_empresa}", file=sys.stderr)
        return 1
    if not args.patch_company and not data.get("cuit"):
        print(f"Error: No CUIT for id_empresa {args.id_empresa}", file=sys.stderr)
        return 1

    # --patch-company: only PATCH type, industria on existing company
    if args.patch_company:
        patch_props = {"type": DEFAULT_COMPANY_TYPE}
        industria = _infer_industria(data.get("actividad_economica", ""), data.get("razon_social", ""))
        if industria:
            patch_props["industria"] = industria
        if args.dry_run:
            print(f"DRY-RUN: Would PATCH company {args.patch_company}:")
            for k, v in patch_props.items():
                print(f"  {k}: {v}")
            return 0
        from tools.hubspot_api.client import get_hubspot_client

        client = get_hubspot_client()
        try:
            client.patch(
                f"crm/v3/objects/companies/{args.patch_company}",
                json_data={"properties": patch_props},
            )
            print(f"Patched company {args.patch_company}: {', '.join(patch_props.keys())}")
        except Exception as e:
            print(f"Error patching: {e}", file=sys.stderr)
            return 1
        print(f"Company: https://app.hubspot.com/contacts/19877595/company/{args.patch_company}")
        return 0

    deal_id = get_deal_hubspot_id(args.hubspot_db, args.id_empresa)
    if not deal_id:
        print(f"Error: No closed-won deal for id_empresa {args.id_empresa}", file=sys.stderr)
        return 1

    # Company name: match deal convention "id_empresa - nombre"
    company_name = f"{data['id_empresa']} - {data['nombre']}" if data.get("nombre") else f"{data['id_empresa']} - {data['razon_social'][:50]}"

    # HubSpot: name required. Standard: name, city, state, zip, address, country. Custom: cuit, type, industria, tipo_icp_contador.
    # Exclude email: HubSpot company object returns 400 for "email" (not a valid company property).
    props = {"name": company_name}
    if data.get("cuit"):
        props["cuit"] = data["cuit"]
    if data.get("localidad"):
        props["city"] = data["localidad"]
    if data.get("provincia"):
        props["state"] = data["provincia"]
    if data.get("codigo_postal"):
        props["zip"] = data["codigo_postal"]
    if data.get("domicilio"):
        props["address"] = data["domicilio"]
    if data.get("pais"):
        props["country"] = data["pais"]
    # ICP, industry, company type
    props["type"] = DEFAULT_COMPANY_TYPE
    industria = _infer_industria(data.get("actividad_economica", ""), data.get("razon_social", ""))
    if industria:
        props["industria"] = industria
    # tipo_icp_contador: for Pyme leave empty (used for accountant subtypes: Operador, Asesor, Híbrido)

    if args.dry_run:
        print("DRY-RUN: Would create company:")
        for k, v in props.items():
            print(f"  {k}: {v}")
        print(f"  Associate as PRIMARY with deal {deal_id}")
        return 0

    from tools.hubspot_api.client import get_hubspot_client

    client = get_hubspot_client()

    # Create company with name first (required), then PATCH additional props
    props_create = {"name": company_name}
    try:
        resp = client.post(
            "crm/v3/objects/companies",
            json_data={"properties": props_create},
        )
        company_id = resp.get("id")
        if not company_id:
            print("Error: No company ID in response", file=sys.stderr)
            return 1
        print(f"Created company {company_id}: {company_name}")
    except Exception as e:
        print(f"Error creating company: {e}", file=sys.stderr)
        return 1

    # PATCH additional properties (skip name)
    extra = {k: v for k, v in props.items() if k != "name" and v}
    if extra:
        try:
            client.patch(
                f"crm/v3/objects/companies/{company_id}",
                json_data={"properties": extra},
            )
            print(f"  Updated: {', '.join(extra.keys())}")
        except Exception as e:
            print(f"  Warning: Could not update some properties: {e}")

    # Associate deal -> company as PRIMARY (type 5)
    try:
        client.post(
            "crm/v4/associations/deals/companies/batch/create",
            json_data={
                "inputs": [
                    {
                        "from": {"id": deal_id},
                        "to": {"id": str(company_id)},
                        "types": [{"associationCategory": "HUBSPOT_DEFINED", "associationTypeId": 5}],
                    }
                ]
            },
        )
        print(f"Associated deal {deal_id} with company {company_id} as PRIMARY")
    except Exception as e:
        print(f"Error associating: {e}", file=sys.stderr)
        return 1

    # Update local deal_associations
    db_path = args.hubspot_db
    if db_path.exists():
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT OR REPLACE INTO deal_associations (deal_hubspot_id, company_hubspot_id, association_type_id, association_category) VALUES (?, ?, 5, 'HUBSPOT_DEFINED')",
            (deal_id, str(company_id)),
        )
        cuit_display = data["cuit"] if "-" in data["cuit"] else f"{data['cuit'][:2]}-{data['cuit'][2:10]}-{data['cuit'][10]}"
        conn.execute(
            "INSERT OR REPLACE INTO companies (hubspot_id, name, cuit, cuit_display) VALUES (?, ?, ?, ?)",
            (str(company_id), company_name, data["cuit"], cuit_display),
        )
        conn.commit()
        conn.close()
        print("Updated local facturacion_hubspot.db")

    print(f"Company: https://app.hubspot.com/contacts/19877595/company/{company_id}")
    print(f"Deal: https://app.hubspot.com/contacts/19877595/deal/{deal_id}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
