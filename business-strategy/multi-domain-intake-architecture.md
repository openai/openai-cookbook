# Multi-Domain Intake & Triage Architecture

**Practice:** Keith L. Jones, CPA — TheCPATaxProblemSolver (FL Firm License **AD0016958**)
**Canonical NAP:** 13475 Atlantic Blvd, Unit 8, Suite M729, Jacksonville FL 32225

**Domains (hub-and-spoke):**

| Domain | Role | Hosting |
|---|---|---|
| `keithjones.cpa` | **Canonical** — booking, intake, payments, client-portal touchpoints, agent-discoverability hub | **Vite SPA on Cloudflare Worker** (custom; Worker handles routing, Link headers, agent-skills index) |
| `thefltaxguy.cpa` | **TOFU consumer / FL geo funnel** — broad FL tax search; future home of *TaxSolver AI – FL Sales & Use Tax Advisor™* | **Lovable.dev** (Supabase + Vercel + edge functions) |
| `taxstrategist.cpa` | **Premium planning ICP funnel** — proactive-planning audience | **Lovable.dev** (Supabase + Vercel + edge functions) |

**Stack ground truth (do not propose alternatives):**

| Layer | Tool |
|---|---|
| Pre-engagement CRM + marketing automation | **HubSpot** (system of record) |
| Post-engagement case mgmt + docs + client comms | **Canopy** (record migrates from HubSpot at engagement signing) |
| IRS transcripts | **TaxHelpSoftware Enterprise** |
| Tax prep | **Drake Tax** (desktop, hosted) |
| Booking | **HubSpot Meetings** (no Calendly / Acuity / TaxDome scheduler) |
| External voice + SMS + AI receptionist | **Quo.com** (3 DIDs, one per domain) |
| Internal calls | **Microsoft Teams Phone** |
| Email + collaboration | **Microsoft 365** (Outlook, Teams, SharePoint, Planner) |
| Workflow / API orchestration | **n8n self-hosted on Azure VM** (Zapier and Make are prohibited) |
| Secrets | **Azure Key Vault** |

**Core rule:** One contact record. One routing decision. One booking surface. HubSpot is the source of truth pre-engagement; Canopy after.

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
| Booking | `/triage-keithjones` | HubSpot Meetings link (canonical-source variant) |
| Post-booking | `/thank-you/booked` | Confirmation + intake reminder |
| Post-intake | `/thank-you/intake-complete` | Next-step expectations |
| Secure upload | `/upload` | Post-triage doc handoff (Canopy after engagement; HubSpot file pre-engagement) |
| Agent skills | `/.well-known/api-catalog` | Cloudflare Worker emits this Link rel **only after TaxSolver AI ships on `thefltaxguy.cpa`** |

### B. `taxstrategist.cpa` — premium planning ICP funnel
Higher-LTV proactive-planning audience. **No separate intake form, no separate scheduler, no separate ops.**

| Page | Path | Role |
|---|---|---|
| Home | `/` | Strategist framing |
| About Keith | `/about` | Credentials, media, results, firm name + license footer |
| For advisors | `/for-advisors` | CPA / attorney referral channel |
| Strategy vs resolution | `/strategy-vs-resolution` | Educational pre-frame |
| Articles | `/insights/*` | Authority content, internal links to canonical CTAs |
| Booking (spoke variant) | `/triage-strategist` | HubSpot Meetings link with strategist UTM stamping |

**Footer requirement:** Display "Keith L. Jones, CPA — Firm License AD0016958" + canonical NAP.

### C. `thefltaxguy.cpa` — TOFU consumer / FL geo funnel
FL search capture. Future home of **TaxSolver AI** (publicly accessible after launch).

| Page | Path | Role |
|---|---|---|
| Home | `/` | "Florida tax problems solved" framing |
| FL sales tax audit | `/florida-sales-tax-audit` | DR-840 / audit defense |
| FDOR collections | `/florida-dor-collections` | Active enforcement |
| Tax warrants | `/florida-tax-warrant-help` | Liens, levies, warrants |
| Voluntary disclosure | `/florida-voluntary-disclosure` | VDA program |
| Remote seller | `/remote-seller-florida-tax-exposure` | Wayfair / nexus |
| Geo pages | `/cities/{miami,tampa,orlando,jacksonville,...}` | Local intent |
| TaxSolver AI | `/ask` (planned) | Public AI advisor surface |
| Booking (spoke variant) | `/triage-fltaxguy` | HubSpot Meetings link with FL UTM stamping |

**Footer requirement:** Same as `taxstrategist.cpa`.

### Funnel model — hub and spoke
- Spokes capture, then **301 only post-capture follow-up paths** to `keithjones.cpa`. Never 301 the spoke homepage — that kills its TOFU SEO.
- Spoke thank-you pages live on the spoke (preserves attribution); drip-email and retargeting destinations point at the canonical.

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
  https://keithjones.cpa/case-review?src_domain={DOMAIN}&intent=general&lane={lane_value}
  ```

### C. Authority / educational
**Triggers on:** blog, advisor pages, strategist content, FL geo / TOFU pages.

- **Copy options:** *Discuss Your Situation* · *Get a Professional Review* · *Book a Tax Problem Case Review*
- **Destination (booking-first, intake-after) — domain-specific Meetings link:**
  ```
  https://keithjones.cpa/triage-keithjones?src_domain=keithjones.cpa
  https://keithjones.cpa/triage-fltaxguy?src_domain=thefltaxguy.cpa
  https://keithjones.cpa/triage-strategist?src_domain=taxstrategist.cpa
  ```
  → on booked, redirect to `/case-review?booked=1&contact_id={hs_contact_id}` for post-booking intake.

### Hybrid recommendation
- Urgent + FL enforcement pages → **intake-first**.
- General + authority pages → **booking-first with immediate intake redirect**.

### Required URL parameters on every CTA
| Param | Purpose | Example |
|---|---|---|
| `src_domain` | Which domain referred | `thefltaxguy.cpa` |
| `intent` | CTA category | `urgent` \| `general` \| `authority` |
| `lane` | Pre-select intake lane (see §3 taxonomy) | `fl_dor_sales_audit` |
| `agency_hint` | Pre-select agency in form | `irs` \| `fdor` \| `both` |
| `utm_source` / `utm_medium` / `utm_campaign` | Standard attribution | passthrough |
| `gclid` / `fbclid` | Ad attribution | passthrough |

All parameters are written into hidden form fields and synced to the contact record (see §3A).

---

## 3. HubSpot properties

All custom contact properties prefixed `intake_*` (captured at first touch / form / call), `triage_*` (workflow-set classification), or `lifecycle_*` (engagement state). Five property groups.

### A. Source attribution

| Property | Type | Values / format |
|---|---|---|
| `intake_source_domain` | Single-select | `keithjones.cpa` · `thefltaxguy.cpa` · `taxstrategist.cpa` |
| `intake_source_site_group` | Single-select | `primary_canonical` · `secondary_authority` · `secondary_florida_funnel` |
| `intake_channel` | Single-select | `web_form` · `quo_voice` · `quo_sms` · `meetings_link` · `direct` |
| `intake_source_page_type` | Single-select | `home` · `service_page` · `blog` · `landing_page` · `advisor_page` · `florida_geo_page` |
| `intake_source_offer` | Single-select | `case_review` · `urgent_triage` · `notice_help` · `sales_tax_help` · `advisor_referral` |
| `intake_source_campaign` | Text | UTM campaign |
| `intake_source_cta_variant` | Text | A/B variant id |
| `utm_landing_path` | Text | First-touch path |
| `intake_first_touch_url` | Text | Set once, never overwritten |
| `intake_latest_funnel_url` | Text | Overwritten each session |
| `intake_first_touch_timestamp` | Date | Set once |
| `quo_phone_number_routed` | Text | Quo DID hit (E.164) |

### B. Intake & qualification

| Property | Type | Values / format |
|---|---|---|
| `intake_existing_client_status` | Single-select | `new_prospect` · `existing_client` · `former_client` · `referral` |
| `intake_agency_track` | Single-select | `irs` · `fdor` · `both` · `other_state` · `unknown` |
| `intake_lane` | Single-select | `irs_collections` · `irs_audit` · `unfiled_returns` · `payroll_tfrp` · `fl_dor_sales_audit` · `fl_dor_voluntary_disclosure` · `planning` · `unqualified` |
| `intake_primary_issue_family` | Single-select | `collections` · `audit` · `notice` · `filing_problem` · `sales_tax_exposure` · `payment_resolution` · `penalty_relief` · `planning` · `other` |
| `intake_notice_type` | Multi-select | `CP14` · `CP501` · `CP503` · `CP504` · `LT11` · `LT1058` · `CP90` · `CP2000` · `Letter_525` · `Letter_3219` · `FL_DR-840` · `FL_warrant` · `other` · `unknown` |
| `intake_tax_years_owed` | Multi-line text | Free-form: `"2019, 2021–2023"` |
| `intake_balance_range` | Single-select | `under_10k` · `10k_25k` · `25k_50k` · `50k_100k` · `100k_250k` · `over_250k` · `unknown` |
| `intake_enforcement_status` | Multi-select | `none` · `lien_filed` · `levy_active` · `wage_garnishment` · `bank_levy` · `passport_revocation` · `warrant_filed` |
| `intake_enforcement_deadline` | Date | Earliest known deadline |
| `intake_state_of_residence` | Single-select | US states + `non_us` |
| `intake_entity_type` | Single-select | `individual` · `sole_prop` · `single_member_llc` · `multi_member_llc` · `s_corp` · `c_corp` · `partnership` · `nonprofit` |
| `intake_returns_unfiled_count` | Number | Years unfiled |
| `intake_contacted_by_revenue_officer` | Single-select | `yes` · `no` · `unknown` |
| `intake_prior_representation` | Single-select | `none` · `cpa` · `attorney` · `enrolled_agent` · `national_firm` |
| `intake_qualifying_signal_count` | Number | 0–3 (FL SaaS 2-Lane ICP rule) |
| `intake_consent_contact` | Boolean | TCPA |
| `intake_consent_no_engagement` | Boolean | Engagement disclaimer |
| `intake_notes` | Multi-line text | Free-form |
| `intake_completed_at` | Date/time | When form submitted |
| `intake_form_version` | Text | e.g. `v1` |

### C. Triage / routing decision

| Property | Type | Values / format |
|---|---|---|
| `triage_score` | Number | 0–100, computed and clamped (see §4C) |
| `triage_tier` | Single-select | `tier_1_emergency` · `tier_2_qualified` · `tier_3_nurture` · `tier_4_disqualified` |
| `triage_routing_decision` | Single-select | `same_day_callback` · `book_case_review` · `manual_review` · `nurture_sequence` · `referral_out` |
| `triage_routing_reason` | Multi-line text | Workflow-set explanation |
| `triage_assigned_owner` | HubSpot Owner | Set by routing |

### D. Lifecycle / engagement (transitions to Canopy at engagement signing)

| Property | Type | Values / format |
|---|---|---|
| `lifecycle_stage_tps` | Single-select | `lead` · `mql_triaged` · `sql_booked` · `consult_held` · `proposal_sent` · `engaged` · `closed_lost` |
| `lifecycle_consult_outcome` | Single-select | `engaged` · `follow_up_needed` · `not_qualified` · `referred_out` · `no_show` |
| `lifecycle_engagement_letter_sent_at` | Date/time | |
| `lifecycle_engagement_letter_signed_at` | Date/time | Triggers Canopy migration |
| `lifecycle_canopy_synced` | Boolean | Mirrored when client created in Canopy |
| `lifecycle_canopy_client_id` | Text | Canopy primary key |

### Property groups in HubSpot UI
**TPS – Source**, **TPS – Intake**, **TPS – Triage**, **TPS – Lifecycle**, **TPS – Quo** (just `quo_phone_number_routed` for now).

---

## 4. Workflow logic — source + case-type triage

Three layers: capture → score → route. n8n owns scoring and external side-effects; HubSpot owns persistence and the visible workflow stages.

### A. Capture
Three input channels, all converging on the same n8n endpoint.

1. **Web form** — single HubSpot form on `keithjones.cpa/case-review` (canonical) and embedded mirrors on the two spokes for inline capture (form GUID is the same; `intake_source_domain` is set from the embedding domain). On submit:
   - HubSpot dedupes on email (fallback phone) → contact create/update.
   - HubSpot fires webhook → n8n `/intake/v1` with `intake_channel = web_form`.
2. **Quo voice / SMS** — inbound call or text on a Quo DID. Quo POSTs to n8n `/quo-inbound/v1` with the DID, ANI (caller phone), and (for SMS) message body. n8n maps DID → `intake_source_domain`, dedupes/creates HubSpot contact, sets `intake_channel = quo_voice|quo_sms` and `quo_phone_number_routed`. See §5.
3. **HubSpot Meetings booking** — booking on `/triage-keithjones`, `/triage-fltaxguy`, or `/triage-strategist`. HubSpot fires the booking webhook → n8n; `intake_channel = meetings_link`, `intake_source_domain` derived from the link slug, `lifecycle_stage_tps = sql_booked`.

### B. Booking-first variant (authority CTAs)
For authority CTAs that go to a `/triage-*` link first:
1. HubSpot Meetings creates contact + meeting.
2. HubSpot workflow **Pending Intake** starts:
   - Wait 2 min → if `intake_completed_at` is empty, send intake email + SMS (via Quo) with prefilled link `?contact_id={hs_contact_id}`.
   - Wait 24h → if still empty, task to owner + second reminder.
   - Wait 72h → set `triage_routing_decision = manual_review`, notify ops via Teams.

### C. Score (n8n)
Scoring runs on every intake submission (web or post-booking). Output → `triage_score` (0–100, clamped) and `triage_tier`. Variable names below match the property internal names with the `intake_` prefix dropped for readability.

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

**Tier mapping (exhaustive — every contact lands in exactly one tier, top-down)**

Active enforcement is row 1 so it wins even when other fields are missing.

| # | Condition | Tier | Routing |
|---|---|---|---|
| 1 | Any of `levy_active`, `wage_garnishment`, `bank_levy`, `warrant_filed` in `enforcement_status` **OR** `triage_score` ≥ 70 | `tier_1_emergency` | `same_day_callback` |
| 2 | Required fields missing or contradictory (`agency_track`, `balance_range`, or `primary_issue_family` blank) | — | `manual_review` |
| 3 | Score 40–69 **AND** `agency_track` ∈ (`irs`, `fdor`, `both`) **AND** `balance_range` ≠ `under_10k` | `tier_2_qualified` | `book_case_review` |
| 4 | Score 40–69 **AND** not row 3 (e.g., `agency_track` = `other_state`, or `under_10k`) | — | `manual_review` |
| 5 | Score 15–39 | `tier_3_nurture` | `nurture_sequence` |
| 6 | Score < 15 **OR** (`balance_range` = `under_10k` **AND** no enforcement) | `tier_4_disqualified` | `referral_out` |

### D. Route (n8n → HubSpot + Quo + Teams)

**`same_day_callback`**
- HubSpot: set `triage_assigned_owner` = on-call, create task "URGENT — call within 1 hr", `lifecycle_stage_tps = mql_triaged`.
- n8n: SMS via Quo to on-call + Teams alert to `#tps-urgent`.
- Send the prospect: SMS + email confirming "we'll call you within the hour" + booking link as fallback.

**`book_case_review`**
- HubSpot: send templated email with prefilled `keithjones.cpa/triage-keithjones?contact_id=...` (or domain-specific variant if known).
- HubSpot workflow waits for `meeting_booked` event → `lifecycle_stage_tps = sql_booked`.
- If not booked in 48h: reminder email + task to owner.

**`manual_review`**
- HubSpot: assign to ops queue owner, `lifecycle_stage_tps = mql_triaged`, internal note with `triage_routing_reason`.
- SLA: cleared within 1 business day.

**`nurture_sequence`**
- HubSpot: enroll in 6-touch educational sequence (IRS basics → OIC primer → FL sales tax → case studies → testimonial → re-engagement CTA).
- Re-evaluate score after each open/click; promote to `tier_2_qualified` if engagement ≥ threshold.

**`referral_out`**
- HubSpot: send referral email (low-balance IRS → IRS self-help / VITA; out-of-scope state → partner network).
- `lifecycle_stage_tps = closed_lost`, reason `not_a_fit`.

### E. Source-aware overrides
Routing rules above run for everyone. Source adds modifiers:

| `intake_source_domain` | Modifier |
|---|---|
| `thefltaxguy.cpa` | If `intake_agency_track = unknown`, set to `fdor` and default `intake_lane = fl_dor_sales_audit` (applied at normalize, before scoring). |
| `taxstrategist.cpa` from `/for-advisors` | Set `intake_existing_client_status = referral`, route to `book_case_review` regardless of score (advisors get a meeting; tier upgraded to `tier_2_qualified` if currently nurture or referral_out). |
| `keithjones.cpa` `/irs-help` urgent CTA | If routing would be `nurture_sequence` or `referral_out`, force `book_case_review` and upgrade tier to `tier_2_qualified`. Active visitors don't get nurture-only treatment. |

### F. Engagement → Canopy migration
When `lifecycle_engagement_letter_signed_at` is set (manually or by signature integration):
1. n8n creates the matter in Canopy (client, engagement scope, opening tasks).
2. Writes back `lifecycle_canopy_client_id` + `lifecycle_canopy_synced = true`.
3. HubSpot `lifecycle_stage_tps = engaged`.
4. Documents collected pre-engagement migrate from HubSpot files / SharePoint to the Canopy matter.

### G. Reporting
See `kpi-dashboard-spec.md` (separate artifact). Wired to HubSpot dashboards + Amplitude.

---

## 5. Quo voice & SMS bridge

See `quo-bridge-spec.md` for the full provisioning + n8n flow. Summary here for cross-reference:

- **3 DIDs** provisioned in Quo.com — one per domain. Each DID maps 1:1 to `intake_source_domain` and is displayed only on its own site.
- **Domain-aware AI receptionist greetings** (e.g., "Thank you for calling The Florida Tax Guy…" vs. "Keith Jones CPA…"). Same human at the back end.
- **Quo → n8n webhook** on inbound voice/SMS event. n8n matches the contact by phone number, creates one if none exists, sets `intake_channel = quo_voice|quo_sms` + `quo_phone_number_routed = <DID>`, logs the activity, and notifies via Teams.

---

## 6. Compliance & data handling

This intake/routing system handles client PII (names, addresses, phones, IRS notice references, tax balances). Treat compliance as table stakes, not optional.

| Authority / Regulation | Requirement met by |
|---|---|
| **IRC §7216** (disclosure of tax return info) | No client tax data flows through any consumer-tier AI. All AI usage is via API endpoints with no-training guarantees. Apollo / Zapier / Make are prohibited as data handlers. |
| **Circular 230 §10.36** (procedures to ensure compliance) | Documented intake → triage → engagement workflow; audit trail in HubSpot + n8n logs. |
| **IRS Pub 4557 §III** (safeguards) | HTTPS-only on all webhooks; Azure Key Vault for credentials; HubSpot SOC 2 portal; Quo SOC 2 + signed BAA-equivalent confidentiality/data-handling agreement before any client data flows. |
| **GLBA 16 CFR §314.4(f) (FTC Safeguards Rule)** | Maintain a **Written Information Security Program (WISP)** listing every third party that touches client data: HubSpot, Canopy, Quo, n8n (Azure VM), TaxHelpSoftware, Microsoft 365, Cloudflare. |
| **FL Board of Accountancy** | All three domains' footers display "Keith L. Jones, CPA — Firm License AD0016958" + canonical NAP (13475 Atlantic Blvd, Unit 8, Suite M729, Jacksonville FL 32225). Spokes are marketing surfaces of the same licensed firm, not separate practices. |
| **NAP discipline** | Never display the residential address in schema, footer, or contact pages. Never display 32 Atlanta Drive. Same canonical NAP on every site. |
| **TCPA** | `intake_consent_contact` checkbox on every form; double opt-in for SMS sequences. |

**Vendor risk decisions:**
- Quo.com: confirm SOC 2 Type II + signed agreement before any client data lands.
- Cloudflare Worker on `keithjones.cpa`: emits `api-catalog` Link rel **only after TaxSolver AI ships publicly** on `thefltaxguy.cpa`. Not before.

---

## 7. Spoke 301 strategy

- **Do not** 301 spoke homepages — that kills their TOFU SEO.
- **Do** 301 post-capture follow-up paths (drip-email click destinations, retargeting URLs, thank-you-page secondary CTAs) to `keithjones.cpa`.
- Spoke thank-you pages live on the spoke (preserves attribution chain back to the originating domain).

---

## 8. Build sequence

Per the practice owner's revenue-ordering call:

1. **HubSpot custom properties** — run `scripts/hubspot/create_properties.py` to upsert the property model in §3.
2. **Web forms** — build the canonical form once in HubSpot, embed on `/case-review` (canonical) and on the two spokes' inline capture spots. Set `intake_source_domain` from the embedding hostname.
3. **Quo DID provisioning** — three DIDs, domain-aware greetings, inbound webhook to n8n. See `quo-bridge-spec.md`.
4. **n8n flows** in this order:
   - Web-form intake → HubSpot upsert + tag (`tps_intake_router_v1`).
   - Quo → HubSpot bridge.
   - Triage router (lane classification + routing).
   - Booking-attribution webhook (HubSpot Meetings → preserve `intake_source_domain` from cookie).
5. **HubSpot Meetings setup** — three meeting links: `/triage-keithjones`, `/triage-fltaxguy`, `/triage-strategist`. Same calendar, different UTM stamping. First question on each: "What's your situation?" → maps to `intake_lane`.
6. **Spoke 301 logic** — implement at the Lovable.dev edge function or Vercel rewrite layer for `thefltaxguy.cpa` and `taxstrategist.cpa`.
7. **Canopy bridge** — n8n workflow on `lifecycle_engagement_letter_signed_at` set → create Canopy matter, write back IDs.
8. **KPI dashboards** — HubSpot + Amplitude; see `kpi-dashboard-spec.md`.

---

## 9. Open decisions

| Decision | Why it matters |
|---|---|
| Final Quo DID assignments | Provision the three numbers; map DID → `intake_source_domain` in n8n. |
| On-call rotation for Tier 1 | Drives the `same_day_callback` SLA and the Quo SMS routing target. |
| Referral-out partner list | Needed before `referral_out` route can ship without a generic email. |
| Canopy field mirror set | Confirm which `intake_*` and `lifecycle_*` properties should mirror to Canopy at engagement. |
| TaxSolver AI launch date | Gates the Cloudflare Worker `api-catalog` Link rel on `keithjones.cpa`. |
