import { createHash, randomUUID } from 'node:crypto';

export const hash = value => createHash('sha256').update(value).digest('hex');

/** A single table holds reviewed controls, fenced intents, and append-only receipts. */
export function createDynamoStore({ send, tableName, deploymentId,
  clock = () => new Date(), leaseSeconds = 180, receiptRetentionDays = 30 }) {
  if (!tableName || !/^[a-z][a-z0-9-]{2,39}$/.test(deploymentId ?? '') ||
      !Number.isInteger(leaseSeconds) || leaseSeconds < 180 ||
      !Number.isInteger(receiptRetentionDays) || receiptRetentionDays < 1 || receiptRetentionDays > 90) {
    throw new Error('INVALID_STORE_CONFIGURATION');
  }
  const locks = new Map();
  const seconds = () => Math.floor(clock().getTime() / 1000);
  // Do not include period or deployment in a lock key: writers sharing a table must serialize a user.
  const stateKey = key => ({ PK: `STATE#${hash(key)}`, SK: 'CURRENT' });
  const lockKey = key => ({ PK: `LOCK#${hash(key)}`, SK: 'LEASE' });
  const get = async Key => (await send('Get', { TableName: tableName, Key, ConsistentRead: true })).Item;
  const condition = key => {
    const owner = locks.get(key);
    if (!owner) throw new Error('LEASE_REQUIRED');
    return { TableName: tableName, Key: lockKey(key),
      ConditionExpression: 'leaseOwner = :owner AND leaseExpiresAt > :now',
      ExpressionAttributeValues: { ':owner': owner, ':now': seconds() } };
  };
  return {
    async getControl() {
      return (await get({ PK: `CONTROL#${deploymentId}`, SK: 'REVIEWED' }))?.document;
    },
    async getState(key) { return (await get(stateKey(key)))?.payload; },
    async assertLock(key) {
      const expected = condition(key);
      const current = await get(lockKey(key));
      if (current?.leaseOwner !== expected.ExpressionAttributeValues[':owner'] ||
          !(current.leaseExpiresAt > seconds())) throw new Error('LEASE_LOST');
    },
    async putState(key, payload) {
      await send('TransactWrite', { TransactItems: [
        { ConditionCheck: condition(key) },
        { Put: { TableName: tableName, Item: { ...stateKey(key), payload,
          updatedAt: clock().toISOString() } } },
      ] });
    },
    async putReceipt(receipt) {
      // UUID append keys prevent a duplicate invocation from erasing an earlier receipt.
      await send('Put', { TableName: tableName,
        Item: { PK: `RECEIPT#${deploymentId}`, SK: `${clock().toISOString()}#${randomUUID()}`,
          payload: receipt, expiresAt: seconds() + receiptRetentionDays * 86400 },
        ConditionExpression: 'attribute_not_exists(PK)' });
    },
    async withLock(key, fn) {
      if (locks.has(key)) throw new Error('REENTRANT_LOCK');
      const owner = randomUUID();
      try {
        await send('Put', { TableName: tableName,
          Item: { ...lockKey(key), leaseOwner: owner, leaseExpiresAt: seconds() + leaseSeconds },
          ConditionExpression: 'attribute_not_exists(PK) OR leaseExpiresAt <= :now',
          ExpressionAttributeValues: { ':now': seconds() } });
      } catch (error) {
        if (error.name === 'ConditionalCheckFailedException') throw new Error('LEASE_BUSY');
        throw error;
      }
      locks.set(key, owner);
      try { return await fn(); }
      finally {
        locks.delete(key);
        try {
          await send('Delete', { TableName: tableName, Key: lockKey(key),
            ConditionExpression: 'leaseOwner = :owner', ExpressionAttributeValues: { ':owner': owner } });
        } catch { /* A failed release safely leaves the lease until expiry. */ }
      }
    },
  };
}
