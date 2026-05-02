// n8n Function node — normalizePayload
// Coerces HubSpot's submission shape into a stable internal schema:
// lowercase enums, multi-select arrays, parsed dates, trimmed strings.
//
// Inputs:  verified webhook payload
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

  source_domain:            lower(f.tps_source_domain),
  source_site_group:        lower(f.tps_source_site_group),
  source_offer:             lower(f.tps_source_offer),

  existing_client_status:   lower(f.tps_existing_client_status),
  agency_track:             lower(f.tps_agency_track),
  primary_service_line:     lower(f.tps_primary_service_line),
  primary_issue_family:     lower(f.tps_primary_issue_family),
  notice_type:              arr(f.tps_notice_type).map(lower),
  enforcement_status:       arr(f.tps_enforcement_status).map(lower),
  enforcement_deadline:     date(f.tps_enforcement_deadline),
  tax_years_owed:           text(f.tps_tax_years_owed),
  balance_range:            lower(f.tps_balance_range),
  returns_unfiled_count:    num(f.tps_returns_unfiled_count),
  has_been_contacted_by_ro: lower(f.tps_has_been_contacted_by_revenue_officer),
  prior_representation:     lower(f.tps_prior_representation),
  state_of_residence:       upper(f.tps_state_of_residence),
  entity_type:              lower(f.tps_entity_type),
  intake_notes:             text(f.tps_intake_notes),
};

// Field defaults derived from source — must run before scoring so the score
// reflects the corrected agency/service-line. (Routing-only overrides live
// in 05-apply-source-overrides.js and run after tier assignment.)
if (
  fields.source_domain === 'floridataxsavior.com' &&
  (!fields.agency_track || fields.agency_track === 'unknown')
) {
  fields.agency_track = 'fdor';
  if (!fields.primary_service_line) fields.primary_service_line = 'florida_sales_tax';
}

return {
  hs_contact_id: $json.hs_contact_id,
  submitted_at:  $json.submitted_at,
  fields,
};
