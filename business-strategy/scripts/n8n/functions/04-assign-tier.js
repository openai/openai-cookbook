// n8n Function node — assignTier
// Top-down tier assignment from multi-domain-intake-architecture.md §4C.
// Every contact lands in exactly one routing decision; first matching row wins.
//
// Inputs:  scored payload from 03-score-contact
// Outputs: { ...payload, tier, triage_tier, triage_routing_decision, triage_routing_reason }
// (`tier` is also exposed unprefixed for downstream override convenience.)

const f = $json.fields;
const score = $json.triage_score;
const noEnf = $json.no_enforcement;

const ACTIVE = ['levy_active', 'wage_garnishment', 'bank_levy', 'warrant_filed'];
const activeEnforcement = ACTIVE.some((s) => (f.enforcement_status || []).includes(s));
const validAgency = ['irs', 'fdor', 'both'].includes(f.agency_track);
const hasBalance = f.balance_range && f.balance_range !== 'under_10k';
const missingCritical = !f.agency_track || !f.balance_range || !f.primary_issue_family;

let tier = null;
let triage_routing_decision;
let triage_routing_reason;

// Spec §4C tier table, evaluated top-down.
// Row 1 (emergency) MUST come before row 6 (missing-critical catch-all):
// a contact with active enforcement but missing fields is still an
// emergency — get them to a human immediately, fill gaps later.
if (activeEnforcement || score >= 70) {
  tier = 'tier_1_emergency';
  triage_routing_decision = 'same_day_callback';
  triage_routing_reason = activeEnforcement ? 'active_enforcement' : 'high_score';
} else if (missingCritical) {
  triage_routing_decision = 'manual_review';
  triage_routing_reason = 'missing_critical_fields';
} else if (score >= 40 && validAgency && hasBalance) {
  tier = 'tier_2_qualified';
  triage_routing_decision = 'book_case_review';
  triage_routing_reason = 'qualified_score';
} else if (score >= 40) {
  triage_routing_decision = 'manual_review';
  triage_routing_reason = 'score_in_band_but_unclear_fit';
} else if (score >= 15) {
  tier = 'tier_3_nurture';
  triage_routing_decision = 'nurture_sequence';
  triage_routing_reason = 'low_score';
} else {
  tier = 'tier_4_disqualified';
  triage_routing_decision = 'referral_out';
  triage_routing_reason = (f.balance_range === 'under_10k' && noEnf)
    ? 'small_balance_no_enforcement'
    : 'very_low_score';
}

return Object.assign({}, $json, {
  tier,                       // unprefixed for downstream override convenience
  triage_tier: tier,          // matches HubSpot property name
  triage_routing_decision,
  triage_routing_reason,
});
