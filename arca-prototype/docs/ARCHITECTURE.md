# ARCA Prototype — Architecture & File Structure

## High-Level Flow

```
┌─────────────┐     HTTP      ┌─────────────┐     Playwright / REST     ┌─────────────┐
│   Frontend  │ ────────────► │   Backend   │ ───────────────────────► │  AFIP/ARCA  │
│  (React)   │                │  (FastAPI)  │                          │   Portals   │
└─────────────┘                └──────┬──────┘                          └─────────────┘
                                       │
                                       ▼
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
| **Reconciliación** | Cross-reference retenciones vs comprobantes recibidos | ReconciliacionPage |
| **Libro IVA** | Convert CSV or Mis Comprobantes → AFIP Libro IVA Digital format | LibroIVAPage |
| **Banco Galicia** | Savings account statement extraction (service only, no API route yet) | — |

---

## Directory Structure

```
arca-prototype/
├── backend/
│   ├── main.py                 # App entry, CORS, router registration
│   ├── routers/
│   │   └── arca.py             # All ARCA routes
│   └── services/
│       ├── arca_scraper.py     # Low-level Playwright: login, DFE navigation
│       ├── notifications_api.py   # DFE notifications via internal REST API
│       ├── comprobantes_api.py    # Mis Comprobantes (recibidos/emitidos)
│       ├── retenciones_api.py    # Mis Retenciones (Mirequa SPA)
│       ├── reconciliacion_service.py  # Retenciones vs comprobantes logic
│       ├── libro_iva_converter.py # CSV → AFIP Libro IVA Digital format
│       ├── banco_galicia_scraper.py # Banco Galicia statement extraction
│       ├── attachment_download.py # PDF download via DFE REST API
│       ├── veconsumerws_client.py # SOAP consumirComunicacion (optional, WSAA)
│       ├── wsaa_client.py      # WSAA token/sign for AFIP SOAP (optional)
│       └── arca_db.py          # SQLite persistence
├── frontend/
│   └── src/
│       ├── App.jsx
│       └── components/
│           ├── LoginForm.jsx
│           ├── NotificationsPage.jsx
│           ├── ComprobantesPage.jsx
│           ├── RetencionesPage.jsx
│           ├── ReconciliacionPage.jsx
│           └── LibroIVAPage.jsx
├── scripts/
├── data/
├── certs/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── LIBRO_IVA_FORMAT.md
│   └── WSAA_CERTIFICATE_SETUP.md
├── .env
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

### Reconciliación (retenciones vs comprobantes)

```
GET /api/arca/retenciones/reconcile?cuit=...&fecha_desde=...&fecha_hasta=...
    → arca_db.get_retenciones() + arca_db.get_comprobantes()
    → reconciliacion_service.reconcile_retenciones()
    → Returns periodos grouped by (agent_cuit, YYYY-MM) with match_status
```

Cache-only — no ARCA calls. Fast.

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

### Banco Galicia (service only)

`banco_galicia_scraper.py` provides:
- `login_test()` — verify credentials
- `get_savings_account_statements(account_fragment, export_csv)` — extract transactions

Uses Playwright with React-compatible input handling. Env: `GALICIA_DNI`, `GALICIA_USER`, `GALICIA_PASS`. Not yet exposed via API routes; used by scripts or Post-CUIT Enrichment pipeline (see `docs/plans/POST_CUIT_ENRICHMENT_PIPELINE.md`).

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
| `GALICIA_DNI` | Banco Galicia DNI (for banco_galicia_scraper) |
| `GALICIA_USER` | Banco Galicia username |
| `GALICIA_PASS` | Banco Galicia password |
| `GALICIA_HEADLESS` | "true"/"false" (default: "true") |
| `GALICIA_TIMEOUT_MS` | Timeout in ms (default: 30000) |
