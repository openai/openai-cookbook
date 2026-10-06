import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { build } from 'esbuild';

const compiled = await build({
  entryPoints: [new URL('../src/api.ts', import.meta.url).pathname],
  bundle: true, write: false, format: 'iife', globalName: 'ApiModule',
});

function fixture(respond = () => ({ ok: true, status: 200, json: async () => ({ ok: true }) })) {
  const values = new Map([['living-spaces:demo-session', 'original-session']]);
  const requests = [];
  const context = vm.createContext({
    setTimeout, clearTimeout,
    sessionStorage: {
      getItem: key => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
      removeItem: key => values.delete(key),
    },
    fetch: async (path, init) => { requests.push({ path, init }); return respond(path, init); },
  });
  vm.runInContext(compiled.outputFiles[0].text, context);
  return { api: context.ApiModule, requests, values };
}

test('deferred resource requests keep their original session after an account change', async () => {
  const f = fixture();
  const resourceApi = f.api.captureSessionApi();
  f.api.setSessionToken('new-account-session');
  const checkpoint = { action: { type: 'save_game', game: { actorId: 'original-player', score: 42 } }, revisionId: 7 };
  await resourceApi('/api/spaces/original/game');
  await resourceApi('/api/spaces/original/action', checkpoint);
  await f.api.api('/api/auth/session');
  assert.equal(f.requests[0].init.headers.Authorization, 'Bearer original-session');
  assert.equal(f.requests[0].init.method, 'GET');
  assert.equal(f.requests[1].init.headers.Authorization, 'Bearer original-session');
  assert.equal(f.requests[1].init.method, 'POST');
  assert.equal(f.requests[1].init.headers['Content-Type'], 'application/json');
  assert.deepEqual(JSON.parse(f.requests[1].init.body), checkpoint);
  assert.equal(f.requests[2].init.headers.Authorization, 'Bearer new-account-session');
});

test('a pre-rename session migrates without signing the user out', async () => {
  const f = fixture();
  assert.equal(f.api.hasSessionToken(), true);
  await f.api.api('/api/auth/session');
  assert.equal(f.requests[0].init.headers.Authorization, 'Bearer original-session');
  assert.equal(f.values.get('little-worlds:demo-session'), 'original-session');
  assert.equal(f.values.has('living-spaces:demo-session'), false);
  f.api.setSessionToken(null);
  assert.equal(f.values.size, 0);
});

test('an anonymous resource never adopts a later signed-in session', async () => {
  const f = fixture();
  f.api.setSessionToken(null);
  const resourceApi = f.api.captureSessionApi();
  f.api.setSessionToken('new-account-session');
  await resourceApi('/api/spaces/original/game');
  assert.equal(f.requests[0].init.headers.Authorization, undefined);
});

test('revoked resource sessions fail without retrying as or clearing the new account', async () => {
  const f = fixture(() => ({ ok: false, status: 401, json: async () => ({ error: 'Session ended' }) }));
  const resourceApi = f.api.captureSessionApi();
  f.api.setSessionToken('new-account-session');
  await assert.rejects(resourceApi('/api/spaces/original/action', { revisionId: 7 }), error => {
    assert.equal(error instanceof f.api.ApiError, true);
    assert.equal(error.status, 401);
    assert.equal(error.message, 'Session ended');
    return true;
  });
  assert.equal(f.requests.length, 1);
  assert.equal(f.requests[0].init.headers.Authorization, 'Bearer original-session');
  assert.equal(f.values.get('little-worlds:demo-session'), 'new-account-session');
});
