# HubSpot Intake Form Spec — `keithjones.cpa/case-review`

Companion to `multi-domain-intake-architecture.md`. Defines the single canonical intake form: fields, conditional logic, hidden fields, embed, and URL-parameter pre-fill.

**Form internal name:** `tps_case_review_intake_v1`
**Submit destination:** HubSpot contact (create-or-update on email, fallback phone) → fires webhook to n8n `/intake/v1`.
**Embed locations:** `keithjones.cpa/case-review` (primary), inline capture on `thefltaxguy.cpa` and `taxstrategist.cpa` (same form GUID; `intake_source_domain` set from the embedding hostname).

---

## 1. Field list (in display order)

Required fields are marked `*`. Internal names match the property internal names in `multi-domain-intake-architecture.md` §3.

### Step 1 — Identify
| Label | Type | Internal name | Required | Notes |
|---|---|---|---|---|
| First name | Single-line text | `firstname` | * | Standard HubSpot |
| Last name | Single-line text | `lastname` | * | Standard HubSpot |
| Email | Email | `email` | * | Dedupe key |
| Mobile phone | Phone | `phone` | * | Used for SMS triage via Quo |
| State of residence | Dropdown | `intake_state_of_residence` | * | US states + `non_us` |
| Are you currently a client? | Radio | `intake_existing_client_status` | * | `new_prospect` / `existing_client` / `former_client` / `referral` |

### Step 2 — Agency, lane, service
| Label | Type | Internal name | Required | Notes |
|---|---|---|---|---|
| Which tax authority is involved? | Radio | `intake_agency_track` | * | `irs` / `fdor` / `both` / `other_state` / `unknown` |
| What's the main issue? | Dropdown | `intake_primary_issue_family` | * | See §3B options in architecture |
| Which best describes your case? | Dropdown | `intake_lane` | * (auto-suggested from issue + agency) | `irs_collections` · `irs_audit` · `unfiled_returns` · `payroll_tfrp` · `fl_dor_sales_audit` · `fl_dor_voluntary_disclosure` · `planning` · `unqualified` |
| Type of taxpayer | Radio | `intake_entity_type` | * | individual / sole_prop / single_member_llc / multi_member_llc / s_corp / c_corp / partnership / nonprofit |

### Step 3 — Notice & enforcement
| Label | Type | Internal name | Required | Conditional |
|---|---|---|---|---|
| Did you receive a notice? Which one(s)? | Multi-checkbox | `intake_notice_type` | conditional | Show if `intake_primary_issue_family` ∈ {notice, collections, audit, sales_tax_exposure} |
| Upload notice photos / PDFs | File upload (multi) | `intake_notice_files` | optional | Always show; max 10 files, 25 MB each |
| Are any of these happening now? | Multi-checkbox | `intake_enforcement_status` | * | Options as in architecture §3B; `none` is mutually exclusive |
| If there's a deadline, when? | Date | `intake_enforcement_deadline` | conditional | Show if `intake_enforcement_status` ≠ `none` only |

### Step 4 — Scope & history
| Label | Type | Internal name | Required | Conditional |
|---|---|---|---|---|
| What years are involved? | Single-line text | `intake_tax_years_owed` | * | Free-form: `"2019, 2021–2023"` |
| Estimated total balance owed | Dropdown | `intake_balance_range` | * | See §3B options in architecture |
| Number of unfiled returns | Number | `intake_returns_unfiled_count` | conditional | Show if issue family ∈ {filing_problem, collections} |
| Has a Revenue Officer contacted you? | Radio | `intake_contacted_by_revenue_officer` | conditional | Show if `intake_agency_track` ∈ {irs, both} |
| Any prior representation? | Radio | `intake_prior_representation` | * | none / cpa / attorney / enrolled_agent / national_firm |

### Step 5 — Consent & notes
| Label | Type | Internal name | Required | Notes |
|---|---|---|---|---|
| Anything else we should know? | Multi-line text | `intake_notes` | optional | Free-form |
| I agree to be contacted by phone, SMS, and email | Single checkbox | `intake_consent_contact` | * | TCPA |
| I understand this is not engagement until a written agreement is signed | Single checkbox | `intake_consent_no_engagement` | * | Engagement disclaimer |

### Hidden fields (always set, never visible)
| Internal name | Source |
|---|---|
| `intake_source_domain` | URL `?src_domain=` or embedding hostname |
| `intake_source_site_group` | Derived from `src_domain` (see JS in §4) |
| `intake_channel` | Hard-coded `web_form` for the web form; set by n8n on Quo / Meetings paths |
| `intake_source_page_type` | URL `?page_type=` |
| `intake_source_offer` | URL `?offer=` |
| `intake_source_campaign` | URL `?utm_campaign=` |
| `intake_source_cta_variant` | URL `?cta=` |
| `utm_landing_path` | First-touch path |
| `intake_first_touch_url` | First-touch cookie (see §4) |
| `intake_latest_funnel_url` | `document.referrer` or current URL |
| `intake_first_touch_timestamp` | First-touch cookie |
| `intake_form_version` | Hard-coded: `v1` |
| `hutk` | HubSpot tracking cookie (auto-injected by HubSpot embed) |

### Computed / set later (by n8n or HubSpot workflow)
| Internal name | Set by |
|---|---|
| `intake_qualifying_signal_count` | n8n classifier (FL SaaS 2-Lane ICP rule, 0–3) |
| `quo_phone_number_routed` | Quo bridge only; never the web form |

---

## 2. Conditional logic summary

```
IF intake_primary_issue_family IN (notice, collections, audit, sales_tax_exposure)
    SHOW intake_notice_type

IF intake_enforcement_status != [none]
    SHOW intake_enforcement_deadline

IF intake_primary_issue_family IN (filing_problem, collections)
    SHOW intake_returns_unfiled_count

IF intake_agency_track IN (irs, both)
    SHOW intake_contacted_by_revenue_officer

IF intake_existing_client_status == existing_client
    SKIP Steps 3–4 (route directly to existing-client triage)
    SHOW only Step 5 plus a "What's changed?" textarea

IF URL ?intent=urgent
    Pre-select intake_enforcement_status = [levy_active] (user can uncheck)
    Reorder: show Step 3 (enforcement) before Step 2

IF URL ?agency_hint=fdor
    Pre-select intake_agency_track = fdor

IF URL ?agency_hint=irs
    Pre-select intake_agency_track = irs

IF URL ?lane=<value>
    Pre-select intake_lane
```

HubSpot supports the simple show/hide rules natively. Reorder + skip behaviors require the JS shim (§4).

---

## 3. Auto-mapping: issue family + agency → lane

Pre-fills `intake_lane` from `intake_primary_issue_family` + `intake_agency_track`. User can override.

| Issue family | Agency | Default lane |
|---|---|---|
| `collections` | `irs` / `both` | `irs_collections` |
| `audit` | `irs` / `both` | `irs_audit` |
| `notice` | any | (keep blank; classify in n8n from `intake_notice_type`) |
| `filing_problem` | any | `unfiled_returns` |
| `sales_tax_exposure` | `fdor` / `both` | `fl_dor_sales_audit` |
| `payment_resolution` | `fdor` / `both` | `fl_dor_voluntary_disclosure` |
| `payment_resolution` | `irs` / `both` | `irs_collections` |
| `penalty_relief` | any | `irs_collections` (or `fl_dor_sales_audit` if FDOR) |
| `planning` | any | `planning` |
| `other` | any | leave blank → n8n routes to `manual_review` |

Payroll TFRP cases: when `intake_notice_type` includes a payroll-related notice or `intake_notes` mentions "941"/"payroll", set `intake_lane = payroll_tfrp`. Implemented in n8n classifier.

---

## 4. Embed code (canonical + spokes)

Same form GUID embedded everywhere; `intake_source_domain` resolves from URL param or embedding hostname.

```html
<!-- Container -->
<div id="tps-intake-form"></div>

<!-- HubSpot Forms v2 -->
<script charset="utf-8" type="text/javascript" src="//js.hsforms.net/forms/embed/v2.js"></script>

<script>
  (function () {
    // ---- helpers -----------------------------------------------------------
    var qs = function (name) {
      var m = new RegExp('[?&]' + name + '=([^&]*)').exec(window.location.search);
      return m ? decodeURIComponent(m[1].replace(/\+/g, ' ')) : '';
    };

    var setCookie = function (k, v, days) {
      var d = new Date(); d.setTime(d.getTime() + days * 864e5);
      document.cookie = k + '=' + encodeURIComponent(v) + ';expires=' + d.toUTCString() + ';path=/;SameSite=Lax';
    };
    var getCookie = function (k) {
      var m = document.cookie.match(new RegExp('(?:^|; )' + k + '=([^;]*)'));
      return m ? decodeURIComponent(m[1]) : '';
    };

    // ---- first-touch capture (set once, persists 1 year) -------------------
    if (!getCookie('tps_first_touch_url')) {
      setCookie('tps_first_touch_url', window.location.href, 365);
      setCookie('tps_first_touch_path', window.location.pathname, 365);
      setCookie('tps_first_touch_ts', new Date().toISOString(), 365);
    }

    // ---- derive site_group from src_domain or hostname --------------------
    var srcDomain = qs('src_domain') || window.location.hostname.replace(/^www\./, '');
    var siteGroup = ({
      'keithjones.cpa':    'primary_canonical',
      'thefltaxguy.cpa':   'secondary_florida_funnel',
      'taxstrategist.cpa': 'secondary_authority'
    })[srcDomain] || 'primary_canonical';

    // ---- create form -------------------------------------------------------
    hbspt.forms.create({
      portalId: 'PORTAL_ID',
      formId:   'FORM_GUID',
      target:   '#tps-intake-form',
      region:   'na1',

      onFormReady: function ($form) {
        var setVal = function (name, val) {
          if (!val) return;
          var el = $form.find('input[name="' + name + '"], select[name="' + name + '"]');
          if (el.length) { el.val(val).change(); }
        };

        setVal('intake_source_domain',         srcDomain);
        setVal('intake_source_site_group',     siteGroup);
        setVal('intake_channel',               'web_form');
        setVal('intake_source_page_type',      qs('page_type'));
        setVal('intake_source_offer',          qs('offer'));
        setVal('intake_source_campaign',       qs('utm_campaign'));
        setVal('intake_source_cta_variant',    qs('cta'));
        setVal('utm_landing_path',             getCookie('tps_first_touch_path') || window.location.pathname);
        setVal('intake_first_touch_url',       getCookie('tps_first_touch_url'));
        setVal('intake_first_touch_timestamp', getCookie('tps_first_touch_ts'));
        setVal('intake_latest_funnel_url',     document.referrer || window.location.href);
        setVal('intake_form_version',          'v1');

        // Pre-select agency + lane from URL
        var agencyHint = qs('agency_hint');
        if (agencyHint && ['irs','fdor','both'].indexOf(agencyHint) > -1) {
          setVal('intake_agency_track', agencyHint);
        }
        var laneHint = qs('lane');
        if (laneHint) setVal('intake_lane', laneHint);

        // Pre-select enforcement on urgent intent
        if (qs('intent') === 'urgent') {
          var levy = $form.find('input[name="intake_enforcement_status"][value="levy_active"]');
          if (levy.length) { levy.prop('checked', true).change(); }
        }

        // Continuity: post-booking intake completion
        var contactId = qs('contact_id');
        if (contactId) setVal('intake_hs_contact_id', contactId);
      },

      onFormSubmitted: function () {
        var dest = qs('intent') === 'urgent'
          ? '/thank-you/intake-complete?priority=urgent'
          : '/thank-you/intake-complete';
        window.location.href = dest;
      }
    });
  })();
</script>
```

**Spoke embed note:** On `thefltaxguy.cpa` and `taxstrategist.cpa` the same script runs — `srcDomain` resolves from `window.location.hostname` automatically. The Lovable.dev sites just include the `<script>` block in their page template; no Worker logic needed.

---

## 5. Booking-first variant — domain-specific Meetings links

Three HubSpot Meetings links, same calendar, different UTM stamping.

| Link | URL | Default `intake_source_domain` |
|---|---|---|
| Canonical | `keithjones.cpa/triage-keithjones` | `keithjones.cpa` |
| FL funnel | `keithjones.cpa/triage-fltaxguy` | `thefltaxguy.cpa` |
| Strategist | `keithjones.cpa/triage-strategist` | `taxstrategist.cpa` |

1. HubSpot Meetings preserves URL params on the contact record as Activity properties.
2. On the booking confirmation page, redirect to the canonical intake form for completion:
   ```js
   window.location.href = '/case-review?booked=1&contact_id=' + hsContactId
     + '&' + new URLSearchParams(window.location.search).toString();
   ```
3. The form recognizes `?booked=1` and shows: *"Thanks for booking — finish this 2-minute intake so we're ready for your call."*
4. The **Pending Intake** workflow handles non-completers (architecture §4B).

Each link's first form question must be: *"What's your situation?"* — so `intake_lane` is captured even on the meetings-first path.

---

## 6. Validation rules

- **Email:** standard format + reject obvious disposable domains (HubSpot setting).
- **Phone:** E.164 normalization; require US/CA format unless `intake_state_of_residence = non_us`.
- **File upload:** PDF, JPG, PNG, HEIC; max 25 MB per file, 10 files total. Strip EXIF on upload.
- **Free-text fields:** trim, collapse whitespace, max 4,000 chars on `intake_notes`.

---

## 7. Webhook payload to n8n

After HubSpot creates/updates the contact, fire a webhook to `https://n8n.<your-azure-vm>/webhook/intake/v1`. Configure via HubSpot Workflows → "Send a webhook" action; sign with HMAC-SHA256 using `INTAKE_WEBHOOK_SECRET`.

```json
{
  "event": "intake.submitted",
  "form_version": "v1",
  "submitted_at": "2026-05-02T17:42:00Z",
  "hs_contact_id": "12345678",
  "hs_form_guid": "FORM_GUID",
  "fields": {
    "firstname": "...",
    "lastname": "...",
    "email": "...",
    "phone": "+1...",
    "intake_source_domain": "thefltaxguy.cpa",
    "intake_source_site_group": "secondary_florida_funnel",
    "intake_channel": "web_form",
    "intake_source_offer": "urgent_triage",
    "utm_landing_path": "/florida-tax-warrant-help",
    "intake_agency_track": "fdor",
    "intake_lane": "fl_dor_sales_audit",
    "intake_primary_issue_family": "collections",
    "intake_entity_type": "s_corp",
    "intake_notice_type": ["FL_warrant"],
    "intake_enforcement_status": ["levy_active", "lien_filed"],
    "intake_enforcement_deadline": "2026-05-09",
    "intake_tax_years_owed": "2022, 2023",
    "intake_balance_range": "100k_250k",
    "intake_returns_unfiled_count": 0,
    "intake_contacted_by_revenue_officer": "no",
    "intake_prior_representation": "none",
    "intake_state_of_residence": "FL",
    "intake_notes": "..."
  }
}
```

n8n consumes this payload (see `n8n-routing-workflow.md`).

---

## 8. Deployment checklist

- [ ] Run `scripts/hubspot/create_properties.py` (creates the property model).
- [ ] Build the form in HubSpot UI with the fields above.
- [ ] Configure conditional logic in the HubSpot form editor.
- [ ] Add the webhook action to a HubSpot workflow triggered by form submission (HMAC-signed).
- [ ] Embed the form on `keithjones.cpa/case-review` (Vite SPA template).
- [ ] Embed the form on the `thefltaxguy.cpa` and `taxstrategist.cpa` capture pages (Lovable.dev page templates).
- [ ] Stand up the three Meetings links (`/triage-keithjones`, `/triage-fltaxguy`, `/triage-strategist`).
- [ ] Add the post-booking redirect to `/case-review?booked=1`.
- [ ] Smoke-test from each of the three domains; confirm `intake_source_domain` and `intake_channel` populate correctly on the contact record.
