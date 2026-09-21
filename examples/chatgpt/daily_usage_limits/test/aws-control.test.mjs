import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { encodeControl, createControlLoader } from '../aws/control.mjs';
import { hash } from '../aws/store.mjs';
import { uploadControl } from '../aws/upload-control.mjs';
import { captureEnrollment, approveEnrollment } from '../src/enrollment.mjs';
import { exampleConfig, createSyntheticApi } from '../src/synthetic.mjs';

test('large Unicode control documents use small hash-chained items and one warm load', async () => {
  const config = { evidence: '界'.repeat(250_000), cohort: { userIds: Array.from({ length: 3000 }, (_, i) => `user-${i}`) } };
  const enrollment = { members: config.cohort.userIds.map(userId => ({ userId, before: { note: 'é'.repeat(100) } })) };
  const prepared = encodeControl(config, enrollment);
  assert.ok(prepared.parts.length > 5);
  assert.ok(prepared.parts.every(part => Buffer.byteLength(part.document) < 300_000));
  assert.ok(Buffer.byteLength(prepared.document) < 1000, 'manifest size does not grow with part count');
  const parts = new Map(prepared.parts.map(part => [part.hash, part.document])); let reads = 0;
  const load = createControlLoader({ controlSha256: prepared.hash, store: {
    async getControl() { reads++; return prepared.document; },
    async getControlPart(key) { reads++; return parts.get(key); },
  } });
  assert.deepEqual(await load(), { config, enrollment });
  assert.deepEqual(await load(), { config, enrollment });
  assert.equal(reads, prepared.parts.length + 1);
});

test('manifest hash, part hash, sequence, count, and overall size must agree', async () => {
  const prepared = encodeControl({ value: 'x'.repeat(300_000) }, { members: [{ userId: 'one' }] });
  const base = () => new Map(prepared.parts.map(part => [part.hash, part.document]));
  for (const modify of [
    parts => parts.set(prepared.parts[0].hash, 'tampered'),
    parts => parts.delete(prepared.parts[1].hash),
  ]) {
    const parts = base(); modify(parts);
    await assert.rejects(createControlLoader({ controlSha256: prepared.hash,
      store: { getControl: async () => prepared.document, getControlPart: async key => parts.get(key) } })(), /CONTROL_PART_HASH_MISMATCH/);
  }
  for (const patch of [{ parts: 1 }, { bytes: 1 }, { members: 2 }, { first: null }]) {
    const document = JSON.stringify({ ...JSON.parse(prepared.document), ...patch });
    const parts = base();
    await assert.rejects(createControlLoader({ controlSha256: hash(document),
      store: { getControl: async () => document, getControlPart: async key => parts.get(key) } })());
  }
});

async function uploadFixture(t) {
  const now = '2030-04-02T00:00:00Z';
  const config = exampleConfig({ now });
  const captured = await captureEnrollment({ config, api: createSyntheticApi({ config, clock: () => now }), now });
  const enrollment = approveEnrollment(captured.enrollment, captured.hash, now);
  const prepared = encodeControl(config, enrollment);
  const directory = mkdtempSync(join(tmpdir(), 'cookbook controls '));
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  function item(key, document) { return { PK: { S: 'CONTROL#synthetic-demo' }, SK: { S: key }, document: { S: document } }; }
  writeFileSync(join(directory, 'manifest.json'), JSON.stringify(item('REVIEWED', prepared.document)));
  for (const part of prepared.parts) writeFileSync(join(directory, `part-${part.index}.json`), JSON.stringify(item(`PART#${part.hash}`, part.document)));
  const items = new Map(), calls = [];
  async function send(operation, input) {
    calls.push({ operation, input });
    if (operation === 'GetItem') return { Item: items.get(input.Key.SK.S) };
    const key = input.Item.SK.S, previous = items.get(key);
    const values = input.ExpressionAttributeValues;
    const expected = values?.[':previous']?.S ?? values?.[':same']?.S;
    if (previous && (!expected || previous.document.S !== expected)) throw Object.assign(new Error('conditional failure'), { name: 'ConditionalCheckFailedException' });
    items.set(key, structuredClone(input.Item)); return {};
  }
  return { directory, tableName: 'synthetic-table', controlSha256: prepared.hash, now, send, items, calls, prepared };
}

test('control upload is idempotent, checks approval before AWS, and installs manifest last', async t => {
  const h = await uploadFixture(t);
  await uploadControl(h);
  assert.equal(h.calls.at(-1).input.Item.SK.S, 'REVIEWED');
  assert.equal(h.calls.at(-1).input.ConditionExpression, 'attribute_not_exists(PK)');
  assert.ok(h.calls.slice(1, -1).every(call => call.input.ConditionExpression.includes(':same')));
  await uploadControl(h);
  assert.equal(h.calls.at(-1).input.ExpressionAttributeValues[':previous'].S, h.prepared.document);
  const partPath = join(h.directory, 'part-0.json');
  const item = JSON.parse(readFileSync(partPath, 'utf8')); item.document.S = 'unreviewed';
  writeFileSync(partPath, JSON.stringify(item)); const previousCalls = h.calls.length;
  await assert.rejects(uploadControl(h)); assert.equal(h.calls.length, previousCalls);
});

test('control replacement requires the previous reviewed hash and uses compare-and-swap', async t => {
  const h = await uploadFixture(t);
  const old = JSON.stringify({ old: true });
  h.items.set('REVIEWED', { document: { S: old } });
  await assert.rejects(uploadControl(h), /EXISTING_CONTROL_REQUIRES_PREVIOUS_SHA256/);
  assert.equal(h.calls.length, 1);
  await uploadControl({ ...h, previousSha256: hash(old) });
  assert.equal(h.calls.at(-1).input.ExpressionAttributeValues[':previous'].S, old);
});

test('unreferenced prepared items are rejected before upload', async t => {
  const h = await uploadFixture(t);
  const document = JSON.stringify({ data: 'private unrelated file' });
  writeFileSync(join(h.directory, 'part-99.json'), JSON.stringify({ PK: { S: 'CONTROL#synthetic-demo' }, SK: { S: `PART#${hash(document)}` }, document: { S: document } }));
  await assert.rejects(uploadControl(h), /UNEXPECTED_PREPARED_ITEMS/);
  assert.equal(h.calls.length, 0);
});
