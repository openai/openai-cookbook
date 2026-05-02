"""Single source of truth for the intake_/triage_/lifecycle_ contact property definitions.

Mirrors `business-strategy/multi-domain-intake-architecture.md` §3.
Edit here, re-run `create_properties.py`, and HubSpot updates non-destructively.
"""

from __future__ import annotations

from typing import Literal, TypedDict


class Option(TypedDict):
    label: str
    value: str
    displayOrder: int


class Property(TypedDict, total=False):
    name: str
    label: str
    description: str
    groupName: str
    type: Literal["string", "number", "date", "datetime", "enumeration", "bool"]
    fieldType: Literal[
        "text", "textarea", "number", "date", "select", "radio",
        "checkbox", "booleancheckbox", "phonenumber", "file"
    ]
    options: list[Option]
    hasUniqueValue: bool
    formField: bool
    referencedObjectType: str  # for HubSpot Owner properties
    externalOptions: bool      # for HubSpot Owner properties


# ---- groups ----------------------------------------------------------------

GROUPS: list[dict[str, str]] = [
    {"name": "tps_source",    "label": "TPS – Source"},
    {"name": "tps_intake",    "label": "TPS – Intake"},
    {"name": "tps_triage",    "label": "TPS – Triage"},
    {"name": "tps_lifecycle", "label": "TPS – Lifecycle"},
    {"name": "tps_quo",       "label": "TPS – Quo"},
]


# ---- helpers ---------------------------------------------------------------

def _opts(*pairs: tuple[str, str]) -> list[Option]:
    """Build an options list from (value, label) pairs."""
    return [
        {"value": v, "label": l, "displayOrder": i}
        for i, (v, l) in enumerate(pairs)
    ]


US_STATES: list[Option] = _opts(
    *[(s, s) for s in (
        "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN "
        "MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA "
        "WA WV WI WY DC PR"
    ).split()],
    ("non_us", "Non-US"),
)


# ---- A. Source attribution -------------------------------------------------

SOURCE_PROPERTIES: list[Property] = [
    {
        "name": "intake_source_domain",
        "label": "Intake source domain",
        "description": "Which domain the lead originated from.",
        "groupName": "tps_source",
        "type": "enumeration",
        "fieldType": "select",
        "options": _opts(
            ("keithjones.cpa",     "keithjones.cpa"),
            ("thefltaxguy.cpa",    "thefltaxguy.cpa"),
            ("taxstrategist.cpa",  "taxstrategist.cpa"),
        ),
        "formField": True,
    },
    {
        "name": "intake_source_site_group",
        "label": "Intake source site group",
        "description": "Canonical vs funnel role of the source domain.",
        "groupName": "tps_source",
        "type": "enumeration",
        "fieldType": "select",
        "options": _opts(
            ("primary_canonical",         "Primary canonical"),
            ("secondary_authority",       "Secondary – authority"),
            ("secondary_florida_funnel",  "Secondary – Florida funnel"),
        ),
        "formField": True,
    },
    {
        "name": "intake_channel",
        "label": "Intake channel",
        "description": "How the lead arrived.",
        "groupName": "tps_source",
        "type": "enumeration",
        "fieldType": "select",
        "options": _opts(
            ("web_form",       "Web form"),
            ("quo_voice",      "Quo voice"),
            ("quo_sms",        "Quo SMS"),
            ("meetings_link",  "HubSpot Meetings link"),
            ("direct",         "Direct"),
        ),
    },
    {
        "name": "intake_source_page_type",
        "label": "Intake source page type",
        "groupName": "tps_source",
        "type": "enumeration",
        "fieldType": "select",
        "options": _opts(
            ("home",              "Home"),
            ("service_page",      "Service page"),
            ("blog",              "Blog post"),
            ("landing_page",      "Landing page"),
            ("advisor_page",      "Advisor page"),
            ("florida_geo_page",  "Florida geo page"),
        ),
        "formField": True,
    },
    {
        "name": "intake_source_offer",
        "label": "Intake source offer",
        "groupName": "tps_source",
        "type": "enumeration",
        "fieldType": "select",
        "options": _opts(
            ("case_review",       "Case review"),
            ("urgent_triage",     "Urgent triage"),
            ("notice_help",       "Notice help"),
            ("sales_tax_help",    "Sales tax help"),
            ("advisor_referral",  "Advisor referral"),
        ),
        "formField": True,
    },
    {
        "name": "intake_source_campaign",
        "label": "Intake source campaign (utm_campaign)",
        "groupName": "tps_source",
        "type": "string",
        "fieldType": "text",
        "formField": True,
    },
    {
        "name": "intake_source_cta_variant",
        "label": "Intake source CTA variant",
        "groupName": "tps_source",
        "type": "string",
        "fieldType": "text",
        "formField": True,
    },
    {
        "name": "utm_landing_path",
        "label": "UTM landing path",
        "description": "First-touch path on the originating domain.",
        "groupName": "tps_source",
        "type": "string",
        "fieldType": "text",
        "formField": True,
    },
    {
        "name": "intake_first_touch_url",
        "label": "Intake first-touch URL",
        "description": "Set once, never overwritten.",
        "groupName": "tps_source",
        "type": "string",
        "fieldType": "text",
        "formField": True,
    },
    {
        "name": "intake_latest_funnel_url",
        "label": "Intake latest funnel URL",
        "groupName": "tps_source",
        "type": "string",
        "fieldType": "text",
        "formField": True,
    },
    {
        "name": "intake_first_touch_timestamp",
        "label": "Intake first-touch timestamp",
        "groupName": "tps_source",
        "type": "datetime",
        "fieldType": "date",
        "formField": True,
    },
]


# ---- B. Intake & qualification --------------------------------------------

INTAKE_PROPERTIES: list[Property] = [
    {
        "name": "intake_existing_client_status",
        "label": "Client status",
        "groupName": "tps_intake",
        "type": "enumeration",
        "fieldType": "radio",
        "options": _opts(
            ("new_prospect",     "New prospect"),
            ("existing_client",  "Existing client"),
            ("former_client",    "Former client"),
            ("referral",         "Referral"),
        ),
        "formField": True,
    },
    {
        "name": "intake_agency_track",
        "label": "Agency track",
        "groupName": "tps_intake",
        "type": "enumeration",
        "fieldType": "radio",
        "options": _opts(
            ("irs",          "IRS"),
            ("fdor",         "Florida DOR"),
            ("both",         "Both"),
            ("other_state",  "Other state"),
            ("unknown",      "Unknown"),
        ),
        "formField": True,
    },
    {
        "name": "intake_lane",
        "label": "Intake lane",
        "description": "Service lane classification used for routing + reporting.",
        "groupName": "tps_intake",
        "type": "enumeration",
        "fieldType": "select",
        "options": _opts(
            ("irs_collections",            "IRS collections"),
            ("irs_audit",                  "IRS audit"),
            ("unfiled_returns",            "Unfiled returns"),
            ("payroll_tfrp",               "Payroll TFRP"),
            ("fl_dor_sales_audit",         "FL DOR sales audit"),
            ("fl_dor_voluntary_disclosure","FL DOR voluntary disclosure"),
            ("planning",                   "Planning"),
            ("unqualified",                "Unqualified"),
        ),
        "formField": True,
    },
    {
        "name": "intake_primary_issue_family",
        "label": "Primary issue family",
        "groupName": "tps_intake",
        "type": "enumeration",
        "fieldType": "select",
        "options": _opts(
            ("collections",          "Collections"),
            ("audit",                "Audit"),
            ("notice",               "Notice"),
            ("filing_problem",       "Filing problem"),
            ("sales_tax_exposure",   "Sales tax exposure"),
            ("payment_resolution",   "Payment resolution"),
            ("penalty_relief",       "Penalty relief"),
            ("planning",             "Planning"),
            ("other",                "Other"),
        ),
        "formField": True,
    },
    {
        "name": "intake_notice_type",
        "label": "Notice type(s)",
        "groupName": "tps_intake",
        "type": "enumeration",
        "fieldType": "checkbox",
        "options": _opts(
            ("CP14",        "IRS CP14"),
            ("CP501",       "IRS CP501"),
            ("CP503",       "IRS CP503"),
            ("CP504",       "IRS CP504"),
            ("LT11",        "IRS LT11"),
            ("LT1058",      "IRS LT1058"),
            ("CP90",        "IRS CP90"),
            ("CP2000",      "IRS CP2000"),
            ("Letter_525",  "IRS Letter 525"),
            ("Letter_3219", "IRS Letter 3219"),
            ("FL_DR-840",   "FL DR-840"),
            ("FL_warrant",  "FL warrant"),
            ("other",       "Other"),
            ("unknown",     "Unknown"),
        ),
        "formField": True,
    },
    {
        "name": "intake_tax_years_owed",
        "label": "Tax years involved",
        "description": "Free-form text, e.g. '2019, 2021–2023'.",
        "groupName": "tps_intake",
        "type": "string",
        "fieldType": "textarea",
        "formField": True,
    },
    {
        "name": "intake_balance_range",
        "label": "Balance range",
        "groupName": "tps_intake",
        "type": "enumeration",
        "fieldType": "select",
        "options": _opts(
            ("under_10k",   "Under $10k"),
            ("10k_25k",     "$10k–$25k"),
            ("25k_50k",     "$25k–$50k"),
            ("50k_100k",    "$50k–$100k"),
            ("100k_250k",   "$100k–$250k"),
            ("over_250k",   "Over $250k"),
            ("unknown",     "Unknown"),
        ),
        "formField": True,
    },
    {
        "name": "intake_enforcement_status",
        "label": "Enforcement status",
        "groupName": "tps_intake",
        "type": "enumeration",
        "fieldType": "checkbox",
        "options": _opts(
            ("none",                  "None"),
            ("lien_filed",            "Lien filed"),
            ("levy_active",           "Levy active"),
            ("wage_garnishment",      "Wage garnishment"),
            ("bank_levy",             "Bank levy"),
            ("passport_revocation",   "Passport revocation"),
            ("warrant_filed",         "Warrant filed"),
        ),
        "formField": True,
    },
    {
        "name": "intake_enforcement_deadline",
        "label": "Enforcement deadline",
        "groupName": "tps_intake",
        "type": "date",
        "fieldType": "date",
        "formField": True,
    },
    {
        "name": "intake_state_of_residence",
        "label": "State of residence",
        "groupName": "tps_intake",
        "type": "enumeration",
        "fieldType": "select",
        "options": US_STATES,
        "formField": True,
    },
    {
        "name": "intake_entity_type",
        "label": "Entity type",
        "groupName": "tps_intake",
        "type": "enumeration",
        "fieldType": "radio",
        "options": _opts(
            ("individual",          "Individual"),
            ("sole_prop",           "Sole proprietor"),
            ("single_member_llc",   "Single-member LLC"),
            ("multi_member_llc",    "Multi-member LLC"),
            ("s_corp",              "S corp"),
            ("c_corp",              "C corp"),
            ("partnership",         "Partnership"),
            ("nonprofit",           "Nonprofit"),
        ),
        "formField": True,
    },
    {
        "name": "intake_returns_unfiled_count",
        "label": "Unfiled returns (count)",
        "groupName": "tps_intake",
        "type": "number",
        "fieldType": "number",
        "formField": True,
    },
    {
        "name": "intake_contacted_by_revenue_officer",
        "label": "Contacted by Revenue Officer?",
        "groupName": "tps_intake",
        "type": "enumeration",
        "fieldType": "radio",
        "options": _opts(("yes", "Yes"), ("no", "No"), ("unknown", "Unknown")),
        "formField": True,
    },
    {
        "name": "intake_prior_representation",
        "label": "Prior representation",
        "groupName": "tps_intake",
        "type": "enumeration",
        "fieldType": "radio",
        "options": _opts(
            ("none",          "None"),
            ("cpa",           "CPA"),
            ("attorney",      "Attorney"),
            ("enrolled_agent","Enrolled agent"),
            ("national_firm", "National firm"),
        ),
        "formField": True,
    },
    {
        "name": "intake_qualifying_signal_count",
        "label": "Qualifying signal count",
        "description": "0–3, computed by n8n classifier per FL SaaS 2-Lane ICP rule.",
        "groupName": "tps_intake",
        "type": "number",
        "fieldType": "number",
    },
    {
        "name": "intake_notes",
        "label": "Intake notes",
        "groupName": "tps_intake",
        "type": "string",
        "fieldType": "textarea",
        "formField": True,
    },
    {
        "name": "intake_consent_contact",
        "label": "Consent to contact (TCPA)",
        "groupName": "tps_intake",
        "type": "bool",
        "fieldType": "booleancheckbox",
        "options": _opts(("true", "Yes"), ("false", "No")),
        "formField": True,
    },
    {
        "name": "intake_consent_no_engagement",
        "label": "Acknowledged: no engagement until signed",
        "groupName": "tps_intake",
        "type": "bool",
        "fieldType": "booleancheckbox",
        "options": _opts(("true", "Yes"), ("false", "No")),
        "formField": True,
    },
    {
        "name": "intake_completed_at",
        "label": "Intake completed at",
        "groupName": "tps_intake",
        "type": "datetime",
        "fieldType": "date",
    },
    {
        "name": "intake_form_version",
        "label": "Intake form version",
        "groupName": "tps_intake",
        "type": "string",
        "fieldType": "text",
        "formField": True,
    },
]


# ---- C. Triage / routing decision -----------------------------------------

TRIAGE_PROPERTIES: list[Property] = [
    {
        "name": "triage_score",
        "label": "Triage score (0–100)",
        "description": "Computed by n8n; clamped to 0–100.",
        "groupName": "tps_triage",
        "type": "number",
        "fieldType": "number",
    },
    {
        "name": "triage_tier",
        "label": "Triage tier",
        "groupName": "tps_triage",
        "type": "enumeration",
        "fieldType": "select",
        "options": _opts(
            ("tier_1_emergency",     "Tier 1 – Emergency"),
            ("tier_2_qualified",     "Tier 2 – Qualified"),
            ("tier_3_nurture",       "Tier 3 – Nurture"),
            ("tier_4_disqualified",  "Tier 4 – Disqualified"),
        ),
    },
    {
        "name": "triage_routing_decision",
        "label": "Triage routing decision",
        "groupName": "tps_triage",
        "type": "enumeration",
        "fieldType": "select",
        "options": _opts(
            ("same_day_callback",  "Same-day callback"),
            ("book_case_review",   "Book case review"),
            ("manual_review",      "Manual review"),
            ("nurture_sequence",   "Nurture sequence"),
            ("referral_out",       "Referral out"),
        ),
    },
    {
        "name": "triage_routing_reason",
        "label": "Triage routing reason",
        "groupName": "tps_triage",
        "type": "string",
        "fieldType": "textarea",
    },
    {
        "name": "triage_assigned_owner",
        "label": "Triage assigned owner",
        "description": "HubSpot Owner ID set by routing.",
        "groupName": "tps_triage",
        "type": "enumeration",
        "fieldType": "select",
        "referencedObjectType": "OWNER",
        "externalOptions": True,
    },
]


# ---- D. Lifecycle / engagement --------------------------------------------

LIFECYCLE_PROPERTIES: list[Property] = [
    {
        "name": "lifecycle_stage_tps",
        "label": "TPS lifecycle stage",
        "description": "Custom stage track parallel to HubSpot lifecyclestage.",
        "groupName": "tps_lifecycle",
        "type": "enumeration",
        "fieldType": "select",
        "options": _opts(
            ("lead",          "Lead"),
            ("mql_triaged",   "MQL – triaged"),
            ("sql_booked",    "SQL – booked"),
            ("consult_held",  "Consult held"),
            ("proposal_sent", "Proposal sent"),
            ("engaged",       "Engaged"),
            ("closed_lost",   "Closed lost"),
        ),
    },
    {
        "name": "lifecycle_consult_outcome",
        "label": "Consult outcome",
        "groupName": "tps_lifecycle",
        "type": "enumeration",
        "fieldType": "select",
        "options": _opts(
            ("engaged",          "Engaged"),
            ("follow_up_needed", "Follow-up needed"),
            ("not_qualified",    "Not qualified"),
            ("referred_out",     "Referred out"),
            ("no_show",          "No show"),
        ),
    },
    {
        "name": "lifecycle_engagement_letter_sent_at",
        "label": "Engagement letter sent at",
        "groupName": "tps_lifecycle",
        "type": "datetime",
        "fieldType": "date",
    },
    {
        "name": "lifecycle_engagement_letter_signed_at",
        "label": "Engagement letter signed at",
        "description": "Triggers Canopy migration workflow.",
        "groupName": "tps_lifecycle",
        "type": "datetime",
        "fieldType": "date",
    },
    {
        "name": "lifecycle_canopy_synced",
        "label": "Synced to Canopy?",
        "groupName": "tps_lifecycle",
        "type": "bool",
        "fieldType": "booleancheckbox",
        "options": _opts(("true", "Yes"), ("false", "No")),
    },
    {
        "name": "lifecycle_canopy_client_id",
        "label": "Canopy client ID",
        "groupName": "tps_lifecycle",
        "type": "string",
        "fieldType": "text",
    },
]


# ---- E. Quo-specific ------------------------------------------------------

QUO_PROPERTIES: list[Property] = [
    {
        "name": "quo_phone_number_routed",
        "label": "Quo phone number routed (DID)",
        "description": "The Quo DID the inbound call/SMS hit, in E.164 format.",
        "groupName": "tps_quo",
        "type": "string",
        "fieldType": "phonenumber",
    },
]


ALL_PROPERTIES: list[Property] = (
    SOURCE_PROPERTIES
    + INTAKE_PROPERTIES
    + TRIAGE_PROPERTIES
    + LIFECYCLE_PROPERTIES
    + QUO_PROPERTIES
)
