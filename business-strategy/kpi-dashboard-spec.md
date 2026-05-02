# KPI Dashboard Spec — Multi-Domain Intake

Companion to `multi-domain-intake-architecture.md` §4G. Defines the metrics, source systems, and dashboard surfaces that prove the unified-intake investment is paying off and let attribution be tested per domain / channel / lane.

**Surfaces:**
- **HubSpot dashboards** (operational, day-to-day): native HubSpot reports built on the `intake_*`, `triage_*`, and `lifecycle_*` properties.
- **Amplitude** (product analytics): event stream from web forms, Quo events, HubSpot Meetings webhooks. Cross-funnel comparisons + cohort retention.

Wire both from Day 1. Don't ship the unified intake without a way to measure it.

---

## 1. Headline KPIs (revenue-impact)

These six tell you whether the system is working. Build them first.

| # | Metric | Why | Source | Cut by |
|---|---|---|---|---|
| 1 | **Lead volume** | Top-of-funnel health | HubSpot Contacts created | `intake_source_domain`, `intake_channel`, `intake_lane`, week |
| 2 | **Lead → booked-call conversion** | Intake quality + triage routing accuracy | HubSpot Meetings booked / Contacts created | `intake_source_domain`, `intake_channel` |
| 3 | **Booked-call → signed-engagement conversion** | Sales effectiveness + lead fit | `lifecycle_engagement_letter_signed_at` set / Meetings held | `intake_source_domain`, `intake_lane` |
| 4 | **Avg case value (signed engagements)** | Whether premium-funnel domains actually deliver premium cases | HubSpot Deal amount on engaged contacts | `intake_source_domain`, `intake_lane` |
| 5 | **Channel mix per domain** | Which CTAs / channels each domain produces | n8n activity log + HubSpot | `intake_source_domain` × `intake_channel` |
| 6 | **Quo DID inbound volume** | Voice/SMS effectiveness vs. web forms | Quo + HubSpot | `intake_source_domain` (via DID map) × event_type |

---

## 2. Operational KPIs (SLA + quality)

These are dashboards Keith and ops watch daily; they catch problems early.

| Metric | Target | Source | Notes |
|---|---|---|---|
| Tier 1 (`same_day_callback`) **first-touch SLA** | ≥ 90% within 60 min | HubSpot task `created_at` vs. first activity logged | Alert on miss |
| Manual-review queue depth | ≤ 5 open at any time | HubSpot view filtered on `triage_routing_decision = manual_review` and unworked > 1 business day | |
| Pending-intake completion rate (booking-first path) | ≥ 70% within 24h | HubSpot workflow report on **Pending Intake** | Identifies friction in post-booking form |
| Triage classification accuracy (sample) | Reviewed weekly | Manual sample of 20 triaged contacts → compare `triage_tier` to ops judgment | Tunes scoring thresholds |
| Quo voice/SMS → HubSpot match rate (no duplicate contacts) | ≥ 95% | n8n logs of upsert decisions | Catches dedupe regressions |
| Webhook error rate | < 0.5% | n8n error trigger → `#tps-eng-alerts` | Escalates broken signatures, schema drift |

---

## 3. Cohort + retention KPIs (Amplitude)

Run these monthly. They answer "is the funnel actually compounding?"

- **First-touch domain → engaged retention curve** (60-day, 90-day, 6-month).
- **Lane composition shift over time** — is `irs_collections` growing? Is `planning` capturing the strategist-funnel uplift?
- **Spoke → canonical attribution decay** — % of engaged clients whose `intake_first_touch_url` was on a spoke vs. canonical, by month.
- **Channel-mix drift** — is web-form share rising vs. Quo voice as content compounds?

---

## 4. HubSpot dashboard layout

Build **two HubSpot dashboards**:

### Dashboard A — *TPS Intake Funnel*
| Tile | Type | Filter |
|---|---|---|
| Lead volume by domain (last 30 days) | Bar | grouped by `intake_source_domain` |
| Lead volume by lane (last 30 days) | Bar | grouped by `intake_lane` |
| Channel mix per domain | Stacked bar | `intake_source_domain` × `intake_channel` |
| Lead → booked conversion by domain | Line | weekly cohort, `intake_source_domain` |
| Tier distribution this week | Pie | `triage_tier` |
| Manual-review queue depth | Number | `triage_routing_decision = manual_review`, age > 0 |
| Tier 1 SLA — last 7 days | Number + sparkline | task close time vs. created time |

### Dashboard B — *TPS Revenue & Quality*
| Tile | Type | Filter |
|---|---|---|
| Booked → signed conversion by domain | Bar | `lifecycle_engagement_letter_signed_at` non-null / Meetings booked |
| Avg engagement amount by domain | Bar | Deal amount where `lifecycle_stage_tps = engaged` |
| Engaged-client lane mix | Stacked bar | `intake_lane` × month |
| Time to engagement (intake → signed) | Histogram | days |
| Quo DID call volume | Bar | `quo_phone_number_routed` |
| Triage scoring distribution | Histogram | `triage_score` |

---

## 5. Amplitude event taxonomy

Standardize event names so cross-funnel queries are trivial. Emit from each surface:

| Event | Emitted by | Properties |
|---|---|---|
| `intake_form_viewed` | Web form embed (every domain) | `source_domain`, `page_path`, `utm_*`, `cta_variant` |
| `intake_form_started` | Web form embed | same as above + `form_version` |
| `intake_form_submitted` | HubSpot form submit hook → Amplitude HTTP API call from n8n | + all `intake_*` field values (low-cardinality only — no notes / PII text) |
| `quo_call_received` | n8n Quo bridge | `source_domain`, `did`, `urgency`, `agency_hint`, `lane_hint` |
| `quo_sms_received` | n8n Quo bridge | same as above |
| `meeting_booked` | HubSpot Meetings webhook → Amplitude | `source_domain`, `meeting_link_slug`, `intake_lane` |
| `meeting_held` | Manual log or calendar integration | + `lifecycle_consult_outcome` |
| `engagement_signed` | HubSpot lifecycle change → Amplitude | `source_domain`, `intake_lane`, `deal_amount`, `time_to_engagement_days` |
| `triage_routed` | n8n after `applySourceOverrides` | `source_domain`, `triage_tier`, `triage_routing_decision`, `triage_score`, `triage_routing_reason` |

Identify users by HubSpot `vid` + an Amplitude `user_id` mirror; alias Quo phone-only contacts when they later complete a web form with email.

**PII discipline:** never send `intake_notes`, `email`, `phone`, `firstname`, `lastname`, or `tax_years_owed` to Amplitude. Aggregate values + categorical fields only.

---

## 6. Wiring sequence

Build in this order so each piece has data the next depends on.

1. **HubSpot properties** — already covered by `scripts/hubspot/create_properties.py`. Without these, no dashboard tile renders.
2. **n8n → HubSpot writes** — wire all five routing branches to set `triage_*` properties.
3. **HubSpot Dashboard A** — Intake Funnel tiles. Validate on first day of submissions.
4. **n8n → Amplitude HTTP API** — emit `intake_form_submitted`, `triage_routed`, `quo_call_received`, `quo_sms_received`.
5. **HubSpot Meetings webhook → Amplitude** — `meeting_booked`.
6. **HubSpot lifecycle workflow → Amplitude** — `engagement_signed` when `lifecycle_engagement_letter_signed_at` set.
7. **HubSpot Dashboard B** — Revenue & Quality tiles. Needs at least 1–2 weeks of submitted intakes to be meaningful.
8. **Amplitude cohort dashboards** — once 30 days of data exists.

---

## 7. Decision framework — when to act on a KPI

| Signal | Action |
|---|---|
| Lead volume from `thefltaxguy.cpa` < lead volume from `keithjones.cpa` after 60 days | Re-evaluate FL geo SEO + content investment |
| Booked → signed < 25% on a domain | Audit consult quality; tighten triage thresholds |
| Avg case value on `taxstrategist.cpa` ≤ canonical | Strategist funnel isn't differentiating — revisit ICP |
| Tier 1 SLA < 80% | On-call rotation needs adjustment or Quo SMS routing isn't reliable |
| Manual-review depth > 5 sustained | Form has missing-field problem OR scoring thresholds need tuning |
| Pending-intake completion < 50% | Post-booking redirect or email cadence is broken |
| Quo voice/SMS → HubSpot match rate < 90% | Dedupe rules need work; risk of duplicate contacts polluting attribution |

---

## 8. Open decisions

| Decision | Why it matters |
|---|---|
| Amplitude project + workspace | Determines event volume tier and cost. |
| HubSpot Deal pipeline structure | Avg case value tile depends on which Deal stages map to engagement. |
| Time window for "engaged" attribution | First-touch vs. last-touch vs. weighted — pick one and document. |
| Whether to surface dashboards to staff vs. Keith only | Drives HubSpot user permissions. |
