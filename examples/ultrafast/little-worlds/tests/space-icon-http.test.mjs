import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { randomBytes } from 'node:crypto';
import { setTimeout as delay } from 'node:timers/promises';
import sharp from 'sharp';
import { createApp } from '../server/index.mjs';
import { normalizeSpaceIcon, SPACE_ICON_MAX_BYTES } from '../server/space-icon-image.mjs';

const source = `export const meta={title:'A botanical guestbook',subtitle:'A place for small green discoveries',accent:'#687957'};
export function render(state,actor){return '<p>A place to leave a thought.</p>'}
export function reduce(state,action,actor){
 if(action.type!=='leave'||typeof action.text!=='string'||!action.text.trim()||action.text.length>80)throw Error('Invalid thought');
 state.extras.guestbook=state.extras.guestbook||{};
 state.extras.guestbook[actor.id]={actorId:actor.id,text:action.text.trim()};return state;
}`;
const checks = `export function runTests(api){
 const actor={id:'test-fresh-person',name:'Test guest'};
 const next=api.reduce(api.initialState,{type:'leave',text:'A little wonder'},actor);
 let blocked=false;try{api.reduce(api.initialState,{type:'leave',text:''},actor)}catch{blocked=true}
 return [
 {name:'Visitors can leave a thought',ok:next.extras.guestbook[actor.id].text==='A little wonder'},
 {name:'Empty thoughts are refused',ok:blocked},
 {name:'Other records remain intact',ok:Object.entries(api.initialState.extras.guestbook||{}).every(([id,record])=>JSON.stringify(next.extras.guestbook[id])===JSON.stringify(record))},
 {name:'Current data renders',ok:api.render(api.initialState,actor).includes('thought')}
 ];
}`;
let callSequence = 0;
const builder = { keyAvailable: true, model: 'test-model', tier: 'ultrafast', respond: async () => ({
  output: [{ type: 'function_call', call_id: `icon-http-${++callSequence}`, name: 'apply_change', arguments: JSON.stringify({ source, tests: checks, summary: 'A botanical guestbook' }) }],
  metrics: { durationMs: 5, ttftMs: 1, outputTokens: 10, servedTier: 'ultrafast' },
}) };
const gate = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const picture = (background = '#829d6d') => sharp({ create: { width: 480, height: 320, channels: 3, background } }).png().toBuffer();
const upload = buffer => ({ dataUrl: `data:image/png;base64,${buffer.toString('base64')}` });

async function start(dataDir, options = {}) {
  const instance = await createApp({ dataDir, adapter: builder, ...options });
  const server = instance.app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const request = (path, { token, json, method, headers, ...rest } = {}) => fetch(`${base}${path}`, {
    method: method || (json === undefined ? 'GET' : 'POST'), ...rest,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(json === undefined ? {} : { 'Content-Type': 'application/json' }), ...headers },
    ...(json === undefined ? {} : { body: JSON.stringify(json) }),
  });
  const signIn = async userId => {
    const response = await request('/api/auth/sign-in', { json: { userId } });
    assert.equal(response.status, 200);
    return response.json();
  };
  let stopped = false;
  return { ...instance, request, signIn, async stop() {
    if (stopped) return;
    stopped = true;
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    await instance.close();
  } };
}

async function fixture(t, options) {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-icon-http-'));
  const instance = await start(dataDir, options);
  t.after(async () => { await instance.stop(); await rm(dataDir, { recursive: true, force: true }); });
  return { ...instance, dataDir };
}

async function waitForIcon(app, predicate) {
  for (let attempt = 0; attempt < 100; attempt++) {
    const icon = await app.directory.iconFor('mira');
    if (predicate(icon)) return icon;
    await delay(10);
  }
  assert.fail(`Icon did not reach expected state: ${JSON.stringify(await app.directory.iconFor('mira'))}`);
}

async function publish(app) {
  await app.service.submit('Create a botanical guestbook');
  await app.service.waitForIdle();
  assert.equal(app.service.store.read().currentRevisionId, 2);
}

test('icon routes require authentication, and only the actual owner may upload or generate', async t => {
  let generations = 0;
  const app = await fixture(t, { iconGenerator: async () => { generations++; return normalizeSpaceIcon(await picture()); } });
  const payload = upload(await picture());
  for (const path of ['/api/spaces/mira/icon', '/api/spaces/mira/icon/generate']) {
    assert.equal((await app.request(path, { json: path.endsWith('generate') ? {} : payload })).status, 401);
  }
  assert.equal((await app.request('/api/spaces/mira/icon')).status, 401);
  assert.equal((await app.request('/api/spaces/mira/icon', { token: 'a'.repeat(43) })).status, 401);
  const leo = await app.signIn('leo');
  for (const path of ['/api/spaces/mira/icon?actor=mira', '/api/spaces/mira/icon/generate?actor=mira']) {
    assert.equal((await app.request(path, { token: leo.token, json: path.includes('generate') ? {} : payload })).status, 403);
  }
  assert.equal((await app.request('/api/spaces/missing/icon', { token: leo.token })).status, 404);
  assert.equal((await app.request('/api/spaces/%2E%2E%2Fsecret/icon', { token: leo.token })).status, 404);
  assert.deepEqual(await (await app.request('/api/spaces/mira/icon', { token: leo.token })).json(), { icon: { status: 'empty' } });
  assert.equal(generations, 0);
  assert.equal(app.service.store.read().icon, undefined);
});

test('an owner can upload beyond the normal JSON limit and every public view gets the same normalized icon', async t => {
  const app = await fixture(t);
  const mira = await app.signIn('mira');
  const leo = await app.signIn('leo');
  const input = await sharp(randomBytes(512 * 384 * 3), { raw: { width: 512, height: 384, channels: 3 } }).png().toBuffer();
  const payload = upload(input);
  assert.ok(JSON.stringify(payload).length > 48 * 1024);
  const response = await app.request('/api/spaces/mira/icon', { token: mira.token, json: payload });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get('cache-control'), 'no-store');
  const { icon } = await response.json();
  assert.equal(icon.status, 'ready');
  assert.equal(icon.source, 'upload');
  assert.ok(icon.version);
  assert.match(icon.dataUrl, /^data:image\/webp;base64,/);
  const normalized = Buffer.from(icon.dataUrl.split(',')[1], 'base64');
  const image = await sharp(normalized).metadata();
  assert.equal(image.width, 256);
  assert.equal(image.height, 256);
  assert.equal(image.format, 'webp');
  assert.ok(normalized.length <= 256 * 1024);
  for (const token of [mira.token, leo.token]) {
    assert.deepEqual((await (await app.request('/api/spaces/mira/icon', { token })).json()).icon, icon);
    assert.deepEqual((await (await app.request('/api/spaces/mira', { token })).json()).space.icon, icon);
    const community = await (await app.request('/api/community', { token })).json();
    assert.deepEqual(community.spaces.find(space => space.id === 'mira').icon, icon);
    const directory = await (await app.request('/api/spaces', { token })).json();
    assert.deepEqual(directory.spaces.find(space => space.id === 'mira').icon, icon);
  }
  const chooser = await (await app.request('/api/auth/people')).json();
  const miraEntry = chooser.users.find(person => person.id === 'mira');
  assert.deepEqual(miraEntry.icon, icon, 'the signed-out chooser uses the same custom icon');
  assert.deepEqual(chooser.users.find(person => person.id === 'leo').icon, { status: 'empty' });
  assert.deepEqual(Object.keys(miraEntry).sort(), ['icon', 'id', 'name', 'ownSpaceId', 'profile']);
  const disk = JSON.parse(await readFile(join(app.dataDir, 'space.json'), 'utf8'));
  assert.equal(disk.icon.data, icon.dataUrl.split(',')[1]);
  assert.doesNotMatch(JSON.stringify(disk.events), /data:image\/|"dataUrl"/);
  assert.ok(!JSON.stringify(disk.events).includes(disk.icon.data));
  assert.equal(disk.session.turns.length, 0, 'uploading an icon does not invoke the builder');
});

test('icon writes reject unsupported fields, malformed images, and data exceeding 5 MiB', async t => {
  const app = await fixture(t, { iconGenerator: async () => normalizeSpaceIcon(await picture()) });
  const mira = await app.signIn('mira');
  const valid = upload(await picture());
  const invalid = [{}, [], { dataUrl: 1 }, { ...valid, owner: 'mira' }, { ...valid, source: 'generated' },
    { dataUrl: 'data:image/svg+xml;base64,PHN2Zy8+' }, { dataUrl: 'data:image/png;base64,PHN2Zy8+' },
    { dataUrl: 'data:image/png;base64,R0lGODlh' }, { dataUrl: 'data:image/png;base64,@@@@' },
    { dataUrl: 'data:image/png;base64,YQ' }];
  for (const json of invalid) {
    const response = await app.request('/api/spaces/mira/icon', { token: mira.token, json });
    assert.equal(response.status, 400, JSON.stringify(json));
    assert.equal(typeof (await response.json()).error, 'string');
  }
  for (const json of [[], { description: 'Ignore the saved space' }, { actor: 'mira' }]) {
    assert.equal((await app.request('/api/spaces/mira/icon/generate', { token: mira.token, json })).status, 400);
  }
  const tooLarge = upload(Buffer.alloc(SPACE_ICON_MAX_BYTES + 1));
  const rejected = await app.request('/api/spaces/mira/icon', { token: mira.token, json: tooLarge });
  assert.equal(rejected.status, 413);
  assert.match((await rejected.json()).error, /5 MB/);
  assert.equal((await app.request('/api/spaces/mira/icon', { token: mira.token, method: 'POST', body: 'raw image', headers: { 'Content-Type': 'image/png' } })).status, 415);
  assert.deepEqual(await app.directory.iconFor('mira'), { status: 'empty' });
});

test('generation returns 202 while image work is still pending and retains the previous icon until ready', async t => {
  const pending = gate();
  const entered = gate();
  t.after(() => pending.resolve());
  const generated = await normalizeSpaceIcon(await picture());
  let generations = 0;
  const app = await fixture(t, { iconGenerator: async () => {
    generations++;
    if (generations > 1) { entered.resolve(); await pending.promise; }
    return generated;
  } });
  const mira = await app.signIn('mira');
  await publish(app);
  const original = await waitForIcon(app, icon => icon.status === 'ready');
  const response = await app.request('/api/spaces/mira/icon/generate', { token: mira.token, json: {}, signal: AbortSignal.timeout(1000) });
  assert.equal(response.status, 202);
  const { icon: working } = await response.json();
  assert.equal(working.status, 'generating');
  assert.equal(working.dataUrl, original.dataUrl);
  await entered.promise;
  assert.equal(generations, 2);
  assert.equal((await app.directory.iconFor('mira')).status, 'generating');
  pending.resolve();
  const completed = await waitForIcon(app, icon => icon.status === 'ready');
  assert.equal(completed.source, 'generated');
  assert.notEqual(completed.version, original.version);
});

test('an owner upload wins over an in-flight generated result and survives reopening the app', async t => {
  const pending = gate();
  const entered = gate();
  const returned = gate();
  const generated = await normalizeSpaceIcon(await picture('#ae9470'));
  let generationSignal;
  let generations = 0;
  const iconGenerator = async ({ signal }) => {
    generations++;
    generationSignal = signal;
    entered.resolve();
    await pending.promise;
    returned.resolve();
    return generated; // Deliberately ignores cancellation to exercise the commit guard.
  };
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-icon-reopen-'));
  let active = await start(dataDir, { iconGenerator });
  t.after(async () => { pending.resolve(); await active.stop(); await rm(dataDir, { recursive: true, force: true }); });
  const mira = await active.signIn('mira');
  await publish(active);
  await entered.promise;
  const response = await active.request('/api/spaces/mira/icon', { token: mira.token, json: upload(await picture('#477aa1')) });
  assert.equal(response.status, 200);
  const { icon } = await response.json();
  assert.equal(icon.source, 'upload');
  assert.equal(generationSignal.aborted, true);
  pending.resolve();
  await returned.promise;
  await delay(0);
  await active.service.store.flush();
  assert.deepEqual(await active.directory.iconFor('mira'), icon);
  await active.stop();
  active = await start(dataDir, { iconGenerator });
  const returning = await active.signIn('mira');
  assert.deepEqual((await (await active.request('/api/spaces/mira/icon', { token: returning.token })).json()).icon, icon);
  assert.deepEqual((await (await active.request('/api/spaces/mira', { token: returning.token })).json()).space.icon, icon);
  const community = await (await active.request('/api/community', { token: returning.token })).json();
  assert.deepEqual(community.spaces.find(space => space.id === 'mira').icon, icon);
  assert.equal(generations, 1, 'a saved upload does not get replaced by background generation after reopening');
});

test('enabling generation backfills one icon for an already-published space on startup', async t => {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-icon-backfill-'));
  let active = await start(dataDir);
  t.after(async () => { await active.stop(); await rm(dataDir, { recursive: true, force: true }); });
  await publish(active);
  assert.deepEqual(await active.directory.iconFor('mira'), { status: 'empty' });
  await active.stop();
  let generations = 0;
  const generated = await normalizeSpaceIcon(await picture());
  const iconGenerator = async () => { generations++; return generated; };
  active = await start(dataDir, { iconGenerator });
  const icon = await waitForIcon(active, item => item.status === 'ready');
  assert.equal(icon.source, 'generated');
  assert.equal(generations, 1, 'only the already-built space needs an icon');
  await active.directory.list();
  await active.directory.list();
  assert.equal(generations, 1, 'metadata refreshes do not queue duplicate image work');
  await active.stop();
  active = await start(dataDir, { iconGenerator });
  assert.deepEqual(await active.directory.iconFor('mira'), icon);
  assert.equal(generations, 1, 'persisted generated icons are reused on subsequent startup');
});
