# Recibidos & Impuestos Reconciliation — Design Doc

**Date:** 2026-02-24
**Status:** Approved

## Problem

The current reconciliation covers ARCA emitidos (sales invoices) ↔ Colppy ventas. Purchase invoices ("recibidos") are not reconciled against Colppy, and retenciones/percepciones are only matched against ARCA comprobantes recibidos (ARCA ↔ ARCA), not against the ERP.

## Solution: Approach A — Purchase Invoice Reconciliation + Tax Overlay

Add a new **"Recibidos"** tab that reconciles ARCA comprobantes recibidos ↔ Colppy compras by invoice number, with retenciones and percepciones as overlay data.

## Data Sources

| Source | API | Key Fields |
|--------|-----|------------|
| ARCA comprobantes recibidos | SQLite cache (auto-fetch via Playwright) | `numero`, `cuit_contraparte`, `importe_total`, `otros_tributos` |
| Colppy compras | `FacturaCompra.listar_facturasCompra` | `nroFactura`, `idProveedor`, `totalFactura`, `percepcionIVA`, `percepcionIIBB` |
| Colppy proveedores | `Proveedor.listar_proveedor` | `idProveedor`, `CUIT`, `RazonSocial` |
| ARCA retenciones | SQLite cache (from Mirequa) | `cuit_agente_retencion`, `numero_certificado`, `importe_retenido` |

### Key Findings from Data Exploration

- Colppy compras have **no CAE** and **no CUIT** — only `idProveedor`. Requires proveedor lookup.
- Invoice number format `PPPPP-NNNNNNNN` is consistent across ARCA recibidos and Colppy compras.
- ARCA retenciones `numero_comprobante` is a 16-digit payment reference (not invoice number) — retenciones link to invoices via agent CUIT + period, not invoice number.
- 30 fields per Colppy purchase invoice, including: `percepcionIVA`, `percepcionIIBB`, `percepcionIIBB1`, `percepcionIIBB2`, `IIBBLocal`, `IIBBOtro`, `idRetGanancias`.
- ~18% of purchase invoices have non-zero percepciones (mostly `percepcionIVA`).
- CUIT in proveedores is formatted `30-65485516-8` (needs normalization to `30654855168` for ARCA matching).

## Matching Logic

### Primary Match: Invoice Number

1. Normalize invoice numbers: strip leading zeros on punto_venta, ensure `PPPPP-NNNNNNNN` format.
2. Index ARCA recibidos by `numero`.
3. Enrich Colppy compras with supplier CUIT from proveedor lookup, index by `nroFactura`.
4. Cross-match by invoice number.

### Buckets

| Status | Condition |
|--------|-----------|
| `matched` | Same invoice number, amounts within $0.02 |
| `amount_mismatch` | Same invoice number, totals differ |
| `only_arca` | Invoice in ARCA but not in Colppy |
| `only_colppy` | Invoice in Colppy but not in ARCA |

### Percepciones Comparison (per matched pair)

- ARCA side: `otros_tributos` (sum of array indices [39], [41], [43])
- Colppy side: `percepcionIVA` + `percepcionIIBB` + `percepcionIIBB1` + `percepcionIIBB2`
- Flag: `percepciones_diff` when abs(arca - colppy) > $0.02

### Retenciones Overlay

- Load ARCA retenciones from cache (if available) for same CUIT + date range.
- Group by `cuit_agente_retencion` + period (YYYY-MM).
- For each invoice, check if supplier CUIT + invoice period has linked retenciones.
- Attach: `retenciones_count`, `retenciones_total`, `retenciones_detail[]`.

## Backend

### New: `backend/services/reconciliacion_recibidos.py`

```python
async def reconcile_recibidos_stream(
    cuit_representado: str,
    id_empresa: str,
    fecha_desde: str,
    fecha_hasta: str,
) -> AsyncIterator[str]:
```

**SSE Steps:**
1. Load ARCA comprobantes recibidos from cache (auto-fetch if empty) — pct 10-20
2. Colppy login + fetch proveedores → build CUIT map — pct 25-30
3. Colppy fetch compras month-by-month — pct 30-70
4. Normalize + index by invoice number — pct 75-80
5. Cross-match + retenciones overlay + percepciones comparison — pct 85-100

### Colppy API: Proveedor CUIT Lookup

Uses existing `colppy_api.list_proveedores()`. Build map once per reconciliation:

```python
proveedores = await colppy_api.list_proveedores(clave, id_empresa)
cuit_map = {p["idProveedor"]: normalize_cuit(p["CUIT"]) for p in proveedores["data"]}
```

CUIT normalization: `"30-65485516-8"` → `"30654855168"` (strip dashes).

### New endpoint in `backend/routers/arca.py`

```
GET /reconcile/recibidos/stream?cuit={cuit}&id_empresa={id}&fecha_desde={d}&fecha_hasta={d}
→ StreamingResponse (text/event-stream)
```

## Frontend

### Tab Navigation

```
[ Emitidos ]  [ Recibidos ]  [ Retenciones ]
```

"Recibidos" is the new tab. Same date-range form, same progress bar, same summary cards layout.

### Summary Cards

- ARCA Recibidos: count
- Colppy Compras: count
- Matcheados: count (green)
- Discrepancias: count (orange)

### Discrepancies Table

Columns: Nro Factura | Fecha | Proveedor | CUIT | ARCA Total | Colppy Total | Percepciones | Retenciones

Expandable detail row reuses `InvoiceDetail` pattern with:
- Left panel: ARCA recibido (fiscal data + otros_tributos)
- Right panel: Colppy compra (ERP data + percepciones breakdown)
- Percepciones match indicator (✓ or ⚠ diff)
- Retenciones section (if cached): list of linked certificates

## Not In Scope

- No new DB tables or scrapers
- No Colppy retenciones API (doesn't exist — retenciones are payment-side)
- No automatic Mirequa download from this flow (uses existing cache)
- No acknowledgment UX on recibidos (can add later)
