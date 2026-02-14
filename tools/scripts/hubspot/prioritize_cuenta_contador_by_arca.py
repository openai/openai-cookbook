#!/usr/bin/env python3
"""
Prioritize Cuenta Contador Type updates for companies with accountant billing plans.

Uses the SAME criteria as hubspot_industry_enrichment.js for accountant detection:
- Activity text pattern match: contabilidad, impuestos, legales, accounting,
  legal_services, servicios contables, servicio contable, tax, fiscal

Only companies where ARCA (RNS actividad_descripcion) indicates accountant are
prioritized - avoiding SMBs that were sold accountant plans for pricing reasons.

Usage:
    python tools/scripts/hubspot/prioritize_cuenta_contador_by_arca.py
    python tools/scripts/hubspot/prioritize_cuenta_contador_by_arca.py --output tools/outputs/cuenta_contador_prioritized.csv
"""
import argparse
import csv
import re
import sys
from pathlib import Path

# Add tools/scripts for rns_dataset_lookup import
_scripts_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_scripts_dir))

# Accountant patterns - SAME as hubspot_industry_enrichment.js (lines 1436-1440)
# exactAccountantIndustry = 'Contabilidad, impuestos, legales'
# accountantIndustryPatterns = ['contabilidad', 'impuestos', 'legales', 'accounting',
#   'legal_services', 'legal services', 'servicios contables', 'servicio contable', 'tax', 'fiscal']
ACCOUNTANT_ACTIVITY_PATTERNS = [
    'contabilidad',
    'impuestos',
    'legales',
    'accounting',
    'legal_services',
    'legal services',
    'servicios contables',
    'servicio contable',
    'tax',
    'fiscal',
]

# Accountant billing plans (from facturacion Plan description)
ACCOUNTANT_PLANS = {
    'Contador Independiente',
    'Contador Independiente + Sueldos',
    'Contador Inicio + Sueldos',
    'Consultoras y Estudios',
    'Consultoras y Estudios + Sueldos + Portal',
}


def normalize_cuit(s: str) -> str | None:
    """Normalize CUIT to 11 digits."""
    if not s or str(s).strip() == "" or str(s) == "#N/A":
        return None
    digits = re.sub(r"[^\d]", "", str(s).strip())
    return digits if len(digits) == 11 and digits.isdigit() else None


def is_accountant_by_arca(activity_text: str | None) -> bool:
    """
    Check if ARCA activity indicates accountant - same criteria as custom code.
    """
    if not activity_text or not isinstance(activity_text, str):
        return False
    activity_lower = activity_text.lower().strip()
    if len(activity_lower) < 5:
        return False
    return any(
        pattern in activity_lower
        for pattern in ACCOUNTANT_ACTIVITY_PATTERNS
    )


def main():
    parser = argparse.ArgumentParser(
        description="Prioritize Cuenta Contador updates by ARCA activity"
    )
    parser.add_argument(
        "--facturacion",
        type=Path,
        default=Path("tools/outputs/facturacion.csv"),
        help="Path to facturacion.csv",
    )
    parser.add_argument(
        "--reporte",
        type=Path,
        default=Path("tools/outputs/reporte-control-facturacion-p.csv"),
        help="Path to reporte CSV",
    )
    parser.add_argument(
        "--rns-dataset",
        type=Path,
        default=None,
        help="Path to RNS dataset CSV (default: first available in rns_datasets/)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("tools/outputs/cuenta_contador_prioritized_by_arca.csv"),
        help="Output CSV path",
    )
    args = parser.parse_args()

    if not args.facturacion.exists():
        print(f"❌ Facturacion not found: {args.facturacion}")
        sys.exit(1)
    if not args.reporte.exists():
        print(f"❌ Reporte not found: {args.reporte}")
        sys.exit(1)

    # Load CUIT -> plan from facturacion
    cuit_to_plan = {}
    with open(args.facturacion, "r", encoding="utf-8") as f:
        for i, row in enumerate(f):
            if i < 2:
                continue
            parts = row.strip().split(";")
            if len(parts) >= 3:
                cuit = normalize_cuit(parts[1])
                plan = parts[2].strip()
                if cuit and plan and plan in ACCOUNTANT_PLANS:
                    if cuit not in cuit_to_plan:
                        cuit_to_plan[cuit] = plan

    # Load Type-unknown + accountant plan from reporte
    candidates = []
    with open(args.reporte, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            if len(row) < 5 or row[3] != "(No value)":
                continue
            cuit_norm = normalize_cuit(row[2])
            if cuit_norm and cuit_norm in cuit_to_plan:
                candidates.append({
                    "company_id": row[4].strip(),
                    "razon": row[1],
                    "cuit": row[2],
                    "cuit_norm": cuit_norm,
                    "plan": cuit_to_plan[cuit_norm],
                })

    print(f"📋 Cuenta Contador candidates (accountant plan + Type unknown): {len(candidates)}")

    # Load RNS and lookup actividad_descripcion
    rns_dir = _scripts_dir / "rns_datasets"
    rns_file = args.rns_dataset
    if not rns_file:
        csv_files = sorted(rns_dir.glob("*.csv"), key=lambda p: p.stat().st_mtime, reverse=True)
        rns_file = csv_files[0] if csv_files else None

    if not rns_file or not rns_file.exists():
        print(f"❌ RNS dataset not found. Place CSV in tools/scripts/rns_datasets/")
        sys.exit(1)

    from rns_dataset_lookup import RNSDatasetLookup

    lookup = RNSDatasetLookup(dataset_dir=str(rns_dir))
    df = lookup.load_dataset(str(rns_file))

    # Normalize CUIT in dataset (column names are lowercased by load_dataset)
    cuit_col = "cuit" if "cuit" in df.columns else [c for c in df.columns if "cuit" in c.lower()][0]
    df["cuit_norm"] = df[cuit_col].astype(str).str.replace(r"[-\s\.]", "", regex=True)

    act_col = "actividad_descripcion" if "actividad_descripcion" in df.columns else None
    if not act_col:
        act_col = next((c for c in df.columns if "actividad_descripcion" in c), None)
    if not act_col:
        print("❌ actividad_descripcion column not found in RNS dataset")
        sys.exit(1)

    # Build CUIT -> actividad lookup
    cuit_to_actividad = dict(
        zip(
            df["cuit_norm"],
            df[act_col].fillna("").astype(str).str.strip(),
        )
    )

    # Classify each candidate
    prioritized = []
    no_arca = []
    arca_not_accountant = []

    for c in candidates:
        act = cuit_to_actividad.get(c["cuit_norm"], "")
        if not act:
            no_arca.append(c)
            continue
        if is_accountant_by_arca(act):
            c["actividad_descripcion"] = act
            c["arca_indicates_accountant"] = True
            prioritized.append(c)
        else:
            c["actividad_descripcion"] = act
            c["arca_indicates_accountant"] = False
            arca_not_accountant.append(c)

    # Output
    print(f"\n✅ Prioritized (ARCA indicates accountant): {len(prioritized)}")
    print(f"⚠️  ARCA not accountant (skip for now): {len(arca_not_accountant)}")
    print(f"⚠️  No ARCA data in RNS: {len(no_arca)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "company_id",
                "razon",
                "cuit",
                "plan",
                "actividad_descripcion",
                "arca_indicates_accountant",
            ],
        )
        writer.writeheader()
        for c in prioritized:
            writer.writerow({
                "company_id": c["company_id"],
                "razon": c["razon"],
                "cuit": c["cuit"],
                "plan": c["plan"],
                "actividad_descripcion": c.get("actividad_descripcion", ""),
                "arca_indicates_accountant": "True",
            })

    print(f"\n💾 Prioritized list saved to: {args.output}")
    print(f"\nThese {len(prioritized)} companies can be safely updated to Type = Cuenta Contador.")


if __name__ == "__main__":
    main()
