import { readFileSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { hash } from './store.mjs';
import { createControlLoader } from './control.mjs';
import { validateEnrollment } from '../src/enrollment.mjs';

export async function uploadControl({ directory, tableName, controlSha256, previousSha256, send,
  now = new Date().toISOString() }) {
  const manifest = JSON.parse(readFileSync(join(directory, 'manifest.json'), 'utf8'));
  const document = manifest.document?.S;
  if (typeof document !== 'string' || hash(document) !== controlSha256 || manifest.SK?.S !== 'REVIEWED' ||
      !/^CONTROL#[a-z][a-z0-9-]{2,39}$/.test(manifest.PK?.S ?? '')) throw new Error('INVALID_PREPARED_MANIFEST');
  const parts = readdirSync(directory).filter(name => /^part-\d+\.json$/.test(name)).sort().map(name =>
    JSON.parse(readFileSync(join(directory, name), 'utf8')));
  const byHash = new Map();
  for (const part of parts) {
    const content = part.document?.S;
    if (part.PK?.S !== manifest.PK.S || typeof content !== 'string' || part.SK?.S !== `PART#${hash(content)}` ||
        Buffer.byteLength(content) > 300_000) throw new Error('INVALID_PREPARED_PART');
    byHash.set(hash(content), content);
  }
  if (JSON.parse(document).parts !== parts.length || byHash.size !== parts.length ||
      [manifest, ...parts].some(item => Object.keys(item).sort().join(',') !== 'PK,SK,document')) throw new Error('UNEXPECTED_PREPARED_ITEMS');
  const { config, enrollment } = await createControlLoader({ controlSha256,
    store: { getControl: async () => document, getControlPart: async digest => byHash.get(digest) } })();
  validateEnrollment(config, enrollment, now, true);
  const Key = { PK: manifest.PK, SK: manifest.SK };
  const previous = (await send('GetItem', { TableName: tableName, Key, ConsistentRead: true })).Item?.document?.S;
  if (previous !== undefined && hash(previous) !== controlSha256 && hash(previous) !== previousSha256) {
    throw new Error('EXISTING_CONTROL_REQUIRES_PREVIOUS_SHA256');
  }
  if (previous === undefined && previousSha256 !== undefined) throw new Error('EXPECTED_PREVIOUS_CONTROL_MISSING');
  for (const Item of parts) {
    await send('PutItem', { TableName: tableName, Item,
      ConditionExpression: 'attribute_not_exists(PK) OR #document = :same',
      ExpressionAttributeNames: { '#document': 'document' }, ExpressionAttributeValues: { ':same': Item.document } });
  }
  await send('PutItem', { TableName: tableName, Item: manifest,
    ConditionExpression: previous === undefined ? 'attribute_not_exists(PK)' : '#document = :previous',
    ...(previous === undefined ? {} : { ExpressionAttributeNames: { '#document': 'document' },
      ExpressionAttributeValues: { ':previous': { S: previous } } }) });
  return { controlSha256, parts: parts.length, members: enrollment.members.length };
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const [directory, tableName, controlSha256, previousSha256] = process.argv.slice(2);
  if (!directory || !tableName || !/^[a-f0-9]{64}$/.test(controlSha256 ?? '') ||
      (previousSha256 && !/^[a-f0-9]{64}$/.test(previousSha256))) {
    throw new Error('Usage: node aws/upload-control.mjs DIRECTORY TABLE CONTROL_SHA256 [PREVIOUS_CONTROL_SHA256]');
  }
  const sdk = await import('@aws-sdk/client-dynamodb');
  const client = new sdk.DynamoDBClient({ maxAttempts: 3 });
  const result = await uploadControl({ directory, tableName, controlSha256, previousSha256,
    send: (operation, input) => client.send(new sdk[`${operation}Command`](input)) });
  console.log(JSON.stringify({ uploaded: true, ...result }));
}
