# ARCA Tax Data Extraction from List API

**Date:** 2026-02-24
**Status:** Approved

## Problem

ARCA's Mis Comprobantes list API returns 49 fields per emitido invoice, but we only parse 12. The remaining 37 fields include IVA breakdown, neto gravado, otros tributos, and tipo de cambio — critical accounting data that accountants need, especially for `only_arca` discrepancies (invoices in ARCA but not in Colppy).

## Discovery

Raw ARCA emitido array field mapping (reverse-engineered 2026-02-24):

| Index | Field | Example | Verified |
|-------|-------|---------|----------|
| `[13]` | tipo_cambio | `"1"` (ARS), `"1036"` (USD) | Glovoapp USD invoice |
| `[29]` | iva_total | `"596064.35"` | Matches Colppy totalIVA |
| `[31]` | neto_gravado | `"2838401.65"` | Matches Colppy netoGravado |
| `[33]` | neto_no_gravado | `None` | Matches Colppy |
| `[35]` | exento | `None` | — |
| `[37]` | base_imponible_iva | `"2838401.65"` | Same as neto when single rate |
| `[39]` | otros_tributos | `"0"` | Percepciones slot |
| `[41]` | otros_tributos_2 | `"0"` | — |
| `[43]` | otros_tributos_3 | `"0"` | — |
| `[45]` | iva_subtotal | `"596064.35"` | Duplicate of [29] |

**Formula verified:** `[31] + [33] + [35] + [29] + [39] + [41] + [43] = [47]` (total)

## Approach: Forward-Only Extraction

Extract 7 new fields from the raw array we already fetch. No detail-page scraper needed. No backfill of existing cache — new fetches include tax data automatically.

## Changes

### 1. Parser (`comprobantes_api.py`)
Add fields to `_parse_comprobante_emitido()`: tipo_cambio, neto_gravado, neto_no_gravado, exento, iva_total, otros_tributos (sum of [39]+[41]+[43]).

### 2. SQLite (`arca_db.py`)
Add columns via ALTER TABLE migration: tipo_cambio, neto_gravado, neto_no_gravado, exento, iva_total, otros_tributos. All REAL, nullable.

### 3. Record summary (`reconciliacion_emitidos.py`)
Add new fields to `_arca_record_summary()`.

### 4. Frontend (`ReconciliacionPage.jsx`)
Update `InvoiceDetail` ARCA panel to show tax breakdown rows.

## Not in scope
- Detail-page scraper (list API is sufficient)
- Backfill of existing cached data
- Per-aliquot IVA breakdown (ARCA list only gives total; Colppy has per-rate)
