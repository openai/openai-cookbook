import test from 'node:test';
import assert from 'node:assert/strict';
import { createAdminApi, matchesTarget, settingsEquivalent } from '../src/admin-api.mjs';

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

test('an unset effective rule is unsupported and is never inferred to be unlimited', async () => {
  const original = user();
  original.effective_monthly_usage_limit = null;
  const h = harness({ original });
  await rejectsCode(h.api.readSnapshot(userId), 'CAP_SOURCE_UNAVAILABLE');
  assert.equal(h.patches, 0);
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
        object: 'list', data: [{ object: 'workspace.user', id: 'user-alpha' }],
        last_id: mode === 'cursor' ? null : 'user-alpha', has_more: true,
      }) : null });
    await rejectsCode(h.api.listMembers(), { duplicate: 'MEMBER_PAGE_INCONSISTENT', cursor: 'MEMBER_CURSOR_INVALID',
      bound: 'MEMBER_PAGE_BOUND_EXCEEDED' }[mode]);
  }
});

test('history fetches every page, filters target ID, preserves zero, and labels observations', async () => {
  const h = harness({ intercept: ({ url, response }) => {
    if (url.pathname.includes('/analytics/')) {
      assert.equal(url.searchParams.get('start_time'), String(Date.parse(query.start) / 1000));
      assert.equal(url.searchParams.get('end_time'), String(Date.parse(query.end) / 1000));
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
