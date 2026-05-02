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
  const wrapped = `(function () {\n${code}\n})()`;
  const ctx = {
    $json: payload,
    $headers: headers,
    $env: env,
    require, Buffer, Date, Math, JSON, Array, Object, Number, String, Boolean, console,
  };
  return vm.runInNewContext(wrapped, ctx);
}

function pipeline(fields) {
  // Skip HMAC verification in tests (covered separately).
  let p = { hs_contact_id: 'TEST', submitted_at: new Date().toISOString(), fields };
  p = runFn('02-normalize-payload.js', p);
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
    intake_source_domain: 'thefltaxguy.cpa',
    intake_agency_track: 'fdor',
    intake_primary_issue_family: 'collections',
    intake_balance_range: '100k_250k',
    intake_enforcement_status: 'bank_levy',
    intake_state_of_residence: 'FL',
    intake_entity_type: 's_corp',
  });
  expect('t1_fl_bank_levy.routing', r.triage_routing_decision, 'same_day_callback');
  expect('t1_fl_bank_levy.tier',    r.tier, 'tier_1_emergency');
  expectRange('t1_fl_bank_levy.score', r.triage_score, 0, 100);
}

// 2. IRS individual, lien + deadline + $50–100k → tier 2, book
{
  const inTwoWeeks = new Date(Date.now() + 10 * 864e5).toISOString().slice(0, 10);
  const r = pipeline({
    intake_source_domain: 'keithjones.cpa',
    intake_agency_track: 'irs',
    intake_primary_issue_family: 'collections',
    intake_balance_range: '50k_100k',
    intake_enforcement_status: 'lien_filed',
    intake_enforcement_deadline: inTwoWeeks,
    intake_state_of_residence: 'TX',
    intake_entity_type: 'individual',
  });
  expect('t2_irs_lien.routing', r.triage_routing_decision, 'book_case_review');
  expect('t2_irs_lien.tier',    r.tier, 'tier_2_qualified');
}

// 3. Score 40–69 with other_state agency → manual_review (the gap fix)
{
  const inTwoWeeks = new Date(Date.now() + 10 * 864e5).toISOString().slice(0, 10);
  const r = pipeline({
    intake_source_domain: 'keithjones.cpa',
    intake_agency_track: 'other_state',
    intake_primary_issue_family: 'collections',
    intake_balance_range: '100k_250k',
    intake_enforcement_status: 'lien_filed',
    intake_enforcement_deadline: inTwoWeeks,
    intake_state_of_residence: 'NY',
    intake_entity_type: 's_corp',
  });
  expect('t3_other_state.routing', r.triage_routing_decision, 'manual_review');
  expect('t3_other_state.reason',  r.triage_routing_reason, 'score_in_band_but_unclear_fit');
}

// 4. Small balance, no enforcement → tier 4, referral_out
{
  const r = pipeline({
    intake_source_domain: 'keithjones.cpa',
    intake_agency_track: 'irs',
    intake_primary_issue_family: 'notice',
    intake_balance_range: 'under_10k',
    intake_enforcement_status: 'none',
    intake_state_of_residence: 'TX',
    intake_entity_type: 'individual',
  });
  expect('t4_small_no_enf.routing', r.triage_routing_decision, 'referral_out');
  expect('t4_small_no_enf.tier',    r.tier, 'tier_4_disqualified');
  expect('t4_small_no_enf.reason',  r.triage_routing_reason, 'small_balance_no_enforcement');
}

// 5. thefltaxguy.cpa with unknown agency → coerced to fdor + lane defaulted
{
  const r = pipeline({
    intake_source_domain: 'thefltaxguy.cpa',
    intake_agency_track: 'unknown',
    intake_primary_issue_family: 'sales_tax_exposure',
    intake_balance_range: '25k_50k',
    intake_enforcement_status: 'none',
    intake_state_of_residence: 'FL',
    intake_entity_type: 'multi_member_llc',
  });
  expect('t5_fdor_default.agency', r.fields.agency_track, 'fdor');
  expect('t5_fdor_default.lane',   r.fields.lane, 'fl_dor_sales_audit');
  // FL + fdor + multi_member_llc + agency_track + balance(8) = score ~ 28 → tier 3
  expect('t5_fdor_default.tier',   r.tier, 'tier_3_nurture');
}

// 6. Advisor referral via taxstrategist.cpa → forced book_case_review
{
  const r = pipeline({
    intake_source_domain: 'taxstrategist.cpa',
    intake_source_offer: 'advisor_referral',
    intake_existing_client_status: 'referral',
    intake_agency_track: 'irs',
    intake_primary_issue_family: 'audit',
    intake_balance_range: 'under_10k',
    intake_enforcement_status: 'none',
    intake_state_of_residence: 'CA',
    intake_entity_type: 'individual',
  });
  expect('t6_advisor.routing', r.triage_routing_decision, 'book_case_review');
  expect('t6_advisor.tier',    r.tier, 'tier_2_qualified');
}

// 7. Missing critical fields, no enforcement → manual_review (catch-all)
{
  const r = pipeline({
    intake_source_domain: 'keithjones.cpa',
    // no agency_track, no balance_range, no issue_family
    intake_enforcement_status: 'none',
    intake_state_of_residence: 'TX',
    intake_entity_type: 'individual',
  });
  expect('t7_missing.routing', r.triage_routing_decision, 'manual_review');
  expect('t7_missing.reason',  r.triage_routing_reason, 'missing_critical_fields');
}

// 8. Score never exceeds 100 even with every enforcement flag set
{
  const inTwoWeeks = new Date(Date.now() + 5 * 864e5).toISOString().slice(0, 10);
  const r = pipeline({
    intake_source_domain: 'keithjones.cpa',
    intake_agency_track: 'both',
    intake_primary_issue_family: 'collections',
    intake_balance_range: 'over_250k',
    intake_enforcement_status: 'levy_active;wage_garnishment;bank_levy;warrant_filed;lien_filed;passport_revocation',
    intake_enforcement_deadline: inTwoWeeks,
    intake_state_of_residence: 'FL',
    intake_entity_type: 'c_corp',
  });
  expect('t8_max_score.tier', r.tier, 'tier_1_emergency');
  expectRange('t8_max_score.score', r.triage_score, 0, 100);
}

// 9. Score never goes below 0
{
  const r = pipeline({
    intake_source_domain: 'keithjones.cpa',
    intake_agency_track: 'unknown',
    intake_primary_issue_family: 'other',
    intake_balance_range: 'under_10k',
    intake_enforcement_status: 'none',
    intake_state_of_residence: 'TX',
    intake_entity_type: 'individual',
    intake_prior_representation: 'national_firm',
  });
  expectRange('t9_floor.score', r.triage_score, 0, 100);
}

// 10. Active levy + missing critical fields → emergency wins, NOT manual_review
{
  const r = pipeline({
    intake_source_domain: 'keithjones.cpa',
    intake_enforcement_status: 'levy_active',
    intake_state_of_residence: 'TX',
    intake_entity_type: 'individual',
  });
  expect('t10_emergency_with_missing.routing', r.triage_routing_decision, 'same_day_callback');
  expect('t10_emergency_with_missing.tier',    r.tier, 'tier_1_emergency');
  expect('t10_emergency_with_missing.reason',  r.triage_routing_reason, 'active_enforcement');
}

// 11. keithjones.cpa urgent CTA with under_10k → urgent floor catches referral_out
{
  const r = pipeline({
    intake_source_domain: 'keithjones.cpa',
    intake_source_offer: 'urgent_triage',
    intake_agency_track: 'irs',
    intake_primary_issue_family: 'notice',
    intake_balance_range: 'under_10k',
    intake_enforcement_status: 'none',
    intake_state_of_residence: 'TX',
    intake_entity_type: 'individual',
  });
  expect('t11_urgent_floor.routing', r.triage_routing_decision, 'book_case_review');
  expect('t11_urgent_floor.tier',    r.tier, 'tier_2_qualified');
  if (!r.triage_routing_reason || !r.triage_routing_reason.includes('urgent_page_floor')) {
    failed++;
    failures.push(`  t11_urgent_floor.reason\n    expected to include 'urgent_page_floor'\n    actual: ${r.triage_routing_reason}`);
  } else {
    passed++;
  }
}

// 12. Quo voice channel passes through normalize correctly
{
  const r = pipeline({
    intake_source_domain: 'thefltaxguy.cpa',
    intake_channel: 'quo_voice',
    quo_phone_number_routed: '+19045551234',
    intake_agency_track: 'fdor',
    intake_primary_issue_family: 'sales_tax_exposure',
    intake_balance_range: '50k_100k',
    intake_enforcement_status: 'none',
    intake_state_of_residence: 'FL',
    intake_entity_type: 'multi_member_llc',
  });
  expect('t12_quo_voice.channel',     r.fields.channel, 'quo_voice');
  expect('t12_quo_voice.quo_did',     r.fields.quo_phone_number_routed, '+19045551234');
  expect('t12_quo_voice.agency',      r.fields.agency_track, 'fdor');
}

// ---- assertion: tier output uses triage_ prefix on output object ---------
{
  const r = pipeline({
    intake_source_domain: 'keithjones.cpa',
    intake_agency_track: 'irs',
    intake_primary_issue_family: 'collections',
    intake_balance_range: '100k_250k',
    intake_enforcement_status: 'levy_active',
    intake_state_of_residence: 'TX',
    intake_entity_type: 'individual',
  });
  expect('t13_output_keys.has_routing_decision', typeof r.triage_routing_decision, 'string');
  expect('t13_output_keys.has_score',            typeof r.triage_score, 'number');
}

// ---- HMAC verification tests --------------------------------------------
{
  const crypto = require('crypto');
  const SECRET = 'test-secret-1234';
  const body = { hello: 'world', n: 42 };
  const goodSig = crypto.createHmac('sha256', SECRET).update(JSON.stringify(body)).digest('hex');

  // 14. Bare hex signature passes (HubSpot-style)
  try {
    runFn('01-verify-hmac.js', body, { 'x-tps-signature': goodSig }, { INTAKE_WEBHOOK_SECRET: SECRET });
    passed++;
  } catch (e) {
    failed++;
    failures.push(`  t14_hmac_bare.passes\n    threw: ${e.message}`);
  }

  // 15. sha256=<hex> prefixed signature passes (Quo / GitHub-style)
  try {
    runFn('01-verify-hmac.js', body, { 'x-tps-signature': 'sha256=' + goodSig }, { INTAKE_WEBHOOK_SECRET: SECRET });
    passed++;
  } catch (e) {
    failed++;
    failures.push(`  t15_hmac_prefixed.passes\n    threw: ${e.message}`);
  }

  // 16. Wrong signature throws INVALID_SIGNATURE (no RangeError on length mismatch)
  try {
    runFn('01-verify-hmac.js', body, { 'x-tps-signature': 'deadbeef' }, { INTAKE_WEBHOOK_SECRET: SECRET });
    failed++;
    failures.push(`  t16_hmac_wrong.throws\n    expected throw, got success`);
  } catch (e) {
    if (e.message === 'INVALID_SIGNATURE') {
      passed++;
    } else {
      failed++;
      failures.push(`  t16_hmac_wrong.throws\n    expected INVALID_SIGNATURE, got: ${e.message}`);
    }
  }

  // 17. Missing header throws explicit error (not a crash)
  try {
    runFn('01-verify-hmac.js', body, {}, { INTAKE_WEBHOOK_SECRET: SECRET });
    failed++;
    failures.push(`  t17_hmac_missing.throws\n    expected throw, got success`);
  } catch (e) {
    if (e.message === 'Missing X-TPS-Signature header') {
      passed++;
    } else {
      failed++;
      failures.push(`  t17_hmac_missing.throws\n    expected Missing X-TPS-Signature header, got: ${e.message}`);
    }
  }
}

// ---- report --------------------------------------------------------------
console.log(`\n${passed} passed, ${failed} failed`);
if (failures.length) {
  console.log('\nFailures:');
  failures.forEach((f) => console.log(f));
  process.exit(1);
}
