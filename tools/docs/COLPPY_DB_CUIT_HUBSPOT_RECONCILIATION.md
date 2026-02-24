# Colppy DB Facturacion ↔ HubSpot Primary Company CUIT Reconciliation

**Purpose:** Reconcile HubSpot deal primary company CUIT with Colppy DB CUIT (who we invoice). Alternative to facturacion.csv from the billing system — uses Colppy DB as source of truth.

**Last Updated:** 2026-02-24

---

## Overview

| Source | CUIT field | Use |
|--------|------------|-----|
| **Colppy DB** | empresa.CUIT (service holder CUIT) | Company that uses the product |
| **HubSpot** | Primary company (association type 5) CUIT | Who we bill per CRM |

**Rule:** For each deal, the HubSpot primary company CUIT must match the **service holder CUIT** (empresa.CUIT). See [DATA_SOURCES_TERMINOLOGY.md](./DATA_SOURCES_TERMINOLOGY.md) §3.5 for Service holder vs Invoice recipient CUIT.

---

## Data Flow

```
colppy_export.db (facturacion, empresa)
        │
        ▼
export_colppy_cuit_snapshot.py  →  colppy_cuit_snapshot.json
        │
        ├── facturacion.CUIT (invoice recipient CUIT, fechaBaja IS NULL)
        └── empresa.CUIT (service holder CUIT; fallback for id_empresa not in facturacion)

facturacion_hubspot.db (deals, deal_associations, companies)
        │
        ├── deal_associations (type 5 = PRIMARY)
        └── companies.cuit (by hubspot_id)

reconcile_cuit_hubspot_colppy_db.py  →  Compare Colppy CUIT vs HubSpot primary CUIT
```

---

## Status Categories

| Status | Meaning | Action |
|--------|---------|--------|
| **MATCH** | HubSpot primary company CUIT = Colppy DB CUIT | None |
| **MISMATCH** | HubSpot primary CUIT ≠ Colppy DB CUIT | Change primary company to the one with Colppy CUIT |
| **NO_PRIMARY** | Deal has no type 5 association | Add primary company with Colppy DB CUIT |
| **NO_COLPPY_CUIT** | id_empresa not in Colppy DB | Review; may be new or churned |
| **NO_HUBSPOT_CUIT** | Primary company exists but no CUIT in companies table | Enrich company or run full build with Colppy CUITs |

---

## Prerequisites

1. **colppy_export.db** — Export from Colppy MySQL (or use colppy_cuit_snapshot.json)
2. **facturacion_hubspot.db** — Deals, deal_associations, companies
3. **populate_deal_associations.py** — Run to ensure deal_associations is current

---

## Usage

```bash
# Feb 2026
python tools/scripts/colppy/reconcile_cuit_hubspot_colppy_db.py --year 2026 --month 2 --output tools/outputs/cuit_reconcile_colppy_db_202602.md

# All closed-won deals (no month filter)
python tools/scripts/colppy/reconcile_cuit_hubspot_colppy_db.py
```

---

## Reconciling Label Associations in HubSpot

After running CUIT reconciliation:

1. **NO_PRIMARY:** Create or associate the company with Colppy DB CUIT as PRIMARY (type 5). Ensure the company exists in HubSpot with that CUIT.
2. **MISMATCH:** Update the deal's primary association to the company whose CUIT matches Colppy DB. Use `fix_deal_associations.py` or HubSpot UI.
3. **Non-primary labels:** For accountant companies, ensure type 8 (Estudio Contable). For others, type 11 (Múltiples Negocios). See [HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md](./HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md).

---

## Related docs

- [README_BILLING_RECONCILIATION.md](./README_BILLING_RECONCILIATION.md) — Chatbot output instructions, workflow
- [HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md](./HUBSPOT_DEAL_COMPANY_ASSOCIATION_RULES.md) — Association type 5, 8, 11
