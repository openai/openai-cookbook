# Multi-Domain Intake & Triage Architecture

**Practice:** Keith Jones, CPA — TheCPATaxProblemSolver
**Domains:** `keithjones.cpa` (canonical) · `taxstrategist.cpa` (authority funnel) · `floridataxsavior.com` (FL geo funnel)
**Stack:** HubSpot (CRM + forms + meetings + workflows) · n8n (orchestration) · Canopy (practice mgmt) · Microsoft 365 / Exchange Online
**Core rule:** One intake form. One contact record. One routing decision. One booking path. HubSpot is the source of truth.

---

## 1. Domain roles

### A. `keithjones.cpa` — canonical client-experience site
The only domain that hosts conversion-critical assets.

| Page | Path | Role |
|---|---|---|
| Home | `/` | Authority + crisis-first positioning |
| IRS help hub | `/irs-help` | Levy, garnishment, notices, OIC, IA, audit |
| Florida DOR hub | `/florida-dor-help` | Sales tax audit, collections, warrants |
| Sales tax | `/sales-tax-problems` | Nexus, exposure, remote seller |
| Primary intake | `/case-review` | Single canonical intake form |
| Booking | `/meetings/case-review` | Tax Problem Case Review (HubSpot Meetings) |
| Post-booking | `/thank-you/booked` | Confirmation + intake reminder |
| Post-intake | `/thank-you/intake-complete` | Next-step expectations |
| Secure upload | `/upload` | Post-triage doc handoff (Canopy or HubSpot file) |

### B. `taxstrategist.cpa` — authority / positioning funnel
Thought leadership and pre-frame. **No separate intake, no separate scheduler, no separate ops.**

| Page | Path | Role |
|---|---|---|
| Home | `/` | Strategist framing of Keith |
| About | `/about-keith-jones` | Credentials, media, results |
| For advisors | `/for-advisors` | CPA/attorney referral channel |
| Strategy vs resolution | `/tax-strategy-vs-tax-resolution` | Educational pre-frame |
| Articles | `/insights/*` | Authority content, internal links to canonical CTAs |

### C. `floridataxsavior.com` — Florida high-intent funnel
FDOR enforcement and Florida sales tax urgency capture.

| Page | Path | Role |
|---|---|---|
| Home | `/` | "Florida tax problems solved" framing |
| FL sales tax audit | `/florida-sales-tax-audit` | DR-840 / audit defense |
| FDOR collections | `/florida-dor-collections` | Active enforcement |
| Tax warrants | `/florida-tax-warrant-help` | Liens, levies, warrants |
| Remote seller | `/remote-seller-florida-tax-exposure` | Wayfair / nexus |
| Geo pages | `/cities/{miami,tampa,orlando,jacksonville,...}` | Local intent capture |

**Funnel model:** hub-and-spoke. Both spokes route every meaningful CTA to `keithjones.cpa/case-review` with source pre-tagged.

---

## 2. CTA routing rules

Three CTA categories, each with a deterministic destination. Copy varies by page intent — backend does not.

### A. Crisis / urgent enforcement
**Triggers on:** levy, garnishment, bank freeze, warrant, deadline, "final notice" pages.

- **Copy options:** *Get Emergency Case Review* · *Tell Us What Notice You Got* · *Start Your Tax Triage*
- **Destination (intake-first):**
  ```
  https://keithjones.cpa/case-review?src_domain={DOMAIN}&intent=urgent&agency_hint={irs|fdor}
  ```
- **Why intake-first:** urgent leads must not skip triage — qualification data drives the same-day callback queue.

### B. General service
**Triggers on:** OIC, installment agreement, audit defense, resolution overview pages.

- **Copy options:** *See If You Qualify* · *Request a Case Review* · *Start Here*
- **Destination (intake-first):**
  ```
  https://keithjones.cpa/case-review?src_domain={DOMAIN}&intent=general&service={oic|ia|audit|...}
  ```

### C. Authority / educational
**Triggers on:** blog, advisor pages, strategist content.

- **Copy options:** *Discuss Your Situation* · *Get a Professional Review* · *Book a Tax Problem Case Review*
- **Destination (booking-first, intake-after):**
  ```
  https://keithjones.cpa/meetings/case-review?src_domain={DOMAIN}&intent=authority
  ```
  → on booked, redirect to `/case-review?booked=1&contact_id={hs_contact_id}` for post-booking intake.

### Hybrid recommendation
- Urgent + Florida enforcement pages → **intake-first** (Option A in §5).
- General + authority pages → **booking-first with immediate intake redirect** (Option B in §5).

### Required URL parameters on every CTA
| Param | Purpose | Example |
|---|---|---|
| `src_domain` | Which domain referred | `floridataxsavior.com` |
| `intent` | CTA category | `urgent` \| `general` \| `authority` |
| `agency_hint` | Pre-select agency in form | `irs` \| `fdor` \| `both` |
| `service` | Pre-select service line | `oic` \| `ia` \| `audit` \| `sales_tax` |
| `utm_source` / `utm_medium` / `utm_campaign` | Standard attribution | passthrough |
| `gclid` / `fbclid` | Ad attribution | passthrough |

All parameters are written into hidden form fields and synced to the contact record (see §3A).

---

## 3. HubSpot properties to create

All custom contact properties prefixed `tps_` (Tax Problem Solver) for groupability and reporting. Four groups.

### A. Source attribution

| Property (internal) | Type | Values / format |
|---|---|---|
| `tps_source_domain` | Single-select | `keithjones.cpa` · `taxstrategist.cpa` · `floridataxsavior.com` |
| `tps_source_site_group` | Single-select | `primary_canonical` · `secondary_authority` · `secondary_florida_funnel` |
| `tps_source_page_type` | Single-select | `home` · `service_page` · `blog` · `landing_page` · `advisor_page` · `florida_geo_page` |
| `tps_source_offer` | Single-select | `case_review` · `urgent_triage` · `notice_help` · `sales_tax_help` · `advisor_referral` |
| `tps_source_campaign` | Text | UTM campaign |
| `tps_source_cta_variant` | Text | A/B variant id |
| `tps_first_touch_entry_url` | Single-line text | Set once, never overwritten |
| `tps_latest_funnel_entry_url` | Single-line text | Overwritten each session |
| `tps_first_touch_timestamp` | Date | Set once |

### B. Intake & qualification

| Property | Type | Values / format |
|---|---|---|
| `tps_existing_client_status` | Single-select | `new_prospect` · `existing_client` · `former_client` · `referral` |
| `tps_agency_track` | Single-select | `irs` · `fdor` · `both` · `other_state` · `unknown` |
| `tps_primary_service_line` | Single-select | `irs_resolution` · `florida_sales_tax` · `state_tax_dispute` · `notice_response` · `advisory_review` |
| `tps_primary_issue_family` | Single-select | `collections` · `audit` · `notice` · `filing_problem` · `sales_tax_exposure` · `payment_resolution` · `penalty_relief` · `other` |
| `tps_notice_type` | Multi-select | `CP14` · `CP501` · `CP503` · `CP504` · `LT11` · `LT1058` · `CP90` · `CP2000` · `Letter_525` · `Letter_3219` · `FL_DR-840` · `FL_warrant` · `other` · `unknown` |
| `tps_tax_years_owed` | Multi-line text | Free-form: "2019, 2021, 2022" |
| `tps_balance_range` | Single-select | `under_10k` · `10k_25k` · `25k_50k` · `50k_100k` · `100k_250k` · `over_250k` · `unknown` |
| `tps_enforcement_status` | Multi-select | `none` · `lien_filed` · `levy_active` · `wage_garnishment` · `bank_levy` · `passport_revocation` · `warrant_filed` |
| `tps_enforcement_deadline` | Date | Earliest known deadline |
| `tps_state_of_residence` | Single-select | US states + `non_us` |
| `tps_entity_type` | Single-select | `individual` · `sole_prop` · `single_member_llc` · `multi_member_llc` · `s_corp` · `c_corp` · `partnership` · `nonprofit` |
| `tps_returns_unfiled_count` | Number | Years unfiled |
| `tps_has_been_contacted_by_revenue_officer` | Single-select | `yes` · `no` · `unknown` |
| `tps_prior_representation` | Single-select | `none` · `cpa` · `attorney` · `enrolled_agent` · `national_firm` |

### C. Triage / routing decision

| Property | Type | Values / format |
|---|---|---|
| `tps_triage_tier` | Single-select | `tier_1_emergency` · `tier_2_qualified` · `tier_3_nurture` · `tier_4_disqualified` |
| `tps_triage_score` | Number | 0–100, computed (see §4C) |
| `tps_routing_decision` | Single-select | `same_day_callback` · `book_case_review` · `manual_review` · `nurture_sequence` · `referral_out` |
| `tps_routing_reason` | Multi-line text | Workflow-set explanation |
| `tps_assigned_owner` | HubSpot Owner | Set by routing |
| `tps_intake_completed_at` | Date/time | When form submitted |
| `tps_intake_form_version` | Single-line text | e.g. `v1.3` |

### D. Lifecycle / engagement

| Property | Type | Values / format |
|---|---|---|
| `tps_lifecycle_stage` | Single-select | `lead` · `mql_triaged` · `sql_booked` · `consult_held` · `proposal_sent` · `engaged` · `closed_lost` |
| `tps_consult_outcome` | Single-select | `engaged` · `follow_up_needed` · `not_qualified` · `referred_out` · `no_show` |
| `tps_canopy_synced` | Single checkbox | Mirrored when client created in Canopy |
| `tps_canopy_client_id` | Single-line text | Canopy primary key |
| `tps_engagement_letter_sent_at` | Date/time | |
| `tps_engagement_letter_signed_at` | Date/time | |

### Property groups in HubSpot UI
Create four groups so the contact record stays scannable: **TPS – Source**, **TPS – Intake**, **TPS – Triage**, **TPS – Lifecycle**.

---

## 4. Workflow logic — source + case-type triage

Three layers: capture → score → route. n8n owns scoring and external side-effects; HubSpot owns persistence and the visible workflow stages.

### A. Capture (HubSpot form → n8n webhook)
1. Single HubSpot form embedded at `keithjones.cpa/case-review`.
2. Hidden fields populated from URL params (§2). Visible fields drive properties in §3B.
3. On submit:
   - HubSpot creates/updates contact (dedupe on email, fall back to phone).
   - HubSpot fires webhook → n8n endpoint `/intake/v1`.
   - HubSpot sets `tps_intake_completed_at = now()`.

### B. Booking-first variant
For authority CTAs that go to `/meetings/case-review` first:
1. HubSpot Meetings creates contact + meeting.
2. HubSpot workflow **Pending Intake** starts:
   - Wait 2 minutes → if `tps_intake_completed_at` is empty, send intake email + SMS with prefilled link `?contact_id={hs_contact_id}`.
   - Wait 24h → if still empty, task to owner + second reminder.
   - Wait 72h → set `tps_routing_decision = manual_review`, notify ops.

### C. Score (n8n)
Scoring runs on every intake submission. Output → `tps_triage_score` (0–100, always clamped) and `tps_triage_tier`. Variable names below match the property internal names from §3 with the `tps_` prefix dropped for readability.

```
score = 0

# Enforcement urgency — multi-select; flags are independent.
# Sum then clamp to 60 so this section can never alone exceed the 0–100 envelope.
enforcement_subtotal = 0
if "levy_active"         in enforcement_status: enforcement_subtotal += 35
if "wage_garnishment"    in enforcement_status: enforcement_subtotal += 35
if "bank_levy"           in enforcement_status: enforcement_subtotal += 30
if "warrant_filed"       in enforcement_status: enforcement_subtotal += 25
if "lien_filed"          in enforcement_status: enforcement_subtotal += 15
if "passport_revocation" in enforcement_status: enforcement_subtotal += 25
if enforcement_deadline within 14 days:         enforcement_subtotal += 15
score += min(enforcement_subtotal, 60)

# Balance signal (max 20)
if balance_range == "over_250k":  score += 20
if balance_range == "100k_250k":  score += 16
if balance_range == "50k_100k":   score += 12
if balance_range == "25k_50k":    score += 8
if balance_range == "10k_25k":    score += 4

# Fit signal (max 20) — uses agency_track (the defined property), not a separate `agency` var
if agency_track in ("irs","fdor","both"):                          score += 10
if state_of_residence == "FL" and agency_track in ("fdor","both"): score += 5
if entity_type in ("s_corp","multi_member_llc","c_corp"):          score += 5

# Negative signals
if balance_range == "under_10k" and no enforcement:                   score -= 20
if prior_representation == "national_firm" and consult declined before: score -= 10

# Final clamp — guarantees stored value matches the documented 0–100 range.
score = max(0, min(100, score))
```

**Tier mapping (exhaustive — every contact lands in exactly one tier)**

Evaluate top-down; the first matching row wins.

| # | Condition | Tier | Routing |
|---|---|---|---|
| 1 | Any of `levy_active`, `wage_garnishment`, `bank_levy`, `warrant_filed` in `enforcement_status` **OR** score ≥ 70 | `tier_1_emergency` | `same_day_callback` |
| 2 | Score 40–69 **AND** `agency_track` ∈ (`irs`, `fdor`, `both`) **AND** `balance_range` ≠ `under_10k` | `tier_2_qualified` | `book_case_review` |
| 3 | Score 40–69 **AND** not row 2 (e.g., `agency_track` = `other_state` / `unknown`, or `under_10k`) | — | `manual_review` |
| 4 | Score 15–39 | `tier_3_nurture` | `nurture_sequence` |
| 5 | Score < 15 **OR** (`balance_range` = `under_10k` **AND** no enforcement) | `tier_4_disqualified` | `referral_out` |
| 6 | Required fields missing or contradictory (catch-all) | — | `manual_review` |

### D. Route (n8n → HubSpot + downstream)

**`same_day_callback`**
- HubSpot: set owner = on-call, create task "URGENT — call within 1 hr", lifecycle → `mql_triaged`.
- n8n: SMS via Twilio to on-call + Teams/Outlook alert.
- Slack/Teams channel: `#tps-urgent` post with contact link.
- Send the prospect: SMS + email confirming "we'll call you within the hour" + booking link as fallback.

**`book_case_review`**
- HubSpot: send templated email with prefilled `keithjones.cpa/meetings/case-review?contact_id=...`.
- HubSpot workflow waits for `meeting_booked` event → lifecycle → `sql_booked`.
- If not booked in 48h: reminder email + task to owner.

**`manual_review`**
- HubSpot: assign to ops queue owner, lifecycle → `mql_triaged`, internal note with field-level reason.
- SLA: cleared within 1 business day.

**`nurture_sequence`**
- HubSpot: enroll in 6-touch educational sequence (IRS basics → OIC primer → FL sales tax → case studies → testimonial → re-engagement CTA).
- Re-evaluate score after each open/click; promote to `tier_2_qualified` if engagement ≥ threshold.

**`referral_out`**
- HubSpot: send templated referral email (low-balance IRS → IRS self-help / VITA; out-of-scope state → partner network).
- Lifecycle → `closed_lost` with reason `not_a_fit`.

### E. Source-aware overrides
Routing rules above run for everyone. Source adds modifiers:

| `tps_source_domain` | Modifier |
|---|---|
| `floridataxsavior.com` | If `agency_track = unknown`, set to `fdor`. Default `tps_primary_service_line = florida_sales_tax`. |
| `taxstrategist.cpa` from `/for-advisors` | Set `tps_existing_client_status = referral`, route to `book_case_review` regardless of score (advisors get a meeting). |
| `keithjones.cpa` `/irs-help` urgent CTA | Force min tier `tier_2_qualified` (don't nurture an IRS-help-page visitor). |

### F. Reporting (HubSpot dashboards)
- **Funnel by source domain:** sessions → form starts → submissions → tier 1/2 → booked → engaged → revenue.
- **Tier 1 SLA:** % of `same_day_callback` contacted within 60 min.
- **Triage accuracy:** % of `tier_1_emergency` that engage / % of `tier_4_disqualified` that come back as engaged (false-negative rate).
- **Domain ROI:** revenue per session, cost per engaged client by `tps_source_domain`.

---

## 5. Build sequence

1. **HubSpot setup** — create the four property groups + properties in §3, the canonical form, the meeting type, the four workflows in §4.
2. **n8n** — webhook endpoint, scoring node, routing switch, downstream actions (Twilio, Teams, HubSpot updates).
3. **`keithjones.cpa`** — build `/case-review`, `/meetings/case-review`, `/thank-you/*`. Embed form, wire hidden fields.
4. **Secondary domains** — audit existing CTAs, replace destinations with §2 URL pattern. Add `src_domain` and `agency_hint` to every link.
5. **Canopy bridge** — n8n workflow on `tps_lifecycle_stage = engaged` → create Canopy client, write back `tps_canopy_client_id`.
6. **Reporting** — build the four dashboards in §4F.
7. **A/B + iteration** — compare conversion by `tps_source_domain` and `tps_source_offer`; tune CTAs and scoring thresholds monthly.

---

## 6. Open decisions for Keith

| Decision | Why it matters |
|---|---|
| CMS for each domain | Determines whether intake is a HubSpot form embed (recommended) vs. custom POST to n8n. |
| Current scheduler | If anything other than HubSpot Meetings is live today, plan a cutover so Meetings becomes the only booking surface. |
| On-call rotation for Tier 1 | Drives the `same_day_callback` SLA and Twilio routing target. |
| Referral-out partners | Needed before `referral_out` route can ship. |
| Canopy intake fields | Confirm which `tps_*` properties should mirror to Canopy at engagement. |
