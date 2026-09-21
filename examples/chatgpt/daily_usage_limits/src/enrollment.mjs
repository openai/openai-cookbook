import { digest, configDigest, validateConfig, validateSnapshot, planTarget, historyRange, requireThat, time, approvalWindowMs } from './policy.mjs';
import { resolveCohort, validateSavedSelection } from './selection.mjs';

export function enrollmentHash(enrollment) {
  const { approval, ...snapshot } = enrollment;
  return digest(snapshot);
}
export function approveEnrollment(enrollment, hash, now = new Date().toISOString()) {
  requireThat(hash === enrollmentHash(enrollment), 'REVIEW_HASH_MISMATCH');
  requireThat(time(now) >= time(enrollment.capturedAt), 'REVIEW_TIME_INVALID');
  return { ...enrollment, approval: { hash, reviewedAt: now } };
}
export function validateEnrollment(config, enrollment, now, approved = false) {
  validateConfig(config, now);
  requireThat(enrollment?.version === 1 && enrollment.configDigest === configDigest(config), 'ENROLLMENT_POLICY_MISMATCH');
  requireThat(enrollment.workspaceId === config.workspaceId && enrollment.unit === config.unit, 'ENROLLMENT_IDENTITY_MISMATCH');
  requireThat(time(enrollment.capturedAt) <= time(now), 'ENROLLMENT_IN_FUTURE');
  requireThat(Array.isArray(enrollment.members) && enrollment.members.length > 0 &&
    (config.maxMembers == null || enrollment.members.length <= config.maxMembers), 'COHORT_SIZE_INVALID');
  const ids = enrollment.members.map(member => member.userId);
  requireThat(ids.every(id => typeof id === 'string' && id.length > 0) && new Set(ids).size === ids.length, 'COHORT_DUPLICATES');
  validateSavedSelection(config, enrollment);
  if (enrollment.completedAt) requireThat(time(enrollment.completedAt) >= time(enrollment.capturedAt) &&
    time(enrollment.completedAt) <= time(now), 'ENROLLMENT_CAPTURE_TIME_INVALID');
  if (approved) requireThat(enrollment.approval?.hash === enrollmentHash(enrollment) && time(enrollment.approval.reviewedAt) <= time(now), 'ENROLLMENT_APPROVAL_REQUIRED');
}
export async function captureEnrollment({ config, api, now: fixedNow, clock = () => new Date().toISOString() }) {
  const now = fixedNow ?? clock();
  const readNow = () => fixedNow ?? clock();
  const context = validateConfig(config, now);
  const { userIds: ids, activeUserIds: active, selection } = await resolveCohort({ config, api });
  const members = new Array(ids.length);
  let next = 0, error;
  await Promise.all(Array.from({ length: Math.min(config.captureConcurrency ?? config.concurrency, ids.length) }, async () => {
    while (!error) {
      const index = next++;
      if (index >= ids.length) return;
      try {
        const userId = ids[index];
        const before = await api.readSnapshot(userId);
        validateSnapshot(before, config, userId, readNow());
        const history = config.policy.pattern === 'observed_headroom' ? await api.readHistory(userId, historyRange(config, now)) : undefined;
        const plan = planTarget(config, before, readNow(), history);
        requireThat(plan.slot === context.slot, 'CAPTURE_SLOT_CHANGED_RECAPTURE');
        members[index] = { userId, before, plan };
      } catch (caught) { error ??= caught; }
    }
  }));
  if (error) throw error;
  const completedAt = readNow();
  requireThat(time(completedAt) - time(now) <= approvalWindowMs(config), 'CAPTURE_REVIEW_WINDOW_EXPIRED');
  requireThat(validateConfig(config, completedAt).slot === context.slot, 'CAPTURE_SLOT_CHANGED_RECAPTURE');
  const enrollment = { version: 1, configDigest: configDigest(config), workspaceId: config.workspaceId,
    unit: config.unit, capturedAt: now, completedAt, rosterHash: digest(active), selection, members };
  return { enrollment, hash: enrollmentHash(enrollment) };
}
