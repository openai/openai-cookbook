import { captureEnrollment, enrollmentHash, validateEnrollment } from './enrollment.mjs';
import { digest, configDigest, requireThat, time, approvalWindowMs, validateConfig } from './policy.mjs';
import { settingsEquivalent, inheritedSettingsEquivalent } from './admin-api.mjs';

const hasOverride = settings => Array.isArray(settings.override) && settings.override.length > 0;
const same = (left, right, unit) => settingsEquivalent(left.settings, right.settings, unit);

function expiredToFallback(current, previous, unit, now) {
  if (!hasOverride(previous.settings) || !previous.cap.expiresAt ||
      time(previous.cap.expiresAt) > time(now) || hasOverride(current.settings)) return false;
  if (!inheritedSettingsEquivalent(current.settings, previous.settings, unit)) return false;
  // The API can repeat the active fallback in inherited. It must not introduce
  // a second, different rule while the personal override is absent.
  const expected = previous.settings.inherited;
  return settingsEquivalent(current.settings, {
    override: null, effective: expected,
    inherited: current.settings.inherited === null ? null : expected,
  }, unit);
}

export function validateRenewalState(member, state) {
  requireThat(state && member.renewal?.priorStateDigest === digest(state), 'RENEWAL_PRIOR_STATE_CHANGED');
  requireThat(!state.pending && !state.halted, 'RENEWAL_REQUIRES_SETTLED_STATE');
  requireThat(state.original && state.last, 'RENEWAL_PRIOR_STATE_INCOMPLETE');
  return state;
}

function restorationBaseline(state, current, unit, now) {
  requireThat(same(current, state.last, unit) || same(current, state.original, unit) ||
    expiredToFallback(current, state.last, unit, now), 'RENEWAL_CURRENT_STATE_CONFLICT');
  requireThat(inheritedSettingsEquivalent(current.settings, state.original.settings, unit), 'RENEWAL_INHERITED_SOURCE_CHANGED');
  const original = state.original;
  if (original.cap.expiresAt && time(original.cap.expiresAt) <= time(now)) {
    requireThat(expiredToFallback(current, original, unit, now), 'RENEWAL_EXPIRED_ORIGINAL_CONFLICT');
    return current;
  }
  return original;
}

export function validateRenewalProof(config, enrollment, member, state) {
  const proof = enrollment.renewal;
  requireThat(proof?.version === 1 && typeof proof.previousConfigDigest === 'string' &&
    typeof proof.previousEnrollmentHash === 'string' &&
    time(proof.previousPeriodEnd) <= time(config.period.start), 'RENEWAL_PROOF_INVALID');
  validateRenewalState(member, state);
  requireThat(state.configDigest === proof.previousConfigDigest &&
    state.enrollmentHash === proof.previousEnrollmentHash, 'RENEWAL_PRIOR_OWNER_MISMATCH');
  const original = member.renewal.original;
  requireThat(original?.workspaceId === config.workspaceId && original.userId === member.userId &&
    original.unit === config.unit, 'RENEWAL_ORIGINAL_IDENTITY_MISMATCH');
  requireThat(settingsEquivalent(original.settings, original.settings, config.unit), 'RENEWAL_ORIGINAL_INVALID');
  requireThat(digest(original) === digest(restorationBaseline(state, member.before, config.unit, member.before.observedAt)),
    'RENEWAL_ORIGINAL_CHANGED');
  return original;
}

/** Prepare the next period without changing caps, controller state or AWS resources.
 * Dates and counter scope come from explicit admin evidence, never an inferred reset.
 */
export async function captureRenewal({ previousConfig, previousEnrollment, period, api, store,
  now: fixedNow, clock = () => new Date().toISOString() }) {
  const now = fixedNow ?? clock();
  validateEnrollment(previousConfig, previousEnrollment, previousEnrollment.approval?.reviewedAt, true);
  requireThat(time(previousConfig.period.end) <= time(now) &&
    time(period.start) >= time(previousConfig.period.end), 'RENEWAL_REQUIRES_NEXT_PERIOD');
  const config = structuredClone(previousConfig);
  config.period = structuredClone(period);
  config.policy.anchor = period.start;
  config.liveWrites = false;
  const captured = await captureEnrollment({ config, api, ...(fixedNow ? { now } : { clock }) });
  const enrollment = captured.enrollment;
  requireThat(digest(enrollment.selection) === digest(previousEnrollment.selection) &&
    digest(enrollment.members.map(member => member.userId)) ===
      digest(previousEnrollment.members.map(member => member.userId)), 'RENEWAL_COHORT_CHANGED_REVIEW_REQUIRED');
  enrollment.renewal = { version: 1, previousConfigDigest: configDigest(previousConfig),
    previousEnrollmentHash: enrollmentHash(previousEnrollment), previousPeriodEnd: previousConfig.period.end };
  // Bounded reads use the capture concurrency, independently of population size.
  let next = 0;
  await Promise.all(Array.from({ length: Math.min(config.captureConcurrency ?? config.concurrency, enrollment.members.length) }, async () => {
    for (;;) {
      const member = enrollment.members[next++];
      if (!member) return;
      const state = await store.getState(`${config.workspaceId}:${member.userId}`);
      requireThat(state && state.configDigest === enrollment.renewal.previousConfigDigest &&
        state.enrollmentHash === enrollment.renewal.previousEnrollmentHash, 'RENEWAL_PRIOR_OWNER_MISMATCH');
      requireThat(!state.pending && !state.halted && state.last && state.original, 'RENEWAL_REQUIRES_SETTLED_STATE');
      // Expired original rules project to a proven fallback. Their historic
      // form remains in the previous period's archive.
      const original = restorationBaseline(state, member.before, config.unit, now);
      member.renewal = { priorStateDigest: digest(state), original: structuredClone(original) };
      validateRenewalProof(config, enrollment, member, state);
    }
  }));
  enrollment.completedAt = fixedNow ?? clock();
  requireThat(time(enrollment.completedAt) - time(enrollment.capturedAt) <= approvalWindowMs(config), 'CAPTURE_REVIEW_WINDOW_EXPIRED');
  requireThat(validateConfig(config, enrollment.completedAt).slot === enrollment.members[0].plan.slot, 'CAPTURE_SLOT_CHANGED_RECAPTURE');
  return { config, enrollment, hash: enrollmentHash(enrollment) };
}
