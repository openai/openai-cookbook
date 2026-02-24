# Colppy Payment → CRM Integration Flow

**Last Updated:** 2026-02-20  
**Purpose:** Trace all payment entry points in Colppy and document the flow to the CRM (HubSpot via svc_integracion_crm)

**Note:** Salesforce integration code has been removed. Colppy uses HubSpot only.

**See also:** [FIRST_PAYMENT_ENTRY_POINTS.md](./FIRST_PAYMENT_ENTRY_POINTS.md) – Full end-to-end flow, CBU subscription vs money collection, collected vs pending, data model, and scripts.

---

## TL;DR

| Entry Point | Triggers CRM? | Current State |
|-------------|----------------|---------------|
| Paypertic webhook | No | PayperticPayment job updates payment status only; no CRM sync |
| Direct API payment (`POST /api/v1/payment/`) | No | No CRM integration |
| Company registry (`POST /api/v1/company/registry`) | No | TODO: HubSpot lead creation to be implemented (Salesforce code removed) |

---

## 1. Payment Entry Points in colppy-benjamin

### 1.1 Paypertic Webhook

**Route:** `POST /api/v1/webhooks/paypertic/payments`  
**Controller:** `PayperticController::payment()`  
**File:** `app/Http/Controllers/Webhook/PayperticController.php`

**Flow:**
1. Paypertic sends payment status notification (approved, rejected, etc.)
2. Controller dispatches `PayperticPayment` job (async)
3. Returns `{success: true}` immediately

**PayperticPayment job** (`app/Jobs/PayperticPayment.php`):
- Updates `payment_detail` (status, gateway_id, accreditation_date)
- If `status == 'rejected'` → calls `processPaymentRejection()` (reverts company to trial)
- Creates `PaymentDetailStatus` record
- Does **NOT** trigger any CRM sync

**PayperticPayment uses:**
- `external_transaction_id` to find PaymentDetail (matches `payment_detail.external_transaction_id`)

---

### 1.2 Direct API Payment

**Route:** `POST /api/v1/payment/`  
**Controller:** `PaymentController::pay()`  
**File:** `app/Http/Controllers/PaymentController.php`

**Flow:**
1. Request validated via `PaymentRequest`
2. `PaymentService::createPayment($fields)` → `processPayment()` → `responsePaypertic()` → Paypertic API
3. `PaymentDetailService::update()` stores response
4. Returns payment response

**CRM integration:** None.

---

### 1.3 Company Registry (Lead Creation)

**Route:** `POST /api/v1/company/registry`  
**Controller:** `CompanyController::registry()`  
**File:** `app/Http/Controllers/CompanyController.php`

**Flow:**
1. Receives payload: `$request->all()['payload']`
2. **TODO:** HubSpot lead creation to be implemented (previously used Salesforce; now HubSpot only)

---

## 2. Payment → HubSpot CRM Integration (Future)

To add Paypertic → HubSpot sync when payment is approved:

1. Add `dispatchIntegration()` or equivalent inside `PayperticPayment` job when `status == 'approved'` and `is_first_payment`
2. Create a HubSpot job that POSTs to svc_integracion_crm with HubSpot deal properties (e.g. `dealstage`, `closedate`)
3. Map Colppy IdEmpresa → HubSpot deal (via `id_empresa` or `colppy_id` on company)

---

## 3. What Happens in svc_integracion_crm

### 3.1 Current Routes (api.php)

**Existing routes:**
- `GET /api/health`
- `apiResources`: accounts, contacts, deals, events, subscriptions, discounts, plans, deactivations
- `POST /api/deals/{id}/won` (DealWonController)
- `POST /api/webhooks/deal-won` (DealWonController)

---

### 3.2 DEAL_WON_PROCESS.md (svc_integracion_crm)

The `DEAL_WON_PROCESS.md` doc states:
- **Current state:** No automated process when deal is won
- **Recommended:** Manual `POST /api/deals/{id}/won` or HubSpot webhook to `POST /api/webhooks/deal-won`
- **DealWonController** exists and would: update company status, create subscription, create event, update deal payment info

---

### 3.3 CRM Behavior by Scenario

| Scenario | Source | What happens in CRM |
|----------|--------|---------------------|
| **Paypertic: approved** | PayperticPayment | Nothing (no CRM sync) |
| **Paypertic: rejected** | PayperticPayment | Nothing (no CRM sync) |
| **Direct API payment** | PaymentController | Nothing (no CRM sync) |
| **Company registry** | CompanyController | Nothing (TODO: HubSpot lead creation) |
| **Manual deal won** | Manual / HubSpot | DealWonController → update company, subscription, event, deal payment |

---

## 4. CBU Flow Summary (from FIRST_PAYMENT_ENTRY_POINTS.md)

- **Subscription status:** Immediate (optimistic) at user submit
- **Money collection:** 3–7 days (Paypertic)
- **Collected:** `payment_detail.payment_status = 4`, `accreditation_date` set
- **Pending:** `payment_detail.payment_status IN (1, 2, 3)`, `accreditation_date IS NULL`

---

## 5. Related Files

| Repo | File | Purpose |
|------|------|---------|
| colppy-benjamin | `app/Http/Controllers/Webhook/PayperticController.php` | Paypertic webhook handler |
| colppy-benjamin | `app/Jobs/PayperticPayment.php` | Updates payment status (no CRM) |
| colppy-benjamin | `app/Services/Payment/PaymentService.php` | Payment processing |
| colppy-benjamin | `app/Http/Controllers/PaymentController.php` | Direct payment API |
| colppy-benjamin | `app/Http/Controllers/CompanyController.php` | Registry (TODO: HubSpot) |
| svc_integracion_crm | `routes/api.php` | HubSpot API routes |
| svc_integracion_crm | `DEAL_WON_PROCESS.md` | Deal won process (manual) |
| svc_integracion_crm | `app/Http/Controllers/DealsController.php` | HubSpot deals CRUD |
| tools/docs | [FIRST_PAYMENT_ENTRY_POINTS.md](./FIRST_PAYMENT_ENTRY_POINTS.md) | Full payment flow, CBU collected/pending, data model |
