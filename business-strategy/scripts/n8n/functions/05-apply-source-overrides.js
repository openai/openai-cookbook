// n8n Function node — applySourceOverrides
// Routing-only overrides from multi-domain-intake-architecture.md §4E.
// Field defaults (e.g. FDOR coercion for FL funnel) live in
// 02-normalize-payload.js so the score reflects them.
//
// Inputs:  routed payload from 04-assign-tier
// Outputs: same shape with possibly-changed triage_routing_decision / tier / triage_tier

const out = JSON.parse(JSON.stringify($json));
const src = out.fields.source_domain;
const offer = out.fields.source_offer;
const existing = out.fields.existing_client_status;

const appendReason = (s) => {
  out.triage_routing_reason = (out.triage_routing_reason || '')
    + (out.triage_routing_reason ? '|' : '')
    + s;
};

// Upgrade tier only if the current tier is unset, tier_3, or tier_4.
// (Don't downgrade tier_1_emergency to tier_2 — emergencies stay emergencies.)
const upgradeToTier2 = () => {
  if (!out.tier || ['tier_3_nurture', 'tier_4_disqualified'].includes(out.tier)) {
    out.tier = 'tier_2_qualified';
    out.triage_tier = 'tier_2_qualified';
  }
};

// Advisor referrals always get a meeting regardless of score.
if (
  src === 'taxstrategist.cpa' &&
  (offer === 'advisor_referral' || existing === 'referral')
) {
  out.triage_routing_decision = 'book_case_review';
  upgradeToTier2();
  appendReason('advisor_override');
}

// keithjones.cpa /irs-help urgent CTA: floor at booking (don't nurture or refer
// out a visitor who self-identified urgent intent). Catches both nurture and
// referral_out per spec §4E "Force min tier tier_2_qualified".
if (
  src === 'keithjones.cpa' &&
  offer === 'urgent_triage' &&
  ['nurture_sequence', 'referral_out'].includes(out.triage_routing_decision)
) {
  out.triage_routing_decision = 'book_case_review';
  upgradeToTier2();
  appendReason('urgent_page_floor');
}

return out;
