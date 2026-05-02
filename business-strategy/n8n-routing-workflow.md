# n8n Routing Workflow — `tps_intake_router_v1`

Companion to `multi-domain-intake-architecture.md` and `hubspot-intake-form-spec.md`. Defines the n8n workflow that consumes the HubSpot intake webhook (and the Quo voice/SMS bridge), scores the contact, and dispatches the routing decision back to HubSpot + Quo SMS + Microsoft Teams.

**Hosting:** **n8n self-hosted on Azure VM.** Secrets via **Azure Key Vault**. Zapier and Make are prohibited.
**Webhook path:** `POST /webhook/intake/v1` (web form) and `POST /webhook/quo-inbound/v1` (Quo bridge).
**Auth:** HMAC header `X-TPS-Signature` validated against `INTAKE_WEBHOOK_SECRET`.
**Outputs:** HubSpot contact update, Quo SMS (Tier 1 only), Microsoft Teams alert (Tier 1 + manual_review), email task assignment via HubSpot.

---

## 1. Node-by-node walkthrough (web-form path)

```
[1] Webhook (POST /intake/v1)
       │
[2] Function: verifyHmac           ─── on failure → [F1] Respond 401
       │
[3] Function: normalizePayload     (lowercase enums, coerce arrays, parse dates,
       │                            apply source-derived field defaults
       │                            e.g. FL funnel agency_track=fdor)
       │
[4] Function: scoreContact         (implements §4C of architecture spec)
       │
[5] Function: assignTier           (implements tier mapping table, top-down,
       │                            emergency BEFORE missing-fields catch-all)
       │
[6] Function: applySourceOverrides (advisor-referral, urgent-floor)
       │
[7] Switch: triage_routing_decision
       ├── same_day_callback ──► [8a] HubSpot:updateContact ─► [9a] Quo:SMS ─► [10a] Teams:postMessage ─► [11a] HubSpot:createTask(URGENT)
       ├── book_case_review  ──► [8b] HubSpot:updateContact ─► [9b] HubSpot:sendEmail(booking link)
       ├── manual_review     ──► [8c] HubSpot:updateContact ─► [9c] HubSpot:createTask(ops queue)
       ├── nurture_sequence  ──► [8d] HubSpot:updateContact ─► [9d] HubSpot:enrollInWorkflow(nurture)
       └── referral_out      ──► [8e] HubSpot:updateContact ─► [9e] HubSpot:sendEmail(referral)
       │
[12] Respond 200 (with triage_routing_decision + triage_score)
```

The Quo inbound bridge (§5) feeds the same `[3]–[12]` pipeline after creating/upserting the HubSpot contact and stamping `intake_channel = quo_voice|quo_sms`.

---

## 2. Required environment variables

| Var | Purpose |
|---|---|
| `INTAKE_WEBHOOK_SECRET` | HMAC shared secret with HubSpot + Quo |
| `HUBSPOT_PRIVATE_APP_TOKEN` | HubSpot CRM API token (Contacts r/w, Workflows enroll, Tasks write) |
| `QUO_API_KEY` / `QUO_API_BASE` | Quo.com REST endpoint for outbound SMS |
| `QUO_FROM_NUMBER` | Quo DID used as the SMS sender for internal alerts |
| `ON_CALL_PHONE` | E.164 number for Tier 1 SMS to on-call |
| `TEAMS_WEBHOOK_URL` | Incoming-webhook URL for `#tps-urgent` |
| `OPS_QUEUE_OWNER_ID` | HubSpot owner ID for manual-review queue |
| `ON_CALL_OWNER_ID` | HubSpot owner ID for Tier 1 routing |
| `MEETINGS_BASE_URL` | `https://keithjones.cpa` (for `/triage-*` link composition) |

All values stored in **Azure Key Vault** and injected into the n8n container at start (or referenced by Key Vault SDK at request time).

---

## 3. Function node code

The five Function nodes are checked in as standalone files at `business-strategy/scripts/n8n/functions/`. Snippets below are illustrative — paste from the files for accuracy.

### `verifyHmac` (Node 2) — `01-verify-hmac.js`
```js
const crypto = require('crypto');

const secret = $env.INTAKE_WEBHOOK_SECRET;
const sig    = $headers['x-tps-signature'];
const body   = JSON.stringify($json);

if (!secret) throw new Error('INTAKE_WEBHOOK_SECRET not configured');
if (!sig)    throw new Error('Missing X-TPS-Signature header');

const expected = crypto.createHmac('sha256', secret).update(body).digest('hex');
const a = Buffer.from(sig, 'utf8');
const b = Buffer.from(expected, 'utf8');

// Length-guard required: timingSafeEqual throws RangeError on length mismatch.
const ok = a.length === b.length && crypto.timingSafeEqual(a, b);
if (!ok) throw new Error('INVALID_SIGNATURE');

return $json;
```

### `normalizePayload` (Node 3) — `02-normalize-payload.js`
Coerces HubSpot's submission shape into a stable internal schema and applies source-derived field defaults so the score reflects them.

Key behaviors:
- `intake_*` → unprefixed internal field names (e.g. `intake_agency_track` → `agency_track`).
- Multi-select properties parsed as arrays.
- Dates parsed to `Date` objects.
- **FL funnel coercion:** if `intake_source_domain == thefltaxguy.cpa` and `intake_agency_track` is `unknown`/empty, set to `fdor` and default `intake_lane = fl_dor_sales_audit`. Runs here (before scoring) so the fit bonus is applied.

### `scoreContact` (Node 4) — `03-score-contact.js`
Implements the scoring rules from architecture §4C:
- Enforcement subtotal capped at **60** (multi-select can't blow past the envelope).
- Final score clamped to **[0, 100]**.

### `assignTier` (Node 5) — `04-assign-tier.js`
Top-down tier assignment matching architecture §4C. **Active enforcement is checked BEFORE the missing-critical-fields catch-all** — emergencies always win even if other fields are blank.

### `applySourceOverrides` (Node 6) — `05-apply-source-overrides.js`
Routing-only overrides (field defaults already applied in normalize):
- Advisor referral via `taxstrategist.cpa/for-advisors` → forced `book_case_review`, tier upgraded to `tier_2_qualified` (only upgrades from tier_3/tier_4/null — never downgrades tier_1).
- `keithjones.cpa` `/irs-help` urgent CTA: if routing would be `nurture_sequence` **or** `referral_out`, force `book_case_review` and upgrade tier.

---

## 4. Downstream actions

### `same_day_callback` branch
1. **HubSpot:updateContact** — set `triage_score`, `triage_tier`, `triage_routing_decision`, `triage_routing_reason`, `triage_assigned_owner = ON_CALL_OWNER_ID`, `lifecycle_stage_tps = mql_triaged`.
2. **Quo:SMS** — to `ON_CALL_PHONE`:
   ```
   URGENT TPS lead: {firstname} {lastname} | {agency_track} | {enforcement_status}
   {phone} | https://app.hubspot.com/contacts/{portalId}/contact/{hs_contact_id}
   ```
3. **Teams:postMessage** — adaptive card to `#tps-urgent` with score, summary, contact link.
4. **HubSpot:createTask** — assigned to on-call, due now, "URGENT — call within 1 hr".
5. **HubSpot:sendEmail** to prospect — confirms callback within 1 hr + fallback booking link.

### `book_case_review` branch
1. **HubSpot:updateContact** — `triage_assigned_owner = round-robin`.
2. **HubSpot:sendEmail** — booking invitation. Pick the domain-specific Meetings link based on `intake_source_domain`:
   ```
   ${MEETINGS_BASE_URL}/triage-keithjones?contact_id={hs_contact_id}   # canonical
   ${MEETINGS_BASE_URL}/triage-fltaxguy?contact_id={hs_contact_id}     # FL funnel
   ${MEETINGS_BASE_URL}/triage-strategist?contact_id={hs_contact_id}   # strategist
   ```
3. **HubSpot:enrollInWorkflow** — *Booking Reminder* (48h SLA, then escalate to manual_review).

### `manual_review` branch
1. **HubSpot:updateContact** — `triage_assigned_owner = OPS_QUEUE_OWNER_ID`, `lifecycle_stage_tps = mql_triaged`.
2. **HubSpot:createTask** — assigned to ops, due in 1 business day, body includes `triage_routing_reason`.
3. **Teams:postMessage** to `#tps-ops` with field-level reason.

### `nurture_sequence` branch
1. **HubSpot:updateContact** — `lifecycle_stage_tps = lead`.
2. **HubSpot:enrollInWorkflow** — *Educational Nurture* (6 touches; promotion threshold defined in HubSpot).

### `referral_out` branch
1. **HubSpot:updateContact** — `lifecycle_stage_tps = closed_lost`, `triage_routing_decision = referral_out`.
2. **HubSpot:sendEmail** — referral template (IRS self-help / VITA / partner network depending on `agency_track`).

---

## 5. Quo voice & SMS inbound bridge

Detailed setup is in `quo-bridge-spec.md`. Workflow integration summary:

```
[Q1] Webhook (POST /quo-inbound/v1)
       │
[Q2] verifyHmac (same secret)
       │
[Q3] Function: quoNormalize
       │   - DID → intake_source_domain via static map
       │   - ANI → phone (E.164)
       │   - event_type → intake_channel (quo_voice | quo_sms)
       │   - body → intake_notes (for SMS only)
       │
[Q4] HubSpot:upsertContact (dedupe on phone)
       │   - sets intake_channel, quo_phone_number_routed, intake_source_domain
       │   - sets utm_landing_path = "(quo_inbound)"
       │
[Q5] Branch on event_type
       ├── voice → [Q6] Teams alert + create HubSpot task
       │            (no scoring yet — wait for follow-up intake form completion)
       └── sms   → [Q7] route into the same scoreContact → assignTier pipeline
                   (SMS leads have less data; many will land in manual_review,
                    which is correct — humans triage from there)
```

---

## 6. Importable n8n workflow JSON (skeleton)

Trim or extend in the n8n editor. Function nodes contain the code from §3.

```json
{
  "name": "tps_intake_router_v1",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "intake/v1",
        "responseMode": "lastNode",
        "options": { "responseHeaders": { "entries": [{ "name": "X-TPS-Router", "value": "v1" }] } }
      },
      "name": "Webhook",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 2,
      "position": [200, 300],
      "webhookId": "intake-v1"
    },
    {
      "parameters": { "functionCode": "// paste from scripts/n8n/functions/01-verify-hmac.js" },
      "name": "verifyHmac",
      "type": "n8n-nodes-base.function",
      "typeVersion": 1,
      "position": [420, 300]
    },
    {
      "parameters": { "functionCode": "// paste from scripts/n8n/functions/02-normalize-payload.js" },
      "name": "normalizePayload",
      "type": "n8n-nodes-base.function",
      "typeVersion": 1,
      "position": [640, 300]
    },
    {
      "parameters": { "functionCode": "// paste from scripts/n8n/functions/03-score-contact.js" },
      "name": "scoreContact",
      "type": "n8n-nodes-base.function",
      "typeVersion": 1,
      "position": [860, 300]
    },
    {
      "parameters": { "functionCode": "// paste from scripts/n8n/functions/04-assign-tier.js" },
      "name": "assignTier",
      "type": "n8n-nodes-base.function",
      "typeVersion": 1,
      "position": [1080, 300]
    },
    {
      "parameters": { "functionCode": "// paste from scripts/n8n/functions/05-apply-source-overrides.js" },
      "name": "applySourceOverrides",
      "type": "n8n-nodes-base.function",
      "typeVersion": 1,
      "position": [1300, 300]
    },
    {
      "parameters": {
        "dataType": "string",
        "value1": "={{$json[\"triage_routing_decision\"]}}",
        "rules": {
          "rules": [
            { "operation": "equal", "value2": "same_day_callback", "output": 0 },
            { "operation": "equal", "value2": "book_case_review",  "output": 1 },
            { "operation": "equal", "value2": "manual_review",     "output": 2 },
            { "operation": "equal", "value2": "nurture_sequence",  "output": 3 },
            { "operation": "equal", "value2": "referral_out",      "output": 4 }
          ]
        }
      },
      "name": "routeSwitch",
      "type": "n8n-nodes-base.switch",
      "typeVersion": 1,
      "position": [1520, 300]
    }
  ],
  "connections": {
    "Webhook":              { "main": [[{ "node": "verifyHmac",          "type": "main", "index": 0 }]] },
    "verifyHmac":           { "main": [[{ "node": "normalizePayload",    "type": "main", "index": 0 }]] },
    "normalizePayload":     { "main": [[{ "node": "scoreContact",        "type": "main", "index": 0 }]] },
    "scoreContact":         { "main": [[{ "node": "assignTier",          "type": "main", "index": 0 }]] },
    "assignTier":           { "main": [[{ "node": "applySourceOverrides","type": "main", "index": 0 }]] },
    "applySourceOverrides": { "main": [[{ "node": "routeSwitch",         "type": "main", "index": 0 }]] }
  },
  "settings": { "executionOrder": "v1" },
  "active": false
}
```

After importing, add the five downstream branches off `routeSwitch` outputs 0–4 using HubSpot, Quo, and Microsoft Teams nodes per §4. Add an Error Trigger node that posts to `#tps-eng-alerts` if any branch fails.

---

## 7. Test plan

| Scenario | Expected `triage_routing_decision` | Expected `triage_tier` |
|---|---|---|
| FL S-corp, `bank_levy`, $100k–250k | `same_day_callback` | `tier_1_emergency` |
| Active levy with missing `agency_track` | `same_day_callback` | `tier_1_emergency` (emergency wins over missing-fields catch-all) |
| IRS individual, `lien_filed`, $50k–100k, deadline in 10 days | `book_case_review` (score ~58) | `tier_2_qualified` |
| `other_state` LLC, `lien_filed`, $100k–250k (score 40–69, fails fit) | `manual_review` | `null` |
| IRS individual, no enforcement, `under_10k` | `referral_out` | `tier_4_disqualified` |
| `thefltaxguy.cpa` lead, `agency_track = unknown` | route as FDOR | per score |
| `taxstrategist.cpa` `/for-advisors` referral | `book_case_review` regardless of score | `tier_2_qualified` |
| `keithjones.cpa` `/irs-help` urgent CTA, `under_10k`, no enforcement | `book_case_review` (urgent floor) | `tier_2_qualified` |
| Submission missing `agency_track`, no enforcement | `manual_review` | `null` |

The harness at `scripts/n8n/test/test-routing.js` runs eleven such scenarios end-to-end against the actual function-node code. `node test/test-routing.js` from `scripts/n8n/`. Currently 25/25 assertions pass.

---

## 8. Deployment

1. Import the JSON skeleton into n8n.
2. Set the env vars in §2 (Azure Key Vault → n8n container env).
3. Paste function code from `scripts/n8n/functions/` into the five Function nodes.
4. Wire up downstream branches per §4.
5. Activate the workflow.
6. In HubSpot, configure the post-form workflow to send the webhook with the HMAC signature header (use HubSpot's "custom code" action to compute the signature with `INTAKE_WEBHOOK_SECRET`).
7. Provision Quo DIDs and webhook per `quo-bridge-spec.md`.
8. Submit a test intake from each of the three domains and from each of the three Quo DIDs; confirm contact properties update and Tier 1 alerts fire end-to-end.
