import test from 'node:test';
import assert from 'node:assert/strict';
import { createDynamoStore, hash } from '../aws/store.mjs';

function harness() {
  let now = new Date('2030-04-02T00:00:00Z');
  const items = new Map();
  const calls = [];
  const key = item => `${item.PK}|${item.SK}`;
  const conditionalFailure = () => Object.assign(new Error('Condition failed'),
    { name: 'ConditionalCheckFailedException' });
  async function send(operation, input) {
    calls.push({ operation, input });
    if (operation === 'Get') return { Item: items.get(key(input.Key)) };
    if (operation === 'Put') {
      const previous = items.get(key(input.Item));
      if (previous && (input.Item.PK.startsWith('RECEIPT#') ||
          previous.leaseExpiresAt > input.ExpressionAttributeValues[':now'])) throw conditionalFailure();
      items.set(key(input.Item), structuredClone(input.Item));
    } else if (operation === 'TransactWrite') {
      const check = input.TransactItems[0].ConditionCheck;
      const current = items.get(key(check.Key));
      if (current?.leaseOwner !== check.ExpressionAttributeValues[':owner'] ||
          current.leaseExpiresAt <= check.ExpressionAttributeValues[':now']) throw conditionalFailure();
      const puts = input.TransactItems.slice(1).map(item => item.Put);
      for (const put of puts) {
        const previous = items.get(key(put.Item));
        if (put.ConditionExpression === 'attribute_not_exists(PK)' && previous) throw conditionalFailure();
        if (put.ConditionExpression === '#payload = :previous' &&
          JSON.stringify(previous?.payload) !== JSON.stringify(put.ExpressionAttributeValues[':previous'])) throw conditionalFailure();
      }
      for (const put of puts) items.set(key(put.Item), structuredClone(put.Item));
    } else if (operation === 'Delete') {
      const current = items.get(key(input.Key));
      if (current?.leaseOwner !== input.ExpressionAttributeValues[':owner']) throw conditionalFailure();
      items.delete(key(input.Key));
    } else throw new Error('Unsupported fake operation');
    return {};
  }
  const create = () => createDynamoStore({ send, tableName: 'synthetic-table', deploymentId: 'synthetic-demo',
    clock: () => now });
  return { items, calls, create, advance(seconds) { now = new Date(now.getTime() + seconds * 1000); } };
}

test('state writes require a lease and use a transaction fencing the owner and expiry', async () => {
  const h = harness(); const store = h.create();
  await assert.rejects(store.putState('workspace:user', {}), /LEASE_REQUIRED/);
  await store.withLock('workspace:user', async () => {
    await store.assertLock('workspace:user');
    await store.putState('workspace:user', { pending: { amount: '20' } });
    assert.deepEqual(await store.getState('workspace:user'), { pending: { amount: '20' } });
  });
  assert.equal([...h.items.values()].filter(i => i.PK.startsWith('LOCK#')).length, 0);
  const transaction = h.calls.find(c => c.operation === 'TransactWrite').input.TransactItems;
  assert.match(transaction[0].ConditionCheck.ConditionExpression, /leaseOwner.*leaseExpiresAt/);
  assert.equal(transaction[1].Put.Item.expiresAt, undefined, 'pending intents must not expire by TTL');
});

test('a second controller cannot enter an active user lease', async () => {
  const h = harness(); const a = h.create(); const b = h.create();
  await a.withLock('workspace:user', async () => {
    await assert.rejects(b.withLock('workspace:user', () => assert.fail()), /LEASE_BUSY/);
  });
});

test('an expired owner cannot write or delete the replacement lease', async () => {
  const h = harness(); const a = h.create(); const b = h.create();
  let releaseB;
  let bReady;
  const ready = new Promise(resolve => { bReady = resolve; });
  let replacement;
  await a.withLock('workspace:user', async () => {
    h.advance(180);
    replacement = b.withLock('workspace:user', async () => {
      bReady();
      await new Promise(resolve => { releaseB = resolve; });
      await b.putState('workspace:user', { pending: { amount: '30' } });
    });
    await ready;
    await assert.rejects(a.assertLock('workspace:user'), /LEASE_LOST/);
    await assert.rejects(a.putState('workspace:user', { stale: true }));
  });
  assert.equal([...h.items.values()].filter(i => i.PK.startsWith('LOCK#')).length, 1);
  releaseB(); await replacement;
  assert.deepEqual(await a.getState('workspace:user'), { pending: { amount: '30' } });
});

test('receipts append immutable entries and controls are consistently read', async () => {
  const h = harness(); const store = h.create();
  h.items.set('CONTROL#synthetic-demo|REVIEWED', { PK: 'CONTROL#synthetic-demo', SK: 'REVIEWED', document: '{"reviewed":true}' });
  assert.equal(await store.getControl(), '{"reviewed":true}');
  await store.putReceipt({ status: 'pending' });
  await store.putReceipt({ status: 'confirmed' });
  const receipts = [...h.items.values()].filter(i => i.PK.startsWith('RECEIPT#'));
  assert.equal(receipts.length, 2);
  assert.notEqual(receipts[0].SK, receipts[1].SK);
  assert.equal(h.calls[0].input.ConsistentRead, true);
  assert.equal(hash('workspace:user').length, 64);
});

test('a lease shorter than the Lambda timeout safety margin is rejected', () => {
  assert.throws(() => createDynamoStore({ send() {}, tableName: 'table', deploymentId: 'demo-one', leaseSeconds: 120 }),
    /INVALID_STORE_CONFIGURATION/);
});

test('period transition atomically archives exact prior state and preserves original under the same user lease', async () => {
  const h = harness(); const store = h.create(); const key = 'workspace:user';
  const original = { settings: { override: null, effective: { limit: '100' } } };
  const previous = { enrollmentHash: 'a'.repeat(64), original, lastSlot: 30, lastUsage: '77', pending: null };
  const next = { enrollmentHash: 'b'.repeat(64), original, pending: { kind: 'cap', amount: '10' } };
  await assert.rejects(store.transitionState(key, { previous, next }), /LEASE_REQUIRED/);
  await store.withLock(key, async () => {
    await store.putState(key, previous);
    await store.transitionState(key, { previous, next });
    assert.deepEqual(await store.getState(key), next);
    const archive = h.items.get(`STATE#${hash(key)}|ARCHIVE#${previous.enrollmentHash}`);
    assert.deepEqual(archive.payload, previous); assert.equal(archive.expiresAt, undefined);
    await assert.rejects(store.transitionState(key, { previous, next }));
    assert.deepEqual(await store.getState(key), next); assert.deepEqual(archive.payload, previous);
  });
  const transaction = h.calls.find(call => call.operation === 'TransactWrite' && call.input.TransactItems.length === 3).input.TransactItems;
  assert.equal(transaction[1].Put.ConditionExpression, '#payload = :previous');
  assert.equal(transaction[2].Put.ConditionExpression, 'attribute_not_exists(PK)');
});

test('changed state, expired lease and existing archive cannot partially transition a period', async () => {
  for (const conflict of ['state', 'lease', 'archive']) {
    const h = harness(); const store = h.create(); const key = 'workspace:user';
    const previous = { enrollmentHash: 'a'.repeat(64), pending: null };
    const next = { enrollmentHash: 'b'.repeat(64), pending: { amount: '10' } };
    await store.withLock(key, async () => {
      await store.putState(key, previous);
      if (conflict === 'state') await store.putState(key, { ...previous, pending: { amount: '20' } });
      if (conflict === 'lease') h.advance(180);
      const archiveKey = `STATE#${hash(key)}|ARCHIVE#${previous.enrollmentHash}`;
      if (conflict === 'archive') h.items.set(archiveKey, { payload: { retained: true } });
      const before = structuredClone([...h.items.entries()]);
      await assert.rejects(store.transitionState(key, { previous, next }));
      assert.deepEqual([...h.items.entries()], before);
    });
  }
});

test('member completion is a single conditional transaction and retains dedupe through the parent run TTL', async () => {
  const runId = 'a'.repeat(64), expiresAt = 1_909_411_200;
  const calls = [];
  const store = createDynamoStore({ tableName: 'synthetic-table', deploymentId: 'synthetic-demo', receiptRetentionDays: 7,
    clock: () => new Date('2030-04-02T00:00:00Z'),
    async send(operation, input) {
      calls.push({ operation, input });
      if (operation === 'Get') return { Item: { expiresAt } };
      return {};
    } });
  assert.equal(await store.completeMember(runId, 999, { ok: true, status: 'applied' }), true);
  const transaction = calls.find(call => call.operation === 'TransactWrite').input.TransactItems;
  assert.equal(transaction[0].Put.Item.SK, 'MEMBER#999');
  assert.equal(transaction[0].Put.Item.expiresAt, expiresAt);
  assert.equal(transaction[0].Put.ConditionExpression, 'attribute_not_exists(PK)');
  assert.equal(transaction[1].Update.Key.SK, 'PROGRESS');
  assert.match(transaction[1].Update.UpdateExpression, /ADD completed :one, succeeded :success, attention :attention/);
  assert.equal(transaction[1].Update.ExpressionAttributeValues[':success'], 1);
  await store.putRetry(runId, 999, '2030-04-03T00:00:00Z');
  assert.equal(calls.at(-1).input.Item.expiresAt, expiresAt);
});

test('an already committed member result makes a duplicate counter transaction a no-op', async () => {
  const store = createDynamoStore({ tableName: 'synthetic-table', deploymentId: 'synthetic-demo',
    async send(operation, input) {
      if (operation === 'TransactWrite') throw Object.assign(new Error('conditional transaction'), { name: 'TransactionCanceledException' });
      if (operation === 'Get') return { Item: input.Key.SK === 'PROGRESS' ? { expiresAt: 1_909_411_200 } : { ok: true } };
    } });
  assert.equal(await store.completeMember('a'.repeat(64), 0, { ok: true }), false);
});
