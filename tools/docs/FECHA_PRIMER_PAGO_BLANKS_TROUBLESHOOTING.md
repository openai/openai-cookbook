# fecha_primer_pago Blanks: Troubleshooting Guide

**Purpose:** Diagnose why HubSpot `fecha_primer_pago` is blank for deals that have first payments in Colppy.

**Last Updated:** 2026-02-19

---

## Summary: Three Payment Flows That Update HubSpot

| medioPago | Flow | File | Condition for HubSpot Update |
|-----------|------|------|------------------------------|
| **CBU** | Paypertic webhook | `webhooks/paypertic_payments.php` | `status == 'approved'` AND `primerPago == 1` |
| **Visa/MasterCard** | Card gateway callback | `recepcion_op_pago.php` | `estado == 1` AND `primerPago == 1` AND **param.php loads** |
| **Transferencia** | Manual confirmation | `MC_Pagar.php` | `primerPago == 1` AND **SERVER_ENTORNO == 'Prod'** |

---

## Root Causes for Blanks (by medioPago)

### 1. CBU – Paypertic Webhook

**Flow:** Paypertic sends webhook → `paypertic_payments.php` → reads `pago` by `idPago` → updates HubSpot.

**Why blank:**
- **Webhook not received:** Paypertic may not be configured to send to colppy-app URL, or URL is wrong
- **Webhook payload mismatch:** `queueableData['details'][0]['external_reference']` must be `idPago`; if structure changed, lookup fails
- **Deal not found:** `crm_match` has no row for `id_empresa`, and `searchDeal` returns 0 → new deal created but `updateDeal` may use wrong ID
- **Exception swallowed:** `CRMIntegrationException` is caught and only logged; HubSpot update fails silently

**Check:** Paypertic dashboard / logs for webhook delivery; colppy-app logs for `webhook_paypertic_payment` and any CRM errors.

---

### 2. Card (Visa Crédito, Visa Débito, MasterCard) – recepcion_op_pago.php

**Flow:** Gateway (Decidir/ePayco) redirects to `recepcion_op_pago.php` or `confirmacion_epayco.php` → `recepcion_op_pago.php` → HubSpot update.

**Why blank – CRITICAL:**

The entire HubSpot sync block (lines 244–399) is wrapped in:

```php
if((include_once("/var/www/html/colppy/resources/php/common/param.php")) == true) {
```

- **Hardcoded path:** `/var/www/html/colppy/` – if the app is deployed elsewhere (e.g. `/var/www/html/staging`, `/var/www/html/colppy-app`), the include **fails** and the CRM block is **never executed**
- **param.php in .gitignore:** File is environment-specific; if missing in a given environment, include returns false → no HubSpot update

**Fix:** Use a relative or config-based path, e.g.:

```php
$paramPath = defined('ROOT_COLPPY') ? ROOT_COLPPY . 'resources/php/common/param.php' : __DIR__ . '/resources/php/common/param.php';
if (file_exists($paramPath) && (include_once $paramPath) == true) {
```

**Check:** Verify `param.php` exists at `/var/www/html/colppy/resources/php/common/param.php` on the server that receives card callbacks.

---

### 3. Bank Transfer – MC_Pagar.php

**Flow:** User submits transfer details → `MC_Pagar.php` → inserts `pago` → HubSpot update.

**Why blank:**

```php
if (SERVER_ENTORNO == 'Prod') {
    // ... Mixpanel + update_deal + update_deal_stage
}
```

- **Non-production:** If `SERVER_ENTORNO` is not `'Prod'` (e.g. staging, dev), the HubSpot update is **skipped**
- **crm_match missing:** `update_deal()` calls `leerMatchCrm($parametros['idEmpresa'], 'negocio')` – if no row exists, it throws; exception is caught and only logged

**Check:** Confirm `SERVER_ENTORNO` in production; ensure `crm_match` has a row for the deal before transfer confirmation.

---

### 4. Débito Automático (MC_DatosDebito.php)

**Flow:** User adheres to automatic debit → `MC_DatosDebito.php` → updates `pago` and `empresa`.

**Finding:** `MC_DatosDebito.php` does **not** call `update_deal` or any HubSpot sync. The first charge happens later via Paypertic; at that moment the Paypertic webhook should fire. If the first charge is processed differently (e.g. no webhook), `fecha_primer_pago` stays blank.

---

## Validation Checklist

| Check | How |
|-------|-----|
| param.php path | `ls -la /var/www/html/colppy/resources/php/common/param.php` on prod |
| SERVER_ENTORNO | Grep for `SERVER_ENTORNO` in param.php or env config |
| Paypertic webhook URL | Check Paypertic config; compare with `PPT_NOTIFICATION_URL` in colppy-app |
| crm_match coverage | `SELECT * FROM crm_match WHERE table_name='negocio' AND colppy_id IN (...)` for blank id_empresas |
| Logs | `Log::error` in functionsCRM.php; `webhook_paypertic_payment` in Laravel logs |

---

## Reconciliation Script (with medioPago)

Run to see blanks by payment method:

```bash
python tools/scripts/hubspot/reconcile_fecha_primer_pago_colppy.py --month 2026-01
```

Output includes `medioPago` for:
- **MATCH (date diff):** Same id_empresa, different dates (often HS empty, Colppy has date)
- **HubSpot only:** Deals with no Colppy first payment in period (medioPago from first payment lookup)
- **Colppy only:** First payments without matching HubSpot deal

---

---

## Deal Search: How It Works & Failure Points

### Flow (Paypertic / recepcion_op_pago / MC_Pagar)

1. **crm_match lookup:** `SELECT * FROM crm_match WHERE colppy_id = :idEmpresa AND table_name = 'negocio'`
2. **If no row:** Call `searchDeal({"campo": "id_empresa", "valor": idEmpresa})`
3. **searchDeal path:** colppy-app → colppy-crmintegration-connector → svc_integracion_crm → HubSpot `POST /crm/v3/objects/deals/search`
4. **svc_integracion_crm** maps to HubSpot filter: `propertyName: "id_empresa"`, `operator: "EQ"`, `value: valor`
5. **If total == 0:** Create new deal via `storeDeal`; else use `results[0]['id']`

**Reference:** [HUBSPOT_INTEGRATION_ARCHITECTURE.md](./HUBSPOT_INTEGRATION_ARCHITECTURE.md) §1.5

### HubSpot id_empresa Property

- **Type:** `string` (fieldType: text)
- **Meaning:** Colppy `id_empresa` (company/legal entity ID)

### Why the Search Can Fail

| Failure | Cause | Effect |
|---------|-------|--------|
| **Type mismatch** | PHP sends `valor: 123456` (integer); HubSpot stores `id_empresa` as string. If svc_integracion_crm passes the raw value without casting to string, HubSpot Search API may not match. | `total == 0` → new deal created → duplicate |
| **Deal has no id_empresa** | Deal created by workflow, manual, or other flow without `id_empresa` populated. | Search returns 0 → new deal created → duplicate |
| **crm_match empty** | Deal exists in HubSpot but `crm_match` has no row (e.g. deal created outside integration, DB reset). | Falls back to search; if search fails, creates duplicate |
| **Wrong deal when multiple** | Multiple deals share same `id_empresa` (e.g. cross-sell, recovery). Code uses `results[0]` – first result may be wrong stage or wrong deal. | Updates wrong deal; `fecha_primer_pago` may go to churned/lost deal |
| **Network/API error** | svc_integracion_crm unreachable, HubSpot rate limit, or 5xx. | Exception caught and logged; no update |

### Validation

- **Check id_empresa type in requests:** Ensure svc_integracion_crm casts `valor` to string before building the HubSpot filter.
- **For blank id_empresas:** Query HubSpot directly: `hubspot-search-objects` with `filterGroups: [{ filters: [{ propertyName: "id_empresa", operator: "EQ", value: "<id_empresa>" }] }]` – try both string and number for `value`.
- **crm_match coverage:** `SELECT * FROM crm_match WHERE table_name='negocio' AND colppy_id IN (...)` for blank id_empresas.

---

## Recommended Fixes (Priority)

1. **recepcion_op_pago.php:** Replace hardcoded `/var/www/html/colppy/` with `__DIR__` or `ROOT_COLPPY` so param.php loads in all environments.
2. **MC_Pagar.php:** Consider removing or relaxing `SERVER_ENTORNO == 'Prod'` for HubSpot sync if staging should also update CRM (or add explicit env allowlist).
3. **Logging:** Add explicit log when HubSpot update is skipped (param.php fail, non-Prod, etc.) for easier debugging.
4. **svc_integracion_crm:** Ensure `valor` is cast to string when building the HubSpot search filter for `id_empresa` (property is string type).
