import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { prepareRenewal, activateRenewal } from '../aws/renew-period.mjs';
import { encodeControl } from '../aws/control.mjs';
import { captureEnrollment, approveEnrollment, enrollmentHash } from '../src/enrollment.mjs';
import { configDigest, digest } from '../src/policy.mjs';
import { exampleConfig, createSyntheticApi } from '../src/synthetic.mjs';

async function fixture(t) {
  let now = new Date('2030-05-02T00:00:00Z');
  const parent = await mkdtemp(join(tmpdir(), 'cookbook-renewal-'));
  t.after(() => rm(parent, { recursive: true, force: true }));
  const directory = join(parent, 'next');
  const oldNow = '2030-04-02T00:00:00Z';
  const previousConfig = exampleConfig({ now: oldNow });
  const oldCapture = await captureEnrollment({ config: previousConfig, api: createSyntheticApi({ config: previousConfig, clock: () => oldNow }), now: oldNow });
  const previousEnrollment = approveEnrollment(oldCapture.enrollment, oldCapture.hash, oldNow);
  const config = exampleConfig({ now: now.toISOString() });
  config.policy.anchor = config.period.start;
  const capture = await captureEnrollment({ config, api: createSyntheticApi({ config, clock: () => now.toISOString() }), now: now.toISOString() });
  const states = new Map(previousEnrollment.members.map(member => [`${previousConfig.workspaceId}:${member.userId}`,
    { version: 1, configDigest: configDigest(previousConfig), enrollmentHash: oldCapture.hash,
      original: member.before, last: member.before, lastSlot: 1, lastUsage: member.before.usage, pending: null }]));
  const enrollment = { ...capture.enrollment,
    renewal: { version: 1, previousConfigDigest: configDigest(previousConfig), previousEnrollmentHash: oldCapture.hash,
      previousPeriodEnd: previousConfig.period.end },
    members: capture.enrollment.members.map(member => ({ ...member,
      renewal: { priorStateDigest: digest(states.get(`${config.workspaceId}:${member.userId}`)),
        original: states.get(`${config.workspaceId}:${member.userId}`).original } })) };
  const prepared = encodeControl(previousConfig, previousEnrollment);
  const items = new Map([['REVIEWED', { PK: { S: 'CONTROL#synthetic-demo' }, SK: { S: 'REVIEWED' }, document: { S: prepared.document } }],
    ...prepared.parts.map(part => [`PART#${part.hash}`, { document: { S: part.document } }])]);
  const resources = { FunctionName: 'same-function', StateTableName: 'same-table', WorkQueueUrl: 'same-queue',
    ScheduleName: 'same-schedule', ScheduleGroupName: 'same-group', WorkMappingId: 'same-mapping' };
  const parameters = { DeploymentId: 'synthetic-demo', ControlSha256: prepared.hash,
    PilotExpiresAt: previousConfig.period.end.replace('.000Z', 'Z'), RunEventsNotBefore: '2030-04-01T00:00:00Z',
    ScheduleState: 'DISABLED', WorkProcessingEnabled: 'false', ApplyEnabled: 'false', AllowedWriteAction: 'none',
    ScheduledAction: 'apply', CodeBucket: 'same-bucket', CodeKey: 'same-key', CodeObjectVersion: 'same-version',
    AdminSecretArn: 'same-secret-locator', WorkerTimeoutSeconds: '120' };
  const calls = [], waits = [], ddbCalls = [];
  const faults = {};
  const aws = async (service, command, input) => {
    calls.push({ service, command, input });
    if (command === 'describe-stacks') return { Stacks: [{ StackId: 'same-stack-id', StackStatus: faults.status ?? 'UPDATE_COMPLETE',
      Parameters: Object.entries(parameters).map(([ParameterKey, ParameterValue]) => ({ ParameterKey, ParameterValue })),
      Outputs: Object.entries(resources).map(([OutputKey, OutputValue]) => ({ OutputKey, OutputValue })) }] };
    if (command === 'get-function-configuration') return { FunctionArn: 'same-function-arn', State: 'Active',
      LastUpdateStatus: 'Successful', LastModified: parameters.ControlSha256, Timeout: 120, CodeSha256: faults.codeSha ?? 'same-code',
      Environment: { Variables: { STATE_TABLE: resources.StateTableName, DEPLOYMENT_ID: parameters.DeploymentId,
        CONTROL_SHA256: parameters.ControlSha256, APPLY_ENABLED: faults.liveWrites ?? parameters.ApplyEnabled,
        ALLOWED_WRITE_ACTION: parameters.AllowedWriteAction } } };
    if (command === 'get-event-source-mapping') return { State: faults.mapping ?? 'Disabled', FunctionArn: 'same-function-arn' };
    if (command === 'get-schedule') return { State: faults.schedule ?? 'DISABLED', Target: { Arn: 'same-function-arn' } };
    if (command === 'update-stack') {
      for (const row of input.Parameters) if (!row.UsePreviousValue) parameters[row.ParameterKey] = row.ParameterValue;
      if (faults.updateOnce) { faults.updateOnce = false; throw new Error('unknown result after acceptance'); }
      return { StackId: 'same-stack-id' };
    }
    throw new Error('Unexpected fake AWS operation');
  };
  const sendDynamo = async (operation, input) => {
    ddbCalls.push({ operation, input });
    if (operation === 'GetItem') return { Item: items.get(input.Key.SK.S) };
    assert.equal(operation, 'PutItem');
    const key = input.Item.SK.S, previous = items.get(key);
    const expected = input.ExpressionAttributeValues?.[':previous']?.S ?? input.ExpressionAttributeValues?.[':same']?.S;
    if (previous && (!expected || previous.document.S !== expected)) throw new Error('conditional failure');
    items.set(key, structuredClone(input.Item));
    if (key === 'REVIEWED' && faults.uploadOnce) { faults.uploadOnce = false; throw new Error('unknown result after manifest write'); }
    return {};
  };
  const store = { getControl: async () => items.get('REVIEWED')?.document.S,
    getControlPart: async hash => items.get(`PART#${hash}`)?.document.S,
    getState: async key => states.get(key) };
  const options = { stackName: 'same-stack', previousConfig, previousEnrollment, period: config.period, directory,
    aws, store, api: {}, capture: async () => ({ config, enrollment, hash: enrollmentHash(enrollment) }),
    clock: () => now, sleep: async ms => { waits.push(ms); now = new Date(now.getTime() + ms); }, sendDynamo };
  const prepare = () => prepareRenewal(options);
  async function approve() {
    const path = join(directory, 'enrollment.json');
    const value = JSON.parse(await readFile(path, 'utf8'));
    await writeFile(path, JSON.stringify(approveEnrollment(value, enrollmentHash(value), now.toISOString())));
  }
  return { options, prepare, approve, parameters, resources, items, states, calls, waits, ddbCalls, faults, directory };
}

test('renewal preparation preserves the existing stack and writes only a new private review directory', async t => {
  const h = await fixture(t); const result = await h.prepare();
  assert.equal(result.prepared, true); assert.equal(result.capWrites, 0);
  assert.equal(JSON.parse(await readFile(join(h.directory, 'config.json'), 'utf8')).liveWrites, false);
  const enrollment = JSON.parse(await readFile(join(h.directory, 'enrollment.json'), 'utf8'));
  assert.equal(enrollment.approval, undefined); assert.equal(enrollmentHash(enrollment), result.hash);
  assert.ok(h.calls.every(call => call.command.startsWith('get-') || call.command === 'describe-stacks'));
  assert.equal(h.ddbCalls.length, 0);
  const count = h.calls.length;
  await assert.rejects(h.prepare(), /RENEWAL_DIRECTORY_EXISTS/); assert.equal(h.calls.length, count);
});

test('AWS preparation runs real captureRenewal after draining and carries the original settings without writes', async t => {
  const h = await fixture(t);
  const config = { ...h.options.previousConfig, period: h.options.period,
    policy: { ...h.options.previousConfig.policy, anchor: h.options.period.start } };
  const api = createSyntheticApi({ config, clock: () => h.options.clock().toISOString() });
  const result = await prepareRenewal({ ...h.options, api, capture: undefined });
  const enrollment = JSON.parse(await readFile(join(h.directory, 'enrollment.json'), 'utf8'));
  assert.equal(result.prepared, true); assert.equal(enrollment.capturedAt, '2030-05-02T00:02:00.000Z');
  for (const member of enrollment.members) {
    const previous = h.states.get(`${config.workspaceId}:${member.userId}`);
    assert.deepEqual(member.renewal.original, previous.original);
    assert.equal(member.renewal.priorStateDigest, digest(previous));
  }
  assert.equal(api.writes.length, 0); assert.equal(h.ddbCalls.length, 0);
});

test('renewal activation drains old workers, archives controls, and updates only same-stack parameters with every gate off', async t => {
  const h = await fixture(t); await h.prepare(); await h.approve();
  const before = structuredClone(h.parameters); const result = await activateRenewal(h.options);
  assert.equal(result.activated, true); assert.equal(result.writes, false);
  assert.equal(h.waits.reduce((sum, wait) => sum + wait, 0), 120_000);
  const updates = h.calls.filter(call => call.command === 'update-stack'); assert.equal(updates.length, 1);
  const update = updates[0].input;
  assert.equal(update.StackName, 'same-stack-id'); assert.equal(update.UsePreviousTemplate, true);
  for (const key of ['CodeBucket', 'CodeKey', 'CodeObjectVersion', 'AdminSecretArn', 'WorkerTimeoutSeconds', 'DeploymentId']) {
    assert.deepEqual(update.Parameters.find(row => row.ParameterKey === key), { ParameterKey: key, UsePreviousValue: true });
    assert.equal(h.parameters[key], before[key]);
  }
  for (const [key, expected] of Object.entries({ ScheduleState: 'DISABLED', WorkProcessingEnabled: 'false', ApplyEnabled: 'false', AllowedWriteAction: 'none', ScheduledAction: 'preview' })) {
    assert.equal(h.parameters[key], expected);
  }
  assert.notEqual(h.parameters.ControlSha256, before.ControlSha256);
  assert.equal(h.items.get(`MANIFEST#${before.ControlSha256}`).document.S.length > 0, true);
  assert.equal(JSON.parse(await readFile(join(h.directory, 'activation.json'), 'utf8')).stage, 'activated');
});

test('activation rejects live, changing, replaced or unreviewed inputs before uploading controls', async t => {
  for (const fault of ['schedule', 'mapping', 'liveWrites', 'codeSha', 'unapproved', 'state', 'halted', 'pending']) {
    const h = await fixture(t); await h.prepare();
    if (fault !== 'unapproved') await h.approve();
    if (fault === 'schedule') h.faults.schedule = 'ENABLED';
    if (fault === 'mapping') h.faults.mapping = 'Enabled';
    if (fault === 'liveWrites') h.faults.liveWrites = 'true';
    if (fault === 'codeSha') h.faults.codeSha = 'different-code';
    const state = h.states.values().next().value;
    if (fault === 'state') state.lastUsage = '999';
    if (fault === 'halted') state.halted = true;
    if (fault === 'pending') state.pending = { kind: 'cap', amount: '500' };
    await assert.rejects(activateRenewal(h.options));
    assert.equal(h.ddbCalls.length, 0); assert.equal(h.calls.filter(call => call.command === 'update-stack').length, 0);
  }
});

test('an uncertain control upload resumes idempotently with the exact reviewed files', async t => {
  const h = await fixture(t); await h.prepare(); await h.approve(); h.faults.uploadOnce = true;
  await assert.rejects(activateRenewal(h.options));
  assert.equal(h.calls.filter(call => call.command === 'update-stack').length, 0);
  const result = await activateRenewal(h.options);
  assert.equal(result.activated, true); assert.equal(h.calls.filter(call => call.command === 'update-stack').length, 1);
});

test('an orphaned manifest after review expiry reconciles the stopped stack without reuploading, then permits fresh capture', async t => {
  const h = await fixture(t); await h.prepare(); await h.approve(); h.faults.uploadOnce = true;
  await assert.rejects(activateRenewal(h.options));
  await h.options.sleep(16 * 60_000);
  const uploads = h.ddbCalls.length;
  const result = await activateRenewal(h.options);
  assert.equal(result.activated, true); assert.equal(result.reviewRequired, true); assert.equal(result.writes, false);
  assert.equal(h.ddbCalls.length, uploads, 'expired review never starts another upload');
  assert.equal(h.calls.filter(call => call.command === 'update-stack').length, 1);
  const config = { ...h.options.previousConfig, period: h.options.period,
    policy: { ...h.options.previousConfig.policy, anchor: h.options.period.start } };
  const api = createSyntheticApi({ config, clock: () => h.options.clock().toISOString() });
  const fresh = await prepareRenewal({ ...h.options, directory: join(h.directory, '..', 'fresh-after-reconcile'),
    api, capture: undefined });
  assert.equal(fresh.prepared, true); assert.equal(api.writes.length, 0);
});

test('expired orphan recovery rejects tampered immutable parts and never submits a stack update', async t => {
  const h = await fixture(t); await h.prepare(); await h.approve(); h.faults.uploadOnce = true;
  await assert.rejects(activateRenewal(h.options)); await h.options.sleep(16 * 60_000);
  const manifest = JSON.parse(h.items.get('REVIEWED').document.S);
  h.items.get(`PART#${manifest.first}`).document.S = 'tampered';
  const uploads = h.ddbCalls.length;
  await assert.rejects(activateRenewal(h.options), /CONTROL_PART_HASH_MISMATCH/);
  assert.equal(h.ddbCalls.length, uploads); assert.equal(h.calls.filter(call => call.command === 'update-stack').length, 0);
});

test('an accepted stack update with an unknown response resumes by readback without submitting another update', async t => {
  const h = await fixture(t); await h.prepare(); await h.approve(); h.faults.updateOnce = true;
  await assert.rejects(activateRenewal(h.options), /RENEWAL_UPDATE_UNCONFIRMED_RERUN_ACTIVATE/);
  const result = await activateRenewal(h.options);
  assert.equal(result.activated, true); assert.equal(h.calls.filter(call => call.command === 'update-stack').length, 1);
});

test('an accepted update can be reconciled after review expires without any further upload or AWS mutation', async t => {
  const h = await fixture(t); await h.prepare(); await h.approve(); h.faults.updateOnce = true;
  await assert.rejects(activateRenewal(h.options), /RENEWAL_UPDATE_UNCONFIRMED_RERUN_ACTIVATE/);
  await h.options.sleep(16 * 60_000);
  const uploads = h.ddbCalls.length;
  const result = await activateRenewal(h.options);
  assert.equal(result.activated, true); assert.equal(result.reviewRequired, true); assert.equal(result.writes, false);
  assert.equal(h.ddbCalls.length, uploads); assert.equal(h.calls.filter(call => call.command === 'update-stack').length, 1);
});

test('a changed stack during draining and edited renewal files stop activation', async t => {
  const h = await fixture(t); await h.prepare(); await h.approve();
  h.parameters.WorkerTimeoutSeconds = '300';
  const sleep = h.options.sleep;
  await assert.rejects(activateRenewal({ ...h.options, sleep: async ms => { await sleep(ms); h.parameters.WorkerTimeoutSeconds = '600'; } }),
    /RENEWAL_STACK_CHANGED_DURING_DRAIN/);
  assert.equal(h.ddbCalls.length, 0);
  const path = join(h.directory, 'config.json');
  const config = JSON.parse(await readFile(path, 'utf8')); config.policy.ceiling = '999'; await writeFile(path, JSON.stringify(config));
  await assert.rejects(activateRenewal(h.options), /RENEWAL_FILES_CHANGED/);
});

test('review expiry prevents uploading controls and an unchanged preparation avoids a second drain', async t => {
  const h = await fixture(t); await h.prepare(); await h.approve();
  assert.equal(h.waits.reduce((total, value) => total + value, 0), 120_000);
  await h.options.sleep(16 * 60_000);
  await assert.rejects(activateRenewal(h.options), /RENEWAL_REVIEW_EXPIRED_RECAPTURE/);
  assert.equal(h.ddbCalls.length, 0);
});

test('a wholly unstarted installed renewal can be recaptured without changing the period or policy', async t => {
  const h = await fixture(t); await h.prepare(); await h.approve(); await activateRenewal(h.options);
  const captured = await h.options.capture();
  const recapture = { ...h.options, directory: join(h.directory, '..', 'refreshed'),
    period: { ...h.options.period, evidence: 'Fresh independently verified period evidence.' } };
  await h.options.sleep(16 * 60_000);
  recapture.capture = async ({ period, clock }) => {
    const config = { ...captured.config, period };
    const enrollment = structuredClone(captured.enrollment);
    enrollment.configDigest = configDigest(config); enrollment.capturedAt = clock(); enrollment.completedAt = clock();
    return { config, enrollment, hash: enrollmentHash(enrollment) };
  };
  const result = await prepareRenewal(recapture); assert.equal(result.prepared, true);
  const journal = JSON.parse(await readFile(join(recapture.directory, 'activation.json'), 'utf8'));
  assert.equal(journal.previousControlSha256, h.parameters.ControlSha256);
  const changed = { ...recapture, directory: join(h.directory, '..', 'changed'),
    previousConfig: { ...h.options.previousConfig, policy: { ...h.options.previousConfig.policy, ceiling: '999' } } };
  await assert.rejects(prepareRenewal(changed), /RENEWAL_PREVIOUS_CONTROL_MISMATCH/);
});
