// Local test harness for the n8n function-node logic.
// Wraps each function so it runs outside n8n (no $json / $headers / $env globals).
//
// Run:  node test/test-routing.js
// Exits non-zero on any test failure.

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const FN_DIR = path.join(__dirname, '..', 'functions');

// ---- shim n8n's runtime --------------------------------------------------
function runFn(file, payload, headers = {}, env = {}) {
  const code = fs.readFileSync(path.join(FN_DIR, file), 'utf8');
  // Wrap so the function-node body can `return` like n8n expects.
  const wrapped = `(function () {\n${code}\n})()`;
  const ctx = {
    $json: payload,
    $headers: headers,
    $env: env,
    require,
    Buffer,
    Date,
    Math,
    JSON,
    Array,
    Object,
    Number,
    String,
    Boolean,
    console,
  };
  return vm.runInNewContext(wrapped, ctx);
}

function pipeline(fields, opts = {}) {
  // Skip HMAC verification in tests (covered separately).
  let p = { hs_contact_id: 'TEST', submitted_at: new Date().toISOString(), fields };
  p = runFn('02-normalize-payload.js', p);
  // Allow tests to override normalized fields directly (e.g. inject Date objects)
  if (opts.overrideFields) Object.assign(p.fields, opts.overrideFields);
  p = runFn('03-score-contact.js', p);
  p = runFn('04-assign-tier.js', p);
  p = runFn('05-apply-source-overrides.js', p);
  return p;
}

// ---- assertions ----------------------------------------------------------
let passed = 0;
let failed = 0;
const failures = [];

function expect(name, actual, expected) {
  const ok = JSON.stringify(actual) === JSON.stringify(expected);
  if (ok) {
    passed++;
  } else {
    failed++;
    failures.push(`  ${name}\n    expected: ${JSON.stringify(expected)}\n    actual:   ${JSON.stringify(actual)}`);
  }
}

function expectRange(name, actual, lo, hi) {
  if (actual >= lo && actual <= hi) {
    passed++;
  } else {
    failed++;
    failures.push(`  ${name}\n    expected in [${lo}, ${hi}]\n    actual: ${actual}`);
  }
}

// ---- tests ---------------------------------------------------------------

// 1. FL S-corp with active bank levy → tier 1, same-day callback
{
  const r = pipeline({
    tps_source_domain: 'floridataxsavior.com',
    tps_agency_track: 'fdor',
    tps_primary_issue_family: 'collections',
    tps_balance_range: '100k_250k',
    tps_enforcement_status: 'bank_levy',
    tps_state_of_residence: 'FL',
    tps_entity_type: 's_corp',
  });
  expect('t1_fl_bank_levy.routing', r.routing_decision, 'same_day_callback');
  expect('t1_fl_bank_levy.tier',    r.tier, 'tier_1_emergency');
  expectRange('t1_fl_bank_levy.score', r.triage_score, 0, 100);
}

// 2. IRS individual, lien + deadline + $50–100k → tier 2, book
{
  const inTwoWeeks = new Date(Date.now() + 10 * 864e5).toISOString().slice(0, 10);
  const r = pipeline({
    tps_source_domain: 'keithjones.cpa',
    tps_agency_track: 'irs',
    tps_primary_issue_family: 'collections',
    tps_balance_range: '50k_100k',
    tps_enforcement_status: 'lien_filed',
    tps_enforcement_deadline: inTwoWeeks,
    tps_state_of_residence: 'TX',
    tps_entity_type: 'individual',
  });
  expect('t2_irs_lien.routing', r.routing_decision, 'book_case_review');
  expect('t2_irs_lien.tier',    r.tier, 'tier_2_qualified');
}

// 3. Score 40–69 with other_state agency → manual_review (the gap fix)
{
  const inTwoWeeks = new Date(Date.now() + 10 * 864e5).toISOString().slice(0, 10);
  const r = pipeline({
    tps_source_domain: 'keithjones.cpa',
    tps_agency_track: 'other_state',
    tps_primary_issue_family: 'collections',
    tps_balance_range: '100k_250k',
    tps_enforcement_status: 'lien_filed',
    tps_enforcement_deadline: inTwoWeeks,
    tps_state_of_residence: 'NY',
    tps_entity_type: 's_corp',
  });
  expect('t3_other_state.routing', r.routing_decision, 'manual_review');
  expect('t3_other_state.reason',  r.routing_reason, 'score_in_band_but_unclear_fit');
}

// 4. Small balance, no enforcement → tier 4, referral_out
{
  const r = pipeline({
    tps_source_domain: 'keithjones.cpa',
    tps_agency_track: 'irs',
    tps_primary_issue_family: 'notice',
    tps_balance_range: 'under_10k',
    tps_enforcement_status: 'none',
    tps_state_of_residence: 'TX',
    tps_entity_type: 'individual',
  });
  expect('t4_small_no_enf.routing', r.routing_decision, 'referral_out');
  expect('t4_small_no_enf.tier',    r.tier, 'tier_4_disqualified');
  expect('t4_small_no_enf.reason',  r.routing_reason, 'small_balance_no_enforcement');
}

// 5. floridataxsavior.com with unknown agency → coerced to fdor
{
  const r = pipeline({
    tps_source_domain: 'floridataxsavior.com',
    tps_agency_track: 'unknown',
    tps_primary_issue_family: 'sales_tax_exposure',
    tps_balance_range: '25k_50k',
    tps_enforcement_status: 'none',
    tps_state_of_residence: 'FL',
    tps_entity_type: 'multi_member_llc',
  });
  expect('t5_fdor_default.agency', r.fields.agency_track, 'fdor');
  // FL + fdor + multi_member_llc + agency_track + balance(8) = score ~ 28 → tier 3
  expect('t5_fdor_default.tier', r.tier, 'tier_3_nurture');
}

// 6. Advisor referral via taxstrategist.cpa → forced book_case_review
{
  const r = pipeline({
    tps_source_domain: 'taxstrategist.cpa',
    tps_source_offer: 'advisor_referral',
    tps_existing_client_status: 'referral',
    tps_agency_track: 'irs',
    tps_primary_issue_family: 'audit',
    tps_balance_range: 'under_10k',
    tps_enforcement_status: 'none',
    tps_state_of_residence: 'CA',
    tps_entity_type: 'individual',
  });
  expect('t6_advisor.routing', r.routing_decision, 'book_case_review');
  expect('t6_advisor.tier',    r.tier, 'tier_2_qualified');
}

// 7. Missing critical fields → manual_review
{
  const r = pipeline({
    tps_source_domain: 'keithjones.cpa',
    // no agency_track, no balance_range, no issue_family
    tps_enforcement_status: 'lien_filed',
    tps_state_of_residence: 'TX',
    tps_entity_type: 'individual',
  });
  expect('t7_missing.routing', r.routing_decision, 'manual_review');
  expect('t7_missing.reason',  r.routing_reason, 'missing_critical_fields');
}

// 8. Score never exceeds 100 even with every enforcement flag set
{
  const inTwoWeeks = new Date(Date.now() + 5 * 864e5).toISOString().slice(0, 10);
  const r = pipeline({
    tps_source_domain: 'keithjones.cpa',
    tps_agency_track: 'both',
    tps_primary_issue_family: 'collections',
    tps_balance_range: 'over_250k',
    // semicolon-separated → normalized to array
    tps_enforcement_status: 'levy_active;wage_garnishment;bank_levy;warrant_filed;lien_filed;passport_revocation',
    tps_enforcement_deadline: inTwoWeeks,
    tps_state_of_residence: 'FL',
    tps_entity_type: 'c_corp',
  });
  expect('t8_max_score.tier', r.tier, 'tier_1_emergency');
  expectRange('t8_max_score.score', r.triage_score, 0, 100);
}

// 9. Score never goes below 0
{
  const r = pipeline({
    tps_source_domain: 'keithjones.cpa',
    tps_agency_track: 'unknown',  // no fit bonus
    tps_primary_issue_family: 'other',
    tps_balance_range: 'under_10k',
    tps_enforcement_status: 'none',
    tps_state_of_residence: 'TX',
    tps_entity_type: 'individual',
    tps_prior_representation: 'national_firm',
  });
  expectRange('t9_floor.score', r.triage_score, 0, 100);
}

// 10. Active levy + missing critical fields → emergency wins, NOT manual_review
//     (regression test for catch-all-before-emergency bug)
{
  const r = pipeline({
    tps_source_domain: 'keithjones.cpa',
    // intentionally missing agency_track, balance_range, primary_issue_family
    tps_enforcement_status: 'levy_active',
    tps_state_of_residence: 'TX',
    tps_entity_type: 'individual',
  });
  expect('t10_emergency_with_missing.routing', r.routing_decision, 'same_day_callback');
  expect('t10_emergency_with_missing.tier',    r.tier, 'tier_1_emergency');
  expect('t10_emergency_with_missing.reason',  r.routing_reason, 'active_enforcement');
}

// 11. keithjones.cpa urgent CTA with under_10k → urgent floor catches referral_out
{
  const r = pipeline({
    tps_source_domain: 'keithjones.cpa',
    tps_source_offer: 'urgent_triage',
    tps_agency_track: 'irs',
    tps_primary_issue_family: 'notice',
    tps_balance_range: 'under_10k',
    tps_enforcement_status: 'none',
    tps_state_of_residence: 'TX',
    tps_entity_type: 'individual',
  });
  expect('t11_urgent_floor.routing', r.routing_decision, 'book_case_review');
  expect('t11_urgent_floor.tier',    r.tier, 'tier_2_qualified');
  // routing_reason should include the urgent_page_floor marker
  if (!r.routing_reason || !r.routing_reason.includes('urgent_page_floor')) {
    failed++;
    failures.push(`  t11_urgent_floor.reason\n    expected to include 'urgent_page_floor'\n    actual: ${r.routing_reason}`);
  } else {
    passed++;
  }
}

// ---- report --------------------------------------------------------------
console.log(`\n${passed} passed, ${failed} failed`);
if (failures.length) {
  console.log('\nFailures:');
  failures.forEach((f) => console.log(f));
  process.exit(1);
}
