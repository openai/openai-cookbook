# Colppy ↔ HubSpot Reconciliation Report — Group Structure

The reconciliation report is organized into **4 groups** based on date mismatches and presence in each system.

## Group Definitions

### 1. Match but Mismatch in date = same month (fechaPago ≠ close_date)

- **Definition:** id_empresa appears in both Colppy first payments and HubSpot closed-won for the reconciliation month. Both fechaPago and close_date fall in the same month, but the exact day differs.
- **Source:** Colppy has first payment this month; HubSpot has closed-won deal this month; fechaPago ≠ close_date.
- **Action:** Set HubSpot close_date = Colppy fechaPago.

### 2. Match but Mismatch in date = different month (fechaPago ≠ close_date)

- **Definition:** id_empresa appears in Colppy first payments this month, and a HubSpot deal exists for that id_empresa, but the deal's close_date is in a different month.
- **Source:** Colppy has first payment this month; HubSpot deal exists (closed-won) but close_date in another month.
- **Action:** Set HubSpot close_date = Colppy fechaPago.

### 3. Wrong Stage

**COLPPY_NOT_ACTIVE:** Colppy activa ≠ 0 (company inactive), HubSpot closed-won — mismatch. Only these appear when activa ≠ 0. Rows with activa ≠ 0 and HubSpot not closed-won (e.g. closed churn) are excluded.

**WRONG_STAGE:** Colppy activa = 0 (company active), HubSpot deal exists but not closed-won (e.g. closed churn).

**NO_HUBSPOT_DEAL:** In Colppy DB, no id_empresa in HubSpot (no closed-won deal for this id).

- **Action:** COLPPY_NOT_ACTIVE: Review. WRONG_STAGE: Move to closed-won, set close_date = Colppy fechaPago. NO_HUBSPOT_DEAL: Create deal.
- **Report:** Group 3 table includes **Reason** and **HubSpot stage** columns.

### 4. HubSpot closed-won this month, Colppy first payment in different month or absent

- **Definition:** HubSpot has closed-won deal this month; Colppy fechaPago is in a different month, or Colppy has no first payment at all.
- **Reasons:** NOT_IN_COLPPY (id_empresa not in Colppy empresa), IN_EMPRESA_NO_PAGO (in empresa, no pago), PRIMER_PAGO_OTHER_MONTH (first payment in another month), IN_EMPRESA_PAGO_NO_PRIMER (has pago but no primerPago).
- **Action:** Review; may be cross-sell, data entry error, or timing mismatch.

---

## Standard Columns (paired for easy comparison)

Column order: id_empresa | Colppy id_plan | HubSpot id_plan | Colppy fechaPago | HubSpot close_date | HubSpot fecha_primer_pago | **activa** | **HubSpot stage** | Colppy medioPago | Colppy amount | HubSpot amount | HubSpot deal (activa beside HubSpot stage for easy comparison)

**All tables with HubSpot data** (Groups 1, 2, 3, 4) include **HubSpot stage** (deal_stage).

**Group 3 only:** id_empresa | **Reason** | activa | ... (Reason: COLPPY_NOT_ACTIVE, WRONG_STAGE, or NO_HUBSPOT_DEAL)

Dates and amounts are placed side by side for quick comparison.

| Column | Source | Description |
|--------|--------|-------------|
| Reason (Group 3) | group3_reasons | COLPPY_NOT_ACTIVE (activa≠0), WRONG_STAGE (deal not closed-won), NO_HUBSPOT_DEAL (in Colppy, no id_empresa in HubSpot) |
| activa | empresa.activa | 0=Activa, 2=Desactivada Falta Pago, 3=Desactivada Usuario |
| Colppy id_plan | pago.idPlan | Colppy plan ID |
| HubSpot id_plan | deals.id_plan | HubSpot colppy_plan |
| Colppy fechaPago | pago.fechaPago | First payment date |
| HubSpot close_date | deals.close_date | Deal close date |
| HubSpot fecha_primer_pago | deals.fecha_primer_pago | HubSpot first payment date |
| HubSpot stage | deals.deal_stage | Deal stage (closedwon, closed churn, etc.) — present in all groups with HubSpot data |
| Colppy medioPago | pago.medioPago | Payment method |
| Colppy amount | pago.importe | Payment amount |
| HubSpot amount | deals.amount | Deal amount |
| HubSpot deal | deals.deal_name + hubspot_id | Clickable link to deal |

---

## Data Sources

- **Colppy:** colppy_export.db (pago, plan, empresa, facturacion)
- **HubSpot:** facturacion_hubspot.db (deals, deals_any_stage)
