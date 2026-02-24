# ARCA Prototype — Documentation Index

**Purpose:** Entry point for AI context and developers working on the ARCA prototype (AFIP/ARCA portals, Colppy API, Banco Galicia, reconciliación, Libro IVA).

**Last Updated:** 2026-02-24

---

## Quick Reference

| Topic | Document | Location |
|-------|----------|----------|
| **Architecture & flows** | [ARCHITECTURE.md](../../arca-prototype/docs/ARCHITECTURE.md) | `arca-prototype/docs/` |
| **Deployment guide** | [DEPLOYMENT.md](../../arca-prototype/docs/DEPLOYMENT.md) | `arca-prototype/docs/` |
| **Libro IVA format** | [LIBRO_IVA_FORMAT.md](../../arca-prototype/docs/LIBRO_IVA_FORMAT.md) | `arca-prototype/docs/` |
| **WSAA certificate setup** | [WSAA_CERTIFICATE_SETUP.md](../../arca-prototype/docs/WSAA_CERTIFICATE_SETUP.md) | `arca-prototype/docs/` |

---

## What Is ARCA?

ARCA prototype is a **FastAPI backend + React frontend** that integrates with:

- **AFIP/ARCA portals** — DFE (Domicilio Fiscal Electrónico), Mis Comprobantes, Mis Retenciones
- **Colppy API** — Accounting data (empresas, clientes, proveedores, facturas de compra/venta)
- **Banco Galicia** — savings account statement extraction (Playwright scraper)
- **SQLite cache** — `arca_notifications.db` for offline use and acknowledgments

### Deployment

- **Frontend:** Static build on GitHub Pages (`https://<user>.github.io/openai-cookbook/arca-app/`)
- **Backend:** Local machine + Cloudflare Tunnel for remote access
- See [DEPLOYMENT.md](../../arca-prototype/docs/DEPLOYMENT.md) for full setup

---

## Capabilities

| Capability | Description | Backend Service |
|------------|-------------|-----------------|
| Login / DFE | CUIT + Clave Fiscal, DFE | `arca_scraper.py` |
| Notifications | DFE communications, PDF attachments | `notifications_api.py` |
| Comprobantes | Mis Comprobantes (recibidos/emitidos) | `comprobantes_api.py` |
| Retenciones | Mis Retenciones — SICORE, IVA, Ganancias | `retenciones_api.py` |
| Reconciliación (retenciones) | Retenciones vs comprobantes recibidos | `reconciliacion_service.py` |
| **Reconciliación (emitidos)** | ARCA emitidos ↔ Colppy ventas — match by CAE | `reconciliacion_emitidos.py` |
| **Reconciliación (recibidos)** | ARCA recibidos ↔ Colppy compras — match by invoice number | `reconciliacion_recibidos.py` |
| **Discrepancy Acknowledgments** | Mark discrepancies as revisado/esperado/a_corregir/no_corregir | `arca_db.py` |
| **Smart Search** | LLM-powered natural-language search over reconciliation data | `reconciliation_search.py` |
| **Colppy API** | Health, empresas, clientes, proveedores, compras, ventas | `colppy_api.py` |
| Libro IVA | CSV → AFIP Libro IVA Digital format | `libro_iva_converter.py` |
| Banco Galicia | Statement extraction via API routes | `banco_galicia_scraper.py` |

---

## Reconciliación — Three Engines

### 1. Retenciones vs Comprobantes (original)
- **Endpoint:** `GET /api/arca/retenciones/reconcile?cuit=...&fecha_desde=...&fecha_hasta=...`
- **Logic:** `reconciliacion_service.reconcile_retenciones()` — cache-only, no ARCA calls
- **Output:** Periodos grouped by (agent_cuit, YYYY-MM) with match_status

### 2. Emitidos: ARCA ↔ Colppy Ventas
- **Endpoints:** `GET /api/arca/reconcile/emitidos` (JSON) and `/stream` (SSE)
- **Match key:** CAE (Código de Autorización Electrónica) — globally unique per invoice
- **Buckets:** matched, amount_mismatch, currency_mismatch, only_arca, only_colppy, duplicate_cae, missing_cae
- Auto-fetches ARCA data if missing from cache

### 3. Recibidos: ARCA ↔ Colppy Compras
- **Endpoint:** `GET /api/arca/reconcile/recibidos/stream` (SSE)
- **Match key:** Invoice number (PPPPP-NNNNNNNN format)
- **Extra layers:** percepciones comparison, retenciones overlay by supplier CUIT, duplicate invoice detection
- Resolves Colppy `idProveedor → CUIT` via proveedores list

### Discrepancy Acknowledgments
- `GET/POST/DELETE /api/arca/reconcile/acknowledgments`
- Categories: `revisado`, `esperado`, `a_corregir`, `no_corregir`
- Persistent in SQLite — survives re-runs

### Smart Search
- `POST /api/arca/reconcile/search` (SSE)
- Natural-language questions about reconciliation data (LLM-powered)

---

## Banco Galicia

- **API routes:** `GET /api/arca/banco/transactions`, `POST /api/arca/banco/refresh`, `DELETE /api/arca/banco/transactions`
- **Service:** `arca-prototype/backend/services/banco_galicia_scraper.py`
- **Env vars:** `GALICIA_DNI`, `GALICIA_USER`, `GALICIA_PASS`, `GALICIA_HEADLESS`, `GALICIA_TIMEOUT_MS`
- **Note:** Uses `type()` with delay (not `fill()`) for React-compatible input handling

---

## Colppy API

- **Router:** `backend/routers/colppy.py` (prefix: `/api/colppy`)
- **Endpoints:** `GET /health`, `/empresas`, `/clientes`, `/proveedores`, `/comprobantes/compra`, `/comprobantes/venta`
- **Auth pattern:** Login → get `claveSesion` → call operation → logout (per request)
- **Env vars:** `COLPPY_USER`, `COLPPY_PASSWORD`, `COLPPY_ID_EMPRESA`

---

## Data Flow Pattern

- **GET** — Read from SQLite cache (no ARCA call)
- **POST** — Fetch from ARCA → Save to SQLite → Return JSON
- **Reconciliation GET** — Hybrid: ARCA from cache, Colppy live from API

## Stale Data Cleanup (No Outdated Data)

All refresh operations replace cached data to avoid discrepancies:

| Operation | Cleanup behavior |
|-----------|------------------|
| Banco Galicia refresh | `DELETE FROM banco_transactions WHERE account = ?` before insert |
| arca_notifications | Delete by CUIT before re-fetch |
| arca_representados | Delete by cuit_usuario before re-fetch |
| arca_comprobantes / retenciones | Delete by cuit_representado before re-fetch |

---

## Configuration (.env)

| Variable | Purpose |
|----------|---------|
| `ARCA_CUIT` | Default CUIT |
| `ARCA_PASSWORD` | Clave Fiscal |
| `ARCA_HEADLESS` | Playwright headless mode |
| `ARCA_DB_PATH` | SQLite DB path (default: `data/arca_notifications.db`) |
| `COLPPY_USER` | Colppy API username |
| `COLPPY_PASSWORD` | Colppy API password |
| `COLPPY_ID_EMPRESA` | Default Colppy company ID |
| `GALICIA_DNI`, `GALICIA_USER`, `GALICIA_PASS` | Banco Galicia credentials |

---

## Related Plans

- [POST_CUIT_ENRICHMENT_PIPELINE.md](../../docs/plans/POST_CUIT_ENRICHMENT_PIPELINE.md) — pipeline that may use Banco Galicia data
