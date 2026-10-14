import { DAY, HOUR, digest, amount, format, time, requireThat, ceilDiv } from './policy.mjs';

export function creditReleaseForInterval(intervalHours) {
  requireThat(Number.isInteger(intervalHours) && intervalHours >= 1 && intervalHours <= 744, 'INTERVAL_INVALID');
  const presets = { 24: 67, 168: 500, 336: 1000 };
  // Illustrative organization-adjustable amounts, not a credit-to-dollar conversion.
  // Other cadences use a 30-day reference and round upward to whole credits.
  return String(presets[intervalHours] ?? Math.min(2000, Math.ceil(2000 * intervalHours / 720)));
}

export function usdReleaseForInterval(intervalHours) {
  requireThat(Number.isInteger(intervalHours) && intervalHours >= 1 && intervalHours <= 744, 'INTERVAL_INVALID');
  // Separate USD illustration: $200 per month, with cap amounts rounded to cents.
  const presets = { 24: '6.67', 168: '50', 336: '100' };
  const cents = ceilDiv(20_000n * BigInt(intervalHours), 720n);
  return presets[intervalHours] ?? format((cents > 20_000n ? 20_000n : cents) * 10_000n);
}

export function exampleConfig({ now = new Date().toISOString(), pattern = 'fixed_release', cohort = 'selected', unit = 'credit', intervalHours = 24, synthetic = true } = {}) {
  requireThat(['credit', 'usd'].includes(unit), 'UNIT_INVALID');
  const date = new Date(now);
  const release = unit === 'credit' ? creditReleaseForInterval(intervalHours) : usdReleaseForInterval(intervalHours);
  return { version: 1, workspaceId: synthetic ? 'synthetic-workspace' : 'REPLACE_WORKSPACE_ID', unit,
    period: { kind: 'calendar_month', start: new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), 1)).toISOString(),
      end: new Date(Date.UTC(date.getUTCFullYear(), date.getUTCMonth() + 1, 1)).toISOString(), verifiedAt: now,
      evidence: synthetic ? 'Synthetic fixture; no live counter evidence.' : '', counterScopeConfirmed: synthetic },
    policy: { pattern, anchor: new Date(Math.floor(time(now) / HOUR) * HOUR).toISOString(),
      ...(pattern === 'individual_staircase'
        ? { initialHeadroom: release, minimumInitialHeadroom: unit === 'credit' ? '1' : '0.01' }
        : { startCap: release }),
      increment: release, intervalHours, ceiling: unit === 'credit' ? '2000' : '200',
      lookbackDays: 7, coverageHours: 24, multiplierBps: 15_000 },
    cohort: { mode: cohort, userIds: cohort === 'all' ? [] : synthetic ? ['synthetic-user-a', 'synthetic-user-b'] : ['REPLACE_USER_ID'], emails: [], groupIds: [] },
    maxMembers: null, concurrency: 1, captureConcurrency: 1, initialReviewMaxAgeMinutes: 15,
    allowInitialReduction: false, liveWrites: false };
}
export function createSyntheticApi({ config, clock = () => new Date().toISOString(), saved, persist = async () => {},
  initialCap = config.unit === 'credit' ? '2000' : '200' }) {
  requireThat(config.workspaceId === 'synthetic-workspace', 'SYNTHETIC_WORKSPACE_REQUIRED');
  const users = saved ? structuredClone(saved) : Object.fromEntries(['synthetic-user-a', 'synthetic-user-b', 'synthetic-user-c'].map(userId => {
    // Tests may pin a smaller fake before-state without changing the public example.
    const rule = { type: 'limited', limit_amount: { amount: initialCap, unit: config.unit } };
    const effective = { limit: rule, source: { kind: 'workspace_default' } };
    return [userId, { workspaceId: config.workspaceId, userId, email: `${userId}@example.invalid`, unit: config.unit, usage: '0',
      cap: { type: 'limited', amount: rule.limit_amount.amount, unit: config.unit, source: 'workspace_default' },
      settings: { override: null, effective, inherited: effective }, observedAt: clock() }];
  }));
  let fault;
  const api = {
    synthetic: true, writes: [], users,
    groups: { 'synthetic-group-a': ['synthetic-user-a', 'synthetic-user-b'], 'synthetic-group-b': ['synthetic-user-b', 'synthetic-user-c'] },
    injectFault(nextFault) { fault = nextFault; },
    async listMembers() { return Object.keys(users).sort(); },
    async listMemberDirectory() { return (await api.listMembers()).map(userId => ({ userId, email: users[userId].email ?? null })); },
    async resolveEmail(email) {
      const matches = Object.entries(users).filter(([, user]) => user.email?.trim().toLowerCase() === email.trim().toLowerCase());
      requireThat(matches.length === 1, matches.length ? 'EMAIL_RESOLUTION_AMBIGUOUS' : 'EMAIL_NOT_FOUND');
      return { userId: matches[0][0], email: matches[0][1].email };
    },
    async listGroupMembers(groupId) {
      requireThat(Object.hasOwn(api.groups, groupId), 'GROUP_NOT_FOUND');
      return [...api.groups[groupId]].sort();
    },
    async assertMemberActive(userId) { requireThat(Object.hasOwn(users, userId), 'MEMBER_NOT_ACTIVE'); return { userId, email: users[userId].email ?? null }; },
    async readSnapshot(id) {
      requireThat(users[id], 'SYNTHETIC_USER_UNAVAILABLE');
      if (fault?.type === 'read' && fault.userId === id) { fault = null; throw Object.assign(new Error('SIMULATED_READ_FAILURE'), {code:'SIMULATED_READ_FAILURE'}); }
      return structuredClone({ ...users[id], observedAt: clock() });
    },
    async readHistory(userId, { start, end, unit }) {
      return { workspaceId: config.workspaceId, userId, unit, start, end, observedAt: clock(), semantics: 'observed',
        days: Array.from({ length: (time(end) - time(start)) / DAY }, (_, i) => ({ date: new Date(time(start) + i * DAY).toISOString().slice(0, 10), amount: unit === 'credit' ? '20' : '2' })) };
    },
    async setCap(id, target) {
      const error = fault?.userId === id ? fault : null;
      if (error) fault = null;
      if (error?.type === 'before') throw Object.assign(new Error('SIMULATED_WRITE_FAILURE'), {code:'SIMULATED_WRITE_FAILURE', status:error.status, retryAfterMs:error.retryAfterMs});
      const rule = { type: 'limited', limit_amount: { amount: target.amount, unit: target.unit }, limit_expires_at: target.periodEnd };
      users[id] = { ...users[id], cap: {type:'limited',amount:target.amount,unit:target.unit,source:'individual_override',expiresAt:target.periodEnd},
        settings: { ...users[id].settings, override:[rule], effective: {limit:rule,source:{kind:'individual_override'}} } };
      api.writes.push({ userId:id, ...target });
      await persist(users);
      if (error?.type === 'after') throw Object.assign(new Error('SIMULATED_AMBIGUOUS_WRITE'), {code:'SIMULATED_AMBIGUOUS_WRITE'});
    },
    async restore(id, {settings}) {
      const savedSettings = structuredClone(settings);
      const rule = savedSettings.effective?.limit;
      users[id] = { ...users[id], settings:savedSettings, cap: rule ? { type:rule.type, unit:config.unit,
        ...(rule.type === 'limited' ? {amount:String(rule.limit_amount?.amount ?? rule.limit)} : {}),
        source:savedSettings.effective.source.kind, ...(rule.limit_expires_at ? {expiresAt:rule.limit_expires_at} : {}) } : {type:'unset',unit:config.unit} };
      api.writes.push({userId:id,restore:true});
      await persist(users);
    },
  };
  return api;
}

export class MemoryStore {
  states = new Map(); archives = new Map(); receipts = []; locks = new Set();
  async withLock(key, fn) { requireThat(!this.locks.has(key), 'LEASE_BUSY'); this.locks.add(key); try {return await fn();} finally {this.locks.delete(key);} }
  async assertLock(key) {requireThat(this.locks.has(key), 'LOCK_REQUIRED');}
  async getState(key) {return structuredClone(this.states.get(key) ?? null);}
  async putState(key, value) {await this.assertLock(key); this.states.set(key,structuredClone(value));}
  async transitionState(key, { previous, next }) {
    await this.assertLock(key);
    requireThat(digest(await this.getState(key)) === digest(previous), 'RENEWAL_PRIOR_STATE_CHANGED');
    this.archives.set(`${key}:${previous.enrollmentHash}`, structuredClone(previous));
    await this.putState(key, next);
  }
  async putReceipt(value) {this.receipts.push(structuredClone(value));}
}
