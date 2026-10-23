import { createHash } from 'node:crypto';
import { normalizeCohort } from './selection.mjs';

export const HOUR = 3_600_000;
export const DAY = 24 * HOUR;
export const SCALE = 1_000_000n;
export const fail = code => Object.assign(new Error(code), { code });
export function requireThat(condition, code) { if (!condition) throw fail(code); }
export function digest(value) {
  const canonical = item => Array.isArray(item) ? item.map(canonical) : item && typeof item === 'object'
    ? Object.fromEntries(Object.keys(item).sort().map(key => [key, canonical(item[key])])) : item;
  return createHash('sha256').update(JSON.stringify(canonical(value))).digest('hex');
}
export function amount(value) {
  requireThat(typeof value === 'string' && /^\d{1,12}(?:\.\d{1,6})?$/.test(value), 'INVALID_DECIMAL_AMOUNT');
  const [whole, fraction = ''] = value.split('.');
  return BigInt(whole) * SCALE + BigInt(fraction.padEnd(6, '0'));
}
export function format(value) {
  requireThat(value >= 0n, 'NEGATIVE_AMOUNT');
  const fraction = String(value % SCALE).padStart(6, '0').replace(/0+$/, '');
  return `${value / SCALE}${fraction ? `.${fraction}` : ''}`;
}
export const min = (a, b) => a < b ? a : b;
export const max = (a, b) => a > b ? a : b;
export function quantum(unit) {
  requireThat(['credit', 'usd'].includes(unit), 'UNIT_INVALID');
  return unit === 'credit' ? SCALE : 10_000n;
}
export const ceilDiv = (a, b) => (a + b - 1n) / b;
export function capAmount(value, unit) {
  const result = amount(value);
  requireThat(result % quantum(unit) === 0n, 'CAP_PRECISION_INVALID');
  requireThat(result <= 2_147_483_647n * SCALE, 'CAP_TOO_LARGE');
  return result;
}
export function time(value) {
  requireThat(typeof value === 'string' && /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{3})?Z$/.test(value), 'UTC_TIMESTAMP_REQUIRED');
  const parsed = Date.parse(value);
  requireThat(Number.isFinite(parsed) && new Date(parsed).toISOString().replace('.000Z', 'Z') === value.replace('.000Z', 'Z'), 'INVALID_TIMESTAMP');
  return parsed;
}
export function configDigest(config) {
  // Switching write gates does not change the reviewed policy. Everything else does.
  const { liveWrites, ...reviewed } = config;
  return digest(reviewed);
}
export function approvalWindowMs(config) {
  const minutes = config.initialReviewMaxAgeMinutes ?? 15;
  requireThat(Number.isSafeInteger(minutes) && minutes > 0 &&
    minutes <= (time(config.period.end) - time(config.period.start)) / 60_000, 'INITIAL_REVIEW_WINDOW_INVALID');
  return minutes * 60_000;
}
export function validatePolicy(config, now) {
  requireThat(config?.version === 1, 'CONFIG_VERSION_INVALID');
  requireThat(typeof config.workspaceId === 'string' && config.workspaceId.length > 0, 'WORKSPACE_REQUIRED');
  requireThat(['credit', 'usd'].includes(config.unit), 'UNIT_INVALID');
  requireThat(typeof config.liveWrites === 'boolean' && typeof config.allowInitialReduction === 'boolean', 'EXPLICIT_WRITE_GATES_REQUIRED');
  const period = config.period;
  requireThat(['calendar_month', 'billing_cycle'].includes(period?.kind), 'PERIOD_KIND_INVALID');
  const start = time(period.start), end = time(period.end), current = time(now), verified = time(period.verifiedAt);
  requireThat(start < end && end - start >= 20 * DAY && end - start <= 32 * DAY, 'MONTHLY_PERIOD_REQUIRED');
  requireThat(start <= current && current < end, 'OUTSIDE_VERIFIED_PERIOD');
  requireThat(verified >= start && verified <= current && typeof period.evidence === 'string' && period.evidence.trim(), 'PERIOD_CONFIRMATION_REQUIRED');
  requireThat(start % DAY === 0 && end % DAY === 0, 'PERIOD_UTC_MIDNIGHT_REQUIRED');
  requireThat(period.counterScopeConfirmed === true, 'COUNTER_PERIOD_SCOPE_CONFIRMATION_REQUIRED');
  if (period.kind === 'calendar_month') {
    const date = new Date(start);
    requireThat(date.getUTCDate() === 1 && end === Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 1), 'CALENDAR_PERIOD_INVALID');
  }
  const p = config.policy;
  requireThat(['fixed_release', 'observed_headroom', 'individual_staircase'].includes(p?.pattern), 'PATTERN_INVALID');
  requireThat(Number.isInteger(p.intervalHours) && p.intervalHours >= 1 && p.intervalHours <= 744, 'INTERVAL_INVALID');
  const anchor = time(p.anchor);
  requireThat(anchor >= start && anchor < end, 'ANCHOR_OUTSIDE_PERIOD');
  requireThat(current >= anchor, 'BEFORE_POLICY_ANCHOR');
  const ceiling = capAmount(p.ceiling, config.unit);
  requireThat(capAmount(p.increment, config.unit) > 0n, 'RELEASE_BOUNDS_INVALID');
  if (p.pattern === 'individual_staircase') {
    requireThat(!Object.hasOwn(p, 'startCap') && !Object.hasOwn(p, 'startCaps'), 'AMBIGUOUS_START_CAP');
    const initial = capAmount(p.initialHeadroom, config.unit);
    const minimum = capAmount(p.minimumInitialHeadroom, config.unit);
    requireThat(initial > 0n && minimum > 0n && minimum <= initial && minimum <= ceiling, 'INITIAL_HEADROOM_INVALID');
  } else requireThat(capAmount(p.startCap, config.unit) <= ceiling, 'RELEASE_BOUNDS_INVALID');
  if (p.pattern === 'observed_headroom') {
    requireThat(Number.isInteger(p.lookbackDays) && p.lookbackDays >= 1 && p.lookbackDays <= 30, 'LOOKBACK_INVALID');
    requireThat(Number.isInteger(p.coverageHours) && p.coverageHours >= 1 && p.coverageHours <= 744, 'COVERAGE_HOURS_INVALID');
    requireThat(Number.isInteger(p.multiplierBps) && p.multiplierBps > 0 && p.multiplierBps <= 100_000, 'MULTIPLIER_INVALID');
  }
  approvalWindowMs(config);
  return { slot: Math.floor((current - anchor) / (p.intervalHours * HOUR)), current, start, end, ceiling };
}
export function validateConfig(config, now) {
  const context = validatePolicy(config, now);
  normalizeCohort(config.cohort);
  requireThat(config.maxMembers == null || (Number.isSafeInteger(config.maxMembers) && config.maxMembers > 0), 'MAX_MEMBERS_INVALID');
  requireThat(Number.isSafeInteger(config.concurrency) && config.concurrency > 0, 'CONCURRENCY_INVALID');
  const captureConcurrency = config.captureConcurrency ?? config.concurrency;
  requireThat(Number.isSafeInteger(captureConcurrency) && captureConcurrency > 0, 'CAPTURE_CONCURRENCY_INVALID');
  if (config.apiLimits !== undefined) {
    requireThat(config.apiLimits && typeof config.apiLimits === 'object' && !Array.isArray(config.apiLimits) &&
      Object.entries(config.apiLimits).every(([key, value]) => ['maxPages', 'maxRows'].includes(key) &&
        Number.isSafeInteger(value) && value > 0), 'API_LIMITS_INVALID');
  }
  return context;
}
export function validateSnapshot(snapshot, config, userId, now) {
  requireThat(snapshot.workspaceId === config.workspaceId && snapshot.userId === userId, 'IDENTITY_MISMATCH');
  requireThat(snapshot.unit === config.unit && snapshot.cap.unit === config.unit, 'UNIT_TRANSITION_REQUIRES_REENROLLMENT');
  amount(snapshot.usage);
  requireThat(snapshot.settings && Object.hasOwn(snapshot.settings, 'override') && (snapshot.settings.effective || (snapshot.cap.type === 'unset' && snapshot.settings.effective === null && snapshot.settings.inherited === null && (snapshot.settings.override === null || (Array.isArray(snapshot.settings.override) && snapshot.settings.override.length === 0)))), 'EXACT_BEFORE_STATE_REQUIRED');
  requireThat(['limited', 'unlimited', 'unset'].includes(snapshot.cap.type), 'CAP_TYPE_INVALID');
  if (snapshot.cap.type === 'limited') capAmount(snapshot.cap.amount, config.unit);
  if (snapshot.cap.expiresAt) requireThat(time(snapshot.cap.expiresAt) === time(config.period.end), 'CAP_EXPIRY_PERIOD_MISMATCH');
  const age = time(now) - time(snapshot.observedAt);
  requireThat(age >= 0 && age <= 60_000, 'SNAPSHOT_NOT_FRESH');
  requireThat(time(snapshot.observedAt) >= time(config.period.start) && time(snapshot.observedAt) < time(config.period.end), 'SNAPSHOT_OUTSIDE_PERIOD');
}
export function historyRange(config, now) {
  const end = Math.floor(time(now) / DAY) * DAY;
  return { start: new Date(end - config.policy.lookbackDays * DAY).toISOString(), end: new Date(end).toISOString(), unit: config.unit };
}

export function validateInitialHeadroom(config, snapshot, target) {
  if (config.policy.pattern !== 'individual_staircase') return;
  requireThat(snapshot.unit === config.unit, 'UNIT_TRANSITION_REQUIRES_REENROLLMENT');
  requireThat(capAmount(target, config.unit) >= amount(snapshot.usage) + capAmount(config.policy.minimumInitialHeadroom, config.unit),
    'INITIAL_HEADROOM_TOO_LOW_RECAPTURE');
}

// Enrollment freezes this value for the period. Later usage never rebases it.
export function deriveStartingCap(config, snapshot) {
  requireThat(config.policy.pattern === 'individual_staircase', 'INDIVIDUAL_PATTERN_REQUIRED');
  const rounded = ceilDiv(amount(snapshot.usage) + capAmount(config.policy.initialHeadroom, config.unit), quantum(config.unit)) * quantum(config.unit);
  const startCap = format(min(rounded, capAmount(config.policy.ceiling, config.unit)));
  validateInitialHeadroom(config, snapshot, startCap);
  return startCap;
}

export function planTarget(config, snapshot, now, history, { startCap } = {}) {
  const { slot, ceiling } = validatePolicy(config, now);
  const p = config.policy;
  let desired;
  let observedDailyAverage;
  if (p.pattern === 'individual_staircase') {
    requireThat(typeof startCap === 'string', 'INDIVIDUAL_START_CAP_REQUIRED');
    const seed = capAmount(startCap, config.unit);
    requireThat(seed <= ceiling, 'RELEASE_BOUNDS_INVALID');
    desired = seed + BigInt(slot) * amount(p.increment);
  } else if (p.pattern === 'fixed_release') {
    desired = amount(p.startCap) + BigInt(slot) * amount(p.increment);
  } else {
    const range = historyRange(config, now);
    requireThat(history?.semantics === 'observed' && history.workspaceId === config.workspaceId && history.userId === snapshot.userId && history.unit === config.unit, 'HISTORY_SCOPE_MISMATCH');
    requireThat(time(history.start) === time(range.start) && time(history.end) === time(range.end), 'HISTORY_RANGE_MISMATCH');
    requireThat(time(history.observedAt) <= time(now) && time(now) - time(history.observedAt) <= 60_000, 'HISTORY_STALE');
    requireThat(Array.isArray(history.days) && history.days.length === p.lookbackDays, 'MISSING_HISTORY_DAYS');
    const days = new Map(history.days.map(day => [day.date, day.amount]));
    requireThat(days.size === p.lookbackDays, 'DUPLICATE_HISTORY_DAY');
    let total = 0n;
    for (let date = time(range.start); date < time(range.end); date += DAY) {
      const value = days.get(new Date(date).toISOString().slice(0, 10));
      requireThat(value !== undefined && value !== null, 'MISSING_HISTORY_DAY');
      total += amount(value);
    }
    observedDailyAverage = format(ceilDiv(total, BigInt(p.lookbackDays)));
    // History is daily; coverageHours is an explicit linear estimate, independent of cadence.
    const headroom = ceilDiv(total * BigInt(p.coverageHours) * BigInt(p.multiplierBps), BigInt(p.lookbackDays) * 24n * 10_000n);
    const rounded = ceilDiv(amount(snapshot.usage) + headroom, quantum(config.unit)) * quantum(config.unit);
    desired = max(amount(p.startCap), rounded);
    if (snapshot.cap.type === 'limited') desired = max(amount(snapshot.cap.amount), desired);
  }
  const target = min(desired, ceiling);
  return { pattern: p.pattern, slot, slotId: `${config.period.start}/${p.anchor}/${p.intervalHours}/${slot}`,
    ...(p.pattern === 'individual_staircase' ? { startCap, minimumInitialHeadroom: p.minimumInitialHeadroom } : {}),
    amount: format(target), unit: config.unit, ceiling: p.ceiling,
    headroom: format(max(0n, target - amount(snapshot.usage))),
    shortfall: format(max(0n, desired - target)), observedDailyAverage,
    wouldRestrict: snapshot.cap.type !== 'limited' || amount(snapshot.cap.amount) > target,
    usageAtOrAboveTarget: amount(snapshot.usage) >= target,
    historySemantics: p.pattern === 'observed_headroom' ? 'observed, eventually consistent; not finalized' : 'not used' };
}
