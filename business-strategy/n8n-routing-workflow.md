# n8n Routing Workflow — `tps_intake_router_v1`

Companion to `multi-domain-intake-architecture.md` and `hubspot-intake-form-spec.md`. Defines the n8n workflow that consumes the HubSpot intake webhook, scores the contact, and dispatches the routing decision back to HubSpot + downstream channels.

**Webhook path:** `POST /webhook/intake/v1`
**Auth:** HMAC header `X-TPS-Signature` validated against `INTAKE_WEBHOOK_SECRET`.
**Outputs:** HubSpot contact update, Twilio SMS (Tier 1 only), Microsoft Teams alert (Tier 1 only), email task assignment via HubSpot.

---

## 1. Node-by-node walkthrough

```
[1] Webhook (POST /intake/v1)
       │
[2] Function: verifyHmac           ─── on failure → [F1] Respond 401
       │
[3] Function: normalizePayload     (lowercase enums, coerce arrays, parse dates)
       │
[4] Function: scoreContact         (implements §4C of architecture spec)
       │
[5] Function: assignTier           (implements tier mapping table, top-down)
       │
[6] Function: applySourceOverrides (FDOR domain, advisor referral, etc.)
       │
[7] Switch: routing_decision
       ├── same_day_callback ──► [8a] HubSpot:updateContact ─► [9a] Twilio:SMS ─► [10a] Teams:postMessage ─► [11a] HubSpot:createTask(URGENT)
       ├── book_case_review  ──► [8b] HubSpot:updateContact ─► [9b] HubSpot:sendEmail(booking link)
       ├── manual_review     ──► [8c] HubSpot:updateContact ─► [9c] HubSpot:createTask(ops queue)
       ├── nurture_sequence  ──► [8d] HubSpot:updateContact ─► [9d] HubSpot:enrollInWorkflow(nurture)
       └── referral_out      ──► [8e] HubSpot:updateContact ─► [9e] HubSpot:sendEmail(referral)
       │
[12] Respond 200 (with routing_decision + score for HubSpot's webhook log)
```

---

## 2. Required environment variables

| Var | Purpose |
|---|---|
| `INTAKE_WEBHOOK_SECRET` | HMAC shared secret with HubSpot |
| `HUBSPOT_PRIVATE_APP_TOKEN` | HubSpot CRM API token (Contacts: read/write, Workflows: enroll, Tasks: write) |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM_NUMBER` | SMS sender |
| `ON_CALL_PHONE` | E.164 number for Tier 1 SMS |
| `TEAMS_WEBHOOK_URL` | Incoming-webhook URL for `#tps-urgent` |
| `OPS_QUEUE_OWNER_ID` | HubSpot owner ID for manual-review queue |
| `ON_CALL_OWNER_ID` | HubSpot owner ID for Tier 1 routing |
| `BOOKING_URL_BASE` | `https://keithjones.cpa/meetings/case-review` |

---

## 3. Function node code

### `verifyHmac` (Node 2)
```js
const crypto = require('crypto');
const secret = $env.INTAKE_WEBHOOK_SECRET;
const sig    = $headers['x-tps-signature'];
const body   = JSON.stringify($json); // n8n parses JSON; re-stringify deterministically

const expected = crypto.createHmac('sha256', secret).update(body).digest('hex');
const ok = sig && crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected));
if (!ok) {
  throw new Error('INVALID_SIGNATURE');
}
return $json;
```

### `normalizePayload` (Node 3)
```js
const f = $json.fields || {};

const arr = (v) => Array.isArray(v) ? v : (v ? String(v).split(';').map(s => s.trim()) : []);
const lower = (v) => (v == null ? null : String(v).toLowerCase());
const num = (v) => (v == null || v === '' ? null : Number(v));

return {
  hs_contact_id: $json.hs_contact_id,
  submitted_at:  $json.submitted_at,
  fields: {
    email:                    f.email,
    phone:                    f.phone,
    firstname:                f.firstname,
    lastname:                 f.lastname,
    source_domain:            lower(f.tps_source_domain),
    source_site_group:        lower(f.tps_source_site_group),
    source_offer:             lower(f.tps_source_offer),
    existing_client_status:   lower(f.tps_existing_client_status),
    agency_track:             lower(f.tps_agency_track),
    primary_service_line:     lower(f.tps_primary_service_line),
    primary_issue_family:     lower(f.tps_primary_issue_family),
    notice_type:              arr(f.tps_notice_type).map(lower),
    enforcement_status:       arr(f.tps_enforcement_status).map(lower),
    enforcement_deadline:     f.tps_enforcement_deadline ? new Date(f.tps_enforcement_deadline) : null,
    tax_years_owed:           f.tps_tax_years_owed,
    balance_range:            lower(f.tps_balance_range),
    returns_unfiled_count:    num(f.tps_returns_unfiled_count),
    has_been_contacted_by_ro: lower(f.tps_has_been_contacted_by_revenue_officer),
    prior_representation:     lower(f.tps_prior_representation),
    state_of_residence:       (f.tps_state_of_residence || '').toUpperCase(),
    entity_type:              lower(f.tps_entity_type),
    intake_notes:             f.tps_intake_notes
  }
};
```

### `scoreContact` (Node 4)
Implements the scoring rules from architecture §4C, including the enforcement subtotal cap and final 0–100 clamp.

```js
const f = $json.fields;
const inc = (set, v) => Array.isArray(set) && set.indexOf(v) > -1;

let score = 0;

// Enforcement urgency — cap at 60
let enforcementSub = 0;
if (inc(f.enforcement_status, 'levy_active'))         enforcementSub += 35;
if (inc(f.enforcement_status, 'wage_garnishment'))    enforcementSub += 35;
if (inc(f.enforcement_status, 'bank_levy'))           enforcementSub += 30;
if (inc(f.enforcement_status, 'warrant_filed'))       enforcementSub += 25;
if (inc(f.enforcement_status, 'lien_filed'))          enforcementSub += 15;
if (inc(f.enforcement_status, 'passport_revocation')) enforcementSub += 25;

if (f.enforcement_deadline) {
  const days = Math.floor((f.enforcement_deadline - new Date()) / 864e5);
  if (days >= 0 && days <= 14) enforcementSub += 15;
}
score += Math.min(enforcementSub, 60);

// Balance signal
const balanceMap = { 'over_250k': 20, '100k_250k': 16, '50k_100k': 12, '25k_50k': 8, '10k_25k': 4 };
score += balanceMap[f.balance_range] || 0;

// Fit signal — uses agency_track consistently
if (['irs','fdor','both'].includes(f.agency_track)) score += 10;
if (f.state_of_residence === 'FL' && ['fdor','both'].includes(f.agency_track)) score += 5;
if (['s_corp','multi_member_llc','c_corp'].includes(f.entity_type)) score += 5;

// Negative signals
const noEnforcement = !f.enforcement_status || f.enforcement_status.length === 0
  || (f.enforcement_status.length === 1 && f.enforcement_status[0] === 'none');
if (f.balance_range === 'under_10k' && noEnforcement) score -= 20;
// (national_firm + previously declined consult requires a HubSpot lookup; deferred to v2)

// Final clamp — matches the documented 0–100 range
score = Math.max(0, Math.min(100, score));

return Object.assign({}, $json, { triage_score: score, no_enforcement: noEnforcement });
```

### `assignTier` (Node 5)
Top-down evaluation matching the tier table in architecture §4C.

```js
const f = $json.fields;
const score = $json.triage_score;
const noEnf = $json.no_enforcement;

const activeEnforcement = ['levy_active','wage_garnishment','bank_levy','warrant_filed']
  .some(s => f.enforcement_status.includes(s));

const validAgency = ['irs','fdor','both'].includes(f.agency_track);
const hasBalance  = f.balance_range && f.balance_range !== 'under_10k';

// Catch-all: critical fields missing
const missingCritical = !f.agency_track || !f.balance_range || !f.primary_issue_family;

let tier, routing, reason;

if (missingCritical) {
  tier = null; routing = 'manual_review'; reason = 'missing_critical_fields';
} else if (activeEnforcement || score >= 70) {
  tier = 'tier_1_emergency'; routing = 'same_day_callback'; reason = activeEnforcement ? 'active_enforcement' : 'high_score';
} else if (score >= 40 && validAgency && hasBalance) {
  tier = 'tier_2_qualified'; routing = 'book_case_review'; reason = 'qualified_score';
} else if (score >= 40) {
  tier = null; routing = 'manual_review'; reason = 'score_in_band_but_unclear_fit';
} else if (score >= 15) {
  tier = 'tier_3_nurture'; routing = 'nurture_sequence'; reason = 'low_score';
} else {
  tier = 'tier_4_disqualified'; routing = 'referral_out';
  reason = (f.balance_range === 'under_10k' && noEnf) ? 'small_balance_no_enforcement' : 'very_low_score';
}

return Object.assign({}, $json, { tier, routing_decision: routing, routing_reason: reason });
```

### `applySourceOverrides` (Node 6)

```js
const out = JSON.parse(JSON.stringify($json));
const src = out.fields.source_domain;
const offer = out.fields.source_offer;
const existing = out.fields.existing_client_status;

// Florida funnel: if agency unknown, assume FDOR
if (src === 'floridataxsavior.com' && (!out.fields.agency_track || out.fields.agency_track === 'unknown')) {
  out.fields.agency_track = 'fdor';
  out.routing_reason = (out.routing_reason || '') + '|fdor_default_from_source';
}

// Advisor referrals always get a meeting
if (src === 'taxstrategist.cpa' && (offer === 'advisor_referral' || existing === 'referral')) {
  out.routing_decision = 'book_case_review';
  out.tier = out.tier || 'tier_2_qualified';
  out.routing_reason = (out.routing_reason || '') + '|advisor_override';
}

// keithjones.cpa /irs-help urgent CTA: floor at tier 2
if (src === 'keithjones.cpa' && offer === 'urgent_triage' && out.routing_decision === 'nurture_sequence') {
  out.routing_decision = 'book_case_review';
  out.tier = out.tier || 'tier_2_qualified';
  out.routing_reason += '|urgent_page_floor';
}

return out;
```

---

## 4. Downstream actions

### `same_day_callback` branch
1. **HubSpot:updateContact** — set `tps_triage_score`, `tps_triage_tier`, `tps_routing_decision`, `tps_routing_reason`, `tps_assigned_owner = ON_CALL_OWNER_ID`, `tps_lifecycle_stage = mql_triaged`.
2. **Twilio:SMS** — to `ON_CALL_PHONE`:
   ```
   URGENT TPS lead: {firstname} {lastname} | {agency_track} | {enforcement_status}
   {phone} | https://app.hubspot.com/contacts/{portalId}/contact/{hs_contact_id}
   ```
3. **Teams:postMessage** — adaptive card to `#tps-urgent` with score, summary, contact link.
4. **HubSpot:createTask** — assigned to on-call, due now, "URGENT — call within 1 hr".
5. **HubSpot:sendEmail** to prospect — confirms callback within 1 hr + fallback booking link.

### `book_case_review` branch
1. **HubSpot:updateContact** — same as above with `tps_assigned_owner = round-robin`.
2. **HubSpot:sendEmail** — booking invitation with prefilled link:
   `${BOOKING_URL_BASE}?contact_id={hs_contact_id}&src_domain={source_domain}`
3. **HubSpot:enrollInWorkflow** — *Booking Reminder* workflow (48h SLA, then escalate to manual_review).

### `manual_review` branch
1. **HubSpot:updateContact** — `tps_assigned_owner = OPS_QUEUE_OWNER_ID`, `tps_lifecycle_stage = mql_triaged`.
2. **HubSpot:createTask** — assigned to ops, due in 1 business day, body includes `routing_reason` for context.

### `nurture_sequence` branch
1. **HubSpot:updateContact** — `tps_lifecycle_stage = lead`.
2. **HubSpot:enrollInWorkflow** — *Educational Nurture* workflow (6 touches; promotion threshold defined in HubSpot).

### `referral_out` branch
1. **HubSpot:updateContact** — `tps_lifecycle_stage = closed_lost`, `tps_routing_decision = referral_out`.
2. **HubSpot:sendEmail** — referral template (IRS self-help / VITA / partner network depending on `agency_track`).

---

## 5. Importable n8n workflow JSON (skeleton)

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
      "parameters": { "functionCode": "// paste verifyHmac from §3" },
      "name": "verifyHmac",
      "type": "n8n-nodes-base.function",
      "typeVersion": 1,
      "position": [420, 300]
    },
    {
      "parameters": { "functionCode": "// paste normalizePayload from §3" },
      "name": "normalizePayload",
      "type": "n8n-nodes-base.function",
      "typeVersion": 1,
      "position": [640, 300]
    },
    {
      "parameters": { "functionCode": "// paste scoreContact from §3" },
      "name": "scoreContact",
      "type": "n8n-nodes-base.function",
      "typeVersion": 1,
      "position": [860, 300]
    },
    {
      "parameters": { "functionCode": "// paste assignTier from §3" },
      "name": "assignTier",
      "type": "n8n-nodes-base.function",
      "typeVersion": 1,
      "position": [1080, 300]
    },
    {
      "parameters": { "functionCode": "// paste applySourceOverrides from §3" },
      "name": "applySourceOverrides",
      "type": "n8n-nodes-base.function",
      "typeVersion": 1,
      "position": [1300, 300]
    },
    {
      "parameters": {
        "dataType": "string",
        "value1": "={{$json[\"routing_decision\"]}}",
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

After importing, add the five downstream branches off `routeSwitch` outputs 0–4 using HubSpot, Twilio, and Microsoft Teams nodes per §4. Add an Error Trigger node that posts to `#tps-eng-alerts` if any branch fails.

---

## 6. Test plan

| Scenario | Expected `routing_decision` | Expected `tier` |
|---|---|---|
| FL S-corp, `bank_levy`, $100k–250k | `same_day_callback` | `tier_1_emergency` |
| IRS individual, `lien_filed`, $50k–100k, deadline in 10 days | `book_case_review` (score ~58) | `tier_2_qualified` |
| `other_state` LLC, `lien_filed`, $100k–250k (score 40–69, fails fit) | `manual_review` | `null` |
| IRS individual, no enforcement, `under_10k` | `referral_out` | `tier_4_disqualified` |
| `floridataxsavior.com` lead, `agency_track = unknown` | route as FDOR | per score |
| `taxstrategist.cpa` `/for-advisors` referral | `book_case_review` regardless of score | `tier_2_qualified` |
| Submission missing `agency_track` | `manual_review` | `null` |

Run each through n8n's "Test workflow" with sample payloads from `hubspot-intake-form-spec.md` §7.

---

## 7. Deployment

1. Import the JSON skeleton into n8n.
2. Set the env vars in §2.
3. Paste function code into the four Function nodes.
4. Wire up downstream branches per §4.
5. Activate the workflow.
6. In HubSpot, configure the post-form workflow to send the webhook with the HMAC signature header (use HubSpot's "custom code" action to compute the signature with `INTAKE_WEBHOOK_SECRET`).
7. Submit a test intake from each of the three domains; confirm contact properties update and Tier 1 alerts fire end-to-end.
