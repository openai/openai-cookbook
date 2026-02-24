# Deal Search Failure Modes: Deep Dive

**Purpose:** Trace each failure mode for HubSpot deal search (`searchDeal` by `id_empresa`) and document root causes, evidence, and fixes.

**Last Updated:** 2026-02-21

---

## Summary: Five Failure Modes

| Failure | Cause | Effect | Verified? |
|---------|-------|--------|-----------|
| Type mismatch | PHP sends integer; HubSpot `id_empresa` is string | Search may not match | **Unlikely** – HubSpot accepts both |
| Deal has no id_empresa | Deal created without `id_empresa` | Search returns 0 → duplicate | Yes |
| crm_match empty | Deal exists in HubSpot, no crm_match row | Falls back to search; if search fails → duplicate | Yes |
| Wrong deal when multiple | Code uses `results[0]` | Updates wrong deal | Yes |
| Network/API error | svc_integracion_crm unreachable, 5xx | Exception caught, no update | Yes |

---

## 1. Type Mismatch

### Flow

1. **colppy-app** (paypertic_payments.php, recepcion_op_pago.php): `$pago['idEmpresa']` or `$rowEmpresa['idEmpresa']` from MySQL → typically **integer**
2. **Payload:** `["campo" => "id_empresa", "valor" => $pago['idEmpresa']]`
3. **colppy-crmintegration-connector:** Passes payload as-is via `POST deals/search`
4. **svc_integracion_crm** DealsController::search (line 159):
   ```php
   "value" => $request['valor']  // No cast to string
   ```
5. **HubSpot:** Receives `value: 123456` (number in JSON) or `value: "123456"` (string)

### Evidence

- **svc_integracion_crm** `app/Http/Controllers/DealsController.php` line 159: `"value" => $request['valor']` – no `(string)` cast
- **HubSpot property:** `id_empresa` is `type: "string"`, `fieldType: "text"`
- **Empirical test:** Searched HubSpot with `value: "2"` (string) and `value: 2` (number) – **both returned the same deal**. HubSpot appears to coerce.

### Verdict

**Low likelihood** – HubSpot Search API accepts both string and number for this property. Still recommend casting in svc_integracion_crm for consistency.

### Fix

```php
// DealsController.php search()
"value" => (string) $request['valor'],
```

---

## 2. Deal Has No id_empresa

### Flow

Deals created by:
- HubSpot workflow (Lead → Deal conversion)
- Manual creation in HubSpot
- Other integrations (Intercom, etc.)

may not have `id_empresa` populated. Search by `id_empresa` returns 0.

### Evidence

- Reconciliation shows "HubSpot only" deals – deals in HubSpot with no Colppy first payment. Some may have empty `id_empresa`.
- Deal creation flows (workflow, manual) often don't set custom properties.

### Effect

`searchDeal` returns `total == 0` → code creates **new deal** via `storeDeal` → **duplicate** (original deal without id_empresa + new deal with id_empresa).

### Fix

1. **Populate id_empresa** on workflow-created deals (e.g. from contact/company data).
2. **Search fallback:** If search by id_empresa returns 0, optionally search by dealname pattern `"{id_empresa} - "` before creating.
3. **Reconcile script:** `reconcile_missing_deals.py` can fix deals with wrong/empty id_empresa.

---

## 3. crm_match Empty

### Flow

1. Deal exists in HubSpot (e.g. created by workflow, manual, or earlier integration run).
2. `crm_match` has no row for `colppy_id = idEmpresa, table_name = 'negocio'` (e.g. DB reset, different Colppy env, deal created outside integration).
3. Code falls back to `searchDeal`.
4. If search fails (type, format, deal has no id_empresa) → `total == 0` → **new deal created** → **duplicate**.

### Evidence

- `paypertic_payments.php` lines 77–107: `crm_match` lookup first; only if `!$result` does it call `searchDeal`.
- `recepcion_op_pago.php` same pattern.

### Fix

1. **Backfill crm_match:** When a deal is found via search, we already `INSERT INTO crm_match`. The gap is when search returns 0 but deal exists (e.g. no id_empresa).
2. **Run reconcile_missing_deals.py** to fix deals with wrong id_empresa, then backfill crm_match if a separate process exists.

---

## 4. Wrong Deal When Multiple

### Flow

Multiple deals can share the same `id_empresa`:
- Cross-sell (Cro, Cross)
- Recovery (Cerrado Ganado Recupero)
- Multi-entity (108231–108238)

Code uses:
```php
$crm_deal_id = $deal['data']['results'][0]['id'];
```

HubSpot Search API returns results in undefined order. `results[0]` may be:
- Churned deal (31849274)
- Closed lost
- Older deal

### Evidence

- `paypertic_payments.php` line 106: `$crm_deal_id = $deal['data']['results'][0]['id'];`
- `recepcion_op_pago.php` line 315: same
- `functionsCRM.php` search_deal line 559: returns `$result['data']['results'][0]['id']`
- Reconciliation pattern analysis: Cross-sell, multi-entity deals often have blanks.

### Effect

`fecha_primer_pago` is written to the **wrong deal** (e.g. churned). The correct closedwon deal stays blank.

### Fix

1. **Filter by dealstage:** Add filter to search: `dealstage = closedwon` (or include 34692158 for recovery). Requires svc_integracion_crm to support multiple filters.
2. **Sort by closedate DESC:** Prefer most recent closed deal.
3. **Pick by stage:** When multiple results, iterate and pick the one with `dealstage` in (closedwon, 34692158).

---

## 5. Network/API Error

### Flow

- svc_integracion_crm unreachable (DNS, network, downtime)
- HubSpot rate limit (429)
- HubSpot 5xx

### Evidence

- `paypertic_payments.php`: Wrapped in try/catch for `CRMIntegrationException`; logs only.
- `recepcion_op_pago.php` lines 394–398: `catch (CRMIntegrationException $exc)` → `Log::error(__METHOD__, ...)` – no retry, no alert.
- colppy-crmintegration-connector throws `CRMIntegrationException` on HTTP errors.

### Effect

Exception caught and logged. No HubSpot update. `fecha_primer_pago` stays blank.

### Fix

1. **Retry logic:** Retry search/update on 5xx or timeout (e.g. 2 retries with backoff).
2. **Alerting:** Notify on repeated CRMIntegrationException for same id_empresa.
3. **Idempotent retry:** Paypertic may resend webhook; ensure logic is idempotent.

---

## Critical Bug: crm_match Exists but $crm_deal_id Never Set

### Finding

**Both** Paypertic and recepcion_op_pago have the same bug: when `crm_match` **has** a row, `$crm_deal_id` is **never set**, but the update is always executed.

#### paypertic_payments.php

- `$deals_service` is created at line 74 (before the if)
- `$crm_deal_id` is only set inside `if (!$result)` (lines 104 or 106)
- Line 178: `$deals_service->updateDeal($crm_deal_id, ...)` – **$crm_deal_id undefined when $result exists**

#### recepcion_op_pago.php

- `$deals_service` is created only inside `if (!$result)` (line 286)
- `$crm_deal_id` is only set inside `if (!$result)` (lines 312 or 315)
- Line 392: `$deals_service->updateDeal($crm_deal_id, ...)` – **both undefined when $result exists**

### Effect

When crm_match exists (common for first payment after trial – deal created at signup), the script crashes with **undefined variable**. `fecha_primer_pago` is **never updated** in this path. This likely explains many blanks for CBU/card payments where the deal was created before first payment.

### Fix

**paypertic_payments.php:**
```php
if (!$result) {
    // ... search/create, set $crm_deal_id, associations ...
} else {
    $crm_deal_id = $result['crm_id'];
}
$updateDealPayload = [...];
$deal = $deals_service->updateDeal($crm_deal_id, $updateDealPayload);
```

**recepcion_op_pago.php:**
```php
if (!$result) {
    $deals_service = new Deals(null, INTEGRACIONCRM_BASE_URL);
    // ... search/create, associations ...
} else {
    $crm_deal_id = $result['crm_id'];
    $deals_service = new Deals(null, INTEGRACIONCRM_BASE_URL);
}
$updateDealPayload = [...];
$deals_service->updateDeal($crm_deal_id, $updateDealPayload);
```

**Files:** `colppy-app/webhooks/paypertic_payments.php`, `colppy-app/recepcion_op_pago.php`

---

## Recommended Fixes (Priority)

| Priority | Fix | File | Effort |
|----------|-----|------|--------|
| **P1** | Add else branch when crm_match exists | recepcion_op_pago.php | Low |
| **P2** | Filter search by dealstage (closedwon) when multiple | svc_integracion_crm DealsController | Medium |
| **P3** | Cast valor to string in search | svc_integracion_crm DealsController | Low |
| **P4** | Retry on 5xx/timeout | colppy-crmintegration-connector or colppy-app | Medium |
| **P5** | Search by dealname fallback before create | paypertic_payments, recepcion_op_pago | Medium |

---

## Validation Queries

### Check crm_match coverage (requires Colppy MySQL)

```sql
SELECT colppy_id, crm_id FROM crm_match WHERE table_name = 'negocio' AND colppy_id IN (/* blank id_empresas */);
```

### Check HubSpot for multiple deals per id_empresa

```python
# Use hubspot-search-objects with filter id_empresa EQ "X"
# If total > 1, inspect dealstage of each
```

### Check deals with empty id_empresa

```python
# hubspot-search-objects with filter: id_empresa NOT_HAS_PROPERTY or similar
```
