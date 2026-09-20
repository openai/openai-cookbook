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
      const put = input.TransactItems[1].Put;
      items.set(key(put.Item), structuredClone(put.Item));
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
