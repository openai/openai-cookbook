# First Payment: Entry Points End-to-End

**Last Updated:** 2026-02-20  
**Purpose:** Step-by-step walkthrough of each entry point to a first payment, from user action to HubSpot sync

---

## Overview

There are **three main entry points** for a first payment:

| # | Method | Gateway / Source | Entry Point | Systems Involved |
|---|--------|------------------|-------------|------------------|
| 1 | **CBU (bank debit)** | Paypertic | colppy-benjamin API | benjamin → Paypertic → colppy-app → benjamin |
| 2 | **Card (credit/debit)** | Decidir / ePayco / other | recepcion_op_pago.php | colppy-app only |
| 3 | **Bank transfer** | Manual confirmation | MC_Pagar.php | colppy-app only |

---

## Entry Point 1: CBU (Bank Debit) via Paypertic

### Step 1: User initiates payment

- User is in Colppy app (trial ending or choosing plan)
- User enters CBU, CUIT, plan, etc.
- Frontend calls **colppy-benjamin**: `POST /api/v1/payment/`
- Request body: `idEmpresa`, `idUsuario`, `cbu`, `cuit`, `plan`, `importe`, `type: 'cbu'`, `nro_operacion`, etc.

### Step 2: colppy-benjamin processes (synchronous)

**PaymentController::pay()** → **PaymentService::createPayment()** → **processPayment()**:

1. **PaymentCBU::updatePayment()**
   - Loads `pago` by `nroOperacion`
   - Sets `pago.primerPago = 1` (setFirstPayment)
   - Updates `empresa`: `idPlan`, `activa`, `istrial`, `fechaVencimiento`, etc.
   - Sends `AutomaticDebitAdhesionNotification`
   - **Company is activated at this moment** (optimistic)

2. **PaymentCBU::generate()**
   - Builds Paypertic payload with `external_transaction_id`, `notification_url`, `details`, `payer`
   - `notification_url` = `PPT_NOTIFICATION_URL` + `/webhooks/paypertic_payments.php?token=...` (colppy-app)

3. **PaymentDetailService::create()**
   - Creates `payment_detail` with `external_transaction_id`, `is_first_payment`, `payment_status = pending`

4. **responsePaypertic()**
   - Sends payload to Paypertic API
   - Paypertic returns initial response

5. **PaymentDetailService::update()**
   - Updates `payment_detail` with Paypertic response (status, gateway_id)

### Step 3: Paypertic processes (async, 1–3+ days)

- Paypertic debits the bank account
- When done, Paypertic sends webhook to `PPT_NOTIFICATION_URL/webhooks/paypertic_payments.php`

### Step 4: colppy-app receives Paypertic webhook

**webhooks/paypertic_payments.php**:

1. Validates token (`$_GET['token']`)
2. If `status == 'approved'` and `primerPago == 1`:
   - Loads `pago` from DB (shared MySQL)
   - **HubSpot sync:**
     - Creates or finds deal by `id_empresa`
     - Associates contact → deal (ContactsDeal)
     - Associates company → deal (AccountsDeal)
     - Updates deal: `closedate`, `mrr`, `forma_de_pago`, `dealstage`, etc.
     - Calls `updateDealStage()` (route may be missing in svc_integracion_crm)
   - Stores mappings in `crm_match`
3. **Forwards to benjamin:** `POST BENJAMIN_URL/api/v1/webhooks/paypertic/payments` with payload

### Step 5: colppy-benjamin receives forwarded webhook

**PayperticController::payment()**:

1. Dispatches **PayperticPayment** job (async)
2. Returns `{success: true}`

**PayperticPayment job**:

1. Finds `payment_detail` by `external_transaction_id`
2. Updates `payment_detail`: `payment_status`, `payment_gateway_id`, `accreditation_date` (if approved)
3. If `status == 'rejected'`: calls `processPaymentRejection()` (reverts company to trial)
4. Creates `PaymentDetailStatus` record

---

### CBU: Subscription Status vs Money Collection

| Aspect | Timing |
|--------|--------|
| **Subscription status** | **Immediate** (optimistic) – at user submit |
| **Plan access** | Immediate – `empresa.idPlan`, `istrial=0`, `fechaVencimiento` set |
| **Money collection** | **3–7 days** (typical Paypertic delay) |
| **Rejection handling** | Reverts company to trial if Paypertic rejects |

At initiation, `PaymentCBU::updatePayment()` sets `pago.estado=1`, `empresa.istrial=0`, `empresa.idPlan`, etc. The company gets paid-plan access immediately. Paypertic debits the bank 3–7 days later. If rejected, `processPaymentRejection()` reverts.

---

### CBU: Collected vs Pending (How to Read the DB)

**We do not see our bank account in the DB.** Status comes from **Paypertic webhooks**.

| State | How to know | DB indicators |
|-------|-------------|---------------|
| **Collected** | Paypertic webhook said `status="approved"` | `payment_status = 4` (Accredited), `accreditation_date` set |
| **Pending** | Awaiting Paypertic approval | `payment_status IN (1, 2, 3)`, `accreditation_date IS NULL` |
| **Rejected** | Paypertic webhook said `status="rejected"` | `payment_status = 6` (Unpaybled) |

**payment_status values** (PaymentHelper):

| Value | Name | Meaning |
|-------|------|---------|
| 1 | Pending | Created, not yet sent / no webhook |
| 2 | Sent | Paypertic has it (pending, in_process, issued) |
| 3 | Retry | Retry in progress |
| 4 | Accredited | Paypertic approved – money collected |
| 5 | Error | Error |
| 6 | Unpaybled | Rejected |
| 7 | Cancelled | Cancelled |

**Queries:**

```sql
-- Collected (money in)
SELECT * FROM payment_detail pd
JOIN pago p ON p.idPago = pd.payment_id
WHERE pd.is_first_payment = 1 AND pd.payment_gateway = 1
  AND pd.payment_status = 4;

-- Pending (awaiting Paypertic)
SELECT * FROM payment_detail pd
JOIN pago p ON p.idPago = pd.payment_id
WHERE pd.is_first_payment = 1 AND pd.payment_gateway = 1
  AND pd.payment_status IN (1, 2, 3)
  AND pd.accreditation_date IS NULL;
```

---

## Entry Point 2: Card Payment (Credit/Debit)

### Step 1: User initiates payment

- User selects card as payment method
- User is redirected to card gateway (Decidir, etc.)
- User enters card details on gateway

### Step 2: Gateway processes

- Gateway charges the card
- Gateway callbacks to **colppy-app**: `recepcion_op_pago.php` with `noperacion`, `resultado` (APROBADA, RECHAZADA, etc.)

### Step 3: colppy-app processes (synchronous)

**recepcion_op_pago.php**:

1. Validates `resultado` (APROBADA, RECHAZADA, PENDIENTE, FALLIDA)
2. Updates `pago`: `estado`, `nroTarjeta`
3. If `estado == 1` (approved):
   - Loads company and payment data
   - **MC_primerPago.php** – if this is the first approved payment for the company, sets `pago.primerPago = 1`
   - Updates `empresa`: `idPlan`, `fechaVencimiento`, `activa = 0`, `istrial = 0`, etc.
   - **Mixpanel:** `Subscription Billed` event
   - If `primerPago == 1`:
     - **HubSpot sync** (same pattern as Paypertic flow):
       - Creates/finds deal by `id_empresa`
       - Associates contact → deal (ContactsDeal)
       - Associates company → deal (AccountsDeal)
       - Updates deal: `closedate`, `mrr`, `forma_de_pago`, `dealstage`, etc.
       - Calls `updateDealStage()`
4. No forward to colppy-benjamin – this flow does not use benjamin

---

## Entry Point 3: Bank Transfer (Manual Confirmation)

### Step 1: User confirms transfer

- User has made a bank transfer (manual, outside the app)
- User goes to Colppy app and submits transfer details: `fechaTransferencia`, `bancoEmisor`, `nroTransferencia`, plan, importe, etc.
- Frontend calls **colppy-app**: `MC_Pagar.php` with `fechaTransferencia` set

### Step 2: colppy-app processes (synchronous)

**MC_Pagar.php**:

1. **Deal creation (optimistic):**
   - If `!is_create_deal()`: creates or finds deal
   - Creates deal with `deal_stage = 'decisionmakerboughtin'`
   - Associates contact → deal (ContactsDeal)
   - Associates company → deal (AccountsDeal)
   - Stores mappings in `crm_match`
2. **Insert pago:** Inserts `pago` with `fechaTransferencia`, `estado`, etc.
3. **MC_primerPago.php:** If this is the first approved payment for the company, sets `pago.primerPago = 1`
4. Updates `empresa`: `idPlan`, `fechaVencimiento`, etc.
5. No gateway callback – payment is considered confirmed when user submits

### Step 3: No follow-up

- No Paypertic webhook
- No forward to benjamin
- Deal is created at confirmation time; no `updateDealStage` to closedwon (may be manual or later process)

---

## Comparison

| Aspect | CBU (Paypertic) | Card | Bank Transfer |
|--------|-----------------|------|---------------|
| **Initiation** | colppy-benjamin API | Card gateway redirect | User manual confirmation |
| **Company activation** | At initiation (optimistic) | At gateway callback | At confirmation |
| **HubSpot sync** | colppy-app (on webhook) | colppy-app (on callback) | colppy-app (at confirmation) |
| **payment_detail table** | Yes (benjamin) | No (legacy flow) | No |
| **Benjamin involved** | Yes (initiation + webhook) | No | No |
| **Timing** | Async (days) | Sync (seconds) | Sync (immediate) |
| **Deal stage at sync** | closedwon (updateDealStage) | closedwon (updateDealStage) | decisionmakerboughtin |

---

## Database Note

- **colppy-app** and **colppy-benjamin** appear to share the same MySQL for `pago`, `empresa`, `usuario`, etc.
- **payment_detail** is a colppy-benjamin table; it exists only for the CBU/Paypertic flow
- **crm_match** (Colppy ID ↔ HubSpot ID) is in colppy-app’s DB

---

## Flow Diagrams

### CBU (Paypertic)

```
User → [Submit CBU] → colppy-benjamin (company activated, Paypertic API)
                            ↓
                    Paypertic (async)
                            ↓
                    Webhook → colppy-app (HubSpot sync)
                            ↓
                    Forward → colppy-benjamin (PayperticPayment job)
```

### Card

```
User → [Card gateway] → Gateway charges
                            ↓
                    Callback → colppy-app recepcion_op_pago (company activated, HubSpot sync)
```

### Bank Transfer

```
User → [Manual confirmation in app] → colppy-app MC_Pagar (deal created, pago inserted, MC_primerPago)
```

---

---

## Data Model: Where to See First Payment in the DB

### Canonical source: `pago` table

**Database:** Colppy MySQL (shared by colppy-app and colppy-benjamin)

| Column | Type | Meaning |
|--------|------|---------|
| `idPago` | int | Primary key |
| `idEmpresa` | int | Company (FK to empresa.IdEmpresa) |
| `idPlan` | int | Product/plan paid (FK to plan.idPlan) |
| `idUsuario` | varchar | User who paid |
| `fechaPago` | date | Payment date |
| `estado` | int | 1=approved, 2=rejected, 3=pending, 4=fallida |
| `primerPago` | tinyint | **1 = first payment for this company** |
| `nroOperacion` | varchar | Operation ID (gateway reference) |
| `importe` | decimal | Amount |
| `medioPago` | varchar | Payment method (e.g. Visa Débito, CBU) |
| `tipoPago` | int | 1=debito, 2=mensual, 3=anual |
| `fechaTransferencia` | date | For bank transfer (manual confirmation) |

**Query for first payments:**

```sql
SELECT idPago, idEmpresa, idPlan, fechaPago, importe, medioPago, primerPago
FROM pago
WHERE primerPago = 1
  AND (estado = 1 OR (estado = 0 AND fechaTransferencia IS NOT NULL))
ORDER BY fechaPago;
```

- `primerPago = 1` → first payment for that `idEmpresa`
- `estado = 1` → approved (card, CBU when Paypertic confirms)
- `estado = 0 AND fechaTransferencia IS NOT NULL` → bank transfer (manual confirmation)

---

### Secondary source: `payment_detail` table (CBU only)

**Database:** Colppy MySQL (colppy-benjamin migrations)

| Column | Type | Meaning |
|--------|------|---------|
| `id` | int | Primary key |
| `payment_id` | int | FK to pago.idPago |
| `external_transaction_id` | varchar | Paypertic transaction ID |
| `is_first_payment` | tinyint | 1 = first payment (copied from pago.primerPago) |
| `payment_date` | datetime | Payment date |
| `accreditation_date` | datetime | When Paypertic accredited (CBU) |
| `payment_status` | smallint | 1=Pending, 4=Accredited, 5=Error, etc. |
| `total_amount` | double | Amount |
| `payment_gateway` | smallint | 1=Paypertic |

**Coverage:** Only CBU (Paypertic) payments. Card and bank transfer do **not** create `payment_detail` rows.

**Query for first CBU payments:**

```sql
SELECT pd.*, p.idEmpresa, p.idPlan, p.fechaPago
FROM payment_detail pd
JOIN pago p ON p.idPago = pd.payment_id
WHERE pd.is_first_payment = 1
  AND pd.payment_status = 4;
```

---

### Mapping: Product / Plan

| Table | Column | Meaning |
|-------|--------|---------|
| `plan` | `idPlan` | Product ID |
| `plan` | `nombre` | Product name |
| `plan` | `precio` | Price |
| `plan` | `tipo` | Plan type (e.g. contador, administrada) |
| `pago` | `idPlan` | Plan paid in this payment |

**Relationship:** `pago.idPlan` → `plan.idPlan`

---

### Summary: Which table to use

| Use case | Table | Filter |
|----------|-------|--------|
| All first payments (CBU, card, transfer) | `pago` | `primerPago = 1` |
| First CBU payments only | `payment_detail` | `is_first_payment = 1` |
| First payment date per company | `pago` | `primerPago = 1`, `estado = 1` |
| Product paid | `pago.idPlan` → `plan` | — |
| Company | `pago.idEmpresa` → `empresa.IdEmpresa` | — |

---

### Date vs time precision

| Source | Column | Precision |
|--------|--------|-----------|
| `pago` | `fechaPago` | Date only (no time) |
| `payment_detail` | `accreditation_date` | Datetime (CBU only) |
| `payment_detail` | `payment_date` | Datetime (CBU only) |

For **CBU** payments, use `payment_detail.accreditation_date` (or `payment_date`) for time. For **card** and **bank transfer**, only `pago.fechaPago` (date) is available.

---

## Script: First payments by product

```bash
python tools/scripts/colppy/first_payments_by_product.py --start 2026-02-01 --end 2026-02-28
python tools/scripts/colppy/first_payments_by_product.py --csv  # CSV output
```

Requires Colppy MySQL access (DB_HOST, DB_NAME, DB_USER, DB_PASSWORD in `tools/.env`).

---

## Related Documentation

- [COLPPY_PAYMENT_TO_CRM_FLOW.md](./COLPPY_PAYMENT_TO_CRM_FLOW.md) – benjamin/svc_integracion_crm perspective
- [HUBSPOT_INTEGRATION_ARCHITECTURE.md](./HUBSPOT_INTEGRATION_ARCHITECTURE.md) – system architecture
- [COLPPY_MYSQL_SCHEMA.md](./COLPPY_MYSQL_SCHEMA.md) – full schema (empresa, facturacion, plan)
