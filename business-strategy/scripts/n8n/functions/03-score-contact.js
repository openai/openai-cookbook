// n8n Function node — scoreContact
// Implements the scoring rules from multi-domain-intake-architecture.md §4C.
// - Enforcement subtotal capped at 60 (multi-select can't blow past the envelope).
// - Final score clamped to [0, 100] so it always matches the documented range.
//
// Inputs:  normalized payload from 02-normalize-payload
// Outputs: { ...payload, triage_score, no_enforcement }

const f = $json.fields;
const has = (set, v) => Array.isArray(set) && set.indexOf(v) > -1;

let score = 0;

// --- Enforcement urgency (cap at 60) --------------------------------------
let enforcementSub = 0;
if (has(f.enforcement_status, 'levy_active'))         enforcementSub += 35;
if (has(f.enforcement_status, 'wage_garnishment'))    enforcementSub += 35;
if (has(f.enforcement_status, 'bank_levy'))           enforcementSub += 30;
if (has(f.enforcement_status, 'warrant_filed'))       enforcementSub += 25;
if (has(f.enforcement_status, 'lien_filed'))          enforcementSub += 15;
if (has(f.enforcement_status, 'passport_revocation')) enforcementSub += 25;

if (f.enforcement_deadline) {
  const days = Math.floor((f.enforcement_deadline - new Date()) / 864e5);
  if (days >= 0 && days <= 14) enforcementSub += 15;
}
score += Math.min(enforcementSub, 60);

// --- Balance signal (max 20) ---------------------------------------------
const balanceMap = { over_250k: 20, '100k_250k': 16, '50k_100k': 12, '25k_50k': 8, '10k_25k': 4 };
score += balanceMap[f.balance_range] || 0;

// --- Fit signal (max 20) — uses agency_track consistently -----------------
if (['irs', 'fdor', 'both'].includes(f.agency_track)) score += 10;
if (f.state_of_residence === 'FL' && ['fdor', 'both'].includes(f.agency_track)) score += 5;
if (['s_corp', 'multi_member_llc', 'c_corp'].includes(f.entity_type)) score += 5;

// --- Negative signals -----------------------------------------------------
const noEnforcement =
  !f.enforcement_status ||
  f.enforcement_status.length === 0 ||
  (f.enforcement_status.length === 1 && f.enforcement_status[0] === 'none');

if (f.balance_range === 'under_10k' && noEnforcement) score -= 20;
// (national_firm + previously declined consult requires a HubSpot lookup; deferred to v2)

// --- Final clamp ----------------------------------------------------------
score = Math.max(0, Math.min(100, score));

return Object.assign({}, $json, { triage_score: score, no_enforcement: noEnforcement });
