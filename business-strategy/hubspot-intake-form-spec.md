# HubSpot Intake Form Spec — `keithjones.cpa/case-review`

Companion to `multi-domain-intake-architecture.md`. Defines the single canonical intake form: fields, conditional logic, hidden fields, embed, and URL-parameter pre-fill.

**Form internal name:** `tps_case_review_intake_v1`
**Submit destination:** HubSpot contact (create-or-update on email, fallback phone) → fires webhook to n8n `/intake/v1`.

---

## 1. Field list (in display order)

Required fields are marked `*`. All field internal names match the property internal names in `multi-domain-intake-architecture.md` §3.

### Step 1 — Identify
| Label | Type | Internal name | Required | Notes |
|---|---|---|---|---|
| First name | Single-line text | `firstname` | * | Standard HubSpot |
| Last name | Single-line text | `lastname` | * | Standard HubSpot |
| Email | Email | `email` | * | Dedupe key |
| Mobile phone | Phone | `phone` | * | Used for SMS triage |
| State of residence | Dropdown | `tps_state_of_residence` | * | US states + `non_us` |
| Are you currently a client? | Radio | `tps_existing_client_status` | * | `new_prospect` / `existing_client` / `former_client` / `referral` |

### Step 2 — Agency & service
| Label | Type | Internal name | Required | Notes |
|---|---|---|---|---|
| Which tax authority is involved? | Radio | `tps_agency_track` | * | `irs` / `fdor` / `both` / `other_state` / `unknown` |
| What's the main issue? | Dropdown | `tps_primary_issue_family` | * | See §3B options |
| What service do you think you need? | Dropdown | `tps_primary_service_line` | (auto from issue, editable) | See §3B options |
| Type of taxpayer | Radio | `tps_entity_type` | * | individual / sole_prop / single_member_llc / multi_member_llc / s_corp / c_corp / partnership / nonprofit |

### Step 3 — Notice & enforcement
| Label | Type | Internal name | Required | Conditional |
|---|---|---|---|---|
| Did you receive a notice? Which one(s)? | Multi-checkbox | `tps_notice_type` | conditional | Show if `tps_primary_issue_family` ∈ {notice, collections, audit, sales_tax_exposure} |
| Upload notice photos / PDFs | File upload (multi) | `tps_notice_files` | optional | Always show; max 10 files, 25 MB each |
| Are any of these happening now? | Multi-checkbox | `tps_enforcement_status` | * | Options as in §3B; `none` is mutually exclusive |
| If there's a deadline, when? | Date | `tps_enforcement_deadline` | conditional | Show if `tps_enforcement_status` ≠ `none` only |

### Step 4 — Scope & history
| Label | Type | Internal name | Required | Conditional |
|---|---|---|---|---|
| What years are involved? | Single-line text | `tps_tax_years_owed` | * | Free-form: "2019, 2021–2023" |
| Estimated total balance owed | Dropdown | `tps_balance_range` | * | See §3B options |
| Number of unfiled returns | Number | `tps_returns_unfiled_count` | conditional | Show if issue family ∈ {filing_problem, collections} |
| Has a Revenue Officer contacted you? | Radio | `tps_has_been_contacted_by_revenue_officer` | conditional | Show if `tps_agency_track` ∈ {irs, both} |
| Any prior representation? | Radio | `tps_prior_representation` | * | none / cpa / attorney / enrolled_agent / national_firm |

### Step 5 — Consent & notes
| Label | Type | Internal name | Required | Notes |
|---|---|---|---|---|
| Anything else we should know? | Multi-line text | `tps_intake_notes` | optional | Free-form |
| I agree to be contacted by phone, SMS, and email | Single checkbox | `tps_consent_contact` | * | TCPA compliance |
| I understand this is not engagement until a written agreement is signed | Single checkbox | `tps_consent_no_engagement` | * | Engagement disclaimer |

### Hidden fields (always set, never visible)
| Internal name | Source |
|---|---|
| `tps_source_domain` | URL `?src_domain=` |
| `tps_source_site_group` | Derived from `src_domain` (see JS in §4) |
| `tps_source_page_type` | URL `?page_type=` |
| `tps_source_offer` | URL `?offer=` |
| `tps_source_campaign` | URL `?utm_campaign=` |
| `tps_source_cta_variant` | URL `?cta=` |
| `tps_first_touch_entry_url` | First-touch cookie (see §4) |
| `tps_latest_funnel_entry_url` | `document.referrer` or current URL |
| `tps_first_touch_timestamp` | First-touch cookie |
| `tps_intake_form_version` | Hard-coded: `v1` |
| `hutk` | HubSpot tracking cookie (auto-injected by HubSpot embed) |

---

## 2. Conditional logic summary

```
IF tps_primary_issue_family IN (notice, collections, audit, sales_tax_exposure)
    SHOW tps_notice_type

IF tps_enforcement_status != [none]
    SHOW tps_enforcement_deadline

IF tps_primary_issue_family IN (filing_problem, collections)
    SHOW tps_returns_unfiled_count

IF tps_agency_track IN (irs, both)
    SHOW tps_has_been_contacted_by_revenue_officer

IF tps_existing_client_status == existing_client
    SKIP Steps 3–4 (route directly to existing-client triage)
    SHOW only Step 5 plus a "What's changed?" textarea

IF URL ?intent=urgent
    Pre-select tps_enforcement_status = [levy_active] (user can uncheck)
    Reorder: show Step 3 (enforcement) before Step 2

IF URL ?agency_hint=fdor
    Pre-select tps_agency_track = fdor
    Pre-select tps_primary_service_line = florida_sales_tax

IF URL ?agency_hint=irs
    Pre-select tps_agency_track = irs
```

HubSpot supports the simple show/hide rules natively. The reorder + skip behaviors require a small JS shim (§4).

---

## 3. Auto-mapping: issue family → service line

Pre-fills `tps_primary_service_line` based on `tps_primary_issue_family`, but stays editable.

| Issue family | Default service line |
|---|---|
| `collections` | `irs_resolution` (or `florida_sales_tax` if agency=fdor) |
| `audit` | `irs_resolution` (or `florida_sales_tax` if agency=fdor) |
| `notice` | `notice_response` |
| `filing_problem` | `irs_resolution` |
| `sales_tax_exposure` | `florida_sales_tax` |
| `payment_resolution` | `irs_resolution` |
| `penalty_relief` | `irs_resolution` |
| `other` | `advisory_review` |

---

## 4. Embed code for `keithjones.cpa/case-review`

Replace `PORTAL_ID` and `FORM_GUID` with the values from the HubSpot UI after creating the form.

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
      setCookie('tps_first_touch_ts', new Date().toISOString(), 365);
    }

    // ---- derive site_group from src_domain --------------------------------
    var srcDomain = qs('src_domain') || window.location.hostname.replace(/^www\./, '');
    var siteGroup = ({
      'keithjones.cpa':       'primary_canonical',
      'taxstrategist.cpa':    'secondary_authority',
      'floridataxsavior.com': 'secondary_florida_funnel'
    })[srcDomain] || 'primary_canonical';

    // ---- create form -------------------------------------------------------
    hbspt.forms.create({
      portalId: 'PORTAL_ID',
      formId:   'FORM_GUID',
      target:   '#tps-intake-form',
      region:   'na1',

      // Pre-fill known fields from URL + cookies
      onFormReady: function ($form) {
        var setVal = function (name, val) {
          if (!val) return;
          var el = $form.find('input[name="' + name + '"], select[name="' + name + '"]');
          if (el.length) { el.val(val).change(); }
        };

        setVal('tps_source_domain',           srcDomain);
        setVal('tps_source_site_group',       siteGroup);
        setVal('tps_source_page_type',        qs('page_type'));
        setVal('tps_source_offer',            qs('offer'));
        setVal('tps_source_campaign',         qs('utm_campaign'));
        setVal('tps_source_cta_variant',      qs('cta'));
        setVal('tps_first_touch_entry_url',   getCookie('tps_first_touch_url'));
        setVal('tps_first_touch_timestamp',   getCookie('tps_first_touch_ts'));
        setVal('tps_latest_funnel_entry_url', document.referrer || window.location.href);
        setVal('tps_intake_form_version',     'v1');

        // Pre-select agency from hint
        var agencyHint = qs('agency_hint');
        if (agencyHint && ['irs','fdor','both'].indexOf(agencyHint) > -1) {
          setVal('tps_agency_track', agencyHint);
          if (agencyHint === 'fdor') setVal('tps_primary_service_line', 'florida_sales_tax');
        }

        // Pre-select enforcement on urgent intent
        if (qs('intent') === 'urgent') {
          var levy = $form.find('input[name="tps_enforcement_status"][value="levy_active"]');
          if (levy.length) { levy.prop('checked', true).change(); }
        }

        // Continuity: if booking-first flow passed contact_id back, pre-fill email
        var contactId = qs('contact_id');
        if (contactId) {
          // HubSpot will dedupe by email; contact_id is used by n8n for join logic
          setVal('tps_hs_contact_id', contactId);
        }
      },

      // After submit, route to the right thank-you page
      onFormSubmit: function () {
        // analytics hook (GA4 / Meta) goes here if needed
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

---

## 5. Booking-first variant — `keithjones.cpa/meetings/case-review`

For authority-funnel CTAs that hit booking before intake.

1. Use the HubSpot Meetings embed (one meeting type: **Tax Problem Case Review**, 30 min, mutual round-robin or single owner).
2. Append the same `src_domain`, `intent`, `utm_*` parameters; HubSpot Meetings preserves URL params on the contact record as Activity properties.
3. On the booking confirmation page, immediately redirect:
   ```js
   window.location.href = '/case-review?booked=1&contact_id=' + hsContactId
     + '&' + new URLSearchParams(window.location.search).toString();
   ```
4. The intake form recognizes `?booked=1` and shows a banner: *"Thanks for booking — finish this 2-minute intake so we're ready for your call."*
5. The **Pending Intake** workflow (defined in `multi-domain-intake-architecture.md` §4B) handles non-completers.

---

## 6. Validation rules

- **Email:** standard format + reject obvious disposable domains (HubSpot setting).
- **Phone:** E.164 normalization; require US/CA format unless `tps_state_of_residence = non_us`.
- **File upload:** PDF, JPG, PNG, HEIC; max 25 MB per file, 10 files total. Strip EXIF on upload.
- **Free-text fields:** trim, collapse whitespace, max 4,000 chars on `tps_intake_notes`.

---

## 7. Webhook payload to n8n

After HubSpot creates/updates the contact, fire a webhook to `https://n8n.<your-domain>/webhook/intake/v1`. Configure via HubSpot Workflows → "Send a webhook" action triggered on form submission.

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
    "tps_source_domain": "floridataxsavior.com",
    "tps_source_site_group": "secondary_florida_funnel",
    "tps_source_offer": "urgent_triage",
    "tps_agency_track": "fdor",
    "tps_primary_issue_family": "collections",
    "tps_primary_service_line": "florida_sales_tax",
    "tps_entity_type": "s_corp",
    "tps_notice_type": ["FL_warrant"],
    "tps_enforcement_status": ["levy_active", "lien_filed"],
    "tps_enforcement_deadline": "2026-05-09",
    "tps_tax_years_owed": "2022, 2023",
    "tps_balance_range": "100k_250k",
    "tps_returns_unfiled_count": 0,
    "tps_has_been_contacted_by_revenue_officer": "no",
    "tps_prior_representation": "none",
    "tps_state_of_residence": "FL",
    "tps_intake_notes": "..."
  }
}
```

The n8n workflow consumes this payload (see `n8n-routing-workflow.md`).

---

## 8. Deployment checklist

- [ ] Create the 35 properties in HubSpot (script generation possible via HubSpot CRM API).
- [ ] Build the form in HubSpot UI with the fields above.
- [ ] Configure conditional logic in the HubSpot form editor.
- [ ] Add the webhook action to a HubSpot workflow triggered by form submission.
- [ ] Embed the form on `/case-review` using §4 code.
- [ ] Stand up `/meetings/case-review` with the redirect from §5.
- [ ] Replace CTAs on `taxstrategist.cpa` and `floridataxsavior.com` with the `?src_domain=...` URL pattern.
- [ ] Smoke-test from each of the three domains; confirm hidden fields populate correctly on the contact record.
