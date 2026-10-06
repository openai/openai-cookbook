import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { setTimeout as delay } from 'node:timers/promises';

// Explicit opt-in: this runs two real builders and incurs API usage.
if (process.argv.length !== 3 || process.argv[2] !== '--confirm-api-usage') {
  console.error('Usage: node scripts/smoke-live.mjs --confirm-api-usage\nRuns real Ultrafast and standard builds in disposable storage. Requires OPENAI_API_KEY.');
  process.exit(2);
}

await import('../server/environment.mjs');
if (!process.env.OPENAI_API_KEY?.trim()) {
  console.error('Set OPENAI_API_KEY before running the live smoke test.');
  process.exit(2);
}
const { createApp } = await import('../server/index.mjs');
const { publicError } = await import('../server/responses.mjs');
const check = (condition, message) => { if (!condition) throw new Error(message); };
const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-live-'));
const streamAbort = new AbortController();
let instance, server, base, streamTask, streamError, streamEnded = false;
const completedTurns = new Set();
let eventCount = 0;

async function start() {
  instance = await createApp({ dataDir, generateIcons: false });
  server = instance.app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  base = `http://127.0.0.1:${server.address().port}`;
}
async function stop() {
  streamAbort.abort();
  if (server) {
    const closed = new Promise(resolve => server.close(resolve));
    server.closeAllConnections();
    await closed;
    server = undefined;
  }
  if (instance) { await instance.close(); instance = undefined; }
}
async function request(path, token, body, expected = 200) {
  const response = await fetch(`${base}${path}`, {
    method: body === undefined ? 'GET' : 'POST', signal: AbortSignal.timeout(15_000),
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(body === undefined ? {} : { 'Content-Type': 'application/json', Origin: base }) },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  check(response.status === expected, `Unexpected HTTP ${response.status} from ${path}.`);
  return response.json();
}
async function readEvents(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) { streamEnded = true; return; }
      buffer += decoder.decode(value, { stream: true });
      check(buffer.length < 4_000_000, 'Event stream exceeded its buffer limit.');
      let boundary;
      while ((boundary = buffer.indexOf('\n\n')) !== -1) {
        const block = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 2);
        const data = block.split('\n').filter(line => line.startsWith('data:')).map(line => line.slice(5)).join('\n');
        if (!data) continue;
        const event = JSON.parse(data);
        eventCount++;
        if (event.type === 'turn.completed') completedTurns.add(event.turnId);
      }
    }
  } finally { reader.releaseLock(); }
}

try {
  await start();
  const owner = await request('/api/auth/sign-in', null, { userId: 'mira' });
  const space = `/api/spaces/${owner.ownSpaceId}`;
  const stream = await fetch(`${base}${space}/events`, {
    headers: { Authorization: `Bearer ${owner.token}` }, signal: streamAbort.signal,
  });
  check(stream.ok && stream.headers.get('content-type')?.includes('text/event-stream'), 'Owner event stream did not open.');
  streamTask = readEvents(stream).catch(error => { streamError = error; });
  const message = 'Build a small responsive Star Counter with a heading, a star illustration, a visible count and one Add star button. Implement exactly action.type="increment". Store each participant counter at state.extras.counts[actor.id]={actorId:actor.id,count:<integer>}, starting at zero and increasing by one per action. Never change another participant counter. Display the current participant count. Include meaningful tests for incrementing twice, isolation between actors, invalid action rejection and rendering. Keep the implementation concise; no external resources, services or games.';
  const submitted = await request(`${space}/turn`, owner.token, { message, compare: true, appTheme: 'light' }, 202);
  check(submitted.comparisonId && submitted.turnId, 'Builder did not start a comparison.');
  const deadline = Date.now() + 300_000;
  let comparison;
  while (Date.now() < deadline) {
    check(!streamError && !streamEnded, 'Owner event stream ended before sign-out.');
    ({ comparison } = await request(`${space}/comparison`, owner.token));
    check(comparison?.id === submitted.comparisonId, 'Comparison identity changed.');
    for (const lane of ['ultrafast', 'standard']) {
      check(!['failed', 'cancelled'].includes(comparison[lane].status), `${lane} builder did not complete successfully.`);
    }
    if (['ultrafast', 'standard'].every(lane => comparison[lane].status === 'completed')) break;
    await delay(750);
  }
  for (const [lane, tier] of [['ultrafast', 'ultrafast'], ['standard', 'default']]) {
    check(comparison[lane].status === 'completed', `${lane} builder exceeded five minutes.`);
    check(comparison[lane].servedTier === tier, `${lane} was not served by the requested tier.`);
    check(comparison[lane].html?.trim(), `${lane} returned an empty preview.`);
  }
  const published = await request(space, owner.token);
  check(published.html?.trim() && published.revision.checks?.length && published.revision.checks.every(item => item.ok === true), 'Published world did not pass verification.');
  const revisionId = published.revision.id;
  await request(`${space}/action`, owner.token, { action: { type: 'increment' }, revisionId });
  const visitor = await request('/api/auth/sign-in', null, { userId: 'leo' });
  await request(`${space}/turn`, visitor.token, { message: 'Change this world' }, 403);
  const visible = await request(space, visitor.token);
  check(visible.html?.trim() && visible.permissions.canEdit === false, 'Visitor cannot view the published world.');
  check(!('source' in visible.revision) && !('tests' in visible.revision) && !('turns' in visible.session), 'Visitor received private builder data.');
  for (let i = 0; i < 2; i++) await request(`${space}/action`, visitor.token, { action: { type: 'increment' }, revisionId });
  const counts = (await request(space, visitor.token)).state.extras.counts;
  check(counts.mira?.count === 1 && counts.mira.actorId === 'mira' && counts.leo?.count === 2 && counts.leo.actorId === 'leo', 'Counter actions did not preserve participant ownership.');
  await request(`${space}/comparison/${submitted.comparisonId}/finish`, owner.token, {});
  await request('/api/auth/sign-out', owner.token, {});
  await Promise.race([streamTask, delay(5000).then(() => { throw new Error('Event stream did not close after sign-out.'); })]);
  check(!streamError && streamEnded && completedTurns.has(submitted.turnId), 'Owner event stream missed completion or failed during sign-out.');
  await stop();
  await start();
  const restoredOwner = await request('/api/auth/sign-in', null, { userId: 'mira' });
  const restored = await request(space, restoredOwner.token);
  check(restored.revision.id === revisionId && restored.state.extras.counts.mira?.count === 1 && restored.state.extras.counts.leo?.count === 2, 'Published world or counters did not persist after restart.');
  console.log(JSON.stringify({ ok: true, checks: published.revision.checks.length, eventCount, visitorIsolation: true, persistence: true,
    lanes: Object.fromEntries(['ultrafast', 'standard'].map(lane => [lane, { status: comparison[lane].status,
      servedTier: comparison[lane].servedTier, outputTokens: comparison[lane].outputTokens }])) }, null, 2));
} catch (error) {
  console.error(`Live smoke test failed: ${publicError(error)}`);
  process.exitCode = 1;
} finally {
  try { await stop(); } finally { await rm(dataDir, { recursive: true, force: true }); }
}
