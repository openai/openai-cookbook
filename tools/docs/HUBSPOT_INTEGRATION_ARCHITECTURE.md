# HubSpot Integration Architecture

**Last Updated:** 2026-02-20  
**Purpose:** Analysis of the three components that interact with HubSpot: svc_integracion_crm, colppy-app, colppy-crmintegration-connector

---

## TL;DR

| Component | Role | HubSpot Interaction |
|-----------|------|---------------------|
| **svc_integracion_crm** | API gateway | Direct HTTP to `api.hubapi.com` with `HUBSPOT_PRIVATE_TOKEN` |
| **colppy-crmintegration-connector** | PHP HTTP client | Calls svc_integracion_crm (not HubSpot directly) |
| **colppy-app** | Business logic | Uses connector to sync companies, contacts, deals, associations to HubSpot |

**Flow:** colppy-app → colppy-crmintegration-connector → svc_integracion_crm → HubSpot API

---

## 1. svc_integracion_crm

### 1.1 Overview

Laravel 8 API that acts as a **proxy/gateway** between Colppy systems and HubSpot. It receives REST requests, transforms payloads, and forwards them to HubSpot's API.

### 1.2 Configuration

| Config | Value |
|--------|-------|
| `config/crm.php` → `api_url` | `https://api.hubapi.com` |
| Auth | `HUBSPOT_PRIVATE_TOKEN` (env) |
| Route prefix | `/api` |

### 1.3 API Routes (Laravel apiResources + custom)

| Route | Controller | HubSpot API Called |
|-------|-------------|--------------------|
| `GET /api/accounts` | AccountsController | `GET /crm/v3/objects/companies` |
| `POST /api/accounts` | AccountsController | `POST /crm/v3/objects/companies` |
| `GET /api/accounts/{id}` | AccountsController | `GET /crm/v3/objects/companies/{id}` |
| `PUT /api/accounts/{id}` | AccountsController | `PATCH /crm/v3/objects/companies/{id}` |
| `DELETE /api/accounts/{id}` | AccountsController | `DELETE /crm/v3/objects/companies/{id}` |
| `POST /api/accounts/search` | AccountsController | `POST /crm/v3/objects/companies/search` |
| `GET /api/contacts` | ContactsController | `GET /crm/v3/objects/contacts` |
| `POST /api/contacts` | ContactsController | `POST /crm/v3/objects/contacts` |
| ... | ... | ... |
| `POST /api/deals` | DealsController | `POST /crm/v3/objects/deals` |
| `PUT /api/deals/{id}` | DealsController | `PATCH /crm/v3/objects/deals/{id}` |
| `POST /api/deals/search` | DealsController | `POST /crm/v3/objects/deals/search` |
| `POST /api/contacts-deal` | ContactsDealController | `PUT /crm/v3/objects/deals/{id}/associations/contact/{id}/contact_to_deal` |
| `POST /api/accounts-deal` | AccountsDealController | `PUT /crm/v3/objects/deals/{id}/associations/company/{id}/company_to_deal` |
| `POST /api/deals/{id}/won` | DealWonController | Multiple: companies, subscriptions, events, deals |
| `POST /api/webhooks/deal-won` | DealWonController | Same as above (webhook entry) |

### 1.4 Payload Transformation

`Helper::transformPayload($model, $payload)` maps Colppy field names to HubSpot property names using `config/crm.php` → `parameters`:

- **companies** → `razon_social`, `cuit`, `colppy_id`, `estado`, etc.
- **contacts** → `firstname`, `email`, `hs_persona`, `colppy_usuario_id`, etc.
- **deals** → `dealname`, `dealstage`, `id_empresa`, `closedate`, `mrr`, etc.
- **contacts_deal** / **companies_deal** → `deal_id`, `contact_id`, `account_id`, association types

Special handling: `fecha_ultimo_login` (timestamp), `hs_persona` (buyer persona mapping), `provincia` (Argentine province names).

### 1.5 Deal Search Parameter Mapping

DealsController::search expects `campo` and `valor` in the request. It builds HubSpot filter:
```php
"propertyName" => $request['campo'],  // e.g. "id_empresa"
"value" => $request['valor'],
"operator" => "EQ"
```

### 1.6 DealWonProcess Service

When `POST /api/deals/{id}/won` or webhook is called:
1. Update company status to "active"
2. Create subscription record (custom object)
3. Create "Deal Won" event (custom object)
4. Update deal payment info (closedate, forma_de_pago, etc.)
5. Set close date if missing

**Note:** DealWonProcess uses HubSpot API directly; some steps may reference custom objects that need to exist in HubSpot.

---

## 2. colppy-crmintegration-connector

### 2.1 Overview

PHP library (extends `colppy/base-connector`) that provides a typed client for svc_integracion_crm. It does **not** call HubSpot directly.

### 2.2 Architecture

- **Base:** `Colppy\Connector\Contracts\Connector` (from colppy-base-connector)
- **Execute:** `$this->execute($method, $url, $param, $body)` → Guzzle HTTP request to `base_uri + $url`
- **Base URL:** Passed as constructor arg: `new Deals(null, INTEGRACIONCRM_BASE_URL)` → `INTEGRACIONCRM_BASE_URL` = svc_integracion_crm base (e.g. `https://integracioncrm.colppy.com/api`)

### 2.3 Services & Endpoints

| Service Class | Endpoints Called |
|---------------|------------------|
| **Accounts** | GET/POST/PUT/DELETE `accounts`, POST `accounts/search` |
| **Contacts** | GET/POST/PUT/DELETE `contacts`, POST `contacts/search` |
| **Deals** | GET/POST/PUT/DELETE `deals`, POST `deals/search`, PUT `deals/update-deal-stages/{id}` |
| **AccountsDeal** | GET/POST/PUT/DELETE `accounts-deal` |
| **ContactsDeal** | GET/POST/PUT/DELETE `contacts-deal` |
| **ContactsAccount** | GET/POST/PUT/DELETE `contacts-account` |
| **Events** | GET/POST/PUT/DELETE `events` |
| **Subscriptions** | GET/POST/PUT/DELETE `subscriptions` |
| **Discounts** | GET/POST/PUT/DELETE `discounts` |
| **Plans** | GET/POST/PUT/DELETE `plans` |
| **Deactivations** | GET/POST/PUT/DELETE `deactivations` |

### 2.4 Known Gap

`Deals::updateDealStage($dealId)` calls `PUT deals/update-deal-stages/{id}`. **This route does not exist** in svc_integracion_crm's current `routes/api.php`. Either it was removed, or it's implemented elsewhere.

---

## 3. colppy-app

### 3.1 Overview

Main Colppy application (PHP/Laravel). Uses `colppy-crmintegration-connector` with `INTEGRACIONCRM_BASE_URL` to sync data to HubSpot via svc_integracion_crm.

### 3.2 CRM Integration Entry Points

| Entry Point | File | CRM Actions |
|-------------|------|-------------|
| **Paypertic webhook** | `webhooks/paypertic_payments.php` | When payment approved + first payment: create/update deal, associate contact & account, update deal (closedate, mrr, etc.), call updateDealStage. Then forwards to colppy-benjamin. |
| **Payment reception (card)** | `recepcion_op_pago.php` | When payment approved: similar deal create/update, associations |
| **Company/contact provisioning** | `resources/php/common/functionsCRM.php` | create_account, update_account, create_contact, create_deal, create_account_deal, create_contact_deal, etc. |
| **Company registry** | `resources/php/common/funciones.php` | Calls `BENJAMIN_URL/api/v1/company/registry` (colppy-benjamin; Salesforce dispatch removed) |
| **User/company signup** | `AltaDelegate.php` (Empresa, Usuario) | create_account, create_account_deal |
| **Admin sync** | `lib/scripts/admin/syncBDCrm.php` | create_account |

### 3.3 Paypertic → HubSpot Flow (colppy-app)

**Important:** Paypertic can hit **two** webhooks:
1. **colppy-app** `webhooks/paypertic_payments.php` (legacy/primary?) – does full CRM sync
2. **colppy-benjamin** `POST /api/v1/webhooks/paypertic/payments` – only PayperticPayment job (no CRM)

colppy-app's `paypertic_payments.php`:
- Receives webhook, validates token
- When `status == 'approved'` and `primerPago == 1`:
  - Creates or finds deal by `id_empresa`
  - Associates contact to deal (ContactsDeal)
  - Associates company to deal (AccountsDeal)
  - Updates deal: `dealstage`, `closedate`, `mrr`, `forma_de_pago`, etc.
  - Calls `updateDealStage($crm_deal_id)` (route may not exist)
- Forwards payload to colppy-benjamin: `POST BENJAMIN_URL/api/v1/webhooks/paypertic/payments`

### 3.4 crm_match Table

colppy-app uses a `crm_match` table to store Colppy ID ↔ HubSpot ID mappings:
- `colppy_id` (Colppy), `crm_id` (HubSpot), `table_name` (empresa, usuario, negocio, usuario_negocio, empresa_negocio)

### 3.5 Environment Variables

- `INTEGRACIONCRM_BASE_URL` – svc_integracion_crm base URL (e.g. `https://integracioncrm.colppy.com/api`)
- `BENJAMIN_URL` – colppy-benjamin URL (for webhook forwarding)

---

## 4. Data Flow Summary

```
┌─────────────────┐     ┌──────────────────────────────┐     ┌─────────────────┐     ┌──────────────┐
│  colppy-app     │────▶│  colppy-crmintegration-      │────▶│ svc_integracion │────▶│  HubSpot     │
│  (business      │     │  connector (HTTP client)     │     │  _crm (Laravel  │     │  api.        │
│   logic)        │     │  INTEGRACIONCRM_BASE_URL     │     │   API gateway)  │     │  hubapi.com  │
└─────────────────┘     └──────────────────────────────┘     └─────────────────┘     └──────────────┘
        │                                    │                           │
        │                                    │                           │
        │  - Paypertic webhook               │  - GET/POST/PUT/DELETE    │  - HUBSPOT_PRIVATE_TOKEN
        │  - recepcion_op_pago               │  - accounts, deals,      │  - transformPayload()
        │  - functionsCRM.php               │    contacts, associations │  - Direct Http::withToken()
        │  - AltaDelegate                    │                           │
```

---

## 5. Recommendations

1. **Clarify Paypertic webhook routing:** Confirm whether Paypertic sends to colppy-app, colppy-benjamin, or both. colppy-app does the CRM sync; colppy-benjamin only updates payment status.
2. **Fix or remove updateDealStage:** The connector calls `PUT deals/update-deal-stages/{id}` but the route is missing in svc_integracion_crm. Implement the route or remove the call.
3. **Document INTEGRACIONCRM_BASE_URL:** Ensure it's set correctly in colppy-app env (e.g. `https://<svc-host>/api`).
4. **Contacts getContact bug:** `Contacts::getContact($contactId)` incorrectly calls `GET accounts/` + contactId instead of `GET contacts/` + contactId.
