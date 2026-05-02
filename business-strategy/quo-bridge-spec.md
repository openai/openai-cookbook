# Quo.com Voice & SMS Bridge — `tps_quo_bridge_v1`

Companion to `multi-domain-intake-architecture.md` §5 and `n8n-routing-workflow.md`. Defines the three-DID provisioning, the Quo → n8n webhook contract, and the contact-upsert + routing path for inbound voice and SMS.

**Hosting:** n8n on Azure VM. Quo.com is a third-party data handler under WISP (GLBA 16 CFR §314.4(f)) — confirm SOC 2 Type II + signed BAA-equivalent confidentiality / data-handling agreement before any client data flows.

---

## 1. DID provisioning

Provision **three Quo DIDs**, one per domain. Each maps 1:1 to `intake_source_domain` and is displayed only on its own site (header / footer / contact page).

| Domain | DID purpose | Display | Maps to `intake_source_domain` |
|---|---|---|---|
| `keithjones.cpa` | Canonical brand | All canonical pages | `keithjones.cpa` |
| `thefltaxguy.cpa` | FL geo / TOFU | All FL funnel pages | `thefltaxguy.cpa` |
| `taxstrategist.cpa` | Strategist / advisor channel | Strategist pages, advisor page | `taxstrategist.cpa` |

**DID → domain map** (configured in n8n via env or static lookup):

```js
const DID_TO_DOMAIN = {
  '+1XXXXXXXXXX': 'keithjones.cpa',     // canonical
  '+1XXXXXXXXXX': 'thefltaxguy.cpa',    // FL
  '+1XXXXXXXXXX': 'taxstrategist.cpa',  // strategist
};
```

**Display rule:** never share a DID across domains; never display a non-mapped DID.

---

## 2. AI receptionist greetings (domain-aware)

Same human handles all calls; only the greeting changes by DID.

| DID | Greeting (illustrative) |
|---|---|
| `keithjones.cpa` | *"Thank you for calling Keith Jones, CPA. How can we help with your tax problem today?"* |
| `thefltaxguy.cpa` | *"Thank you for calling The Florida Tax Guy. How can we help with your Florida tax matter today?"* |
| `taxstrategist.cpa` | *"Thank you for calling Tax Strategist. Are you reaching out for proactive planning or for a referral?"* |

The receptionist captures: caller intent (1 sentence), preferred callback time, urgency (yes/no), and optional notice type. These pass into the webhook body for n8n classification.

---

## 3. Inbound webhook contract (Quo → n8n)

**Endpoint:** `POST https://n8n.<azure-vm>/webhook/quo-inbound/v1`
**Auth:** HMAC `X-TPS-Signature: sha256=<hex>` over the **exact raw body bytes Quo transmits**, using `INTAKE_WEBHOOK_SECRET`. The receiving n8n Webhook node must be configured with **Options → Binary Data: true** so verifyHmac compares against the wire bytes, not a re-serialization of the parsed JSON. See `n8n-routing-workflow.md` §3 verifyHmac notes.
**Content-Type:** `application/json`

### Voice event payload
```json
{
  "event_type": "quo.voice.completed",
  "event_id": "evt_abc123",
  "occurred_at": "2026-05-02T14:33:00Z",
  "did": "+1XXXXXXXXXX",
  "ani": "+1YYYYYYYYYY",
  "duration_seconds": 412,
  "recording_url": "https://files.quo.com/...",
  "transcript_url": "https://files.quo.com/...",
  "ai_summary": {
    "intent_sentence": "Caller received an FDOR DR-840 audit notice for 2023 sales tax.",
    "agency_hint": "fdor",
    "lane_hint": "fl_dor_sales_audit",
    "urgency": true,
    "preferred_callback_time": "today after 3pm ET",
    "notice_type_mentioned": ["FL_DR-840"]
  },
  "caller": {
    "name": "Maria Garcia",
    "phone": "+1YYYYYYYYYY",
    "email": null
  }
}
```

### SMS event payload
```json
{
  "event_type": "quo.sms.received",
  "event_id": "evt_xyz789",
  "occurred_at": "2026-05-02T14:36:00Z",
  "did": "+1XXXXXXXXXX",
  "ani": "+1YYYYYYYYYY",
  "body": "Hi - got a CP504 today, what do I do?",
  "ai_summary": {
    "intent_sentence": "IRS CP504 final notice received; requests guidance.",
    "agency_hint": "irs",
    "lane_hint": "irs_collections",
    "urgency": true,
    "notice_type_mentioned": ["CP504"]
  },
  "caller": { "name": null, "phone": "+1YYYYYYYYYY", "email": null }
}
```

---

## 4. n8n flow — `tps_quo_bridge_v1`

```
[Q1] Webhook (POST /quo-inbound/v1)
       │
[Q2] verifyHmac (shared secret)
       │
[Q3] Function: quoNormalize
       │  - DID → intake_source_domain (DID_TO_DOMAIN)
       │  - event_type → intake_channel ("quo_voice" | "quo_sms")
       │  - ai_summary.agency_hint → intake_agency_track (if not already set)
       │  - ai_summary.lane_hint → intake_lane (if not already set)
       │  - ai_summary.notice_type_mentioned → intake_notice_type (additive)
       │  - body / intent_sentence → intake_notes
       │
[Q4] HubSpot:upsertContact (dedupe on phone, fallback to email if present)
       │  Properties set:
       │   - phone, firstname, lastname (if present)
       │   - intake_source_domain, intake_channel, quo_phone_number_routed = did
       │   - intake_agency_track, intake_lane, intake_notice_type (if hints provided)
       │   - utm_landing_path = "(quo_inbound)"
       │   - intake_completed_at = occurred_at
       │   - intake_form_version = "quo_v1"
       │
[Q5] Branch on event_type
       ├── voice → [Q6a] Teams alert to #tps-urgent (always)
       │            [Q6b] HubSpot:createTask "Returning Quo voice call from {firstname}"
       │            [Q6c] HubSpot:logActivity (call) with recording + transcript URLs
       │            (no scoring yet — wait for follow-up intake form)
       │
       └── sms   → [Q7a] Run scoreContact + assignTier + applySourceOverrides
                   [Q7b] If routing == same_day_callback:
                          - Quo:SMS reply "We'll call you within the hour"
                          - Teams alert to #tps-urgent
                          - HubSpot:createTask URGENT
                   [Q7c] Else if routing == book_case_review:
                          - Quo:SMS reply with /triage-{domain} link
                   [Q7d] Else:
                          - HubSpot:createTask for human triage
```

---

## 5. Function node — `quoNormalize`

```js
// n8n Function node — quoNormalize
// Maps Quo inbound payloads to the same internal field shape used by
// 02-normalize-payload.js so downstream nodes can be reused.
//
// Env: QUO_DID_KEITHJONES, QUO_DID_FLTAXGUY, QUO_DID_STRATEGIST
//
// Inputs:  verified Quo webhook payload
// Outputs: { hs_contact_id: null, submitted_at, fields: {...} }

const DID_TO_DOMAIN = {
  [$env.QUO_DID_KEITHJONES]: 'keithjones.cpa',
  [$env.QUO_DID_FLTAXGUY]:   'thefltaxguy.cpa',
  [$env.QUO_DID_STRATEGIST]: 'taxstrategist.cpa',
};

const ev = $json;
const did = ev.did;
const sourceDomain = DID_TO_DOMAIN[did] || 'keithjones.cpa';
const channel = ev.event_type && ev.event_type.startsWith('quo.voice') ? 'quo_voice' : 'quo_sms';

const ai = ev.ai_summary || {};
const caller = ev.caller || {};

const fields = {
  email:                    caller.email || null,
  phone:                    ev.ani || caller.phone || null,
  firstname:                (caller.name || '').split(' ')[0] || null,
  lastname:                 (caller.name || '').split(' ').slice(1).join(' ') || null,

  source_domain:            sourceDomain,
  source_site_group:        ({
    'keithjones.cpa':    'primary_canonical',
    'thefltaxguy.cpa':   'secondary_florida_funnel',
    'taxstrategist.cpa': 'secondary_authority',
  })[sourceDomain],
  source_offer:             null,
  channel,
  utm_landing_path:         '(quo_inbound)',
  quo_phone_number_routed:  did,

  existing_client_status:   null,
  agency_track:             ai.agency_hint || null,
  lane:                     ai.lane_hint || null,
  primary_issue_family:     null,
  notice_type:              ai.notice_type_mentioned || [],
  enforcement_status:       ai.urgency ? ['levy_active'] : [],  // conservative — humans verify
  enforcement_deadline:     null,
  tax_years_owed:           null,
  balance_range:            null,
  returns_unfiled_count:    null,
  contacted_by_ro:          null,
  prior_representation:     null,
  state_of_residence:       null,
  entity_type:              null,
  qualifying_signal_count:  null,
  intake_notes:             ai.intent_sentence || ev.body || null,
};

// Apply the same FL-funnel default that 02-normalize-payload uses,
// so Quo and web-form leads score consistently.
if (
  fields.source_domain === 'thefltaxguy.cpa' &&
  (!fields.agency_track || fields.agency_track === 'unknown')
) {
  fields.agency_track = 'fdor';
  if (!fields.lane) fields.lane = 'fl_dor_sales_audit';
}

return {
  hs_contact_id: null,
  submitted_at:  ev.occurred_at,
  fields,
};
```

> **Caveat on `enforcement_status`:** the Quo AI summary's `urgency` boolean is a soft signal. Setting `levy_active` here will trip the Tier 1 emergency check, which is the safe default — operators verify and clear false positives at first contact. Tighten this rule once we have a labeled corpus from real calls.

---

## 6. HubSpot upsert — dedupe rules

When n8n hits HubSpot from the Quo bridge:

1. **Lookup by phone (E.164).** If found → update.
2. **Else lookup by email** if Quo captured it. If found → update.
3. **Else create** with the Quo-supplied phone + name.

Set `intake_channel`, `quo_phone_number_routed`, and `intake_source_domain` on every upsert (overwrite is fine — most recent inbound wins for these specifically).

For `intake_agency_track`, `intake_lane`, and `intake_notice_type`: only write if the existing contact value is empty. Don't overwrite human-curated values with AI-derived hints.

---

## 7. Outbound SMS via Quo

For Tier 1 alerts and booking reminders, send SMS through Quo's outbound endpoint:

```
POST https://api.quo.com/v1/sms/send
Authorization: Bearer ${QUO_API_KEY}

{
  "from": "${QUO_FROM_NUMBER}",   // a dedicated alert DID, separate from the three brand DIDs
  "to":   "${ON_CALL_PHONE}",
  "body": "URGENT TPS lead: ..."
}
```

Use a **dedicated alert DID** for outbound — not one of the three brand DIDs — so caller-ID on inbound stays clean and brand-aligned.

---

## 8. Provisioning checklist

- [ ] Confirm Quo SOC 2 Type II + signed data-handling agreement.
- [ ] Provision 3 brand DIDs + 1 alert DID.
- [ ] Configure domain-aware AI receptionist greetings per §2.
- [ ] Configure Quo → n8n webhook URL + HMAC secret.
- [ ] Add `QUO_DID_KEITHJONES`, `QUO_DID_FLTAXGUY`, `QUO_DID_STRATEGIST`, `QUO_FROM_NUMBER`, `QUO_API_KEY`, `QUO_API_BASE` to Azure Key Vault.
- [ ] Build `tps_quo_bridge_v1` workflow in n8n.
- [ ] Update each domain's contact page + footer to display its mapped DID only.
- [ ] Smoke-test: place one call and one SMS to each DID; verify HubSpot contact created with correct `intake_source_domain`, `intake_channel`, `quo_phone_number_routed`.
- [ ] Add Quo to the WISP vendor list.

---

## 9. Open decisions

| Decision | Why it matters |
|---|---|
| Final 3 brand DIDs | Configures the static map in §1 + receptionist scripts. |
| Alert DID | Outbound Tier 1 SMS sender — must not collide with brand DIDs. |
| AI receptionist scripts | Final wording per domain; legal review for any disclaimers. |
| `urgency` heuristic refinement | Replace conservative `urgency → levy_active` mapping once labeled data exists. |
