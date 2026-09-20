import test from 'node:test';
import assert from 'node:assert/strict';
import { createHandler, createSecretProvider } from '../aws/lambda.mjs';
import { hash } from '../aws/store.mjs';
import { createAdminApi } from '../src/admin-api.mjs';

function harness(overrides = {}) {
  const calls = { secret: 0, controls: 0, api: [], execute: [], receipts: [], metrics: [], logs: [] };
  const config = { workspaceId: 'synthetic-workspace', liveWrites: false,
    period: { start: '2030-04-01T00:00:00Z', end: '2030-05-01T00:00:00Z' } };
  const document = JSON.stringify({ config, enrollment: { members: [{ userId: 'synthetic-user' }] } });
  const options = {
    deploymentId: 'synthetic-demo', clock: () => new Date('2030-04-02T00:00:00Z'),
    pilotExpiresAt: '2030-04-30T00:00:00Z', controlSha256: hash(document),
    store: { async getControl() { calls.controls++; return document; },
      async putReceipt(receipt) { calls.receipts.push(receipt); } },
    async secretProvider() { calls.secret++; return 'synthetic-key-not-a-credential'; },
    apiFactory(options) { calls.api.push(options); return {}; },
    async execute(options) { calls.execute.push(options); return { ok: true, mode: 'preview', results: [{}] }; },
    async putMetric(name, value) { calls.metrics.push({ name, value }); },
    log(line) { calls.logs.push(line); },
    ...overrides,
  };
  return { calls, options, handle: createHandler(options),
    event: { version: 1, action: 'preview', scheduledAt: '2030-04-02T00:00:00Z' } };
}

test('preview reads reviewed controls and credentials but passes writes off', async () => {
  const h = harness();
  const result = await h.handle(h.event);
  assert.equal(result.ok, true);
  assert.equal(h.calls.execute[0].apply, false);
  assert.equal(h.calls.api[0].allowWrites, false);
  assert.equal(h.calls.api[0].timeoutMs, 10_000);
  assert.equal(h.calls.receipts[0].kind, 'aws_invocation');
  assert.doesNotMatch(h.calls.logs.join(''), /synthetic-workspace|synthetic-key/);
});

test('probe proves only handler entry and receipt, with no API or credential access', async () => {
  const h = harness(); await h.handle({ ...h.event, action: 'probe' });
  assert.equal(h.calls.secret, 0); assert.equal(h.calls.controls, 0);
  assert.equal(h.calls.execute.length, 0);
});

test('apply and restore are disabled by default before secret access', async () => {
  for (const action of ['apply', 'restore']) {
    const h = harness();
    await assert.rejects(h.handle({ ...h.event, action }), /USAGE_CONTROLLER_FAILED/);
    assert.equal(h.calls.secret, 0); assert.equal(h.calls.execute.length, 0);
  }
});

test('live apply requires both deployment and reviewed configuration opt-in', async () => {
  const config = { liveWrites: true, workspaceId: 'synthetic-workspace',
    period: { start: '2030-04-01T00:00:00Z', end: '2030-05-01T00:00:00Z' } };
  const document = JSON.stringify({ config, enrollment: { approved: true, members: [{ userId: 'synthetic-user' }] } });
  const h = harness({ applyEnabled: true, controlSha256: hash(document) });
  h.options.store.getControl = async () => document;
  await h.handle({ ...h.event, action: 'apply' });
  assert.equal(h.calls.execute[0].apply, true);
  assert.equal(h.calls.api[0].allowWrites, true);
});

test('changed controls, expiry, stale events, injected config, and low time all fail closed', async () => {
  for (const overrides of [
    { controlSha256: '0'.repeat(64) }, { pilotExpiresAt: '2030-04-01T00:00:00Z' },
    { pilotExpiresAt: 'invalid' },
  ]) {
    const h = harness(overrides);
    await assert.rejects(h.handle(h.event)); assert.equal(h.calls.secret, 0);
  }
  for (const eventPatch of [
    { scheduledAt: '2030-04-01T00:00:00Z' }, { scheduledAt: '2030-04-03T00:00:00Z' },
    { config: { liveWrites: true } }, { action: 'unknown' },
  ]) {
    const h = harness(); await assert.rejects(h.handle({ ...h.event, ...eventPatch }));
    assert.equal(h.calls.secret, 0);
  }
  const h = harness(); await assert.rejects(h.handle(h.event, { getRemainingTimeInMillis: () => 44_000 }));
  assert.equal(h.calls.secret, 0);
});

test('controller failures trigger the Lambda retry path and suppress private error payloads', async () => {
  const h = harness({ execute: async () => ({ ok: false, results: [{ status: 'blocked' }] }) });
  await assert.rejects(h.handle(h.event), /USAGE_CONTROLLER_FAILED/);
  assert.equal(h.calls.receipts[0].ok, false);
  assert.equal(h.calls.metrics.some(m => m.name === 'ControllerIssue' && m.value === 1), true);
  const secrets = harness({ secretProvider: async () => { throw new Error('private-secret-body'); } });
  await assert.rejects(secrets.handle(secrets.event), error => !error.message.includes('private-secret-body'));
  assert.doesNotMatch(secrets.calls.logs.join(''), /private-secret-body/);
});

test('remaining-time callback prevents launching additional members near timeout', async () => {
  const h = harness(); let remaining = 100_000;
  await h.handle(h.event, { getRemainingTimeInMillis: () => remaining });
  assert.equal(h.calls.execute[0].shouldContinue(), true);
  remaining = 40_000;
  assert.equal(h.calls.execute[0].shouldContinue(), false);
});

test('real API factory receives the explicit enrolled identity allowlist and moving time budget', async () => {
  let fetched = false;
  const h = harness({
    apiFactory: options => createAdminApi({ ...options, fetchImpl: async () => {
      fetched = true; throw new Error('synthetic transport failure');
    } }),
    execute: async ({ api }) => {
      await assert.rejects(api.readSnapshot('synthetic-user'), { code: 'API_READ_TRANSPORT_FAILED' });
      await assert.rejects(api.readSnapshot('not-enrolled'), { code: 'IDENTITY_NOT_ALLOWLISTED' });
      return { ok: true, results: [] };
    },
  });
  await h.handle(h.event);
  assert.equal(fetched, true);
});

test('secret provider accepts only the fixed ARN and expected JSON field', async () => {
  const arn = 'arn:aws:secretsmanager:us-east-1:000000000000:secret:synthetic-example';
  const provider = createSecretProvider({ secretArn: arn, sendGetSecret: async requested => {
    assert.equal(requested, arn); return { SecretString: '{"apiKey":"synthetic-not-a-key"}' };
  } });
  assert.equal(await provider(), 'synthetic-not-a-key');
  assert.throws(() => createSecretProvider({ secretArn: 'not-an-arn' }), /INVALID_SECRET_ARN/);
  await assert.rejects(createSecretProvider({ secretArn: arn,
    sendGetSecret: async () => ({ SecretString: 'not json' }) })(), /INVALID_SECRET_FORMAT/);
});
