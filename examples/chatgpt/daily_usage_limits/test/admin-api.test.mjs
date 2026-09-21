import test from 'node:test';
import assert from 'node:assert/strict';
import { createAdminApi, inheritedSettingsEquivalent, matchesTarget, settingsEquivalent } from '../src/admin-api.mjs';

const workspaceId = 'workspace-example';
const userId = 'user-example';
const NOW = '2030-06-15T12:00:00.000Z';
const END = '2030-07-01T00:00:00.000Z';
const key = 'synthetic-key-not-a-credential';
const rule = (amount = '100', unit = 'credit', expiry) => ({ type: 'limited', limit: null,
  limit_amount: { amount, unit }, ...(expiry ? { limit_expires_at: expiry } : {}) });
const effective = (limit, source = { kind: 'workspace_default', seat_type: 'default' }) => ({ limit, source });
const inherited = unit => effective(rule('100', unit));
function user({ unit = 'credit', override = null, source, fallback } = {}) {
  return { object: 'workspace.user.usage_limit', id: userId,
    account_user_id: `${userId}__${workspaceId}`, override_monthly_usage_limit: override,
    effective_monthly_usage_limit: effective(override?.[0] ?? rule('100', unit),
      source ?? (override?.length ? { kind: 'individual_override' } : undefined)),
    inherited_monthly_usage_limit: fallback ?? inherited(unit) };
}
const directoryUser = (id = userId, email = 'synthetic@example.com') => ({
  object: 'workspace.user', id, email, name: 'Fictional User', role: 'member',
  seat_type: 'chatgpt', is_scim_managed: false,
});
const memberPage = (data = [], hasMore = false) => ({ object: 'list', data,
  first_id: data[0]?.id ?? null, last_id: data.at(-1)?.id ?? null, has_more: hasMore });
const groupId = 'group-example';
const groupUser = (id = userId, status = 'active') => ({ object: 'compliance.workspace.user', id,
  email: null, name: null, created_at: 0, role: 'standard-user', status, is_scim_managed: false });
const groupPage = (data = [], cursor = null, hasMore = false) => ({ object: 'list', data,
  last_id: data.at(-1)?.id ?? null, cursor, has_more: hasMore });
const groupResource = () => ({ object: 'directory.workspace.group', id: groupId, workspace_id: workspaceId,
  name: 'Fictional Group', created_at: 0, member_count: 1, source: 'manual' });
function harness({ unit = 'credit', usage = 25, original = user({ unit }), allowWrites = false,
  intercept, options = {} } = {}) {
  const requests = [];
  let current = structuredClone(original);
  let patches = 0;
  const response = value => ({ ok: true, status: 200, headers: new Headers(),
    json: async () => structuredClone(value) });
  const fetchImpl = async (url, init) => {
    requests.push({ url, ...init });
    if (intercept) {
      const result = await intercept({ url: new URL(url), init, response,
        requests, current, patchCount: patches });
      if (result) return result;
    }
    const path = new URL(url).pathname;
    if (path.endsWith('/usage_limits/workspace')) return response({ id: workspaceId });
    if (init.method === 'PATCH') {
      patches += 1;
      const input = JSON.parse(init.body).override_monthly_usage_limit;
      let override = null;
      if (input) {
        const saved = { ...input, limit: input.limit ?? null };
        delete saved.temporary;
        if (input.temporary) saved.limit_expires_at = END;
        override = [saved];
      }
      current = user({ unit, override });
      return response(current);
    }
    if (path.endsWith('/monthly-usage')) return response({
      id: userId, account_user_id: `${userId}__${workspaceId}`, current_month_usage: usage,
      current_month_usage_unit: unit,
      effective_monthly_usage_limit: current.effective_monthly_usage_limit?.limit ?? null,
    });
    if (path.endsWith(`/users/${userId}`)) return response(current);
    throw new Error('Unexpected synthetic endpoint');
  };
  return { requests, response, get patches() { return patches; }, api: createAdminApi({
    apiKey: key, workspaceId, userIds: [userId], allowWrites, fetchImpl, clock: () => NOW, ...options,
  }) };
}
const rejectsCode = (promise, code) => assert.rejects(promise, error => error.code === code);
const historyRow = (date, { id = userId, credits = 4, usd = null, actorId = id } = {}) => {
  const start = Date.parse(`${date}T00:00:00Z`) / 1000;
  return { object: 'workspace.usage.result', user_id: id,
    actor: { type: 'ACCOUNT_USER', user_id: actorId }, start_time: start, end_time: start + 86400,
    totals: { credits, cost_usd: usd, estimated_cost_usd: 999 }, clients: [] };
};
const query = { start: '2030-06-10T00:00:00Z', end: '2030-06-12T00:00:00Z', unit: 'credit' };

test('connection check uses three bounded GETs and returns only workspace, unit and Users Read status', async () => {
  for (const unit of ['credit', 'usd']) {
    const h = harness({ unit, original: { effective_monthly_usage_limit: null },
      options: { userIds: [], maxPages: 1, maxRows: 1 },
      intercept: ({ url, response }) => url.pathname.endsWith('/users')
        ? response(memberPage([directoryUser()], true)) : undefined });
    assert.deepEqual(await h.api.checkConnection(), { workspaceId, unit, usersRead: true });
    assert.deepEqual(h.requests.map(request => new URL(request.url).pathname + new URL(request.url).search), [
      `/v1/manage/workspaces/${workspaceId}/usage_limits/workspace`,
      `/v1/manage/workspaces/${workspaceId}/users?limit=1`,
      `/v1/manage/workspaces/${workspaceId}/usage_limits/users/${userId}/monthly-usage`,
    ]);
    assert.ok(h.requests.every(request => request.method === 'GET' && request.redirect === 'error' &&
      new URL(request.url).origin === 'https://api.chatgpt.com' && request.body === undefined));
    assert.equal(h.patches, 0);
    await rejectsCode(h.api.readSnapshot(userId), 'IDENTITY_NOT_ALLOWLISTED');
    assert.equal(h.requests.length, 3, 'connection check must not expand the enrollment allowlist');
  }
});

test('connection check rejects empty or malformed first-member pages without paging or monthly reads', async () => {
  const rows = [
    [memberPage(), 'CONNECTION_MEMBER_UNAVAILABLE'],
    [memberPage([], true), 'MEMBER_PAGE_INVALID'],
    [memberPage([directoryUser(), directoryUser('user-other')]), 'MEMBER_PAGE_INVALID'],
    [{ ...memberPage([directoryUser()]), first_id: 'user-other' }, 'MEMBER_PAGE_INVALID'],
    [{ ...memberPage([directoryUser()]), has_more: null }, 'MEMBER_PAGE_INVALID'],
    [memberPage([{ ...directoryUser(), email: undefined }]), 'MEMBER_PAGE_INCONSISTENT'],
    [memberPage([{ ...directoryUser(), id: '../other' }]), 'MEMBER_PAGE_INCONSISTENT'],
  ];
  for (const [page, code] of rows) {
    const h = harness({ intercept: ({ url, response }) => url.pathname.endsWith('/users') ? response(page) : undefined });
    await rejectsCode(h.api.checkConnection(), code);
    assert.equal(h.requests.length, 2);
    assert.equal(h.patches, 0);
  }
});

test('connection check requires matching workspace and sampled account identity and a documented unit', async () => {
  for (const [monthly, code] of [
    [{ id: 'user-other', account_user_id: `${userId}__${workspaceId}`, current_month_usage_unit: 'credit' }, 'USER_READBACK_MISMATCH'],
    [{ id: userId, account_user_id: `${userId}__other-workspace`, current_month_usage_unit: 'credit' }, 'USER_READBACK_MISMATCH'],
    ...[undefined, null, 'eur'].map(unit => [
      { id: userId, account_user_id: `${userId}__${workspaceId}`, current_month_usage_unit: unit }, 'USAGE_UNIT_UNAVAILABLE']),
  ]) {
    const h = harness({ intercept: ({ url, response }) => url.pathname.endsWith('/users')
      ? response(memberPage([directoryUser()])) : url.pathname.endsWith('/monthly-usage') ? response(monthly) : undefined });
    await rejectsCode(h.api.checkConnection(), code);
    assert.equal(h.requests.length, 3);
  }
  for (const workspace of [null, { id: 'other-workspace' }]) {
    const h = harness({ intercept: ({ response }) => response(workspace) });
    await rejectsCode(h.api.checkConnection(), 'WORKSPACE_READBACK_MISMATCH');
    assert.equal(h.requests.length, 1);
  }
});

test('connection check preserves sanitized HTTP failures and never retries authentication', async () => {
  for (const status of [401, 403, 429]) {
    const h = harness({ intercept: ({ url }) => url.pathname.endsWith('/users') ? {
      ok: false, status, headers: new Headers({ 'retry-after': '10' }),
      json() { assert.fail('private error body must not be read'); },
    } : undefined });
    await assert.rejects(h.api.checkConnection(), error => error.code === `ADMIN_HTTP_${status}` &&
      error.message === `ADMIN_HTTP_${status}` && error.retryable === (status === 429));
    assert.equal(h.requests.length, 2);
    assert.equal(h.patches, 0);
  }
});

test('connection check honors the remaining invocation budget before each GET', async () => {
  let remaining = 20_000;
  const h = harness({ options: { remainingTimeMs: () => remaining },
    intercept: ({ url, response }) => {
      if (url.pathname.endsWith('/users')) {
        remaining = 5_000;
        return response(memberPage([directoryUser()]));
      }
    } });
  await rejectsCode(h.api.checkConnection(), 'API_TIME_BUDGET_EXHAUSTED');
  assert.equal(h.requests.length, 2);
  assert.equal(h.patches, 0);
});

test('snapshot preserves original settings/source and rounds counters upward', async () => {
  const original = user({ source: { kind: 'group_default', group_id: 'group-example', group_name: 'Example' } });
  const h = harness({ original, usage: 25.1234567 });
  const snapshot = await h.api.readSnapshot(userId);
  assert.equal(snapshot.usage, '25.123457');
  assert.equal(snapshot.cap.source, 'group_default');
  assert.deepEqual(snapshot.settings.effective, original.effective_monthly_usage_limit);
  assert.equal(snapshot.settings.override, null);
  assert.equal(h.requests.length, 4);
  assert.equal(h.patches, 0);
  assert.ok(h.requests.every(request => request.url.startsWith('https://api.chatgpt.com/v1/')));
  assert.ok(h.requests.every(request => request.redirect === 'error'));
});

test('identity allowlist cannot be expanded by a method argument', async () => {
  const h = harness();
  await rejectsCode(h.api.readSnapshot('user-other'), 'IDENTITY_NOT_ALLOWLISTED');
  assert.equal(h.requests.length, 0);
  assert.throws(() => createAdminApi({ apiKey: key, workspaceId: '../other' }), /EXPLICIT_IDENTITY_ALLOWLIST_REQUIRED/);
});

test('wrong workspace and cross-workspace user IDs stop reads', async () => {
  for (const kind of ['workspace', 'user']) {
    const h = harness({ intercept: ({ url, response }) => {
      if (kind === 'workspace' && url.pathname.endsWith('/workspace')) return response({ id: 'other-workspace' });
      if (kind === 'user' && url.pathname.endsWith(`/users/${userId}`)) {
        return response({ ...user(), account_user_id: `${userId}__other-workspace` });
      }
    } });
    await rejectsCode(h.api.readSnapshot(userId), kind === 'workspace' ? 'WORKSPACE_READBACK_MISMATCH' : 'USER_READBACK_MISMATCH');
  }
});

test('missing, null, negative, and precision-unsafe counters are not zero', async () => {
  for (const usage of [null, -1, NaN, 1e12, 'not-a-number']) {
    const h = harness({ usage });
    await assert.rejects(h.api.readSnapshot(userId), /AMOUNT_/);
  }
});

test('tiny scientific-notation counters round upward', async () => {
  const h = harness({ usage: 1e-10 });
  assert.equal((await h.api.readSnapshot(userId)).usage, '0.000001');
});

test('USD requires tagged native amount and matching unit', async () => {
  const h = harness({ unit: 'usd', original: user({ unit: 'usd', override: [rule('125.50', 'usd')] }) });
  const snapshot = await h.api.readSnapshot(userId);
  assert.equal(snapshot.unit, 'usd');
  assert.equal(snapshot.cap.amount, '125.5');
  const mismatch = harness({ unit: 'usd', original: user() });
  await rejectsCode(mismatch.api.readSnapshot(userId), 'CAP_UNIT_MISMATCH');
});

test('unsupported multiple original rules and missing original state fail closed', async () => {
  const h = harness({ original: user({ override: [rule(), rule('200')] }) });
  await rejectsCode(h.api.readSnapshot(userId), 'OVERRIDE_NOT_RESTORABLE');
  const original = user();
  delete original.override_monthly_usage_limit;
  await rejectsCode(harness({ original }).api.readSnapshot(userId), 'BEFORE_STATE_UNAVAILABLE');
});

test('a null effective rule cannot hide an inherited rule', async () => {
  const original = user();
  original.effective_monthly_usage_limit = null;
  const h = harness({ original });
  await rejectsCode(h.api.readSnapshot(userId), 'UNSET_CAP_CONFLICT');
  assert.equal(h.patches, 0);
});

const unsetUser = () => ({ ...user(), override_monthly_usage_limit: null,
  effective_monthly_usage_limit: null, inherited_monthly_usage_limit: null });

test('explicitly absent settings produce an unset cap without an invented source or unlimited rule', async () => {
  const h = harness({ original: unsetUser() });
  const snapshot = await h.api.readSnapshot(userId);
  assert.deepEqual(snapshot.cap, { type: 'unset', unit: 'credit' });
  assert.deepEqual(snapshot.settings, { override: null, effective: null, inherited: null });
  assert.equal(snapshot.usage, '25');
  assert.equal(matchesTarget(snapshot, { amount: '500', unit: 'credit', periodEnd: END }), false);
  assert.equal(settingsEquivalent(snapshot.settings, { ...snapshot.settings, override: [] }, 'credit'), true);
  const unlimited = { override: [{ type: 'unlimited' }], inherited: null,
    effective: effective({ type: 'unlimited' }, { kind: 'individual_override' }) };
  assert.equal(settingsEquivalent(snapshot.settings, unlimited, 'credit'), false);
  assert.equal(h.requests.length, 4);
  assert.equal(h.patches, 0);
});

test('every before-state field must be explicit on both user reads', async () => {
  for (const field of ['override_monthly_usage_limit', 'effective_monthly_usage_limit', 'inherited_monthly_usage_limit']) {
    for (const read of [1, 2]) {
      let count = 0;
      const h = harness({ original: unsetUser(), intercept: ({ url, response }) => {
        if (url.pathname.endsWith(`/users/${userId}`) && ++count === read) {
          const body = unsetUser(); delete body[field]; return response(body);
        }
      } });
      await rejectsCode(h.api.readSnapshot(userId), 'BEFORE_STATE_UNAVAILABLE');
      assert.equal(h.patches, 0);
    }
  }
  assert.throws(() => settingsEquivalent({ override: null, effective: null },
    { override: null, effective: null, inherited: null }, 'credit'), { code: 'BEFORE_STATE_UNAVAILABLE' });
});

test('unset caps reject conflicting overrides, missing monthly state and changed repeated reads', async () => {
  await rejectsCode(harness({ original: { ...unsetUser(), override_monthly_usage_limit: [rule()] } })
    .api.readSnapshot(userId), 'UNSET_CAP_CONFLICT');
  await rejectsCode(harness({ original: { ...unsetUser(), effective_monthly_usage_limit: { limit: null, source: null } } })
    .api.readSnapshot(userId), 'CAP_SOURCE_UNAVAILABLE');
  for (const variant of ['missing', 'different', 'changed']) {
    let count = 0;
    const h = harness({ original: unsetUser(), intercept: ({ url, response }) => {
      if (url.pathname.endsWith('/monthly-usage') && variant !== 'changed') {
        return response({ id: userId, account_user_id: `${userId}__${workspaceId}`,
          current_month_usage: 25, current_month_usage_unit: 'credit',
          ...(variant === 'different' ? { effective_monthly_usage_limit: rule() } : {}) });
      }
      if (url.pathname.endsWith(`/users/${userId}`) && ++count === 2 && variant === 'changed') return response(user());
    } });
    await rejectsCode(h.api.readSnapshot(userId), { missing: 'CAP_UNAVAILABLE',
      different: 'CAP_CHANGED_BETWEEN_READS', changed: 'SETTINGS_CHANGED_BETWEEN_READS' }[variant]);
    assert.equal(h.patches, 0);
  }
});

test('fallback comparison preserves the active rule across personal-override representation changes', () => {
  for (const source of [{ kind: 'group_default', group_id: 'group-original', group_name: 'Fictional group' },
    { kind: 'workspace_default', seat_type: 'default' }, { kind: 'role_based_personal_budget', role_id: 'role-original' }]) {
    const fallback = effective(rule('40000'), source);
    const before = { override: null, effective: fallback, inherited: null };
    const limit = rule('500', 'credit', END);
    const after = { override: [limit], effective: effective(limit, { kind: 'individual_override' }), inherited: fallback };
    assert.equal(inheritedSettingsEquivalent(before, after, 'credit'), true);
    assert.equal(inheritedSettingsEquivalent(after, before, 'credit'), true);
    assert.equal(settingsEquivalent(before, after, 'credit'), false);
    for (const inherited of [null, effective(rule('39999'), source),
      effective(rule('40000'), { ...source, identity_revision: 'changed' })]) {
      assert.equal(inheritedSettingsEquivalent(before, { ...after, inherited }, 'credit'), false);
    }
    const absent = { override: null, effective: null, inherited: null };
    assert.equal(inheritedSettingsEquivalent(absent, after, 'credit'), false);
    assert.equal(inheritedSettingsEquivalent(absent, { ...after, inherited: null }, 'credit'), true);
  }
});

test('adapter writes and restores exact unset and group-default settings in either native unit', async () => {
  for (const unit of ['credit', 'usd']) for (const hasGroup of [false, true]) {
    const group = hasGroup ? effective(rule('40000', unit), { kind: 'group_default', group_id: 'group-original' }) : null;
    const original = { override: null, effective: group, inherited: null };
    let settings = structuredClone(original);
    const patches = [];
    const resource = () => ({ id: userId, account_user_id: `${userId}__${workspaceId}`,
      override_monthly_usage_limit: settings.override, effective_monthly_usage_limit: settings.effective,
      inherited_monthly_usage_limit: settings.inherited });
    const api = createAdminApi({ apiKey: key, workspaceId, userIds: [userId], allowWrites: true, clock: () => NOW,
      fetchImpl: async (url, init) => {
        const path = new URL(url).pathname;
        let value;
        if (path.endsWith('/usage_limits/workspace')) value = { id: workspaceId };
        else if (init.method === 'PATCH') {
          const body = JSON.parse(init.body); patches.push(body);
          const input = body.override_monthly_usage_limit;
          if (input === null) settings = structuredClone(original);
          else {
            const limit = structuredClone(input); delete limit.temporary; limit.limit_expires_at = END;
            settings = { override: [limit], effective: effective(limit, { kind: 'individual_override' }), inherited: group };
          }
          value = resource();
        } else if (path.endsWith('/monthly-usage')) value = { id: userId, account_user_id: `${userId}__${workspaceId}`,
          current_month_usage: 25, current_month_usage_unit: unit, effective_monthly_usage_limit: settings.effective?.limit ?? null };
        else { assert.ok(path.endsWith(`/users/${userId}`)); value = resource(); }
        return { ok: true, status: 200, headers: new Headers(), json: async () => structuredClone(value) };
      } });
    const before = await api.readSnapshot(userId);
    await api.setCap(userId, { amount: '500', unit, periodEnd: END, expectedSettings: before.settings });
    const after = await api.readSnapshot(userId);
    assert.equal(matchesTarget(after, { amount: '500', unit, periodEnd: END }), true);
    assert.equal(inheritedSettingsEquivalent(before.settings, after.settings, unit), true);
    await api.restore(userId, { settings: before.settings, unit, periodEnd: END, expectedSettings: after.settings });
    const restored = await api.readSnapshot(userId);
    assert.deepEqual(restored.settings, original);
    assert.equal(settingsEquivalent(restored.settings, before.settings, unit), true);
    assert.deepEqual(patches.at(-1), { override_monthly_usage_limit: null });
    assert.equal(patches.length, 2);
  }
});

test('Lambda time budget stops reads and prevents PATCH without a readback reserve', async () => {
  const noRead = harness({ options: { remainingTimeMs: () => 5000 } });
  await rejectsCode(noRead.api.readSnapshot(userId), 'API_TIME_BUDGET_EXHAUSTED');
  assert.equal(noRead.requests.length, 0);
  const noWrite = harness({ allowWrites: true, options: { remainingTimeMs: () => 49000 } });
  await rejectsCode(noWrite.api.setCap(userId, { amount: '50', unit: 'credit', periodEnd: END }), 'API_TIME_BUDGET_EXHAUSTED');
  assert.equal(noWrite.requests.filter(request => request.method === 'GET').length, 4);
  assert.equal(noWrite.patches, 0);
});

test('unknown cap fields and inconsistent source are rejected', async () => {
  const h = harness({ original: user({ override: [{ ...rule(), future_setting: true }] }) });
  await rejectsCode(h.api.readSnapshot(userId), 'UNKNOWN_CAP_FIELD');
  await rejectsCode(harness({ original: user({ override: [rule()], source: { kind: 'workspace_default' } }) })
    .api.readSnapshot(userId), 'OVERRIDE_SOURCE_MISMATCH');
});

test('role-based source is retained and compared', async () => {
  const h = harness({ original: user({ source: { kind: 'role_based_personal_budget', role_id: 'role-example' } }) });
  const snapshot = await h.api.readSnapshot(userId);
  assert.equal(snapshot.cap.source, 'role_based_personal_budget');
  const different = structuredClone(snapshot.settings);
  different.effective.source.role_id = 'role-other';
  assert.equal(settingsEquivalent(snapshot.settings, different, 'credit'), false);
});

test('settings comparison tolerates decimal formatting and null/empty inheritance', async () => {
  const snapshot = await harness().api.readSnapshot(userId);
  const equivalent = structuredClone(snapshot.settings);
  equivalent.override = [];
  equivalent.effective.limit.limit_amount.amount = '100.00';
  assert.equal(settingsEquivalent(snapshot.settings, equivalent, 'credit'), true);
});

test('snapshot detects cap changes and same-amount source changes during reads', async () => {
  const capChanged = harness({ intercept: ({ url, response }) => {
    if (url.pathname.endsWith('/monthly-usage')) return response({
      id: userId, account_user_id: `${userId}__${workspaceId}`, current_month_usage: 25,
      current_month_usage_unit: 'credit', effective_monthly_usage_limit: rule('101'),
    });
  } });
  await rejectsCode(capChanged.api.readSnapshot(userId), 'CAP_CHANGED_BETWEEN_READS');
  let userReads = 0;
  const sourceChanged = harness({ intercept: ({ url, response }) => {
    if (url.pathname.endsWith(`/users/${userId}`) && ++userReads === 2) {
      return response(user({ source: { kind: 'group_default', group_id: 'group-new' } }));
    }
  } });
  await rejectsCode(sourceChanged.api.readSnapshot(userId), 'SETTINGS_CHANGED_BETWEEN_READS');
});

test('writes are off by default and targets are fixed absolute temporary amounts', async () => {
  await rejectsCode(harness().api.setCap(userId, { amount: '50', unit: 'credit', periodEnd: END }), 'WRITES_DISABLED');
  const h = harness({ allowWrites: true });
  // A separately approved initial lowering is allowed by the transport adapter.
  await h.api.setCap(userId, { amount: '50', unit: 'credit', periodEnd: END });
  const patch = h.requests.find(request => request.method === 'PATCH');
  assert.deepEqual(JSON.parse(patch.body), { override_monthly_usage_limit: {
    type: 'limited', limit_amount: { amount: '50', unit: 'credit' }, temporary: true,
  } });
  assert.equal(patch.headers['Idempotency-Key'], undefined);
  assert.equal(matchesTarget(await h.api.readSnapshot(userId), { amount: '50', unit: 'credit', periodEnd: END }), true);
});

test('write bounds, unit transitions, and period expiration prevent PATCH', async () => {
  for (const target of [
    { amount: '1.1', unit: 'credit', periodEnd: END },
    { amount: '2147483648', unit: 'credit', periodEnd: END },
    { amount: '1.001', unit: 'usd', periodEnd: END },
    { amount: '1', unit: 'usd', periodEnd: END },
    { amount: '1', unit: 'credit', periodEnd: NOW },
  ]) {
    const h = harness({ allowWrites: true });
    await assert.rejects(h.api.setCap(userId, target));
    assert.equal(h.patches, 0);
  }
});

test('fresh adapter read detects edit after engine authorization', async () => {
  const expectedSettings = (await harness().api.readSnapshot(userId)).settings;
  const h = harness({ allowWrites: true, original: user({ override: [rule('101')] }) });
  await rejectsCode(h.api.setCap(userId, { amount: '110', unit: 'credit', periodEnd: END, expectedSettings }),
    'SETTINGS_CHANGED_BEFORE_WRITE');
  assert.equal(h.patches, 0);
});

test('initial reductions stop when usage changes between approval and the last read', async () => {
  const h = harness({ allowWrites: true, usage: 26 });
  await rejectsCode(h.api.setCap(userId, { amount: '50', unit: 'credit', periodEnd: END, expectedUsage: '25' }),
    'USAGE_CHANGED_BEFORE_WRITE');
  assert.equal(h.patches, 0);
});

test('no write starts in the last thirty seconds of an approved period', async () => {
  const h = harness({ allowWrites: true, options: { clock: () => '2030-06-30T23:59:31Z' } });
  await rejectsCode(h.api.setCap(userId, { amount: '50', unit: 'credit', periodEnd: END }), 'WRITE_PERIOD_EXPIRED');
  assert.equal(h.patches, 0);
});

test('review expiry during internal reads prevents set and restore mutations', async () => {
  const settings = (await harness().api.readSnapshot(userId)).settings;
  for (const command of ['setCap', 'restore']) {
    let clock = NOW;
    const h = harness({ allowWrites: true, options: { clock: () => clock }, intercept: ({ requests }) => {
      if (requests.length === 4) clock = '2030-06-15T12:01:00.000Z';
    } });
    const target = { amount: '50', unit: 'credit', periodEnd: END, settings,
      notAfter: '2030-06-15T12:01:00.000Z' };
    await rejectsCode(h.api[command](userId, target), 'OPERATION_REVIEW_EXPIRED');
    assert.equal(h.requests.filter(request => request.method === 'GET').length, 4);
    assert.equal(h.patches, 0);
  }
});

test('expired or invalid operation review deadlines stop before any API request', async () => {
  for (const notAfter of [NOW, 'invalid', '2030-06-15T12:01:00']) {
    const h = harness({ allowWrites: true });
    await rejectsCode(h.api.setCap(userId, { amount: '50', unit: 'credit', periodEnd: END, notAfter }),
      'OPERATION_REVIEW_EXPIRED');
    assert.equal(h.requests.length, 0);
  }
});

test('target matching requires an individual temporary override and exact expiry', async () => {
  const h = harness({ original: user({ override: [rule('50')] }) });
  const snapshot = await h.api.readSnapshot(userId);
  assert.equal(matchesTarget(snapshot, { amount: '50', unit: 'credit', periodEnd: END }), false);
  const temporary = await harness({ original: user({ override: [rule('50', 'credit', END)] }) }).api.readSnapshot(userId);
  assert.equal(matchesTarget(temporary, { amount: '50', unit: 'credit', periodEnd: '2030-07-02T00:00:00Z' }), false);
});

test('restore clears original inheritance without creating a persistent override', async () => {
  const h = harness({ allowWrites: true });
  const original = await h.api.readSnapshot(userId);
  await h.api.setCap(userId, { amount: '50', unit: 'credit', periodEnd: END });
  await h.api.restore(userId, { settings: original.settings, unit: 'credit', periodEnd: END });
  assert.deepEqual(JSON.parse(h.requests.filter(request => request.method === 'PATCH').at(-1).body),
    { override_monthly_usage_limit: null });
  assert.equal(settingsEquivalent(original.settings, (await h.api.readSnapshot(userId)).settings, 'credit'), true);
});

test('restore retains persistent tagged, legacy, and unlimited overrides', async () => {
  for (const originalRule of [rule('75'), { type: 'limited', limit: 75 }, { type: 'unlimited', limit: null }]) {
    const h = harness({ allowWrites: true, original: user({ override: [originalRule] }) });
    const original = await h.api.readSnapshot(userId);
    await h.api.setCap(userId, { amount: '50', unit: 'credit', periodEnd: END });
    await h.api.restore(userId, { settings: original.settings, unit: 'credit', periodEnd: END });
    const body = JSON.parse(h.requests.filter(request => request.method === 'PATCH').at(-1).body);
    assert.equal(body.override_monthly_usage_limit.temporary, undefined);
    assert.equal(settingsEquivalent(original.settings, (await h.api.readSnapshot(userId)).settings, 'credit'), true);
  }
});

test('temporary restore requires the exact saved current expiry', async () => {
  const h = harness({ allowWrites: true, original: user({ override: [rule('75', 'credit', END)] }) });
  const original = await h.api.readSnapshot(userId);
  await h.api.setCap(userId, { amount: '50', unit: 'credit', periodEnd: END });
  await h.api.restore(userId, { settings: original.settings, unit: 'credit', periodEnd: END });
  assert.equal(settingsEquivalent(original.settings, (await h.api.readSnapshot(userId)).settings, 'credit'), true);
  await rejectsCode(h.api.restore(userId, { settings: original.settings, unit: 'credit',
    periodEnd: '2030-07-02T00:00:00Z' }), 'TEMPORARY_EXPIRY_NOT_RESTORABLE');
});

test('transport timeout or unreadable PATCH response remains an unknown outcome without retry', async () => {
  for (const transport of [true, false]) {
    const h = harness({ allowWrites: true, intercept: ({ init }) => {
      if (init.method === 'PATCH') {
        if (transport) throw new Error('sensitive transport details');
        return { ok: true, json: async () => { throw new Error('sensitive body'); } };
      }
    } });
    await assert.rejects(h.api.setCap(userId, { amount: '110', unit: 'credit', periodEnd: END }), error => {
      assert.equal(error.code, 'WRITE_OUTCOME_UNKNOWN');
      assert.equal(error.outcomeUnknown, true);
      assert.equal(error.message.includes('sensitive'), false);
      return true;
    });
    assert.equal(h.requests.filter(request => request.method === 'PATCH').length, 1);
  }
});

test('rate limits expose Retry-After without exposing API response bodies', async () => {
  const h = harness({ intercept: () => ({ ok: false, status: 429,
    headers: new Headers({ 'Retry-After': '60' }), json: async () => { throw new Error('must not read'); } }) });
  await assert.rejects(h.api.readSnapshot(userId), error => {
    assert.equal(error.status, 429);
    assert.equal(error.retryAfterMs, 60000);
    assert.equal(error.retryable, true);
    return true;
  });
  await rejectsCode(h.api.waitBeforeRetry(1, { retryAfterMs: 60000 }), 'RETRY_DELAY_REQUIRES_LATER_RUN');
});

test('HTTP-date Retry-After is honored and a write-side server error remains uncertain', async () => {
  const rateLimit = harness({ intercept: () => ({ ok: false, status: 429,
    headers: new Headers({ 'Retry-After': 'Sat, 15 Jun 2030 12:00:03 GMT' }) }) });
  await assert.rejects(rateLimit.api.readSnapshot(userId), error => error.retryAfterMs === 3000);
  const serverError = harness({ allowWrites: true, intercept: ({ init }) => init.method === 'PATCH' ?
    { ok: false, status: 500, headers: new Headers() } : null });
  await assert.rejects(serverError.api.setCap(userId, { amount: '110', unit: 'credit', periodEnd: END }), error =>
    error.status === 500 && error.outcomeUnknown === true);
  assert.equal(serverError.requests.filter(request => request.method === 'PATCH').length, 1);
});

test('409 conflicts are surfaced and 401/403 are non-retryable', async () => {
  for (const status of [401, 403, 409]) {
    const h = harness({ intercept: () => ({ ok: false, status, headers: new Headers() }) });
    await assert.rejects(h.api.readSnapshot(userId), error => {
      assert.equal(error.status, status);
      assert.equal(error.retryable, false);
      assert.equal(error.conflict, status === 409);
      return true;
    });
  }
});

test('all-members capture paginates active member IDs and discards personal fields', async () => {
  const h = harness({ intercept: ({ url, response }) => {
    if (url.pathname.endsWith('/users')) {
      const second = url.searchParams.has('after');
      if (second) assert.equal(url.searchParams.get('after'), 'user-alpha');
      const id = second ? 'user-beta' : 'user-alpha';
      return response({ object: 'list', data: [{ object: 'workspace.user', id, email: 'synthetic@example.com' }],
        first_id: id, last_id: id, has_more: !second });
    }
  }, options: { userIds: [] } });
  assert.deepEqual(await h.api.listMembers(), ['user-alpha', 'user-beta']);
  await rejectsCode(h.api.readSnapshot('user-alpha'), 'IDENTITY_NOT_ALLOWLISTED');
});

test('member duplicate pages, missing cursors, and bounded pagination fail closed', async () => {
  for (const mode of ['duplicate', 'cursor', 'bound']) {
    const h = harness({ options: { maxPages: mode === 'bound' ? 1 : 1000 },
      intercept: ({ url, response }) => url.pathname.endsWith('/users') ? response({
        object: 'list', data: [directoryUser('user-alpha')], first_id: 'user-alpha',
        last_id: mode === 'cursor' ? null : 'user-alpha', has_more: true,
      }) : null });
    await rejectsCode(h.api.listMembers(), { duplicate: 'MEMBER_PAGE_INCONSISTENT', cursor: 'MEMBER_PAGE_INVALID',
      bound: 'MEMBER_PAGE_BOUND_EXCEEDED' }[mode]);
  }
});

test('member directory paginates IDs and nullable emails and discards other personal fields', async () => {
  const h = harness({ intercept: ({ url, response }) => {
    if (url.pathname.endsWith('/users')) {
      assert.equal(url.searchParams.get('limit'), '1000');
      const second = url.searchParams.has('after');
      if (second) assert.equal(url.searchParams.get('after'), 'user-alpha');
      return response(memberPage([second ? directoryUser('user-beta', 'Beta@Example.com') :
        directoryUser('user-alpha', null)], !second));
    }
  }, options: { userIds: [] } });
  assert.deepEqual(await h.api.listMemberDirectory(), [
    { userId: 'user-alpha', email: null }, { userId: 'user-beta', email: 'Beta@Example.com' },
  ]);
  assert.equal(h.patches, 0);
  await rejectsCode(h.api.readSnapshot('user-alpha'), 'IDENTITY_NOT_ALLOWLISTED');
});

test('member directory bounds, required email fields and page identities fail closed', async () => {
  for (const { page, options, code } of [
    { page: memberPage([directoryUser('user-alpha'), directoryUser('user-beta')]),
      options: { maxRows: 1 }, code: 'MEMBER_ROW_BOUND_EXCEEDED' },
    { page: memberPage([directoryUser('user-alpha')], true), options: { maxPages: 1 }, code: 'MEMBER_PAGE_BOUND_EXCEEDED' },
    { page: memberPage([{ object: 'workspace.user', id: userId }]), code: 'MEMBER_PAGE_INCONSISTENT' },
    { page: { ...memberPage([directoryUser()]), first_id: 'other' }, code: 'MEMBER_PAGE_INVALID' },
    { page: null, code: 'MEMBER_PAGE_INVALID' },
  ]) {
    const h = harness({ options, intercept: ({ url, response }) =>
      url.pathname.endsWith('/users') ? response(page) : null });
    await rejectsCode(h.api.listMemberDirectory(), code);
    assert.equal(h.patches, 0);
  }
});

test('email lookup trims, lowercases and URL-encodes exact addresses without a cursor', async () => {
  const h = harness({ intercept: ({ url, response }) => {
    if (url.pathname.endsWith('/users')) {
      assert.equal(url.searchParams.get('email'), 'alex+qa@example.com');
      assert.equal(url.searchParams.has('after'), false);
      assert.equal(url.searchParams.get('limit'), '1');
      assert.ok(url.search.includes('%2B'));
      return response(memberPage([directoryUser(userId, 'Alex+QA@example.com')]));
    }
  }, options: { userIds: [] } });
  assert.deepEqual(await h.api.resolveEmail('  ALEX+QA@Example.COM  '),
    { userId, email: 'Alex+QA@example.com' });
  assert.equal(h.requests.length, 2);
  assert.equal(h.patches, 0);
  await rejectsCode(h.api.readSnapshot(userId), 'IDENTITY_NOT_ALLOWLISTED');
});

test('invalid email selectors stop before requests', async () => {
  for (const email of [null, '', '   ', 'not-an-email', 'two@@example.com', 'two words@example.com']) {
    const h = harness();
    await rejectsCode(h.api.resolveEmail(email), 'EMAIL_INVALID');
    assert.equal(h.requests.length, 0);
  }
});

test('email lookup rejects missing, ambiguous and conflicting results', async () => {
  for (const { page, code } of [
    { page: memberPage(), code: 'EMAIL_MEMBER_NOT_FOUND' },
    { page: memberPage([directoryUser(), directoryUser('user-other')]), code: 'EMAIL_MEMBER_AMBIGUOUS' },
    { page: memberPage([directoryUser(userId, 'other@example.com')]), code: 'EMAIL_MEMBER_MISMATCH' },
    { page: memberPage([directoryUser(userId, null)]), code: 'EMAIL_MEMBER_MISMATCH' },
    { page: memberPage([directoryUser()], true), code: 'EMAIL_LOOKUP_INVALID' },
    { page: { ...memberPage([directoryUser()]), last_id: 'user-other' }, code: 'EMAIL_LOOKUP_INVALID' },
    { page: null, code: 'EMAIL_LOOKUP_INVALID' },
  ]) {
    const h = harness({ intercept: ({ url, response }) =>
      url.pathname.endsWith('/users') ? response(page) : null });
    await rejectsCode(h.api.resolveEmail('synthetic@example.com'), code);
    assert.equal(h.patches, 0);
  }
});

test('active-member assertion requires an explicit allowlist before any request', async () => {
  const h = harness();
  await rejectsCode(h.api.assertMemberActive('user-other'), 'IDENTITY_NOT_ALLOWLISTED');
  assert.equal(h.requests.length, 0);
});

test('point member GET is confirmed by the active collection email lookup', async () => {
  const h = harness({ intercept: ({ url, response }) => {
    if (url.pathname === `/v1/manage/workspaces/${workspaceId}/users/${userId}`) return response(directoryUser());
    if (url.pathname.endsWith('/users')) {
      assert.equal(url.searchParams.get('email'), 'synthetic@example.com');
      assert.equal(url.searchParams.has('after'), false);
      return response(memberPage([directoryUser()]));
    }
  } });
  assert.deepEqual(await h.api.assertMemberActive(userId), { userId, email: 'synthetic@example.com' });
  assert.equal(h.requests.length, 3);
  assert.equal(h.patches, 0);
});

test('active-member assertion rejects inactive, reassigned and mismatched email identities', async () => {
  for (const page of [memberPage(), memberPage([directoryUser('user-other')])]) {
    const h = harness({ intercept: ({ url, response }) => {
      if (url.pathname === `/v1/manage/workspaces/${workspaceId}/users/${userId}`) return response(directoryUser());
      if (url.pathname.endsWith('/users')) return response(page);
    } });
    await rejectsCode(h.api.assertMemberActive(userId), 'MEMBER_NOT_ACTIVE');
    assert.equal(h.patches, 0);
  }
  const h = harness({ intercept: ({ url, response }) =>
    url.pathname === `/v1/manage/workspaces/${workspaceId}/users/${userId}` ? response(directoryUser('user-other')) : null });
  await rejectsCode(h.api.assertMemberActive(userId), 'USER_READBACK_MISMATCH');
});

test('null-email active-member assertion falls back to the bounded active directory', async () => {
  for (const present of [true, false]) {
    const h = harness({ intercept: ({ url, response }) => {
      if (url.pathname === `/v1/manage/workspaces/${workspaceId}/users/${userId}`) return response(directoryUser(userId, null));
      if (url.pathname.endsWith('/users')) {
        assert.equal(url.searchParams.has('email'), false);
        return response(memberPage(present ? [directoryUser(userId, null)] : []));
      }
    } });
    if (present) assert.deepEqual(await h.api.assertMemberActive(userId), { userId, email: null });
    else await rejectsCode(h.api.assertMemberActive(userId), 'MEMBER_NOT_ACTIVE');
    assert.equal(h.requests.length, 4);
    assert.equal(h.patches, 0);
  }
});

test('active-member assertion preserves point-GET permission and missing-member errors', async () => {
  for (const status of [403, 404]) {
    const h = harness({ intercept: ({ url }) =>
      url.pathname === `/v1/manage/workspaces/${workspaceId}/users/${userId}` ?
        { ok: false, status, headers: new Headers() } : null });
    await rejectsCode(h.api.assertMemberActive(userId), `ADMIN_HTTP_${status}`);
    assert.equal(h.requests.length, 2);
  }
});

test('group members use opaque cursors, skip deactivated users and return sorted auth-user IDs', async () => {
  const h = harness({ options: { userIds: [] }, intercept: ({ url, response }) => {
    if (url.pathname.endsWith(`/groups/${groupId}`)) return response(groupResource());
    if (url.pathname.endsWith(`/groups/${groupId}/users`)) {
      assert.equal(url.searchParams.get('limit'), '100');
      assert.equal(url.searchParams.get('order'), 'asc');
      assert.equal(url.searchParams.has('after'), false);
      const second = url.searchParams.has('cursor');
      if (second) assert.equal(url.searchParams.get('cursor'), 'opaque+/=cursor');
      return response(second ? groupPage([groupUser('user-alpha')]) :
        groupPage([groupUser('user-beta'), groupUser('user-disabled', 'deactivated')], 'opaque+/=cursor', true));
    }
  } });
  assert.deepEqual(await h.api.listGroupMembers(groupId), ['user-alpha', 'user-beta']);
  assert.equal(h.requests.length, 4);
  assert.equal(h.patches, 0);
  await rejectsCode(h.api.readSnapshot('user-alpha'), 'IDENTITY_NOT_ALLOWLISTED');
});

test('directory group, page and member object tags may be omitted when the schema defaults them', async () => {
  const group = groupResource(); delete group.object;
  const member = groupUser(); delete member.object;
  const page = groupPage([member]); delete page.object;
  const h = harness({ intercept: ({ url, response }) => {
    if (url.pathname.endsWith(`/groups/${groupId}`)) return response(group);
    if (url.pathname.endsWith(`/groups/${groupId}/users`)) return response(page);
  } });
  assert.deepEqual(await h.api.listGroupMembers(groupId), [userId]);
});

test('group ID and returned workspace/group identities are checked before listing users', async () => {
  const invalid = harness();
  await rejectsCode(invalid.api.listGroupMembers('../other'), 'GROUP_ID_INVALID');
  assert.equal(invalid.requests.length, 0);
  for (const extra of [{ id: 'group-other' }, { workspace_id: 'workspace-other' }, { object: 'wrong' }]) {
    const h = harness({ intercept: ({ url, response }) =>
      url.pathname.endsWith(`/groups/${groupId}`) ? response({ ...groupResource(), ...extra }) : null });
    await rejectsCode(h.api.listGroupMembers(groupId), 'GROUP_READBACK_MISMATCH');
    assert.equal(h.requests.length, 2);
  }
});

test('group pages reject unknown status, duplicate identities, wrong tags and invalid cursors', async () => {
  for (const { pages, code } of [
    { pages: [groupPage([groupUser(userId, 'inactive')])], code: 'GROUP_MEMBER_STATUS_INVALID' },
    { pages: [groupPage([groupUser(), groupUser()])], code: 'GROUP_MEMBER_PAGE_INCONSISTENT' },
    { pages: [groupPage([{ ...groupUser(), object: 'workspace.user' }])], code: 'GROUP_MEMBER_PAGE_INCONSISTENT' },
    { pages: [groupPage([groupUser()], null, true)], code: 'GROUP_MEMBER_CURSOR_INVALID' },
    { pages: [groupPage([groupUser()], 'repeat', true), groupPage([groupUser('user-other')], 'repeat', true)],
      code: 'GROUP_MEMBER_CURSOR_INVALID' },
    { pages: [{ ...groupPage([groupUser()]), last_id: 'user-other' }], code: 'GROUP_MEMBER_PAGE_INVALID' },
    { pages: [null], code: 'GROUP_MEMBER_PAGE_INVALID' },
  ]) {
    let pageIndex = 0;
    const h = harness({ intercept: ({ url, response }) => {
      if (url.pathname.endsWith(`/groups/${groupId}`)) return response(groupResource());
      if (url.pathname.endsWith(`/groups/${groupId}/users`)) return response(pages[pageIndex++]);
    } });
    await rejectsCode(h.api.listGroupMembers(groupId), code);
    assert.equal(h.patches, 0);
  }
});

test('group pagination bounds count deactivated users and prevent unbounded scans', async () => {
  for (const { options, page, code } of [
    { options: { maxRows: 1 }, page: groupPage([groupUser(), groupUser('user-disabled', 'deactivated')]),
      code: 'GROUP_MEMBER_ROW_BOUND_EXCEEDED' },
    { options: { maxPages: 1 }, page: groupPage([groupUser()], 'next', true), code: 'GROUP_MEMBER_PAGE_BOUND_EXCEEDED' },
  ]) {
    const h = harness({ options, intercept: ({ url, response }) => {
      if (url.pathname.endsWith(`/groups/${groupId}`)) return response(groupResource());
      if (url.pathname.endsWith(`/groups/${groupId}/users`)) return response(page);
    } });
    await rejectsCode(h.api.listGroupMembers(groupId), code);
  }
});

test('group permission and missing-group errors remain explicit without partial results', async () => {
  for (const status of [403, 404]) {
    const h = harness({ intercept: ({ url }) => url.pathname.endsWith(`/groups/${groupId}`) ?
      { ok: false, status, headers: new Headers() } : null });
    await rejectsCode(h.api.listGroupMembers(groupId), `ADMIN_HTTP_${status}`);
    assert.equal(h.requests.length, 2);
  }
});

test('history fetches every page, filters target ID, preserves zero, and labels observations', async () => {
  const h = harness({ intercept: ({ url, response }) => {
    if (url.pathname.includes('/analytics/')) {
      assert.equal(url.searchParams.get('start_time'), String(Date.parse(query.start) / 1000));
      assert.equal(url.searchParams.get('end_time'), String(Date.parse(query.end) / 1000));
      assert.equal(url.searchParams.get('limit'), '30000');
      assert.equal(url.searchParams.has('group'), false);
      const second = url.searchParams.has('page');
      if (second) assert.equal(url.searchParams.get('page'), 'cursor-example');
      return response({ object: 'page', data: second ? [historyRow('2030-06-11', { credits: 0 })] :
        [historyRow('2030-06-10'), historyRow('2030-06-10', { id: 'user-other' })],
      has_more: !second, next_page: second ? null : 'cursor-example' });
    }
  } });
  const history = await h.api.readHistory(userId, query);
  assert.deepEqual(history.days, [{ date: '2030-06-10', amount: '4' }, { date: '2030-06-11', amount: '0' }]);
  assert.equal(history.semantics, 'observed');
  assert.equal(history.finalizedThrough, undefined);
});

test('native USD uses cost_usd, never estimated credit conversion', async () => {
  const h = harness({ intercept: ({ url, response }) => url.pathname.includes('/analytics/') ? response({
    object: 'page', data: [historyRow('2030-06-10', { credits: null, usd: 1.2345678 }),
      historyRow('2030-06-11', { credits: null, usd: 0 })], has_more: false, next_page: null,
  }) : null });
  const history = await h.api.readHistory(userId, { ...query, unit: 'usd' });
  assert.equal(history.days[0].amount, '1.234568');
  assert.equal(history.days[1].amount, '0');
});

test('missing, duplicate, null, wrong actor, mixed unit, and aggregate daily rows stop history', async () => {
  const variants = [
    { rows: [historyRow('2030-06-10')], code: 'HISTORY_DAY_UNAVAILABLE' },
    { rows: [historyRow('2030-06-10'), historyRow('2030-06-10')], code: 'HISTORY_DUPLICATE_DAY' },
    { rows: [historyRow('2030-06-10', { credits: null })], code: 'AMOUNT_UNAVAILABLE' },
    { rows: [historyRow('2030-06-10', { actorId: 'user-other' })], code: 'HISTORY_ACTOR_MISMATCH' },
    { rows: [historyRow('2030-06-10', { usd: 0 })], code: 'HISTORY_UNIT_TRANSITION' },
    { rows: [historyRow('2030-06-10', { id: null })], code: 'HISTORY_SCOPE_INVALID' },
    { rows: [historyRow('2030-06-09')], code: 'HISTORY_ROW_BOUNDARY_INVALID' },
  ];
  for (const { rows, code } of variants) {
    const h = harness({ intercept: ({ url, response }) => url.pathname.includes('/analytics/') ?
      response({ object: 'page', data: rows, has_more: false, next_page: null }) : null });
    await rejectsCode(h.api.readHistory(userId, query), code);
  }
});

test('history bounds require completed UTC days and pagination cannot loop indefinitely', async () => {
  const h = harness({ intercept: ({ url, response }) => url.pathname.includes('/analytics/') ?
    response({ object: 'page', data: [], has_more: true, next_page: 'same-cursor' }) : null });
  await rejectsCode(h.api.readHistory(userId, { ...query, start: '2030-06-10T01:00:00Z' }), 'HISTORY_WINDOW_INVALID');
  await rejectsCode(h.api.readHistory(userId, { ...query, end: '2030-06-16T00:00:00Z' }), 'HISTORY_WINDOW_INVALID');
  await rejectsCode(h.api.readHistory(userId, query), 'HISTORY_CURSOR_INVALID');
});

test('concurrent and sequential users share one paginated history index', async () => {
  const otherId = 'user-other';
  const firstPageStarted = Promise.withResolvers();
  const releaseFirstPage = Promise.withResolvers();
  let pages = 0;
  let currentTime = Date.parse(NOW);
  const h = harness({ options: { userIds: [userId, otherId], clock: () => new Date(currentTime).toISOString() },
    intercept: async ({ url, response }) => {
      if (!url.pathname.includes('/analytics/')) return;
      pages += 1;
      const second = url.searchParams.has('page');
      if (!second) {
        firstPageStarted.resolve();
        await releaseFirstPage.promise;
      }
      currentTime += 10000;
      const date = second ? '2030-06-11' : '2030-06-10';
      return response({ object: 'page', data: [historyRow(date, { credits: second ? 0 : 4 }),
        historyRow(date, { id: otherId, credits: null, usd: second ? 0 : 1.5 })],
      has_more: !second, next_page: second ? null : 'history-next' });
    } });
  const first = h.api.readHistory(userId, query);
  await firstPageStarted.promise;
  const other = h.api.readHistory(otherId, { ...query, unit: 'usd' });
  releaseFirstPage.resolve();
  const [credits, dollars] = await Promise.all([first, other]);
  assert.equal(pages, 2);
  assert.deepEqual(credits.days.map(day => day.amount), ['4', '0']);
  assert.deepEqual(dollars.days.map(day => day.amount), ['1.5', '0']);
  assert.equal(credits.observedAt, NOW);
  assert.equal(dollars.observedAt, NOW);
  credits.days[0].amount = '999';
  const reused = await h.api.readHistory(userId, query);
  assert.equal(reused.days[0].amount, '4');
  assert.equal(reused.observedAt, NOW);
  assert.equal(pages, 2);
});

test('history cache expires after sixty seconds and refetches after clock rollback', async () => {
  let currentTime = Date.parse(NOW);
  let pages = 0;
  const h = harness({ options: { clock: () => new Date(currentTime).toISOString() },
    intercept: ({ url, response }) => {
      if (!url.pathname.includes('/analytics/')) return;
      pages += 1;
      return response({ object: 'page', data: ['2030-06-10', '2030-06-11'].map(date =>
        historyRow(date, { credits: pages })), has_more: false, next_page: null });
    } });
  const original = await h.api.readHistory(userId, query);
  currentTime += 60000;
  assert.deepEqual(await h.api.readHistory(userId, query), original);
  assert.equal(pages, 1);
  currentTime += 1;
  const refreshed = await h.api.readHistory(userId, query);
  assert.equal(pages, 2);
  assert.equal(refreshed.observedAt, new Date(currentTime).toISOString());
  assert.equal(refreshed.days[0].amount, '2');
  currentTime -= 1;
  const afterRollback = await h.api.readHistory(userId, query);
  assert.equal(pages, 3);
  assert.equal(afterRollback.observedAt, new Date(currentTime).toISOString());
  assert.equal(afterRollback.days[0].amount, '3');
});

test('failed shared history pagination is discarded and can be retried', async () => {
  let failSecondPage = true;
  let pages = 0;
  const h = harness({ intercept: ({ url, response }) => {
    if (!url.pathname.includes('/analytics/')) return;
    pages += 1;
    const second = url.searchParams.has('page');
    if (second && failSecondPage) return { ok: false, status: 503, headers: new Headers() };
    return response({ object: 'page', data: [historyRow(second ? '2030-06-11' : '2030-06-10')],
      has_more: !second, next_page: second ? null : 'next' });
  } });
  await Promise.all([rejectsCode(h.api.readHistory(userId, query), 'ADMIN_HTTP_503'),
    rejectsCode(h.api.readHistory(userId, query), 'ADMIN_HTTP_503')]);
  assert.equal(pages, 2);
  failSecondPage = false;
  assert.deepEqual((await h.api.readHistory(userId, query)).days.map(day => day.amount), ['4', '4']);
  assert.equal(pages, 4);
});

test('concurrent history ranges never mix and only the current range remains cached', async () => {
  const laterQuery = { ...query, start: '2030-06-12T00:00:00Z', end: '2030-06-14T00:00:00Z' };
  const earlierStarted = Promise.withResolvers();
  const releaseEarlier = Promise.withResolvers();
  const pages = { earlier: 0, later: 0 };
  const h = harness({ intercept: async ({ url, response }) => {
    if (!url.pathname.includes('/analytics/')) return;
    const earlier = url.searchParams.get('start_time') === String(Date.parse(query.start) / 1000);
    pages[earlier ? 'earlier' : 'later'] += 1;
    if (earlier && pages.earlier === 1) {
      earlierStarted.resolve();
      await releaseEarlier.promise;
    }
    const dates = earlier ? ['2030-06-10', '2030-06-11'] : ['2030-06-12', '2030-06-13'];
    return response({ object: 'page', data: dates.map(date => historyRow(date, { credits: earlier ? 1 : 9 })),
      has_more: false, next_page: null });
  } });
  const earlierRead = h.api.readHistory(userId, query);
  await earlierStarted.promise;
  const later = await h.api.readHistory(userId, laterQuery);
  releaseEarlier.resolve();
  const earlier = await earlierRead;
  assert.deepEqual(earlier.days, [{ date: '2030-06-10', amount: '1' }, { date: '2030-06-11', amount: '1' }]);
  assert.deepEqual(later.days, [{ date: '2030-06-12', amount: '9' }, { date: '2030-06-13', amount: '9' }]);
  assert.deepEqual(await h.api.readHistory(userId, laterQuery), later);
  assert.deepEqual(pages, { earlier: 1, later: 1 });
  assert.deepEqual(await h.api.readHistory(userId, query), earlier);
  assert.deepEqual(pages, { earlier: 2, later: 1 });
  await h.api.readHistory(userId, laterQuery);
  assert.deepEqual(pages, { earlier: 2, later: 2 });
});

test('slow pagination and a clock rollback during fetch cannot make history fresh', async () => {
  for (const delay of [60001, -1]) {
    let currentTime = Date.parse(NOW);
    let changeClock = true;
    let pages = 0;
    const h = harness({ options: { clock: () => new Date(currentTime).toISOString() },
      intercept: ({ url, response }) => {
        if (!url.pathname.includes('/analytics/')) return;
        pages += 1;
        const second = url.searchParams.has('page');
        if (second && changeClock) currentTime += delay;
        return response({ object: 'page', data: [historyRow(second ? '2030-06-11' : '2030-06-10')],
          has_more: !second, next_page: second ? null : 'next' });
      } });
    await rejectsCode(h.api.readHistory(userId, query), 'HISTORY_STALE');
    changeClock = false;
    const history = await h.api.readHistory(userId, query);
    assert.equal(history.observedAt, new Date(currentTime).toISOString());
    assert.equal(pages, 4);
  }
});

test('cached history still enforces allowlist, units, windows and each target user row', async () => {
  const otherId = 'user-other';
  const h = harness({ options: { userIds: [userId, otherId] }, intercept: ({ url, response }) =>
    url.pathname.includes('/analytics/') ? response({ object: 'page',
      data: [historyRow('2030-06-10'), historyRow('2030-06-11'),
        historyRow('2030-06-10', { id: otherId, actorId: userId })],
      has_more: false, next_page: null }) : null });
  await h.api.readHistory(userId, query);
  const requests = h.requests.length;
  await rejectsCode(h.api.readHistory('user-unlisted', query), 'IDENTITY_NOT_ALLOWLISTED');
  await rejectsCode(h.api.readHistory(userId, { ...query, unit: 'other' }), 'UNIT_UNAVAILABLE');
  await rejectsCode(h.api.readHistory(userId, { ...query, end: query.start }), 'HISTORY_WINDOW_INVALID');
  await rejectsCode(h.api.readHistory(otherId, query), 'HISTORY_ACTOR_MISMATCH');
  await rejectsCode(h.api.readHistory(userId, { ...query, unit: 'usd' }), 'HISTORY_UNIT_TRANSITION');
  assert.equal(h.requests.length, requests);
});

test('shared history preserves row and page bounds and retries malformed pages', async () => {
  for (const { options, code } of [
    { options: { maxRows: 1 }, code: 'HISTORY_ROW_BOUND_EXCEEDED' },
    { options: { maxPages: 1 }, code: 'HISTORY_PAGE_BOUND_EXCEEDED' },
  ]) {
    const h = harness({ options, intercept: ({ url, response }) => url.pathname.includes('/analytics/') ?
      response({ object: 'page', data: [historyRow('2030-06-10'), historyRow('2030-06-11')],
        has_more: true, next_page: 'next' }) : null });
    await rejectsCode(h.api.readHistory(userId, query), code);
  }
  let malformed = true;
  let pages = 0;
  const h = harness({ intercept: ({ url, response }) => {
    if (!url.pathname.includes('/analytics/')) return;
    pages += 1;
    return response(malformed ? null : { object: 'page', data: [historyRow('2030-06-10'), historyRow('2030-06-11')],
      has_more: false, next_page: null });
  } });
  await rejectsCode(h.api.readHistory(userId, query), 'HISTORY_PAGE_INVALID');
  malformed = false;
  await h.api.readHistory(userId, query);
  assert.equal(pages, 2);
});
