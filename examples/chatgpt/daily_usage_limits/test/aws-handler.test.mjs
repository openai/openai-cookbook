import test from 'node:test';
import assert from 'node:assert/strict';
import { createHandler, createSecretProvider, runProgress } from '../aws/lambda.mjs';
import { encodeControl } from '../aws/control.mjs';

function harness({ count = 3, ...overrides } = {}) {
  let now = new Date('2030-04-02T00:00:00Z');
  const calls = { secrets: 0, controls: 0, contexts: 0, cohortChecks: 0, api: [], execute: [], receipts: [], metrics: [], logs: [], deferred: [] };
  const config = { workspaceId: 'synthetic-workspace', liveWrites: true,
    period: { start: '2030-04-01T00:00:00Z', end: '2030-05-01T00:00:00Z' } };
  const enrollment = { members: Array.from({ length: count }, (_, i) => ({ userId: `synthetic-${i}` })) };
  const prepared = encodeControl(config, enrollment);
  const parts = new Map(prepared.parts.map(part => [part.hash, part.document]));
  const runs = new Map(), results = new Map(), retries = new Map(), locks = new Set();
  const pending = [];
  const store = {
    async getControl() { calls.controls++; return prepared.document; },
    async getControlPart(hash) { return parts.get(hash); },
    async putReceipt(value) { calls.receipts.push(value); },
    async withLock(key, fn) {
      if (locks.has(key)) throw new Error('LEASE_BUSY');
      locks.add(key); try { return await fn(); } finally { locks.delete(key); }
    },
    async getRun(id) { return runs.get(id); },
    async createRun(run) { if (!runs.has(run.runId)) runs.set(run.runId, { ...run, cursor: 0, completed: 0, succeeded: 0, attention: 0 }); return runs.get(run.runId); },
    async setRunCursor(id, cursor) { runs.get(id).cursor = cursor; },
    async getMemberResult(id, index) { return results.get(`${id}:${index}`); },
    async completeMember(id, index, outcome) {
      const key = `${id}:${index}`;
      if (results.has(key)) return false;
      results.set(key, outcome); const run = runs.get(id); run.completed++; run[outcome.ok ? 'succeeded' : 'attention']++; return true;
    },
    async getRetry(id, index) { return retries.get(`${id}:${index}`); },
    async putRetry(id, index, value) { retries.set(`${id}:${index}`, value); },
    async pauseRun(id, value) { runs.get(id).notBefore = value; },
    async cancelRun(id) { runs.get(id).cancelled = true; },
  };
  const options = { store, deploymentId: 'synthetic-demo', controlSha256: prepared.hash,
    pilotExpiresAt: '2030-04-30T00:00:00Z', clock: () => now,
    queueArn: 'synthetic-queue', dispatchBatchSize: 13,
    queue: { async send(batch) { pending.push(...structuredClone(batch)); },
      async defer(receipt, seconds) { calls.deferred.push({ receipt, seconds }); } },
    createExecutionContext(value) { calls.contexts++; return value; },
    async validateCurrentCohort() { calls.cohortChecks++; },
    async secretProvider() { calls.secrets++; return 'synthetic-key-not-a-credential'; },
    apiFactory(value) { calls.api.push(value); return {}; },
    async execute(value) { calls.execute.push(value); return { ok: true, results: [{ ok: true, status: 'applied' }] }; },
    async putMetric(name, value) { calls.metrics.push({ name, value }); },
    log(line) { calls.logs.push(line); }, ...overrides };
  let serial = 0;
  const records = batch => ({ Records: batch.map(body => ({ body: JSON.stringify(body), messageId: `message-${serial++}`,
    receiptHandle: `receipt-${serial}`, eventSource: 'aws:sqs', eventSourceARN: 'synthetic-queue', attributes: { ApproximateReceiveCount: '1' } })) });
  const handle = createHandler(options);
  return { handle, options, store, calls, pending, runs, results, parts, prepared, records,
    event: { version: 1, action: 'preview', scheduledAt: now.toISOString() },
    advance(ms) { now = new Date(now.getTime() + ms); },
    async drain() { while (pending.length) assert.deepEqual(await handle(records(pending.splice(0, 8))), { batchItemFailures: [] }); } };
}

test('probe needs no controls, credentials, queue or API', async () => {
  const h = harness();
  assert.equal((await h.handle({ ...h.event, action: 'probe' })).apiAccessed, false);
  assert.equal(h.calls.controls, 0); assert.equal(h.calls.secrets, 0); assert.equal(h.pending.length, 0);
});

test('connection check runs before controls with a read-only bounded adapter and no member output', async () => {
  const h = harness({ controlSha256: '0'.repeat(64) });
  let adapterOptions;
  const handle = createHandler({ ...h.options, apiFactory(options) {
    adapterOptions = options;
    return { async checkConnection() { return { workspaceId: options.workspaceId,
      unit: 'usd', usersRead: true, members: [{ email: 'private@example.invalid' }], apiKey: options.apiKey }; } };
  } });
  const result = await handle({ ...h.event, action: 'check_connection', workspaceId: 'workspace-synthetic' });
  assert.deepEqual(result, { ok: true, action: 'check_connection', workspaceId: 'workspace-synthetic',
    unit: 'usd', usersRead: true, capWrites: 0, checkId: result.checkId, receiptRecorded: true });
  assert.match(result.checkId, /^[a-f0-9]{64}$/);
  assert.equal(adapterOptions.allowWrites, false); assert.deepEqual(adapterOptions.userIds, []);
  assert.equal(adapterOptions.maxPages, 1); assert.equal(adapterOptions.maxRows, 1);
  assert.equal(adapterOptions.timeoutMs, 10_000); assert.equal(adapterOptions.remainingTimeMs(), 0);
  assert.equal(h.calls.secrets, 1); assert.equal(h.calls.controls, 0); assert.equal(h.calls.contexts, 0);
  assert.equal(h.calls.cohortChecks, 0); assert.equal(h.calls.execute.length, 0);
  assert.equal(h.pending.length, 0); assert.equal(h.runs.size, 0);
  assert.equal(h.calls.receipts[0].kind, 'aws_connection_check');
  assert.deepEqual(h.calls.metrics, [{ name: 'ConnectionCheckSucceeded', value: 1 }]);
  assert.doesNotMatch(JSON.stringify([result, h.calls.receipts, h.calls.logs]), /private@example|synthetic-key/);
});

test('connection events reject unexpected fields and malformed workspace identities before secret access', async () => {
  for (const change of [{ workspaceId: undefined }, { workspaceId: 123 }, { workspaceId: '../other' }, { workspaceId: '' },
    { workspaceId: 'a'.repeat(161) }, { apiKey: 'injected' }, { allowWrites: true },
    { baseUrl: 'https://example.invalid' }, { userIds: ['unreviewed'] }, { runId: 'a'.repeat(64) }]) {
    const h = harness();
    await assert.rejects(h.handle({ ...h.event, action: 'check_connection', workspaceId: 'workspace-synthetic', ...change }));
    assert.equal(h.calls.secrets, 0); assert.equal(h.calls.controls, 0);
  }
  const h = harness();
  await assert.rejects(h.handle({ ...h.event, workspaceId: 'workspace-synthetic' }));
  assert.equal(h.calls.secrets, 0);
});

test('connection authentication failures return a safe result without triggering Lambda retries', async () => {
  for (const code of ['ADMIN_HTTP_401', 'ADMIN_HTTP_403', 'ADMIN_HTTP_429', 'UNIT_UNAVAILABLE', 'PRIVATE_SECRET']) {
    const h = harness(); let requests = 0;
    const handle = createHandler({ ...h.options, apiFactory() {
      return { async checkConnection() { requests++; throw Object.assign(new Error('private response and synthetic-key'), { code }); } };
    } });
    const result = await handle({ ...h.event, action: 'check_connection', workspaceId: 'workspace-synthetic' });
    assert.equal(result.ok, false); assert.equal(result.capWrites, 0); assert.equal(requests, 1);
    assert.equal(result.code, code === 'PRIVATE_SECRET' ? 'CONNECTION_CHECK_FAILED' : code);
    assert.equal(result.receiptRecorded, true); assert.equal(h.pending.length, 0);
    assert.doesNotMatch(JSON.stringify([result, h.calls.receipts, h.calls.logs]), /private response|synthetic-key|PRIVATE_SECRET/);
  }
});

test('connection auth rejection stays handled when receipt or metric storage also fails', async () => {
  const h = harness();
  const handle = createHandler({ ...h.options, store: { ...h.store, async putReceipt() { throw new Error('private storage error'); } },
    async putMetric() { throw new Error('private metric error'); },
    apiFactory: () => ({ async checkConnection() { throw Object.assign(new Error('private response'), { code: 'ADMIN_HTTP_403' }); } }) });
  const result = await handle({ ...h.event, action: 'check_connection', workspaceId: 'workspace-synthetic' });
  assert.equal(result.code, 'ADMIN_HTTP_403'); assert.equal(result.receiptRecorded, false);
  assert.equal(h.calls.secrets, 1); assert.equal(h.pending.length, 0);
});

test('connection result returns without auxiliary AWS calls when only the response reserve remains', async () => {
  for (const authFailure of [false, true]) {
    const h = harness(); let remaining = 45_000;
    const handle = createHandler({ ...h.options, apiFactory: () => ({ async checkConnection() {
      remaining = 5_000;
      if (authFailure) throw Object.assign(new Error('private auth body'), { code: 'ADMIN_HTTP_401' });
      return { workspaceId: 'workspace-synthetic', unit: 'credit', usersRead: true };
    } }) });
    const result = await handle({ ...h.event, action: 'check_connection', workspaceId: 'workspace-synthetic' },
      { getRemainingTimeInMillis: () => remaining });
    assert.equal(result.ok, !authFailure); assert.equal(result.receiptRecorded, false);
    assert.equal(h.calls.receipts.length, 0); assert.equal(h.calls.metrics.length, 0);
    assert.equal(h.calls.secrets, 1); assert.equal(h.pending.length, 0);
  }
});

test('connection time, event-age, cutoff and expiry gates bound secret and API access', async () => {
  const h = harness(); const event = { ...h.event, action: 'check_connection', workspaceId: 'workspace-synthetic' };
  const result = await h.handle(event, { getRemainingTimeInMillis: () => 40_000 });
  assert.equal(result.code, 'TIME_BUDGET_EXHAUSTED'); assert.equal(h.calls.secrets, 0);
  for (const options of [{ pilotExpiresAt: h.event.scheduledAt }, { runEventsNotBefore: '2030-04-02T00:00:01Z' }]) {
    const stopped = harness(options);
    await assert.rejects(stopped.handle(event)); assert.equal(stopped.calls.secrets, 0);
  }
  await assert.rejects(h.handle({ ...event, scheduledAt: '2030-04-01T00:00:00Z' }));
  let remaining = 45_000;
  const deadline = createHandler({ ...h.options, async secretProvider() { remaining = 30_000; return 'synthetic-key'; } });
  assert.equal((await deadline(event, { getRemainingTimeInMillis: () => remaining })).code, 'TIME_BUDGET_EXHAUSTED');
  assert.equal(h.calls.api.length, 0);
  const expired = createHandler({ ...h.options, apiFactory: () => ({ async checkConnection() {
    h.advance(31 * 86400_000); return { workspaceId: event.workspaceId, unit: 'credit', usersRead: true };
  } }) });
  assert.equal((await expired(event)).code, 'PILOT_EXPIRED');
});

test('connection check rejects malformed adapter results without returning their contents', async () => {
  for (const connection of [{ workspaceId: 'other', unit: 'credit', usersRead: true },
    { workspaceId: 'workspace-synthetic', unit: 'unknown', usersRead: true },
    { workspaceId: 'workspace-synthetic', unit: 'usd', usersRead: false }, null]) {
    const h = harness({ apiFactory: () => ({ checkConnection: async () => connection }) });
    const result = await h.handle({ ...h.event, action: 'check_connection', workspaceId: 'workspace-synthetic' });
    assert.equal(result.code, 'CONNECTION_RESPONSE_INVALID'); assert.equal(result.capWrites, 0);
  }
});

test('1,001 reviewed members progress through resumable batches with exact unique completion', async () => {
  const h = harness({ count: 1001 });
  const started = await h.handle(h.event);
  assert.equal(started.total, 1001); assert.equal(started.completed, 0);
  await h.drain();
  const run = h.runs.get(started.runId);
  assert.deepEqual(runProgress(run), { runId: started.runId, total: 1001, queued: 1001, completed: 1001,
    succeeded: 1001, attention: 0, outstanding: 0, status: 'completed' });
  assert.equal(new Set(h.calls.execute.flatMap(call => call.memberIds)).size, 1001);
  assert.ok(h.calls.execute.every(call => call.memberIds.length === 1 && call.executionContext.enrollment.members.length === 1001));
  assert.equal(h.calls.contexts, 1); assert.equal(h.calls.controls, 1); assert.equal(h.calls.cohortChecks, 1);
  assert.equal(h.calls.api.length, 1, 'warm API and history cache are reused');
  await h.handle(h.records([{ version: 1, kind: 'member', runId: run.runId, index: 0 }]));
  await h.handle(h.event); await h.drain();
  assert.equal(run.completed, 1001); assert.equal(h.calls.execute.length, 1001); assert.equal(h.calls.cohortChecks, 1);
});

test('uncertain sends and checkpoints retry without losing a member', async () => {
  const h = harness({ count: 21 }); const started = await h.handle(h.event);
  const feed = h.pending.shift(); const original = h.store.setRunCursor;
  let failed = false;
  h.store.setRunCursor = async (...args) => { if (!failed) { failed = true; throw new Error('store unavailable after send'); } return original(...args); };
  assert.equal((await h.handle(h.records([feed]))).batchItemFailures.length, 1);
  h.pending.unshift(feed);
  await h.drain();
  assert.equal(h.runs.get(started.runId).completed, 21); assert.equal(h.calls.execute.length, 21);
});

test('partial failures defer only their own record and do not starve later members', async () => {
  const h = harness({ count: 2 }); const started = await h.handle(h.event); h.pending.length = 0;
  let first = true;
  const execute = async value => {
    if (value.memberIds[0] === 'synthetic-0' && first) { first = false; return { results: [{ ok: false, retryable: true, code: 'ADMIN_HTTP_503', retryAfterMs: 60_000 }] }; }
    return { results: [{ ok: true, status: 'applied' }] };
  };
  const handle = createHandler({ ...h.options, execute });
  const messages = [0, 1].map(index => ({ version: 1, kind: 'member', runId: started.runId, index }));
  const records = h.records(messages);
  assert.deepEqual((await handle(records)).batchItemFailures, [{ itemIdentifier: records.Records[0].messageId }]);
  assert.equal(h.runs.get(started.runId).completed, 1);
  assert.equal(h.calls.deferred[0].seconds, 60);
  h.advance(60_000);
  assert.deepEqual((await handle(h.records([messages[0]]))).batchItemFailures, []);
  assert.equal(h.runs.get(started.runId).completed, 2);
});

test('429 creates a durable run pause so another member respects Retry-After', async () => {
  const h = harness({ count: 2 }); const { runId } = await h.handle(h.event); let calls = 0;
  const handle = createHandler({ ...h.options, execute: async () => { calls++; return { results: [{ ok: false, retryable: true, code: 'ADMIN_HTTP_429', retryAfterMs: 90_000 }] }; } });
  const records = h.records([0, 1].map(index => ({ version: 1, kind: 'member', runId, index })));
  assert.equal((await handle(records)).batchItemFailures.length, 2);
  assert.equal(calls, 1); assert.equal(h.calls.deferred.length, 2);
  assert.equal(h.runs.get(runId).completed, 0);
});

test('business conflicts finish as attention while unaffected members succeed', async () => {
  const h = harness({ count: 2 }); const { runId } = await h.handle(h.event);
  const handle = createHandler({ ...h.options, execute: async ({ memberIds }) => ({ results: [{ ok: memberIds[0] !== 'synthetic-0', code: 'MANUAL_ADMIN_CHANGE_CONFLICT' }] }) });
  assert.deepEqual(await handle(h.records([0, 1].map(index => ({ version: 1, kind: 'member', runId, index })))), { batchItemFailures: [] });
  assert.equal(h.runs.get(runId).succeeded, 1); assert.equal(h.runs.get(runId).attention, 1);
});

test('control tampering, expired starts and write gates stop before secret access', async () => {
  for (const overrides of [{ controlSha256: '0'.repeat(64) }, { pilotExpiresAt: 'invalid' }, { pilotExpiresAt: '2030-04-01T00:00:00Z' }]) {
    const h = harness(overrides); await assert.rejects(h.handle(h.event)); assert.equal(h.calls.secrets, 0);
  }
  const h = harness(); h.parts.set(h.prepared.parts[0].hash, 'tampered');
  await assert.rejects(h.handle(h.event)); assert.equal(h.calls.secrets, 0);
  for (const action of ['apply', 'restore']) {
    const gated = harness(); await assert.rejects(gated.handle({ ...gated.event, action })); assert.equal(gated.calls.secrets, 0);
  }
});

test('apply needs its explicit action gate and the worker selects only reviewed identities', async () => {
  const h = harness({ applyEnabled: true, allowedWriteAction: 'apply' });
  const { runId } = await h.handle({ ...h.event, action: 'apply' }); await h.drain();
  assert.ok(h.calls.execute.every(call => call.apply));
  const hostile = [{ version: 1, kind: 'member', runId, index: 99 },
    { version: 1, kind: 'member', runId, index: 0, userId: 'other-user' }];
  assert.equal((await h.handle(h.records(hostile))).batchItemFailures.length, 2);
  assert.equal(h.calls.execute.length, 3);
});

test('cutoff rejects old async starts and cancels old queued runs during restoration', async () => {
  const h = harness(); const { runId } = await h.handle(h.event);
  h.advance(1000);
  const handle = createHandler({ ...h.options, runEventsNotBefore: '2030-04-02T00:00:01Z', applyEnabled: true, allowedWriteAction: 'restore' });
  await assert.rejects(handle(h.event));
  assert.deepEqual(await handle(h.records([{ version: 1, kind: 'member', runId, index: 0 }])), { batchItemFailures: [] });
  assert.equal(h.calls.execute.length, 0); assert.equal(h.runs.get(runId).cancelled, true);
  await assert.rejects(handle({ ...h.event, action: 'apply', scheduledAt: '2030-04-02T00:00:01Z' }));
});

test('explicit cancellation works after expiry with writes disabled and prevents queued work', async () => {
  const h = harness(); const { runId } = await h.handle(h.event); h.advance(31 * 86400_000);
  const cancelled = await h.handle({ version: 1, action: 'cancel_run', runId });
  assert.equal(cancelled.status, 'cancelled'); await h.drain(); assert.equal(h.calls.execute.length, 0);
});

test('cancelled work from a replaced control is consumed without loading new controls or writing', async () => {
  const h = harness(); const { runId } = await h.handle(h.event);
  await h.store.cancelRun(runId);
  const handle = createHandler({ ...h.options, controlSha256: 'a'.repeat(64) });
  assert.deepEqual(await handle(h.records([{ version: 1, kind: 'feed', runId },
    { version: 1, kind: 'member', runId, index: 0 }])), { batchItemFailures: [] });
  assert.equal(h.calls.execute.length, 0); assert.equal(h.calls.controls, 1);
});

test('low remaining time leaves a member outstanding and clears cached API deadline after invocation', async () => {
  const h = harness(); const { runId } = await h.handle(h.event);
  const record = h.records([{ version: 1, kind: 'member', runId, index: 0 }]);
  assert.equal((await h.handle(record, { getRemainingTimeInMillis: () => 40_000 })).batchItemFailures.length, 1);
  assert.equal(h.runs.get(runId).completed, 0); assert.equal(h.calls.execute.length, 0);
  assert.equal(h.calls.api[0].remainingTimeMs(), 0);
});

test('secret provider validates the fixed ARN and secret JSON without exposing the body', async () => {
  const arn = 'arn:aws:secretsmanager:us-east-1:000000000000:secret:synthetic-example';
  const provider = createSecretProvider({ secretArn: arn, sendGetSecret: async requested => {
    assert.equal(requested, arn); return { SecretString: '{"apiKey":"synthetic-not-a-key"}' };
  } });
  assert.equal(await provider(), 'synthetic-not-a-key');
  assert.throws(() => createSecretProvider({ secretArn: 'invalid' }), /INVALID_SECRET_ARN/);
  await assert.rejects(createSecretProvider({ secretArn: arn, sendGetSecret: async () => ({ SecretString: 'private body' }) })(), /INVALID_SECRET_FORMAT/);
});
