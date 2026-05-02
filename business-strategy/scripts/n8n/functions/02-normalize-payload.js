// n8n Function node — normalizePayload
// Coerces HubSpot's submission shape into a stable internal schema:
// lowercase enums, multi-select arrays, parsed dates, trimmed strings.
// Also applies source-derived field defaults so the score reflects them.
//
// Inputs:  verified webhook payload from 01-verify-hmac
// Outputs: { hs_contact_id, submitted_at, fields: {...} }

const f = $json.fields || {};

const arr = (v) => {
  if (Array.isArray(v)) return v;
  if (v == null || v === '') return [];
  return String(v).split(';').map((s) => s.trim()).filter(Boolean);
};
const lower = (v) => (v == null ? null : String(v).trim().toLowerCase());
const upper = (v) => (v == null ? null : String(v).trim().toUpperCase());
const num   = (v) => (v == null || v === '' ? null : Number(v));
const date  = (v) => (v ? new Date(v) : null);
const text  = (v) => (v == null ? null : String(v).trim());

const fields = {
  email:                    text(f.email),
  phone:                    text(f.phone),
  firstname:                text(f.firstname),
  lastname:                 text(f.lastname),

  source_domain:            lower(f.intake_source_domain),
  source_site_group:        lower(f.intake_source_site_group),
  source_offer:             lower(f.intake_source_offer),
  channel:                  lower(f.intake_channel),
  utm_landing_path:         text(f.utm_landing_path),
  quo_phone_number_routed:  text(f.quo_phone_number_routed),

  existing_client_status:   lower(f.intake_existing_client_status),
  agency_track:             lower(f.intake_agency_track),
  lane:                     lower(f.intake_lane),
  primary_service_line:     lower(f.intake_primary_service_line),
  primary_issue_family:     lower(f.intake_primary_issue_family),
  notice_type:              arr(f.intake_notice_type).map(lower),
  enforcement_status:       arr(f.intake_enforcement_status).map(lower),
  enforcement_deadline:     date(f.intake_enforcement_deadline),
  tax_years_owed:           text(f.intake_tax_years_owed),
  balance_range:            lower(f.intake_balance_range),
  returns_unfiled_count:    num(f.intake_returns_unfiled_count),
  contacted_by_ro:          lower(f.intake_contacted_by_revenue_officer),
  prior_representation:     lower(f.intake_prior_representation),
  state_of_residence:       upper(f.intake_state_of_residence),
  entity_type:              lower(f.intake_entity_type),
  qualifying_signal_count:  num(f.intake_qualifying_signal_count),
  intake_notes:             text(f.intake_notes),
};

// Field defaults derived from source — must run before scoring so the score
// reflects the corrected agency/lane. (Routing-only overrides live in
// 05-apply-source-overrides.js and run after tier assignment.)
if (
  fields.source_domain === 'thefltaxguy.cpa' &&
  (!fields.agency_track || fields.agency_track === 'unknown')
) {
  fields.agency_track = 'fdor';
  if (!fields.lane) fields.lane = 'fl_dor_sales_audit';
}

return {
  hs_contact_id: $json.hs_contact_id,
  submitted_at:  $json.submitted_at,
  fields,
};
