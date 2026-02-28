# colppy_export.db Refresh Strategy: Transactional vs Snapshot

**Purpose:** Map each table in `colppy_export.db` to an optimal refresh strategy (incremental vs full snapshot) to reduce MySQL load and export time.

**Source:** Colppy MySQL → SQLite via `export_colppy_to_sqlite.py`  
**Last Updated:** 2026-02-26

---

## 1. Table Classification

| Table | Type | Natural Key | Time/Change Columns | Rows (approx) |
|-------|------|-------------|---------------------|---------------|
| **pago** | Transactional | idPago | fechaPago, created_at, updated_at | ~30k+ |
| **payment_detail** | Transactional | payment_id | (child of pago) | ~30k+ |
| **empresa** | Snapshot | IdEmpresa | record_insert_ts, record_update_ts | ~68k |
| **facturacion** | Snapshot | idFacturacion | fechaAlta, fechaBaja | ~28k |
| **plan** | Snapshot | idPlan | (small, rarely changes) | ~635 |

---

## 2. Refresh Strategy by Table

### 2.1 Transactional (Incremental)

**pago** and **payment_detail** are append-only event streams. New rows = new payments. Can be refreshed incrementally.

| Table | Incremental Strategy | Notes |
|-------|----------------------|-------|
| **pago** | `WHERE fechaPago >= :last_sync_date` | Fetch only new rows since last export. |
| **payment_detail** | Fetch by `payment_id IN (SELECT idPago FROM pago WHERE ...)` | Must be refreshed after pago; same date range. |

**Benefits:** For daily refresh, only fetch ~100–500 new rows vs ~30k full. Reduces MySQL load and export time.

**Requirement:** Store `last_sync_date` in `colppy_sync_state` table.

**Implementation:** Uses DELETE + INSERT (not INSERT OR REPLACE) for upserts.

---

### 2.2 Snapshot (Full or Targeted)

**empresa**, **facturacion**, and **plan** are dimension tables that can change in place.

| Table | Strategy | Rationale |
|-------|----------|-----------|
| **empresa** | Snapshot (full or by ID set) | CUIT, name, activa can change. Has `record_update_ts` but not all consumers need it. |
| **facturacion** | Snapshot | fechaBaja changes when churned; no updated_at. Need current state for active billing. |
| **plan** | Full snapshot | ~635 rows; cheap. Rarely changes. |

**Options for empresa/facturacion:**
- **Full snapshot:** Replace entire table each run. Simple, consistent. ~100k rows total.
- **Targeted snapshot:** Only refresh rows for `id_empresa` in deals we care about (e.g. recent months). Reduces volume but adds complexity.
- **Incremental (empresa):** If `record_update_ts` is reliable: `WHERE record_update_ts >= :last_sync`. Requires UPSERT logic.

---

## 3. Current vs Proposed Behavior

### Current (export_colppy_to_sqlite.py)

| Mode | Behavior |
|------|----------|
| **Full** (no --year --month) | DROP + CREATE all 5 tables. Full snapshot. ~135k rows, 1–2 min. |
| **Timeframe** (--year --month) | Fetch first payments for month → DELETE existing rows for that month's IDs → INSERT. Merge into existing DB. |

**Timeframe mode** is already incremental for *first payments*: it only touches data for the requested month. But it does not support incremental *pago* for all payments (e.g. recurring).

---

## 4. Recommended Optimization Phases

### Phase 1: Incremental pago (low risk)

1. Add `last_pago_sync` to `colppy_export_refresh_logs` or a `sync_state` table.
2. New mode: `--incremental` or `--incremental-since YYYY-MM-DD`
   - Fetch `pago` WHERE `fechaPago >= last_sync`
   - Fetch `payment_detail` for those payment_ids
   - UPSERT into SQLite (INSERT OR REPLACE by idPago)
3. Keep full snapshot as fallback for initial load or `--full`.

**Impact:** Daily refresh: ~50–200 new rows vs ~30k. Reduces MySQL query time and network transfer.

---

### Phase 2: Snapshot frequency by table

| Table | Full refresh | Incremental / targeted |
|-------|--------------|-------------------------|
| **plan** | Weekly or on demand | N/A (small) |
| **empresa** | Weekly full; or incremental by `record_update_ts` if supported | Daily: only empresas with first payment in last N days |
| **facturacion** | Weekly full; or sync only active (fechaBaja IS NULL) | Daily: targeted by id_empresa from new pago |

---

### Phase 3: Hybrid refresh script

```text
--incremental          # pago + payment_detail since last sync
--snapshot-tables      # empresa, facturacion, plan (full)
--snapshot-targeted    # empresa, facturacion only for id_empresa in recent pago
--year --month         # (existing) timeframe merge for first payments
```

---

## 5. Consumers and Dependencies

| Consumer | Tables used | Refresh needs |
|----------|-------------|---------------|
| **Reconciliation** (Colppy ↔ HubSpot) | pago, facturacion, plan, payment_detail | First payments by month; current facturacion |
| **fix_deal_associations** (--colppy-db) | facturacion, empresa | id_empresa → CUIT mapping |
| **create_company_from_colppy** | facturacion, empresa | Company data for NO_PRIMARY deals |
| **export_colppy_cuit_snapshot** | facturacion, empresa | CUIT mapping |
| **export_reconciliation_snapshot** | pago, facturacion, plan, payment_detail | First payments, active billing |
| **export_reconciliation_db_snapshot** | facturacion_hubspot.db + colppy_export.db | Both DBs |

---

## 6. Sync State Table (Proposed)

```sql
CREATE TABLE IF NOT EXISTS colppy_sync_state (
    id              INTEGER PRIMARY KEY CHECK (id = 1),
    last_pago_sync   TEXT,   -- ISO date, e.g. 2026-02-25
    last_empresa_sync TEXT,
    last_facturacion_sync TEXT,
    updated_at       TEXT
);
```

Single row. Updated after each successful incremental run.

---

## 7. Summary

| Table | Current | Recommended | Effort |
|-------|---------|-------------|--------|
| **pago** | Full or timeframe merge | Incremental by fechaPago | Medium |
| **payment_detail** | Full or timeframe merge | Incremental (follow pago) | Low |
| **empresa** | Full or targeted by ID | Full weekly; incremental daily optional | Medium |
| **facturacion** | Full or targeted by ID | Full weekly; targeted by id_empresa optional | Medium |
| **plan** | Full | Full (cheap) | Low |

**Priority:** Start with Phase 1 (incremental pago) for the biggest gain. Plan and empresa/facturacion optimizations can follow.
