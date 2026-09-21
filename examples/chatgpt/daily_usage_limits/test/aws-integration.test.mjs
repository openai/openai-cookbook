import test from 'node:test';
import assert from 'node:assert/strict';
import { createHandler } from '../aws/lambda.mjs';
import { encodeControl } from '../aws/control.mjs';
import { execute, createExecutionContext } from '../src/controller.mjs';
import { validateCurrentCohort } from '../src/selection.mjs';
import { captureEnrollment, approveEnrollment } from '../src/enrollment.mjs';
import { exampleConfig, createSyntheticApi, MemoryStore } from '../src/synthetic.mjs';
import { createAdminApi } from '../src/admin-api.mjs';

test('Lambda connection check uses the real adapter for exactly three fixed-base read requests before enrollment', async () => {
  for (const unit of ['credit', 'usd']) {
    const requests = [], receipts = [];
    const workspaceId = 'workspace-synthetic', userId = 'member-synthetic';
    const handle = createHandler({ deploymentId: 'synthetic-demo', controlSha256: '0'.repeat(64),
      pilotExpiresAt: '2030-05-01T00:00:00Z', clock: () => new Date('2030-04-02T00:00:00Z'),
      store: { putReceipt: async value => receipts.push(value) }, putMetric: async () => {}, log() {},
      secretProvider: async () => 'synthetic-key-not-a-credential',
      apiFactory: options => createAdminApi({ ...options, fetchImpl: async (url, init) => {
        requests.push({ url, method: init.method });
        assert.equal(init.redirect, 'error'); assert.equal(init.method, 'GET'); assert.equal(init.body, undefined);
        assert.equal(init.headers.Authorization, 'Bearer synthetic-key-not-a-credential');
        let body;
        if (url.endsWith('/usage_limits/workspace')) body = { id: workspaceId };
        else if (url.endsWith('/users?limit=1')) body = { object: 'list', has_more: true,
          first_id: userId, last_id: userId, data: [{ object: 'workspace.user', id: userId, email: 'private@example.invalid' }] };
        else if (url.endsWith(`/usage_limits/users/${userId}/monthly-usage`)) body = {
          id: userId, account_user_id: `${userId}__${workspaceId}`, current_month_usage_unit: unit,
          current_month_usage: 123.456, effective_monthly_usage_limit: null };
        else throw new Error('Unexpected endpoint');
        return { ok: true, status: 200, headers: new Headers(), json: async () => body };
      } }),
    });
    const result = await handle({ version: 1, action: 'check_connection', workspaceId, scheduledAt: '2030-04-02T00:00:00Z' },
      { getRemainingTimeInMillis: () => 120_000 });
    assert.equal(result.ok, true); assert.equal(result.unit, unit); assert.equal(result.capWrites, 0);
    assert.equal(requests.length, 3);
    assert.ok(requests.every(request => request.url.startsWith(`https://api.chatgpt.com/v1/manage/workspaces/${workspaceId}/`)));
    assert.doesNotMatch(JSON.stringify([result, receipts]), /member-synthetic|private@example|123\.456|synthetic-key/);
  }
});

async function fixture({ count = 3, pilotExpiresAt = '2030-04-30T00:00:00Z', configure = () => {} } = {}) {
  let now = '2030-04-02T00:00:00Z';
  const config = { ...exampleConfig({ now, cohort: 'all' }), liveWrites: true };
  Object.assign(config.policy, { startCap: '20', increment: '20', ceiling: '200' });
  const api = createSyntheticApi({ config, clock: () => now, initialCap: '10' });
  const original = structuredClone(api.users['synthetic-user-a']);
  for (const key of Object.keys(api.users)) delete api.users[key];
  for (let index = 0; index < count; index++) {
    const userId = `synthetic-user-${index}`;
    api.users[userId] = { ...structuredClone(original), userId, email: `${userId}@example.invalid` };
  }
  configure(config, api);
  const captured = await captureEnrollment({ config, api, now });
  const enrollment = approveEnrollment(captured.enrollment, captured.hash, now);
  const prepared = encodeControl(config, enrollment);
  const parts = new Map(prepared.parts.map(part => [part.hash, part.document]));
  const store = new MemoryStore(); const runs = new Map(), finished = new Map(), retry = new Map();
  Object.assign(store, {
    getControl: async () => prepared.document, getControlPart: async key => parts.get(key),
    getRun: async key => runs.get(key),
    async createRun(run) { if (!runs.has(run.runId)) runs.set(run.runId, { ...run, cursor: 0, completed: 0, succeeded: 0, attention: 0 }); return runs.get(run.runId); },
    async setRunCursor(id, cursor) { runs.get(id).cursor = cursor; },
    getMemberResult: async (id, index) => finished.get(`${id}:${index}`),
    async completeMember(id, index, value) {
      const key = `${id}:${index}`; if (finished.has(key)) return false;
      finished.set(key, value); const run = runs.get(id); run.completed++; run[value.ok ? 'succeeded' : 'attention']++; return true;
    },
    getRetry: async (id, index) => retry.get(`${id}:${index}`),
    async putRetry(id, index, value) { retry.set(`${id}:${index}`, value); },
    async pauseRun(id, value) { runs.get(id).notBefore = value; },
    async cancelRun(id) { runs.get(id).cancelled = true; },
  });
  const pending = [], deferred = []; let messageId = 0;
  const options = { store, execute, createExecutionContext, validateCurrentCohort, apiFactory: () => api,
    secretProvider: async () => 'synthetic-not-a-real-secret', putMetric: async () => {},
    deploymentId: 'synthetic-demo', controlSha256: prepared.hash, applyEnabled: true,
    allowedWriteAction: 'apply', pilotExpiresAt, clock: () => new Date(now), log() {}, queueArn: 'synthetic-queue',
    queue: { async send(batch) { pending.push(...batch); },
      async defer(receipt, seconds) { deferred.push({ receipt, seconds }); } } };
  const handle = createHandler(options);
  const records = (messages, receiveCount = 1) => ({ Records: messages.map(body => ({ body: JSON.stringify(body),
    messageId: String(messageId++), receiptHandle: 'synthetic-receipt', eventSource: 'aws:sqs',
    eventSourceARN: 'synthetic-queue', attributes: { ApproximateReceiveCount: String(receiveCount) } })) });
  async function drain(worker = handle) {
    while (pending.length) {
      assert.deepEqual(await worker(records(pending.splice(0, 10))), { batchItemFailures: [] });
    }
  }
  return { config, enrollment, api, store, runs, finished, retry, pending, deferred, records, prepared, handle, options, drain,
    setNow(value) { now = value; }, event: action => ({ version: 1, action, scheduledAt: now }) };
}

async function individualFixture({ configure = () => {}, ...options } = {}) {
  return fixture({ ...options, configure(config, api) {
    config.policy = { pattern: 'individual_staircase', anchor: config.policy.anchor,
      initialHeadroom: '500', minimumInitialHeadroom: '100', increment: '500', intervalHours: 24, ceiling: '5000' };
    ['0', '206', '3491'].forEach((usage, index) => { api.users[`synthetic-user-${index}`].usage = usage; });
    configure(config, api);
  } });
}

const memberMessages = (runId, indexes = [0, 1, 2]) => indexes.map(index => ({ version: 1, kind: 'member', runId, index }));
const currentCaps = h => [0, 1, 2].map(index => h.api.users[`synthetic-user-${index}`].cap.amount);

test('individual AWS workers bind different captured starts and consume duplicate deliveries once', async () => {
  const h = await individualFixture();
  assert.deepEqual(h.enrollment.members.map(member => member.startCap), ['500', '706', '3991']);
  const { runId } = await h.handle(h.event('apply')); await h.drain();
  assert.deepEqual(currentCaps(h), ['500', '706', '3991']);
  assert.equal(h.api.writes.length, 3);
  const coldWorker = createHandler(h.options);
  assert.deepEqual(await coldWorker(h.records(memberMessages(runId))), { batchItemFailures: [] });
  await coldWorker(h.event('apply')); await h.drain(coldWorker);
  // Another hourly check creates a distinct run in the same daily policy slot.
  h.setNow('2030-04-02T01:00:00Z');
  const hourly = await coldWorker(h.event('apply')); await h.drain(coldWorker);
  assert.notEqual(hourly.runId, runId);
  assert.equal(h.api.writes.length, 3);
  for (const id of [runId, hourly.runId]) {
    assert.equal(h.runs.get(id).completed, 3); assert.equal(h.runs.get(id).succeeded, 3);
    assert.equal(h.runs.get(id).attention, 0);
  }
  for (const member of h.enrollment.members) {
    const state = await h.store.getState(`${h.config.workspaceId}:${member.userId}`);
    assert.equal(state.lastSlot, 0); assert.equal(state.pending, null);
    assert.deepEqual(state.original, member.before);
  }
});

test('individual queued retries preserve absolute intent while other members finish and a later slot catches up', async () => {
  const h = await individualFixture();
  await h.handle(h.event('apply')); await h.drain();
  h.setNow('2030-04-03T00:00:00Z');
  const { runId } = await h.handle(h.event('apply'));
  assert.deepEqual(await h.handle(h.records([h.pending.shift()])), { batchItemFailures: [] });
  const messages = h.pending.splice(0);
  h.api.injectFault({ type: 'before', userId: 'synthetic-user-1', status: 503, retryAfterMs: 60_000 });
  const first = h.records(messages);
  assert.deepEqual(await h.handle(first), { batchItemFailures: [{ itemIdentifier: first.Records[1].messageId }] });
  assert.equal(h.runs.get(runId).completed, 2); assert.equal(h.runs.get(runId).succeeded, 2);
  assert.equal(h.api.writes.length, 5);
  const key = `${h.config.workspaceId}:synthetic-user-1`;
  const intent = (await h.store.getState(key)).pending;
  assert.equal(intent.amount, '1206'); assert.equal(intent.slot, 1);
  assert.equal(h.retry.get(`${runId}:1`), '2030-04-03T00:01:00.000Z');
  const coldWorker = createHandler(h.options);
  h.setNow('2030-04-03T00:00:30Z');
  const early = h.records(memberMessages(runId, [1]), 2);
  assert.equal((await coldWorker(early)).batchItemFailures.length, 1);
  assert.equal(h.deferred.at(-1).seconds, 30); assert.equal(h.api.writes.length, 5);
  // Simulated offline clock: a delayed delivery reconciles the saved target,
  // then a fresh scheduled run evaluates the genuinely later policy slot.
  h.setNow('2030-04-05T00:00:00Z');
  assert.deepEqual(await coldWorker(h.records(memberMessages(runId, [1]), 3)), { batchItemFailures: [] });
  assert.equal(h.api.users['synthetic-user-1'].cap.amount, '1206');
  assert.equal((await h.store.getState(key)).lastSlot, 1);
  assert.equal(h.runs.get(runId).completed, 3); assert.equal(h.runs.get(runId).attention, 0);
  await coldWorker(h.event('apply')); await h.drain(coldWorker);
  assert.deepEqual(currentCaps(h), ['2000', '2206', '5000']);
  assert.deepEqual(h.api.writes.filter(write => write.userId === 'synthetic-user-1').map(write => write.amount), ['706', '1206', '2206']);
  assert.equal((await h.store.getState(key)).pending, null);
});

test('individual member redelivery recovers a lost queue completion without another cap write', async () => {
  const h = await individualFixture();
  const { runId } = await h.handle(h.event('apply'));
  assert.deepEqual(await h.handle(h.records([h.pending.shift()])), { batchItemFailures: [] });
  const complete = h.store.completeMember; let failCompletion = true;
  h.store.completeMember = async (id, index, value) => {
    if (index === 0 && failCompletion) { failCompletion = false; throw new Error('Synthetic completion storage outage'); }
    return complete(id, index, value);
  };
  const first = h.records(h.pending.splice(0));
  assert.deepEqual(await h.handle(first), { batchItemFailures: [{ itemIdentifier: first.Records[0].messageId }] });
  assert.equal(h.api.writes.length, 3); assert.equal(h.runs.get(runId).completed, 2);
  assert.equal((await h.store.getState(`${h.config.workspaceId}:synthetic-user-0`)).pending, null);
  const coldWorker = createHandler(h.options);
  assert.deepEqual(await coldWorker(h.records(memberMessages(runId, [0]), 2)), { batchItemFailures: [] });
  assert.equal(h.api.writes.length, 3); assert.equal(h.runs.get(runId).completed, 3);
  assert.equal(h.finished.get(`${runId}:0`).status, 'duplicate_slot');
  assert.equal(h.runs.get(runId).succeeded, 3);
});

test('individual AWS runs jump missed daily slots without replaying every increment and hold the monthly ceiling', async () => {
  const h = await individualFixture();
  await h.handle(h.event('apply')); await h.drain();
  h.setNow('2030-04-05T00:00:00Z');
  await h.handle(h.event('apply')); await h.drain();
  assert.deepEqual(currentCaps(h), ['2000', '2206', '5000']);
  assert.equal(h.api.writes.length, 6, 'one absolute target per member, not three incremental PATCHes');
  h.setNow('2030-04-11T00:00:00Z');
  await h.handle(h.event('apply')); await h.drain();
  assert.deepEqual(currentCaps(h), ['5000', '5000', '5000']);
  assert.equal(h.api.writes.length, 8, 'the member already at the ceiling is held without another PATCH');
  h.setNow('2030-04-12T00:00:00Z');
  await h.handle(h.event('apply')); await h.drain();
  assert.equal(h.api.writes.length, 8);
  assert.ok(h.api.writes.every(write => Number(write.amount) <= 5000 && write.periodEnd === h.config.period.end));
  for (const member of h.enrollment.members) assert.equal((await h.store.getState(`${h.config.workspaceId}:${member.userId}`)).lastSlot, 10);
});

test('individual queued restoration preserves unset, inherited and explicit original settings', async () => {
  const h = await individualFixture({ configure(config, api) {
    config.allowInitialReduction = true;
    Object.assign(api.users['synthetic-user-0'], { cap: { type: 'unset', unit: 'credit' },
      settings: { override: null, effective: null, inherited: null } });
    const inherited = { limit: { type: 'limited', limit_amount: { amount: '40000', unit: 'credit' } },
      source: { kind: 'group_default', group_id: 'synthetic-group-original' } };
    Object.assign(api.users['synthetic-user-1'], { cap: { type: 'limited', amount: '40000', unit: 'credit', source: 'group_default' },
      settings: { override: null, effective: inherited, inherited } });
    const original = { type: 'limited', limit_amount: { amount: '4200', unit: 'credit' } };
    Object.assign(api.users['synthetic-user-2'], { cap: { type: 'limited', amount: '4200', unit: 'credit', source: 'individual_override' },
      settings: { ...api.users['synthetic-user-2'].settings, override: [original],
        effective: { limit: original, source: { kind: 'individual_override' } } } });
  } });
  const initial = await h.handle(h.event('apply')); await h.drain();
  assert.equal(h.runs.get(initial.runId).succeeded, 3);
  h.setNow('2030-04-03T00:00:00Z');
  await h.handle(h.event('apply')); await h.drain();
  assert.deepEqual(currentCaps(h), ['1000', '1206', '4491']);
  const restoreWorker = createHandler({ ...h.options, allowedWriteAction: 'restore' });
  const { runId } = await restoreWorker(h.event('restore')); await h.drain(restoreWorker);
  assert.equal(h.runs.get(runId).succeeded, 3); assert.equal(h.api.writes.filter(write => write.restore).length, 3);
  for (const member of h.enrollment.members) {
    assert.deepEqual(h.api.users[member.userId].settings, member.before.settings);
    const state = await h.store.getState(`${h.config.workspaceId}:${member.userId}`);
    assert.deepEqual(state.original, member.before); assert.equal(state.restored, true); assert.equal(state.pending, null);
  }
  assert.deepEqual(await restoreWorker(h.records(memberMessages(runId))), { batchItemFailures: [] });
  h.setNow('2030-04-04T00:00:00Z');
  await h.handle(h.event('apply')); await h.drain();
  assert.equal(h.api.writes.length, 9, 'closed enrollment cannot restart its allocations after restoration');
});

test('AWS queue runs the real core for 1,001 members, duplicate delivery, next slot, and exact restoration', async () => {
  const h = await fixture({ count: 1001 });
  assert.ok(h.prepared.parts.length > 1, 'full approved enrollment is actually chunked');
  const initial = await h.handle(h.event('apply')); await h.drain();
  assert.equal(h.api.writes.length, 1001); assert.equal(h.runs.get(initial.runId).succeeded, 1001);
  await h.handle(h.event('apply')); await h.drain(); assert.equal(h.api.writes.length, 1001);
  h.setNow('2030-04-03T00:00:00Z');
  await h.handle(h.event('apply')); await h.drain(); assert.equal(h.api.writes.length, 2002);
  assert.equal(h.api.users['synthetic-user-0'].cap.amount, '40');
  const restore = createHandler({ ...h.options, allowedWriteAction: 'restore' });
  await restore(h.event('restore')); await h.drain(restore);
  for (const member of h.enrollment.members) assert.deepEqual(h.api.users[member.userId].settings, member.before.settings);
  const writes = h.api.writes.length;
  h.setNow('2030-04-03T00:01:00Z'); await h.handle(h.event('apply')); await h.drain();
  assert.equal(h.api.writes.length, writes);
});

test('a slow coordinator roster check crossing pilot expiry never queues cap changes', async () => {
  const h = await fixture({ pilotExpiresAt: '2030-04-02T00:01:00Z' });
  const original = h.api.listMembers;
  h.api.listMembers = async () => { h.setNow('2030-04-02T00:02:00Z'); return original(); };
  await assert.rejects(h.handle(h.event('apply')));
  assert.equal(h.api.writes.length, 0); assert.equal(h.pending.length, 0);
});

test('authentication recovery keeps pending intent, then a fresh run reconciles it', async () => {
  const h = await fixture({ count: 1 });
  h.api.injectFault({ type: 'before', userId: 'synthetic-user-0', status: 403 });
  const first = await h.handle(h.event('apply')); await h.drain();
  assert.equal(h.runs.get(first.runId).attention, 1);
  const key = 'synthetic-workspace:synthetic-user-0';
  assert.equal((await h.store.getState(key)).halted, true);
  const pending = (await h.store.getState(key)).pending;
  await h.handle(h.event('resume_auth')); await h.drain();
  assert.equal(h.api.writes.length, 0); assert.deepEqual((await h.store.getState(key)).pending, pending);
  h.setNow('2030-04-02T00:00:01Z'); await h.handle(h.event('apply')); await h.drain();
  assert.equal(h.api.writes.length, 1);
});
