# ARCA Prototype — Architecture & File Structure

## High-Level Flow

```
┌─────────────┐     HTTP      ┌─────────────┐     Playwright / REST     ┌─────────────┐
│   Frontend  │ ────────────► │   Backend   │ ───────────────────────► │  AFIP/ARCA  │
│  (React)   │                │  (FastAPI)  │                          │   Portals   │
└─────────────┘                └──────┬──────┘                          └─────────────┘
                                       │          httpx
                                       ├─────────────────────────────► ┌─────────────┐
                                       │                               │ Colppy API  │
                                       ▼                               └─────────────┘
                                ┌─────────────┐
                                │   SQLite    │
                                │  (cache)    │
                                └─────────────┘
```

---

## Capabilities Overview

| Capability | Description | Frontend Page |
|------------|-------------|---------------|
| **Login / DFE** | CUIT + Clave Fiscal login, Domicilio Fiscal Electrónico | Login |
| **Notifications** | DFE communications, PDF attachments | NotificationsPage |
| **Comprobantes** | Mis Comprobantes (recibidos + emitidos) | ComprobantesPage |
| **Retenciones** | Mis Retenciones — Exportar para Aplicativo (SICORE, IVA, Ganancias) | RetencionesPage |
| **Reconciliación (retenciones)** | Cross-reference retenciones vs comprobantes recibidos | ReconciliacionPage |
| **Reconciliación (emitidos)** | ARCA comprobantes emitidos ↔ Colppy facturas de venta (by CAE) | ReconciliacionPage |
| **Reconciliación (recibidos)** | ARCA comprobantes recibidos ↔ Colppy facturas de compra (by invoice number) | ReconciliacionPage |
| **Discrepancy Acknowledgments** | Mark discrepancies as revisado/esperado/a_corregir/no_corregir | ReconciliacionPage |
| **Smart Search** | LLM-powered natural-language search over reconciliation data | ReconciliacionPage |
| **Colppy API** | Health, empresas, clientes, proveedores, compras, ventas | — (API only) |
| **Libro IVA** | Convert CSV or Mis Comprobantes → AFIP Libro IVA Digital format | LibroIVAPage |
| **Banco Galicia** | Savings account statement extraction | BancoGaliciaPage |

---

## Directory Structure

```
arca-prototype/
├── backend/
│   ├── main.py                 # App entry, CORS, router registration
│   ├── routers/
│   │   ├── arca.py             # All ARCA routes (~40 endpoints)
│   │   └── colppy.py           # Colppy API routes (health, empresas, clientes, etc.)
│   └── services/
│       ├── arca_scraper.py     # Low-level Playwright: login, DFE navigation
│       ├── notifications_api.py   # DFE notifications via internal REST API
│       ├── comprobantes_api.py    # Mis Comprobantes (recibidos/emitidos)
│       ├── retenciones_api.py    # Mis Retenciones (Mirequa SPA)
│       ├── reconciliacion_service.py  # Retenciones vs comprobantes logic
│       ├── reconciliacion_emitidos.py # ARCA emitidos ↔ Colppy ventas (by CAE)
│       ├── reconciliacion_recibidos.py # ARCA recibidos ↔ Colppy compras (by invoice number)
│       ├── reconciliation_search.py   # LLM-powered natural-language search
│       ├── colppy_api.py       # Colppy REST API client (login, empresas, clientes, comprobantes)
│       ├── libro_iva_converter.py # CSV → AFIP Libro IVA Digital format
│       ├── banco_galicia_scraper.py # Banco Galicia statement extraction
│       ├── attachment_download.py # PDF download via DFE REST API
│       ├── veconsumerws_client.py # SOAP consumirComunicacion (optional, WSAA)
│       ├── wsaa_client.py      # WSAA token/sign for AFIP SOAP (optional)
│       └── arca_db.py          # SQLite persistence (incl. acknowledgments table)
├── frontend/
│   └── src/
│       ├── App.jsx             # Main app shell + BackendStatus indicator
│       ├── apiConfig.js        # Runtime backend URL config (avoids circular imports)
│       └── components/
│           ├── LoginForm.jsx
│           ├── NotificationsPage.jsx
│           ├── ComprobantesPage.jsx
│           ├── RetencionesPage.jsx
│           ├── ReconciliacionPage.jsx   # Emitidos + Recibidos + Acknowledgments + Smart Search
│           ├── BancoGaliciaPage.jsx
│           └── LibroIVAPage.jsx
├── scripts/
├── data/                       # Runtime data (gitignored)
├── certs/                      # WSAA certs (private keys gitignored)
├── docs/
│   ├── ARCHITECTURE.md
│   ├── DEPLOYMENT.md           # GitHub Pages + Cloudflare Tunnel setup
│   ├── LIBRO_IVA_FORMAT.md
│   └── WSAA_CERTIFICATE_SETUP.md
├── .env                        # Credentials (gitignored)
└── api.http
```

---

## PDF Attachment Download

The PDF download uses the **DFE internal REST API** — no UI automation or WSAA certificates required.

### Flow

1. **Login** — Playwright logs in with CUIT + Clave Fiscal at auth.afip.gob.ar
2. **DFE auth** — Navigate to DFE to capture token/sign from the autorización endpoint
3. **Open DFE app** — Load ve.cloud.afip.gob.ar with token to establish session cookies
4. **Discover metadata** — `GET /api/v1/communications/{notification_id}` to get `adjuntos` (idArchivo, filename)
5. **Download PDF** — `GET /api/v1/communications/{notification_id}/{idArchivo}` returns the PDF binary
6. **Save** — Write to `data/attachments/` and SQLite cache

### API Usage

**POST** — Download and cache:

```http
POST /api/arca/attachments/download
Content-Type: application/json

{
  "cuit": "20268448536",
  "password": "YOUR_CLAVE_FISCAL",
  "notification_id": 582958952,
  "id_archivo": 0,
  "filename": ""
}
```

- `id_archivo`: Optional. Pass `0` (or omit) to auto-discover from notification detail. Or pass the known ID.
- `filename`: Optional. Auto-discovered from API if empty.

**GET** — Retrieve from cache:

```http
GET /api/arca/notificaciones/582958952/pdf?cuit=20268448536
```

### Prerequisites

- Notification must exist in cache (run `POST /api/arca/notificaciones-contenido` first)
- Valid Clave Fiscal credentials

### Optional: veconsumerws (WSAA)

For environments where the REST API is not available, the codebase includes `veconsumerws_client` and `wsaa_client` for SOAP-based PDF retrieval. See `docs/WSAA_CERTIFICATE_SETUP.md`. The current implementation uses the REST API as the primary method.

---

## Other Request Flows

### Notifications (DFE)

```
POST /api/arca/notificaciones-contenido
    → notifications_api.get_notifications_with_content()
        → Login → DFE → fetch /api/v1/communications
        → arca_db.save_notifications()
```

### Comprobantes Recibidos / Emitidos

```
POST /api/arca/comprobantes-recibidos
    → comprobantes_api.get_comprobantes_recibidos()
        → Login → Mis Comprobantes → AJAX generarConsulta → listaResultados
        → arca_db.save_comprobantes(direccion="R")

POST /api/arca/comprobantes-emitidos
    → comprobantes_api.get_comprobantes_emitidos()
        → arca_db.save_comprobantes(direccion="E")
```

### Mis Retenciones (Mirequa)

```
POST /api/arca/retenciones/download
    → retenciones_api.download_retenciones()
        → Login → Search "Mis Retenciones" → Mirequa (Vue SPA)
        → Check "Exportar para aplicativos SIAP"
        → Select impuesto (767=SICORE, 216=IVA, 217=Ganancias)
        → Select tipo (retencion/percepcion) → Consultar
        → Intercept JSON API response → Save CSV + arca_db.save_retenciones()
```

### Reconciliación: Retenciones vs Comprobantes

```
GET /api/arca/retenciones/reconcile?cuit=...&fecha_desde=...&fecha_hasta=...
    → arca_db.get_retenciones() + arca_db.get_comprobantes()
    → reconciliacion_service.reconcile_retenciones()
    → Returns periodos grouped by (agent_cuit, YYYY-MM) with match_status
```

Cache-only — no ARCA calls. Fast.

### Reconciliación: Emitidos (ARCA ↔ Colppy Ventas)

```
GET /api/arca/reconcile/emitidos?cuit=...&fecha_desde=...&fecha_hasta=...
    → reconciliacion_emitidos.reconcile_emitidos()
        → ARCA: arca_db.get_comprobantes(direccion="E") (from SQLite cache)
        → Colppy: colppy_api.list_comprobantes_venta() (live API call)
        → Match by CAE (Código de Autorización Electrónica)
        → Buckets: matched, amount_mismatch, currency_mismatch, only_arca, only_colppy,
                   duplicate_cae, missing_cae

GET /api/arca/reconcile/emitidos/stream  (SSE, same params)
    → Real-time progress events via Server-Sent Events
```

If ARCA data is missing for the requested date range, the service auto-fetches from ARCA using Playwright before reconciling.

### Reconciliación: Recibidos (ARCA ↔ Colppy Compras)

```
GET /api/arca/reconcile/recibidos/stream?cuit=...&fecha_desde=...&fecha_hasta=...  (SSE)
    → reconciliacion_recibidos.reconcile_recibidos_stream()
        → ARCA: comprobantes recibidos (auto-fetch if missing)
        → Colppy: colppy_api.list_comprobantes_compra() (live API)
        → Match by invoice number (PPPPP-NNNNNNNN format)
        → Additional layers:
          - Percepciones: ARCA otros_tributos vs Colppy percepcionIVA+IIBB
          - Retenciones overlay: linked ARCA retenciones by supplier CUIT + period
          - Duplicate invoice detection with source attribution
```

Colppy purchase invoices lack CAE/CUIT — the service resolves `idProveedor → CUIT` via the proveedores list.

### Discrepancy Acknowledgments

```
GET  /api/arca/reconcile/acknowledgments?status=...
POST /api/arca/reconcile/acknowledgments
     body: { discrepancy_key, status, category, reason, acknowledged_by, context_json }
DELETE /api/arca/reconcile/acknowledgments/{discrepancy_key}
```

Categories: `revisado` (reviewed), `esperado` (expected), `a_corregir` (needs fix), `no_corregir` (accepted).
Stored in `reconciliation_acknowledgments` table in the same SQLite DB.

### Smart Search (LLM-powered)

```
POST /api/arca/reconcile/search  (SSE)
     body: { query, cuit, fecha_desde, fecha_hasta, scope, conversation, discrepancies, matched_pairs }
     → reconciliation_search.search_invoices_stream()
     → Natural-language questions about reconciliation data
```

### Libro IVA Digital

```
GET /api/arca/libro-iva/generate?cuit=...&fecha_desde=...&fecha_hasta=...&tipo=ventas|compras
    → arca_db.get_comprobantes() → libro_iva_converter.comprobantes_to_libro_iva()
    → build_libro_iva_zip() → Returns ZIP for AFIP import

POST /api/arca/libro-iva/convert (multipart: file, tipo)
    → csv_to_libro_iva_ventas_full() or csv_to_libro_iva_compras_full()
    → build_libro_iva_zip() → Returns ZIP
```

See `docs/LIBRO_IVA_FORMAT.md` for AFIP fixed-position format.

### Banco Galicia

```
GET  /api/arca/banco/transactions?account=...
POST /api/arca/banco/refresh
     body: { account_fragment, export_csv }
     → banco_galicia_scraper.get_savings_account_statements()
     → Playwright login → extract transactions from DOM → save to SQLite
DELETE /api/arca/banco/transactions?account=...
```

Uses Playwright with React-compatible input handling (`type()` with delay instead of `fill()`).
Env: `GALICIA_DNI`, `GALICIA_USER`, `GALICIA_PASS`, `GALICIA_HEADLESS`, `GALICIA_TIMEOUT_MS`.

### Colppy API

All Colppy endpoints follow login → call → logout per request (short-lived sessions).

```
GET /api/colppy/health         → Test connectivity (login + list_empresas)
GET /api/colppy/empresas       → List accessible companies
GET /api/colppy/clientes       → List clients for a company (?id_empresa=...)
GET /api/colppy/proveedores    → List suppliers for a company
GET /api/colppy/comprobantes/compra  → Purchase invoices (?from_date=&to_date=)
GET /api/colppy/comprobantes/venta   → Sales invoices (?from_date=&to_date=)
```

Env: `COLPPY_USER`, `COLPPY_PASSWORD`, `COLPPY_ID_EMPRESA`.

---

## Data Flow Pattern

- **GET** — Read from SQLite cache (no ARCA call)
- **POST** — Fetch from ARCA → Save to SQLite → Return JSON

---

## Configuration (.env)

| Variable | Purpose |
|----------|---------|
| `ARCA_CUIT` | Default CUIT |
| `ARCA_PASSWORD` | Clave Fiscal |
| `ARCA_HEADLESS` | Playwright headless mode |
| `ARCA_TIMEOUT_MS` | Playwright timeout |
| `ARCA_DB_PATH` | (Optional) SQLite DB path; default: `data/arca_notifications.db` |
| `ARCA_CERT_PATH` | (Optional) WSAA cert for veconsumerws |
| `ARCA_KEY_PATH` | (Optional) Private key for veconsumerws |
| `COLPPY_USER` | Colppy API username |
| `COLPPY_PASSWORD` | Colppy API password |
| `COLPPY_ID_EMPRESA` | Default Colppy company ID |
| `GALICIA_DNI` | Banco Galicia DNI (for banco_galicia_scraper) |
| `GALICIA_USER` | Banco Galicia username |
| `GALICIA_PASS` | Banco Galicia password |
| `GALICIA_HEADLESS` | "true"/"false" (default: "true") |
| `GALICIA_TIMEOUT_MS` | Timeout in ms (default: 30000) |

---

## Deployment

### Frontend — GitHub Pages

The React frontend is built as static files and deployed to GitHub Pages:

- **Build output:** `docs/arca-app/` (Vite builds from `frontend/` into the repo's `docs/` directory)
- **GitHub Pages URL:** `https://<user>.github.io/openai-cookbook/arca-app/`
- **Vite config:** `base` is set to `/openai-cookbook/arca-app/` in production builds
- **Deployment:** GitHub Actions workflow (`.github/workflows/deploy-pages.yml`) triggers on changes to `docs/**`
- **Runtime backend URL:** Configurable via `localStorage.getItem("arca_backend_url")` — click the status dot in the header to change

### Backend — Local + Cloudflare Tunnel

The backend must run locally (Playwright requires a browser). To share with remote users:

1. Start backend: `cd arca-prototype && .venv/bin/uvicorn backend.main:app --reload --port 8000`
2. Start tunnel: `cloudflared tunnel --url http://localhost:8000`
3. Share the `*.trycloudflare.com` URL — users paste it into the backend URL field on the frontend

See `docs/DEPLOYMENT.md` for detailed setup instructions.
