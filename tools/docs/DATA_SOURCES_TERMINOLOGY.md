# Data Sources — Standard Terminology

**Purpose:** Canonical definitions for billing, HubSpot, and Colppy data. Use this nomenclature consistently across docs, scripts, and conversations.

**Last Updated:** 2026-02-25

---

## 1. The Three Data Sources

| Term | What it is | Artifacts | Use when |
|------|------------|-----------|----------|
| **Billing** | The billing system / billing process. Separate from Colppy. Produces the CRM mapping export. | `facturacion.csv` | Referring to the billing system export, CRM mapping source, or curated billing list. |
| **HubSpot** | CRM: deals and companies. One product = one deal; billed to the primary company (association type 5). | Deals, companies, deal_associations | Referring to CRM data, deal–company associations, or HubSpot API. |
| **Colppy** | Colppy product DB (MySQL). Where actual payments happen and records are generated. | Colppy MySQL: `pago`, `facturacion`, `empresa`, `plan`, etc. | Referring to Colppy internal data, first payments, recurring payments, or Colppy staging/production DB. |

---

## 2. Detailed Definitions

### 2.1 Billing

- **Definition:** The billing system / billing process. A separate system that produces a manual export for CRM mapping.
- **Artifact:** `facturacion.csv` — manual export from the billing process.
- **Location:** `tools/outputs/facturacion.csv` (or path passed to scripts).
- **Key columns:** Email; Customer Cuit; Plan; Id Plan; Amount; Product CUIT; Id Empresa
- **Use "Billing" when:** Talking about the billing system, the facturacion.csv file, or the curated list used for CRM/HubSpot mapping.
- **Do NOT use "facturacion" alone** for this — say **"billing"** or **"facturacion.csv"** (billing export) to avoid confusion with Colppy's facturacion table.

### 2.2 HubSpot

- **Definition:** HubSpot CRM. Deals represent products (id_empresa); companies are the legal entities. Each deal has a PRIMARY company (association type 5) — the company we bill for that product.
- **Artifacts:** Deals, companies, deal_associations (from HubSpot API).
- **Location:** HubSpot API; local copy in `facturacion_hubspot.db` (deals, companies, deal_associations).
- **Use "HubSpot" when:** Referring to deals, companies, associations, or any CRM data from HubSpot.

### 2.3 Colppy

- **Definition:** Colppy product database (MySQL). Where actual payments happen, first payments and recurring payments are recorded, and Colppy's internal billing/facturacion data lives.
- **Artifacts:** Colppy MySQL tables: `pago`, `facturacion`, `empresa`, `plan`, `payment_detail`, etc. Also `colppy_export.db` (SQLite export for offline use).
- **Location:** Colppy MySQL (staging/production); `tools/data/colppy_export.db` (local export).
- **Use "Colppy" when:** Referring to Colppy internal data, payments, first payments, Colppy's facturacion table, or the Colppy product DB.
- **Important:** Colppy has its own `facturacion` table — this is **Colppy facturacion**, NOT the billing system. When we say "Colppy facturacion" we mean the Colppy MySQL `facturacion` table.

---

## 3. Nomenclature Quick Reference

| Concept | Say | Avoid |
|---------|-----|-------|
| The CSV from the billing process | **Billing** or **facturacion.csv** (billing export) | "facturacion" alone |
| The Colppy MySQL facturacion table | **Colppy facturacion** or **Colppy MySQL facturacion** | "facturacion" when context is Colppy |
| Deals + companies in CRM | **HubSpot** | — |
| Payments, first payments, Colppy DB | **Colppy** or **Colppy MySQL** | — |
| The SQLite built from billing CSV + HubSpot | **facturacion_hubspot.db** | — |

---

## 3.5 CUIT Types (Service Holder vs Invoice Recipient)

Two distinct CUIT concepts matter for billing and HubSpot reconciliation:

| Term | Meaning | Source | Use when |
|------|---------|--------|----------|
| **Service holder CUIT** | The company that uses the Colppy product (titular del servicio). For HubSpot reconciliation, the deal's primary company must match this CUIT. | `empresa.CUIT` (Colppy DB); billing `product_cuit` (facturacion.csv) | Referring to who we bill for the product; HubSpot primary company must match this. |
| **Invoice recipient CUIT** | The entity we send the invoice to (CUIT facturado a). May equal the service holder (direct billing) or differ when an accountant receives the invoice (channel billing). | Colppy `facturacion.CUIT`; billing `customer_cuit` (facturacion.csv) | Referring to who receives the invoice. |

**Direct billing:** Service holder = Invoice recipient (same CUIT).

**Channel billing (e.g. accountant):** Service holder ≠ Invoice recipient — invoice goes to the accountant, but the service is for the client company.

---

## 4. facturacion_hubspot.db — What Lives Where

| Table | Source | Meaning |
|-------|--------|---------|
| `facturacion` | **Billing** (facturacion.csv) | Billing export loaded into DB. Master for CRM mapping. |
| `deals` | **HubSpot** | Deals from HubSpot API. |
| `companies` | **HubSpot** | Companies from HubSpot API. |
| `deal_associations` | **HubSpot** | Deal–company associations (type 5 = PRIMARY). |

**Rule:** In `facturacion_hubspot.db`, the `facturacion` table = billing (facturacion.csv). It is NOT Colppy facturacion.

---

## 4.1 Colppy id_empresa Rule (HubSpot Must Match Colppy)

**Colppy is source of truth.** HubSpot deals MUST use Colppy id_empresa. If not, they will not match in reconciliation.

- When the same company (CUIT) has two id_empresa in billing — one Colppy (active plan), one CRM (Pendiente de Pago) — HubSpot deals must use the **Colppy id_empresa**.
- Example: Colppy 87956, CRM 97897 (same CUIT) → HubSpot deal must have id_empresa=87956, not 97897.
- **Fix:** Use `fix_colppy_id_empresa_on_deals.py` to update deals with wrong id_empresa.

**Deals for Colppy first payments:** When Colppy has a first payment for id_empresa X, there MUST be a HubSpot deal for that id_empresa. If missing, create the deal. Run `reconcile_missing_deals.py --dry-run` to get the list; it reports "Create new deals for:" — treat as list requiring approval before creation. Do NOT create deals without explicit user confirmation.

**id_plan (colppy_plan):** HubSpot deal property `colppy_plan` is the internal name for Colppy id_plan. It must match Colppy `pago.idPlan` for the deal; this defines the amount in HubSpot. Either side can be blank; reconciliation only flags mismatch when both are non-blank and differ.

**Close date:** Colppy `fechaPago` (first payment date) is master. HubSpot `close_date` must match. Sales may force a different close date (compliance issue); reconciliation flags `close_date` mismatches.

---

## 5. Reconciliation Directions (Standard Terms)

| Reconciliation | Sources | Script |
|-----------------|---------|--------|
| **HubSpot ↔ Billing** | Deals (HubSpot) vs facturacion table (from billing CSV) | `reconcile_hubspot_deals_facturacion.py` |
| **Colppy ↔ HubSpot** | First payments (Colppy) vs closed-won deals (HubSpot) | `reconcile_colppy_hubspot_db_only.py`, `reconcile_with_recovery_check.py` |
| **Billing ↔ Colppy** | facturacion.csv (billing) vs Colppy MySQL facturacion | `reconcile_facturacion_colppy.py` |

---

## 6. Data Flow (High Level)

```
Billing (facturacion.csv) ──────┐
                                ├──► facturacion_hubspot.db
HubSpot (deals, companies) ──────┘         │
                                           ├──► Reconciliation scripts
Colppy MySQL (pago, facturacion, etc.) ────┤
     │                                     │
     └──► colppy_export.db (offline) ──────┘
```

- **Billing** and **HubSpot** feed `facturacion_hubspot.db`.
- **Colppy** is queried directly (or via `colppy_export.db` when staging is unavailable).
- Reconciliation compares these sources using the standard terms above.
