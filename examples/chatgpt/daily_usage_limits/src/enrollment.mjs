import { digest, configDigest, validateConfig, validateSnapshot, planTarget, historyRange, requireThat, time } from './policy.mjs';

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
  requireThat(Array.isArray(enrollment.members) && enrollment.members.length > 0 && enrollment.members.length <= config.maxMembers, 'COHORT_SIZE_INVALID');
  const ids = enrollment.members.map(member => member.userId);
  requireThat(ids.every(id => typeof id === 'string' && id.length > 0) && new Set(ids).size === ids.length, 'COHORT_DUPLICATES');
  if (config.cohort.mode === 'selected') requireThat(digest([...ids].sort()) === digest([...config.cohort.userIds].sort()), 'COHORT_REVIEW_MISMATCH');
  if (approved) requireThat(enrollment.approval?.hash === enrollmentHash(enrollment) && time(enrollment.approval.reviewedAt) <= time(now), 'ENROLLMENT_APPROVAL_REQUIRED');
}
export async function captureEnrollment({ config, api, now: fixedNow, clock = () => new Date().toISOString() }) {
  const now = fixedNow ?? clock();
  const readNow = () => fixedNow ?? clock();
  validateConfig(config, now);
  const active = await api.listMembers();
  requireThat(Array.isArray(active) && new Set(active).size === active.length, 'ROSTER_INVALID');
  const ids = config.cohort.mode === 'all' ? [...active].sort() : [...config.cohort.userIds].sort();
  requireThat(ids.length > 0 && ids.length <= config.maxMembers, 'COHORT_SIZE_INVALID');
  requireThat(ids.every(id => active.includes(id)), 'SELECTED_USER_NOT_ACTIVE_MEMBER');
  const members = [];
  // Capture is deliberately sequential, limiting API fan-out even for the all-members path.
  for (const userId of ids) {
    const before = await api.readSnapshot(userId);
    validateSnapshot(before, config, userId, readNow());
    const history = config.policy.pattern === 'observed_headroom' ? await api.readHistory(userId, historyRange(config, now)) : undefined;
    const plan = planTarget(config, before, readNow(), history);
    members.push({ userId, before, plan });
  }
  const enrollment = { version: 1, configDigest: configDigest(config), workspaceId: config.workspaceId,
    unit: config.unit, capturedAt: now, rosterHash: digest([...active].sort()), members };
  return { enrollment, hash: enrollmentHash(enrollment) };
}
