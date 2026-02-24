# Colppy MySQL Database Schema

**Purpose:** Documents the Colppy staging/production MySQL schema and its mapping to HubSpot and local tools.

**Database:** `colppy` on `colppydb-staging.colppy.com` (staging)  
**Last Updated:** 2026-02-19

---

## 1. Overview

The Colppy MySQL database contains billing, company, user, and plan data. Key tables used for HubSpot integration and MRR analysis:

| Table | Rows (staging) | Purpose |
|-------|----------------|---------|
| `empresa` | ~68k | Companies (id_empresa = IdEmpresa) |
| `facturacion` | ~28k | Billing records |
| `usuario` | ~82k | Users |
| `usuario_empresa` | — | User–company associations |
| `empresasHubspot` | ~10k | Empresas synced to HubSpot |
| `crm_match` | ~268k | Colppy ID ↔ HubSpot CRM ID mapping |
| `plan` | ~635 | Subscription plans |

---

## 2. Key Tables

### 2.1 empresa (Companies)

| Column | Type | Description |
|--------|------|-------------|
| IdEmpresa | int | Primary key. Maps to HubSpot `id_empresa` on deals. |
| Nombre | varchar | Company name |
| razonSocial | varchar | Legal name |
| CUIT | varchar | Argentine tax ID (11 digits) |
| idCondicionIva | int | IVA condition |
| idPlan | int | FK to plan |
| activa | int | 0=active, 2=deactivated (payment failure), 3=deactivated (user) |
| FechaAlta | datetime | Registration date |
| email | varchar | Contact email |

**HubSpot link:** `IdEmpresa` = `id_empresa` on HubSpot deals.

---

### 2.2 facturacion (Colppy facturacion)

**Colppy's internal billing/facturacion table** — NOT the billing system (facturacion.csv). See [DATA_SOURCES_TERMINOLOGY.md](./DATA_SOURCES_TERMINOLOGY.md).

| Column | Type | Description |
|--------|------|-------------|
| idFacturacion | int | Primary key |
| IdEmpresa | int | FK to empresa |
| razonSocial | varchar | Billing name |
| CUIT | varchar | Customer CUIT |
| fechaAlta | date | Start date |
| fechaBaja | date | End date (NULL = active) |

**Note:** The billing system exports `facturacion.csv` (separate from Colppy). `build_facturacion_hubspot_mapping.py` loads that billing CSV into `facturacion_hubspot.db`. Column names may differ between billing CSV and Colppy facturacion.

---

### 2.3 usuario (Users)

| Column | Type | Description |
|--------|------|-------------|
| id | int | Primary key |
| idUsuario | varchar | User identifier |
| nombreUsuario | varchar | Email / username |
| idUltimaEmpresa | int | Last-used empresa |
| idRol | int | Role |
| fechaRegistro | datetime | Registration date |

---

### 2.4 usuario_empresa (User–Company)

| Column | Type | Description |
|--------|------|-------------|
| idUsuarioEmpresa | int | Primary key |
| idUsuario | int | FK to usuario |
| company_id | int | FK to empresa |
| esAdministrador | bool | Is admin |
| esContador | bool | Is accountant |

---

### 2.5 empresasHubspot

| Column | Type | Description |
|--------|------|-------------|
| idEmpresa | int | Empresa ID synced to HubSpot |

---

### 2.6 crm_match (Colppy ↔ HubSpot)

| Column | Type | Description |
|--------|------|-------------|
| id | int | Primary key |
| crm_id | varchar | HubSpot object ID |
| colppy_id | varchar | Colppy ID |
| table_name | varchar | Source table (e.g. empresa, usuario) |

---

### 2.7 plan

| Column | Type | Description |
|--------|------|-------------|
| idPlan | int | Primary key |
| nombre | varchar | Plan name |
| precio | decimal | Price |
| meses | int | Billing period |
| topeFacturas | int | Invoice limit |

---

## 3. Python Models

Use `tools/database/models.py`:

```python
from database import Empresa, Facturacion, Usuario, Plan, CrmMatch, get_db

# By ID
empresa = Empresa.find_by_id(12345)
plan = Plan.find_by_id(1)

# By CUIT
empresa = Empresa.find_by_cuit("20123456789")

# Active empresas
empresas = Empresa.find_activas(limit=100)

# Facturacion by id_empresa
rows = Facturacion.find_by_id_empresa("12345")

# CRM match (Colppy → HubSpot)
matches = CrmMatch.find_by_colppy_id("12345", table_name="empresa")
```

---

## 4. Relationship to facturacion_hubspot.db

| Colppy MySQL | facturacion_hubspot.db (SQLite) |
|--------------|----------------------------------|
| `empresa` | Not direct. Companies come from HubSpot API by CUIT. |
| `facturacion` | `facturacion` table, populated from `facturacion.csv` export. |
| `IdEmpresa` | `id_empresa` in deals, facturacion. |
| `CUIT` | `customer_cuit`, `cuit` in companies. |

The local SQLite DB is built from `facturacion.csv` (billing export) + HubSpot API, not from direct MySQL queries. For live MySQL data, use the `database` package and `Empresa`, `Facturacion`, etc.

---

## 5. Full Table List (219 tables)

See `tools/setup_database.py` or run:

```python
from database import get_db
db = get_db()
tables = db.list_tables()
```

Key prefixes: `ar_` (sales), `ap_` (purchases), `gl_` (general ledger), `te_` (treasury), `st_` (inventory), `em_` (company config).
