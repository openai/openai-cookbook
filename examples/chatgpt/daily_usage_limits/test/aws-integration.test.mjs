import test from 'node:test';
import assert from 'node:assert/strict';
import { createHandler } from '../aws/lambda.mjs';
import { hash } from '../aws/store.mjs';
import { execute } from '../src/controller.mjs';
import { captureEnrollment, approveEnrollment } from '../src/enrollment.mjs';
import { exampleConfig, createSyntheticApi, MemoryStore } from '../src/synthetic.mjs';

function smallCreditFixture(options) {
  const config=exampleConfig(options);
  Object.assign(config.policy,{startCap:'20',increment:'20',ceiling:'200'});
  return config;
}

test('AWS handler runs the real core: apply, duplicate delivery, next slot, and exact restore', async () => {
  let now = '2030-04-02T00:00:00Z';
  const config = { ...smallCreditFixture({ now, cohort: 'all' }), liveWrites: true };
  const api = createSyntheticApi({ config, clock: () => now, initialCap: '10' });
  const captured = await captureEnrollment({ config, api, now });
  const enrollment = approveEnrollment(captured.enrollment, captured.hash, now);
  const document = JSON.stringify({ config, enrollment });
  const store = new MemoryStore();
  store.getControl = async () => document;
  const handle = createHandler({ store, execute, apiFactory: () => api,
    secretProvider: async () => 'synthetic-not-a-real-secret', putMetric: async () => {},
    deploymentId: 'synthetic-demo', controlSha256: hash(document), applyEnabled: true,
    pilotExpiresAt: '2030-04-30T00:00:00Z', clock: () => new Date(now), log() {} });
  const event = action => ({ version: 1, action, scheduledAt: now });
  await handle(event('apply'));
  assert.equal(api.writes.length, 3);
  await handle(event('apply'));
  assert.equal(api.writes.length, 3, 'duplicate event must not grant more');
  now = '2030-04-03T00:00:00Z';
  await handle(event('apply'));
  assert.equal(api.writes.length, 6);
  assert.equal(api.users['synthetic-user-a'].cap.amount, '40');
  await handle(event('restore'));
  for (const member of enrollment.members) {
    assert.deepEqual(api.users[member.userId].settings, member.before.settings);
  }
  const afterRestore = api.writes.length;
  await handle(event('apply'));
  assert.equal(api.writes.length, afterRestore, 'a restored enrollment must remain stopped');
});

test('AWS pilot refuses oversized cohorts before any credentials or API access', async () => {
  const now = '2030-04-02T00:00:00Z';
  const config = exampleConfig({ now });
  const document = JSON.stringify({ config, enrollment: { members: new Array(26).fill({ userId: 'synthetic-user' }) } });
  const store = new MemoryStore(); store.getControl = async () => document;
  const handle = createHandler({ store, execute, apiFactory: () => assert.fail('API accessed'),
    secretProvider: async () => assert.fail('Secret accessed'), putMetric: async () => {},
    deploymentId: 'synthetic-demo', controlSha256: hash(document),
    pilotExpiresAt: '2030-04-30T00:00:00Z', clock: () => new Date(now), log() {} });
  await assert.rejects(handle({ version: 1, action: 'preview', scheduledAt: now }));
  assert.equal(store.receipts[0].code, 'COHORT_TOO_LARGE_FOR_LAMBDA');
});

test('a slow member listing that crosses pilot expiry cannot start a cap change', async () => {
  let now = '2030-04-02T00:00:00Z';
  const config = { ...smallCreditFixture({ now }), liveWrites: true };
  const api = createSyntheticApi({ config, clock: () => now, initialCap: '10' });
  const captured = await captureEnrollment({ config, api, now });
  const enrollment = approveEnrollment(captured.enrollment, captured.hash, now);
  const document = JSON.stringify({ config, enrollment });
  const store = new MemoryStore(); store.getControl = async () => document;
  const originalList = api.listMembers;
  api.listMembers = async () => { now = '2030-04-02T00:02:00Z'; return originalList(); };
  const handle = createHandler({ store, execute, apiFactory: () => api,
    secretProvider: async () => 'synthetic-key', putMetric: async () => {},
    deploymentId: 'synthetic-demo', controlSha256: hash(document), applyEnabled: true,
    pilotExpiresAt: '2030-04-02T00:01:00Z', clock: () => new Date(now), log() {} });
  await assert.rejects(handle({ version: 1, action: 'apply', scheduledAt: now }));
  assert.equal(api.writes.length, 0);
});

test('manual authentication recovery preserves pending intent without a cap write', async () => {
  const now = '2030-04-02T00:00:00Z';
  const config = { ...smallCreditFixture({ now }), liveWrites: true,
    cohort: { mode: 'selected', userIds: ['synthetic-user-a'] } };
  const api = createSyntheticApi({ config, clock: () => now, initialCap: '10' });
  const captured = await captureEnrollment({ config, api, now });
  const enrollment = approveEnrollment(captured.enrollment, captured.hash, now);
  const document = JSON.stringify({ config, enrollment });
  const store = new MemoryStore(); store.getControl = async () => document;
  const handle = createHandler({ store, execute, apiFactory: () => api,
    secretProvider: async () => 'synthetic-key', putMetric: async () => {},
    deploymentId: 'synthetic-demo', controlSha256: hash(document), applyEnabled: true,
    pilotExpiresAt: '2030-04-30T00:00:00Z', clock: () => new Date(now), log() {} });
  const event = action => ({ version: 1, action, scheduledAt: now });
  api.injectFault({ type: 'before', userId: 'synthetic-user-a', status: 403 });
  await assert.rejects(handle(event('apply')));
  const key = 'synthetic-workspace:synthetic-user-a';
  assert.equal((await store.getState(key)).halted, true);
  const pending = (await store.getState(key)).pending;
  await handle(event('resume_auth'));
  assert.equal(api.writes.length, 0);
  assert.deepEqual((await store.getState(key)).pending, pending);
  await handle(event('apply'));
  assert.equal(api.writes.length, 1);
});
