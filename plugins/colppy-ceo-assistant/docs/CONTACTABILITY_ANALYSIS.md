# ICP Hypothesis Implementation (MCP-first) — v1.0

Goal: infer a user/company ICP as early as possible (first session) and persist it to both HubSpot and Mixpanel with confidence and source, so GTM and Product can act before confirmation.

**Mixpanel Project ID:** 2201475 (Colppy User Level Production)

---

## 0) Scope (this file = “Hypothesis Only”)

Out of the full ICP model, this .md covers:

* Property creation (HubSpot + Mixpanel)
* Event/property contracts needed to infer ICP fast
* Scoring rules (weights, precedence, conflict handling)
* MCP tasks (create, backfill, schedule, validate)

Confirmation logic (wizard/DBR) and coverage tiles are out-of-scope here and will come in “ICP Confirmation & Coverage — v1.0”.

---

## 1) Properties to create (idempotent)

Create these on **Contact** and **Company** in HubSpot, and as **Profile properties** in Mixpanel.

```json
{
  "properties": [
    {
      "name": "icp_hypothesis",
      "type": "enumeration",
      "options": ["pyme_operator", "accountant_advisor", "tech_integrator", "unknown"],
      "description": "Best current ICP guess (hypothesis)",
      "overwrite": true
    },
    {
      "name": "icp_confidence",
      "type": "number",
      "range": [0,100],
      "description": "Confidence score for hypothesis (0–100)",
      "overwrite": true
    },
    {
      "name": "icp_source",
      "type": "enumeration",
      "options": ["behavior", "wizard", "hubspot"],
      "description": "Source of the latest update to hypothesis",
      "overwrite": true
    },
    {
      "name": "icp_secondary",
      "type": "enumeration",
      "options": ["pyme_operator", "accountant_advisor", "tech_integrator", "unknown"],
      "description": "Second-best ICP guess (used for conflicts/ambiguity)",
      "overwrite": true
    }
  ]
}
```

### MCP Tasks

* `hubspot.properties.create` (Contact + Company) with the JSON above (run idempotently).
* `mixpanel.profiles.ensure_properties` with the same definitions (idempotent).

---

## 2) Event & property contracts (data you must emit)

Create or verify these **events** and **properties**. Names can be adapted to your current schema; keep semantics.

### A) Wizard answers (event: `Finalizar Wizard`)

**Current Event Properties Available:**
* `Tipo Plan Empresa`: enum (pendiente_pago, basic, administrada_plus, superior_a_tres_mil, etc.)
* `company_id`: numeric (company identifier)
* `$user_id`: string (user email/identifier)

**Missing Properties (Required for ICP Scoring):**
* `role_in_company`: enum (values include `Contador/Asesor`, `Dueño`, `Administración`, `Finanzas`, `Operaciones`, …)
* `company_type`: enum (must include `Estudio contable`, `Empresa PyME`, …)
* `plan_to_implement`: enum (`Ahora`, `Esta semana`, `Este mes`, `Más adelante`)

**HubSpot Properties (Available for Mapping):**
* `rol_wizard`: string ("¿Cuál es tu rol? wizard") - **Maps to role_in_company**
* `lead_company_type`: enum (Cuenta Contador, Cuenta Pyme, etc.) - **Maps to company_type**
* `implementacion_wizard`: string ("¿Cuándo querés implementar Colppy? wizard") - **Maps to plan_to_implement**

**Mixpanel Profile Properties (To Be Created):**
* `$set_once`: `first_role_in_company`, `first_company_type`, `first_plan_to_implement`
* `$set`: latest copies of the same (optional)

### B) Early behavior (first 60–120 minutes)

Emit **distinct** events (actual Mixpanel event names):

* `Finalizó configuración FE` (AFIP connection event)
* `Generó comprobante de venta` (first invoice event - filter for first time ever)
* `Finalizó importación` (clients imported event)
* `Cambia Empresa desde Header` (multiempresa exploration event)
* `Crear Empresa` with `count_created_companies` (int)

Optional **profile helpers** (updated on event):

* `$set`: `did_key_event_early` (true if any of the three: Finalizó configuración FE, Generó comprobante de venta, Finalizó importación within 120m)
* `$set`: `explored_multiempresa_early` (true if Cambia Empresa desde Header within 120m)
* `$set`: `created_companies_early` (int from Crear Empresa within 120m window)

### C) Identity signals (profile)

* `company_domain`: string (from email)
* `domain_contains_accounting_keywords`: boolean (regex on `estudio|contable|contador`)
* `domain_in_pymes_allowlist`: boolean (maintained list; optional)

### MCP Tasks

* `mixpanel.events.ensure` for event schemas and required properties.
* `mixpanel.profiles.ensure_properties` for the profile helpers.
* (Optional) `mixpanel.transformations.create` to compute the early-window booleans from timestamps server-side.

---

## 3) Scoring rules (weights & precedence)

> Principle: compute two candidate confidences (Accountant vs Operator), **boost** with intent (“Ahora/Esta semana”), then pick the max as the hypothesis. Keep the other as `icp_secondary`. Always stamp `icp_source`.

### Weight table

| Signal type      | Condition (examples)                                               | ICP                | Confidence Δ |
| ---------------- | ------------------------------------------------------------------ | ------------------ | ------------ |
| Wizard           | `role_in_company = Contador/Asesor`                                | accountant_advisor | +90          |
| Wizard           | `company_type = Estudio contable`                                  | accountant_advisor | +90          |
| Wizard           | `role_in_company ∈ {Dueño, Administración, Finanzas, Operaciones}` | pyme_operator      | +70          |
| Wizard (booster) | `plan_to_implement ∈ {Ahora, Esta semana}`                         | boost winning ICP  | +10          |
| Behavior (≤120m) | `Finalizó configuración FE OR Generó comprobante de venta OR Finalizó importación` | pyme_operator      | +80          |
| Behavior (≤120m) | `Cambia Empresa desde Header OR Crear Empresa>=2`                  | accountant_advisor | +70          |
| Identity (weak)  | `domain_contains_accounting_keywords = true`                       | accountant_advisor | +10          |
| Identity (weak)  | `domain_in_pymes_allowlist = true`                                 | pyme_operator      | +10          |

### Precedence & conflicts

1. Compute `conf_accountant` and `conf_operator` as the **max** applicable signal for each type + **sum** of boosters.
2. Hypothesis:

   * if `conf_accountant > conf_operator` ⇒ `icp_hypothesis = accountant_advisor`
   * else if `conf_operator > conf_accountant` ⇒ `icp_hypothesis = pyme_operator`
   * else ⇒ `icp_hypothesis = unknown`
3. `icp_confidence = max(conf_accountant, conf_operator)` (cap at 100).
4. `icp_secondary` = the other side when there is a clear winner; empty if `unknown`.
5. `icp_source`:

   * `wizard` if a wizard rule contributed the **winning** confidence
   * else `behavior` if a behavior rule contributed the **winning** confidence
   * else `hubspot` (reserved for later if HS sets it first)

---

## 4) Compute & write-back flow (real-time + backfill)

### Real-time (recommended)

* Trigger on any of: `Finalizar Wizard`, `Finalizó configuración FE`, `Generó comprobante de venta`, `Finalizó importación`, `Cambia Empresa desde Header`, `Crear Empresa`.
* Recalculate confidences with a 120-minute window for behavior signals (relative to `first_session_at` or `trial_start_at`).
* Update Mixpanel **profile** with `$set`: `icp_hypothesis`, `icp_confidence`, `icp_secondary`, `icp_source`.
* Mirror to HubSpot contact/company if empty or if the new `icp_confidence` is **higher** than the stored one.

### Backfill (one-time + nightly)

* One-time: scan last 90 days of trials; compute hypothesis; upsert to both systems.
* Nightly: recompute for users with new wizard/behavior activity in the past 24h; upsert deltas only.

### MCP Tasks

* `mixpanel.jql.run` (or equivalent) to compute confidences (see sample below).
* `mixpanel.profiles.set` to write hypothesis fields.
* `hubspot.contacts.batch_upsert` and `hubspot.companies.batch_upsert` with the four fields (guard with confidence comparison).
* `scheduler.create_job` to run nightly backfill.

---

## 5) Sample JQL (Mixpanel) — hypothesis calculator (pseudocode)

```javascript
function main() {
  return Events({
    from_date: params.from_date,  // e.g., "2025-09-01"
    to_date: params.to_date       // e.g., "2025-10-04"
  })
  .filter(function(e){
    return inArray(e.name, [
      "Finalizar Wizard",
      "Finalizó configuración FE","Generó comprobante de venta","Finalizó importación",
      "Cambia Empresa desde Header","Crear Empresa"
    ]);
  })
  .groupByUser(mkReducer())
  .map(writeProfilePatch);
}

function mkReducer(){
  return function(acc, e){
    acc = acc || init();
    // capture first session anchor
    if (!acc.first_session_at || e.time < acc.first_session_at) acc.first_session_at = e.time;

    // wizard signals
    if (e.name === "Finalizar Wizard"){
      if (e.properties.role_in_company === "Contador/Asesor") acc.conf_accountant = Math.max(acc.conf_accountant, 90), acc.source_accountant = "wizard";
      if (e.properties.company_type === "Estudio contable") acc.conf_accountant = Math.max(acc.conf_accountant, 90), acc.source_accountant = "wizard";
      if (inArray(e.properties.role_in_company, ["Dueño","Administración","Finanzas","Operaciones"])) acc.conf_operator = Math.max(acc.conf_operator, 70), acc.source_operator = "wizard";
      if (inArray(e.properties.plan_to_implement, ["Ahora","Esta semana"])) acc.boost += 10;
    }

    // 120m window
    var within120 = (e.time - acc.first_session_at) <= 120*60;
    if (within120){
      if (inArray(e.name, ["Finalizó configuración FE","Generó comprobante de venta","Finalizó importación"])) acc.conf_operator = Math.max(acc.conf_operator, 80), acc.source_operator = acc.source_operator || "behavior";
      if (inArray(e.name, ["Cambia Empresa desde Header"]) || (e.name==="Crear Empresa" && e.properties.count_created_companies>=2)) acc.conf_accountant = Math.max(acc.conf_accountant, 70), acc.source_accountant = acc.source_accountant || "behavior";
    }

    return acc;
  }
}

function init(){
  return {conf_accountant:0, conf_operator:0, boost:0, first_session_at:null, source_accountant:null, source_operator:null};
}

function writeProfilePatch(user){
  var a = user.value.conf_accountant;
  var o = user.value.conf_operator;
  var boost = user.value.boost;

  var winner = "unknown", secondary = "", conf = 0, src = "behavior";
  if (a>o){ winner = "accountant_advisor"; secondary="pyme_operator"; conf = Math.min(100, a+boost); src = user.value.source_accountant || src; }
  else if (o>a){ winner = "pyme_operator"; secondary="accountant_advisor"; conf = Math.min(100, o+boost); src = user.value.source_operator || src; }

  return {
    "$distinct_id": user.key,
    "$set": {
      "icp_hypothesis": winner,
      "icp_confidence": conf,
      "icp_secondary": secondary,
      "icp_source": src
    }
  };
}
```

> Use as body for `mixpanel.jql.run`, then pipe each object to `mixpanel.profiles.set`.

---

## 6) HubSpot mirror (guarded upsert)

Write to Contact and (if available) the associated Company when:

* Destination field is empty, **or**
* Incoming `icp_confidence` > stored `icp_confidence`.

Payload example for batch upsert:

```json
{
  "upserts": [
    {
      "email": "user@empresa.com",
      "properties": {
        "icp_hypothesis": "pyme_operator",
        "icp_confidence": 80,
        "icp_source": "behavior",
        "icp_secondary": "accountant_advisor"
      }
    }
  ],
  "update_only_if_confidence_higher": true
}
```

### MCP Tasks

* `hubspot.contacts.batch_upsert` with guard flag
* `hubspot.companies.batch_upsert` (if you key by domain or companyId)
* `job.log` count of updated vs skipped (for audit)

---

## 7) Scheduling & monitoring

* **Real-time**: subscribe to the five early events; run the calculator; patch Mixpanel profile immediately.
* **Nightly**: backfill for users with activity in last 24h; run HS mirror.
* **Monitoring** (hypothesis health):

  * % of new trials with non-`unknown` `icp_hypothesis`
  * Median minutes to first hypothesis
  * Distribution of `icp_confidence`
  * Source mix (`wizard` vs `behavior`)

(Metrics will later feed the confirmation/coverage dashboard.)

---

## 8) Acceptance criteria (done = usable)

* Properties exist in both systems (Contact + Company in HS; Profile in MP).
* Events and profile helpers are present and populated for new trials.
* Hypothesis is set within the **first session** for ≥60% of new trials.
* Sync to HubSpot respects confidence guard and is idempotent.
* Nightly job reports updated/skipped counts without errors.

---

## 9) Rollback / safety

* All writes are **profile-level**; no deletion of history.
* Keep previous hypothesis changes in system audit logs (Mixpanel change history, HubSpot property history).
* If misclassification spike detected, disable the job, adjust weights, and re-run nightly backfill.

---

### Quick MCP run-order (copy/paste checklist)

1. Create properties (HS + MP)
2. Ensure event schemas (MP)
3. Deploy JQL calculator (MP)
4. Wire real-time triggers (MP → calculator → MP profile set)
5. Backfill last 90 days (MP JQL → HS/MP upserts with confidence guard)
6. Schedule nightly job + add monitoring logs

---

If you want, I’ll extend this with the “Confirmation & Coverage — v1.0” .md next (wizard/DBR confirmation, guardrails, and the coverage tiles).
