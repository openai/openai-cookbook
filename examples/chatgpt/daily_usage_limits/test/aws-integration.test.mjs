import test from 'node:test';
import assert from 'node:assert/strict';
import { createHandler } from '../aws/lambda.mjs';
import { encodeControl } from '../aws/control.mjs';
import { execute, createExecutionContext } from '../src/controller.mjs';
import { validateCurrentCohort } from '../src/selection.mjs';
import { captureEnrollment, approveEnrollment } from '../src/enrollment.mjs';
import { exampleConfig, createSyntheticApi, MemoryStore } from '../src/synthetic.mjs';

async function fixture({ count = 3, pilotExpiresAt = '2030-04-30T00:00:00Z' } = {}) {
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
  const pending = []; let messageId = 0;
  const options = { store, execute, createExecutionContext, validateCurrentCohort, apiFactory: () => api,
    secretProvider: async () => 'synthetic-not-a-real-secret', putMetric: async () => {},
    deploymentId: 'synthetic-demo', controlSha256: prepared.hash, applyEnabled: true,
    allowedWriteAction: 'apply', pilotExpiresAt, clock: () => new Date(now), log() {}, queueArn: 'synthetic-queue',
    queue: { async send(batch) { pending.push(...batch); }, async defer() {} } };
  const handle = createHandler(options);
  async function drain(worker = handle) {
    while (pending.length) {
      const Records = pending.splice(0, 10).map(body => ({ body: JSON.stringify(body), messageId: String(messageId++),
        receiptHandle: 'synthetic-receipt', eventSource: 'aws:sqs', eventSourceARN: 'synthetic-queue', attributes: { ApproximateReceiveCount: '1' } }));
      assert.deepEqual(await worker({ Records }), { batchItemFailures: [] });
    }
  }
  return { config, enrollment, api, store, runs, pending, prepared, handle, options, drain,
    setNow(value) { now = value; }, event: action => ({ version: 1, action, scheduledAt: now }) };
}

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
