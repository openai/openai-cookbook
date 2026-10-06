import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { request as httpRequest } from 'node:http';
import { createApp } from '../server/index.mjs';

const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const result = { output: [{ type: 'function_call', name: 'control_app', arguments: JSON.stringify({ type: 'click', target: 'sign-in' }) }] };
const offer = { sdp: 'v=0\r\na=offer' };
const plan = session => ({
  sessionId: session.session.id, controlToken: session.controlToken, requestId: 'first-action',
  conversation: [{ role: 'user', text: 'Sign in as Leo' }],
  surface: { title: 'Little Worlds', url: '/', context: 'Welcome, signed out.', text: 'Pick a person', controls: [{ id: 'sign-in', role: 'button', label: 'Leo' }] }, history: [],
});
async function fixture(t, respond = async () => result) {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-voice-'));
  let sessions = 0, plans = 0;
  const instance = await createApp({
    dataDir, apiKey: 'test-server-key', adapter: { keyAvailable: false, respond: async () => { throw Error('No builder calls expected'); } },
    voiceFetchImpl: async () => Response.json({ session: { id: `live_http_${++sessions}` }, transport: { type: 'webrtc', sdp: 'v=0\r\na=answer' } }),
    voiceAdapter: { keyAvailable: true, respond: async args => { plans++; return respond(args); } },
  });
  const server = instance.app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const request = (path, { json, headers = {}, signal } = {}) => fetch(base + path, {
    method: json === undefined ? 'GET' : 'POST', signal,
    headers: { Origin: base, ...(json === undefined ? {} : { 'Content-Type': 'application/json' }), ...headers },
    ...(json === undefined ? {} : { body: JSON.stringify(json) }),
  });
  t.after(async () => { server.closeAllConnections(); await new Promise(done => server.close(done)); await instance.close(); await rm(dataDir, { recursive: true, force: true }); });
  return { request, base, instance, calls: () => ({ sessions, plans }) };
}

test('welcome voice works without simulated login but cannot bypass application authorization', async t => {
  const { request, calls } = await fixture(t);
  const status = await request('/api/voice/status');
  assert.equal(status.status, 200);
  assert.equal((await status.json()).available, true);
  assert.equal((await request('/api/voice/status', { headers: { Origin: '', 'Sec-Fetch-Site': 'same-origin' } })).status, 200);
  const response = await request('/api/voice/session', { json: offer });
  assert.equal(response.status, 201);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  const session = await response.json();
  const action = await request('/api/voice/plan', { json: plan(session) });
  assert.equal(action.status, 200);
  assert.deepEqual(await action.json(), { action: { type: 'click', target: 'sign-in' } });
  assert.equal((await request('/api/spaces/mira/turn', { json: { message: 'Change this space' }, headers: { Authorization: `Bearer ${session.controlToken}` } })).status, 401);
  assert.equal((await request('/api/voice/end', { json: { sessionId: session.session.id, controlToken: session.controlToken } })).status, 200);
  assert.equal((await request('/api/voice/plan', { json: plan(session) })).status, 403);
  assert.deepEqual(calls(), { sessions: 1, plans: 1 });
});

test('voice enforces exact local origin and host before creating paid sessions', async t => {
  const { request, base, calls } = await fixture(t);
  for (const headers of [
    { Origin: 'https://example.com' }, { Origin: 'null' }, { Origin: '' },
    { Origin: 'http://127.0.0.1:1' },
    { Origin: base, 'Sec-Fetch-Site': 'cross-site' },
  ]) assert.equal((await request('/api/voice/session', { json: offer, headers })).status, 403, JSON.stringify(headers));
  const deniedHost = await new Promise((resolve, reject) => {
    const req = httpRequest(base + '/api/voice/session', { method: 'POST', headers: { Origin: base, Host: 'evil.example.com', 'Content-Type': 'application/json' } }, response => {
      response.resume(); response.on('end', () => resolve(response.statusCode));
    });
    req.on('error', reject); req.end(JSON.stringify(offer));
  });
  assert.equal(deniedHost, 403);
  assert.deepEqual(calls(), { sessions: 0, plans: 0 });
  const permitted = await request('/api/voice/session', { json: offer, headers: { Origin: '', Referer: base + '/welcome' } });
  assert.equal(permitted.status, 201);
});

test('voice rejects content types, extra fields, and oversized snapshots before model work', async t => {
  const { request, calls } = await fixture(t);
  assert.equal((await request('/api/voice/session', { json: offer, headers: { 'Content-Type': 'text/plain' } })).status, 415);
  assert.equal((await request('/api/voice/session', { json: { ...offer, model: 'injected-model' } })).status, 400);
  assert.equal((await request('/api/voice/session', { json: { sdp: 'x'.repeat(200_000) } })).status, 413);
  const session = await (await request('/api/voice/session', { json: offer })).json();
  assert.equal((await request('/api/voice/plan', { json: { ...plan(session), tools: [{ name: 'execute' }] } })).status, 400);
  assert.deepEqual(calls(), { sessions: 1, plans: 0 });
});

test('disconnecting the browser aborts pending voice work and allows the next action', { timeout: 10_000 }, async t => {
  const began = deferred(), stopped = deferred(); let first = true;
  const { request } = await fixture(t, async ({ signal }) => {
    if (!first) return result;
    first = false;
    return new Promise((_, reject) => { signal.addEventListener('abort', () => { stopped.resolve(); reject(signal.reason); }, { once: true }); began.resolve(); });
  });
  const session = await (await request('/api/voice/session', { json: offer })).json();
  const controller = new AbortController();
  const pending = request('/api/voice/plan', { json: plan(session), signal: controller.signal }).catch(error => error);
  await began.promise; controller.abort(); await stopped.promise; await pending;
  const next = await request('/api/voice/plan', { json: { ...plan(session), requestId: 'second-action' } });
  assert.equal(next.status, 200);
});
