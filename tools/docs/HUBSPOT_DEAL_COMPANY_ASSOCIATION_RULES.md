# HubSpot Deal–Company Association Rules

**Purpose:** Rules for handling deal–company associations when matching billing to HubSpot. See [DATA_SOURCES_TERMINOLOGY.md](./DATA_SOURCES_TERMINOLOGY.md) for standard terms (Billing, HubSpot, Colppy).

---

## 0. Core Billing Rule (Billing is Master for CRM Mapping)

**One product = one billing CUIT = PRIMARY association.**

| Role | CUIT | Association | Meaning |
|------|------|-------------|---------|
| **Billing company** | `customer_cuit` from billing (facturacion.csv / facturacion table) | **PRIMARY** (type 5) | The company we bill for the product. Exactly one per deal. |
| **Other companies** | Different CUITs | Not PRIMARY (e.g. type 8, 11) | Accountant, referrer, integrator, etc. Different legal entities. |

**Rule:** You can only bill a product to one single CUIT. That company must be the PRIMARY association on the deal. A product can have other companies (accountant, etc.) associated with different CUITs, but they are not primary.

**CUIT required for PRIMARY:** We do not accept companies without a valid CUIT as PRIMARY. A company must have a CUIT in HubSpot to be set as billing/primary. If the company has no CUIT (empty or invalid), it must be enriched or merged with the correct company record before it can be PRIMARY.

**Reference:** [ICP_COMPANY_DEFINITIONS_AND_ASSUMPTIONS.md](./ICP_COMPANY_DEFINITIONS_AND_ASSUMPTIONS.md) — Primary company and association type 8 (Estudio Contable).

---

## 0.1 How to Know Which Non-Primary Company Is the Accountant (Type 8)

**When a deal has multiple companies** (billing + others), use the **Company `type`** field to assign the correct association label:

| Company `type` (HubSpot) | Association label | Type ID |
|-------------------------|-------------------|---------|
| `Cuenta Contador` | Estudio Contable (accountant) | **8** |
| `Cuenta Contador y Reseller` | Estudio Contable (accountant) | **8** |
| `Contador Robado` | Estudio Contable (accountant) | **8** |
| Other (multi-entity, referrer, etc.) | Compañía con Múltiples Negocios | **11** |

**Rule:** If a non-primary company has `type` ∈ `Cuenta Contador` \| `Cuenta Contador y Reseller` \| `Contador Robado`, it should have **association type 8** (Estudio Contable). Use `fix_deal_associations.py --fix-label DEAL_ID COMPANY_ID --remove 11 --add 8` to correct mislabeled associations.

**Empresa Administrada + industria contabilidad:** Companies with `type` = Empresa Administrada and `industria` containing "contabilidad" (e.g. "Contabilidad, impuestos, legales") are accountant firms misclassified. Fix company records with `icp_type_from_billing.py --fix-empresa-administrada-accountants`. The fix_deal_associations script also treats them as type 8 when assigning secondary labels.

**Name-based inference (fallback):** When `company.type` and `industria` are both empty, the script infers accountant from the company name. Patterns include: "estudio contable", "contador", "contadores", "asesor impositivo", "contaduría", "contadoría", "asesoramiento contable", "servicios contables". Example: "Estudio Contable Ferretti" with no type/industria → type 8 (Estudio Contable). This fallback is used only when type and industria are empty; it does not override explicit type/industria.

**Company enrichment:** When accountant is inferred from name, the script also PATCHes the company record with `type` = "Cuenta Contador" and `industria` = "Contabilidad, impuestos, legales". This enriches the HubSpot company so future runs use type/industria instead of name inference.

**Audit (type 8/11 validation):** After each fix batch, the script audits all non-primary companies on fixed deals. If a company has association type 8 (Estudio Contable) but `company.type` (and name fallback) does not warrant accountant → the label is corrected to type 11 (Múltiples Negocios). Conversely, if a company has type 11 but `company.type` or name warrants accountant → corrected to type 8. This prevents mislabeled associations (e.g. Power Silens with type 8 but company.type null).

**Source of truth:** Company `type` in HubSpot (primary). Name inference is fallback when type/industria are empty. See [ICP_COMPANY_DEFINITIONS_AND_ASSUMPTIONS.md](./ICP_COMPANY_DEFINITIONS_AND_ASSUMPTIONS.md) for `ACCOUNTANT_COMPANY_TYPES`.

---

## 1. CUIT Format Handling

**Problem:** HubSpot may store CUIT in different formats:
- `33715806679` (11 digits)
- `33-71580667-9` (formatted with hyphens)

**Rule:** Always treat both as the same legal entity. Normalize to 11 digits for matching.

**Implementation:**
- When **searching** HubSpot by CUIT: include BOTH formats in the `IN` filter
  ```python
  values = [format_cuit_display(c) for c in batch] + list(batch)  # both 33-71580667-9 and 33715806679
  ```
- When **matching** billing to companies: normalize `customer_cuit` to 11 digits before lookup

---

## 2. Multiple Companies per CUIT (Duplicates)

**Problem:** Same legal entity (CUIT) can have multiple company records in HubSpot due to:
- Different CUIT formats at creation time
- Legacy imports or integrations
- Deal creation creating a new company instead of linking to existing

**Rule:** Treat all companies with the same normalized CUIT as the same legal entity. **One company per CUIT:** There is no reason to have multiple HubSpot companies for the same CUIT; all duplicates should be merged.

**When associating deals to billing company:**
1. **Search** with both CUIT formats → may return multiple companies
2. **If multiple companies:** Pick ONE for the association:
   - Prefer the one already associated with the deal (if any)
   - Prefer the one whose name contains `id_empresa` matching billing
   - Prefer the one with `type` set (per `icp_type_from_billing.py`)
   - Otherwise: **merge duplicates first** using `merge_duplicate_companies.py`, then use merged result
3. **Do NOT** assume "first result" is correct — explicitly pick or merge

**Script logic:** `fix_deal_associations.py` verifies each company has a valid CUIT in HubSpot before applying. When a company lacks CUIT, it fixes it: (1) PATCH the company with `customer_cuit` from facturacion, or (2) find another company with that CUIT and use it. Only skips when both fixes fail. `build_facturacion_hubspot_mapping.py` and `fix_deal_associations.py`:
- Store **all** companies per CUIT (multiple rows per cuit in `companies` table)
- Check if deal has **any** company with `customer_cuit` as PRIMARY (not just one specific company)
- Exclude false positives when deal has a different company record with same CUIT

**Scripts:** `merge_duplicate_companies.py` (pairwise) or `merge_duplicates_by_cuit.py` (batch). Batch script finds all CUITs in facturacion with multiple companies and merges them into one per CUIT. Primary selection: prefer company with `type` set, then prefer name not just a number. Usage: `--dry-run` to preview, `--apply` to execute, `--batch N` to limit, `--exclude-test` to skip test CUIT.

---

## 3. Deal Stage and Facturacion Matching

**Problem:** A company can have multiple deals. Only some correspond to current billing (billing table).

**Rule:** Always consider `dealstage` when evaluating deal–company–facturacion alignment.

| dealstage | Meaning | In facturacion? |
|-----------|---------|-----------------|
| `closedwon` | Active, paying | Yes |
| `34692158` | Cerrado Ganado Recupero (recovery) | Yes |
| `closedlost` | Lost, no revenue | No |
| `31849274` | Cerrado Churn (customer left) | No |

**Implications:**
- **closedwon** (and 34692158): Expect a matching facturacion row for `customer_cuit` + `id_empresa`
- **closedlost** / **31849274** (churn): Correctly NOT in facturacion — customer is no longer paying
- A company with 2 deals (one closedwon, one churn) is valid — both associations stay; facturacion only has the active one

**Reference:** [README_HUBSPOT_CONFIGURATION.md](./README_HUBSPOT_CONFIGURATION.md) — Main Sales Pipeline stages

---

## 3.1 HubSpot ↔ Billing Reconciliation (Deals + id_empresa + CUIT)

**Purpose:** Verify that deals in the DB align with billing (facturacion table from facturacion.csv) by:
1. **id_empresa** — each deal must have a billing row for that id_empresa
2. **Primary company CUIT** — the deal's PRIMARY (type 5) company CUIT must equal billing.customer_cuit for that id_empresa

**Script:** `reconcile_hubspot_deals_facturacion.py`

**Usage:**
```bash
python tools/scripts/hubspot/reconcile_hubspot_deals_facturacion.py --year 2025 --month 11
python tools/scripts/hubspot/reconcile_hubspot_deals_facturacion.py --year 2025 --month 11 --output tools/outputs/hubspot_facturacion_reconcile_202511.md
```

**Statuses:**
| Status | Meaning |
|--------|---------|
| MATCH | HubSpot primary company CUIT = billing.customer_cuit for that id_empresa |
| MISMATCH | HubSpot primary CUIT ≠ billing.customer_cuit — fix associations in HubSpot |
| NO_PRIMARY | Deal has no type 5 association — add primary company |
| NO_FACTURACION | id_empresa not in billing table (facturacion.csv) |
| NO_CUIT | Primary company has no CUIT in HubSpot |

**Prerequisite:** Run `populate_deal_associations.py` so `deal_associations` is current before reconciliation.

**When to run:** After HubSpot refresh (`--refresh-deals-only`) and before Colppy/billing CSV reconciliation. This step validates HubSpot ↔ DB alignment separately from billing.

---

## 4. Summary Checklist

When analyzing or fixing deal–company associations:

- [ ] Normalize CUIT to 11 digits; search with both formats
- [ ] If multiple companies per CUIT: pick explicitly or merge first
- [ ] Filter by `dealstage` when matching to facturacion (closedwon/34692158 = active)
- [ ] Churn/lost deals on a company are expected — do not remove those associations

---

## 5. Fix Workflow (No Full Populate After Each Batch)

**Scripts:**
- `fix_deal_associations.py` — fixes Groups 1, 2, 3 & 4, updates local `deal_associations` after each batch
- `populate_deal_associations.py --deals 123,456` — incremental refresh for specific deals (e.g. after merges)

**Local DB updates (reconciliation):**
- When removing PRIMARY from a company: deletes that row from `deal_associations`
- When adding billing as PRIMARY: inserts `(deal, billing_company, type 5)`
- When adding accountant as type 8 (Group 3): inserts `(deal, accountant_company, type 8)` — considers ALL companies per CUIT
- When adding type 8 to accountant missing it (Group 4): inserts `(deal, company, type 8)` — for non-primary Cuenta Contador companies that have only 341
- When fixing secondary labels (8 or 11): removes old type, inserts new type in `deal_associations`
- Run `populate_deal_associations.py` periodically to refresh from HubSpot for full reconciliation

**Workflow:**
1. Run `fix_deal_associations.py --status` to see counts
2. Fix in batches: `fix_deal_associations.py --group 2 --batch 5 --log-fixed` (updates local DB; no full populate)
3. After merges: `populate_deal_associations.py --deals id1,id2,id3` to refresh those deals only
4. Full populate only when needed (e.g. new session, or to verify)

**Avoid duplicate deals:** When facturacion has rows without matching deals, run `reconcile_missing_deals.py --dry-run` first. It finds existing deals with wrong/empty `id_empresa` (e.g. deal name "54468 - X" but id_empresa=54274). Run `reconcile_missing_deals.py --apply` to fix them in HubSpot.

**Deal creation — confirmation required:** For facturacion rows with no matching deal in HubSpot, **do NOT create deals without explicit user confirmation**. Creation must be approved manually. The reconcile script reports "Create new deals for:" — treat this as a list requiring approval before any creation.

**Logging (default: always on):** All HubSpot sync scripts log to `edit_logs` in `facturacion_hubspot.db` by default. fix_deal_associations logs every fix batch; use `--no-log` to skip. Columns: `timestamp`, `script`, `action`, `outcome`, `detail`, `deal_id`, `deal_name`, `deal_url`, `company_id`, `company_name`, `company_url`, `customer_cuit`. Outcomes: `fixed` (detail: `cuit_ok`|`cuit_patched`|`cuit_alternative`), `failed` (detail: error message), `skipped` (detail: `no_customer_cuit`|`cuit_unfixable`), `dry_run` (when `--dry-run`). Merge, reconcile, build, and populate scripts also log.

**Redundant type 8 removal (`--remove-redundant-type8`):** Only removes type 8 when the **same company record** has both Primary (5) and type 8 (Estudio Contable). A company cannot be both the customer and their own accountant. We do **not** remove type 8 from a different company record, even if it shares the same CUIT as Primary — deals can have multiple accountants; if the association exists, the company is an actual accountant.

---

## 6. Accountant Portfolio & Churn (MRR Matrix)

**Purpose:** The MRR matrix (`analyze_accountant_mrr_matrix.py`) analyzes accountant portfolio behavior including **churned** deals.

**Team doc:** [MRR_DASHBOARD_DEFINITIONS.md](./MRR_DASHBOARD_DEFINITIONS.md) – Shareable definitions, formulas, and how the dashboard works. The build script only fetches deals for `id_empresa` in facturacion, so churned deals are missing by default.

**Script:** `populate_accountant_deals.py` — fetches deals associated with accountant companies (type 8 or Cuenta Contador) from HubSpot, including those with `id_empresa` not in facturacion (churned).

**Workflow for MRR matrix with churn:**
1. Run `build_facturacion_hubspot_mapping.py --csv` (companies, deals from facturacion; `--csv` exports mapping as backup)
2. Run `populate_deal_associations.py` (associations for existing deals)
3. Run `populate_accountant_deals.py` (adds churned deals from accountant associations)
4. Run `analyze_accountant_mrr_matrix.py` (or `--serve` for dashboard)

**When to populate vs when to rebuild dashboard:**

| Action | When to use |
|--------|-------------|
| **Run populate** (`populate_accountant_deals.py`, `populate_deal_associations.py`, `build_facturacion_hubspot_mapping.py`) | First-time setup; HubSpot data changed (new deals, associations, companies); previously ran with `--limit` and now need full dataset |
| **Rebuild dashboard only** (`analyze_accountant_mrr_matrix.py --html` or `--serve`) | Regenerating the MRR dashboard from existing DB; nothing changed in HubSpot or facturacion |

**Do NOT re-run populate** when only rebuilding the dashboard. Populate scripts call the HubSpot API and update the local SQLite DB. If HubSpot data is unchanged, populate adds no new data and is unnecessary.

---

## 7. ICP Dashboard

**Purpose:** Dashboard for Ideal Customer Profiles (ICP Operador, Asesor, Híbrido, Contador, PYME) with paying customers, MRR, and churn.

**Script:** `analyze_icp_dashboard.py` — builds HTML dashboard from facturacion_hubspot.db.

**ICP definitions** (from NPS_TO_ICP_DATA_FLOW.md):
- **ICP Operador:** tipo_icp_contador = "Operador" (empresa contadora que opera directamente)
- **ICP Asesor:** tipo_icp_contador = "Asesor" (empresa contadora que asesora)
- **ICP Híbrido:** tipo_icp_contador = "Híbrido" (empresa contadora híbrida)
- **ICP Contador:** type in (Cuenta Contador, Cuenta Contador y Reseller, Contador Robado) AND tipo_icp_contador empty
- **ICP PYME:** type = Cuenta Pyme (facturamos a la PyME)

**Metrics:**
- Paying customers: unique CUITs billed (customer_cuit), no duplication
- MRR by ICP: from billing company (tipo_icp_contador when set, else type)
- Churn deals: id_empresa NOT in facturacion; all churn associated with billed companies
- Churn by ICP: from primary company (association type 5)
- Self-billed vs Intermediary: customer_cuit = product_cuit vs not

**Usage:**
```bash
python tools/scripts/hubspot/analyze_icp_dashboard.py --html tools/outputs/icp_dashboard.html
python tools/scripts/hubspot/analyze_icp_dashboard.py --serve
```

**Note:** Run `build_facturacion_hubspot_mapping.py` to fetch `tipo_icp_contador` from HubSpot. Until then, accountant companies appear as "ICP Contador" (fallback when tipo_icp_contador is empty).

---

## 8. Facturacion Data Safety (Prevent Accidental Wipe)

**Purpose:** Prevent `facturacion.csv` (billing export) from being overwritten or corrupted, which would wipe `facturacion` and `companies` tables in the DB.

**Rules:**

| Do | Don't |
|----|-------|
| Keep `facturacion.csv` as the canonical billing source | Never overwrite with `echo` or manual commands |
| Use `facturacion_hubspot_mapping.csv` as backup (output of build with `--csv`) | Never truncate or replace facturacion.csv without a valid source |
| Run build with `--csv` periodically to refresh the mapping backup | Don't run build with an empty or corrupt facturacion.csv |

**Reconciliation with Colppy MySQL:** Run `reconcile_facturacion_colppy.py` to compare facturacion.csv with Colppy MySQL (live billing). See [FACTURACION_COLPPY_RECONCILIATION.md](./FACTURACION_COLPPY_RECONCILIATION.md).

**Build script safeguards:**
- Refuses to run if `facturacion.csv` has fewer than 50 data rows (avoids wiping DB with empty input)
- Use `--force` only for small test datasets
- Use `--restore-from-mapping` to recover when facturacion.csv was overwritten

**Recovery when facturacion.csv is empty/corrupt:**
```bash
python tools/scripts/hubspot/build_facturacion_hubspot_mapping.py \
  --restore-from-mapping tools/outputs/facturacion_hubspot_mapping.csv
```
Then run the full build as usual.

---

## 9. Keeping the dashboard and data up to date

**Current state:** Nothing runs automatically. The MRR dashboard (and company-wide ICP section) stay in sync with billing and HubSpot only when you run the pipeline manually.

**Data chain:**

| Step | What it uses | What it updates |
|------|----------------|-----------------|
| **1. Billing export** | Colppy/billing system | `tools/outputs/facturacion.csv` (canonical source). You must export and place this file; no script creates it from an API. |
| **2. Build** | `facturacion.csv` + HubSpot API (companies by CUIT, deals by id_empresa) | `facturacion_hubspot.db` (companies, deals, facturacion tables) |
| **3. Populate associations** | DB + HubSpot API | `deal_associations` in DB |
| **4. Populate accountant deals** | DB + HubSpot API | `deals` in DB (adds churned deals for MRR matrix) |
| **5. Dashboard** | DB only | `mrr_dashboard.html` (and optionally `docs/mrr_dashboard.html` for GitHub Pages) |

**Refresh order when you want up-to-date dashboards:**

1. **Update billing:** Replace `tools/outputs/facturacion.csv` with a fresh export from your billing source (same columns/format as before).
2. **Run the refresh script (recommended):**
   ```bash
   ./tools/scripts/hubspot/refresh_dashboard.sh --output-dir docs
   ```
   This runs: build (with `--csv`) → populate_deal_associations → populate_accountant_deals → analyze_accountant_mrr_matrix → analyze_icp_dashboard, and writes `docs/mrr_dashboard.html` and `docs/icp_dashboard.html`.
3. **Dashboard-only (no billing/HubSpot refresh):** If only regenerating HTML from the existing DB:
   ```bash
   ./tools/scripts/hubspot/refresh_dashboard.sh --dashboard-only --output-dir docs
   ```
4. **Publish:** Commit and push so GitHub Pages serves the new `docs/mrr_dashboard.html` (if you use the deploy-from-branch workflow).

**Script options:** `--dashboard-only` (skip build and populate), `--output-dir DIR` (default `docs`), `--facturacion PATH`, `--db PATH`. Env: `FACTURACION`, `DB`, `OUTPUT_DIR`.

**GitHub Action (implemented):** `.github/workflows/refresh-dashboard.yaml`

- **Triggers:** Manual (`workflow_dispatch`), push to `main` when dashboard scripts or workflow change, and **schedule** (Mondays 12:00 UTC).
- **Secrets:** Set `HUBSPOT_API_KEY` (or `HUBSPOT_ACCESS_TOKEN`) so build and populate can call the HubSpot API. Optional: `FACTURACION_CSV` = base64-encoded `facturacion.csv`; if set, the workflow writes it to `tools/outputs/facturacion.csv` and runs a full refresh; if not set, it runs dashboard-only using the **cached DB** from the previous run.
- **Cache:** The workflow caches `tools/outputs` (DB only; `facturacion.csv` is removed before saving) so scheduled runs without `FACTURACION_CSV` can still regenerate the dashboard from the last built DB.
- **Commit:** On success, it commits and pushes `docs/mrr_dashboard.html` and `docs/icp_dashboard.html` with message `chore: refresh MRR and ICP dashboards [skip ci]`.

**First-time CI setup:** Run the workflow once with `FACTURACION_CSV` set (export facturacion.csv, then `base64 -i tools/outputs/facturacion.csv | pbcopy` or equivalent and paste into the repo secret) and `HUBSPOT_API_KEY` set, so the DB is built and cached. Later scheduled runs can omit `FACTURACION_CSV` to only refresh the HTML from the cached DB.
