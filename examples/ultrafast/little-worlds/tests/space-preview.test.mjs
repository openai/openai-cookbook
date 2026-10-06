import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { createApp } from '../server/index.mjs';
import { addEvent } from '../server/store.mjs';

const source = `// Private source implementation marker.
export const meta={title:'Published garden',subtitle:'',accent:'#687957'};
export function render(state,actor){return '<section><h1>Published garden</h1><p>Hello '+actor.name+'</p><p>'+Object.keys(state.extras.guestbook||{}).length+' shared thoughts</p></section>'}
export function reduce(state,action,actor){
 if(action.type!=='leave'||typeof action.text!=='string'||!action.text.trim()||action.text.length>80)throw Error('Invalid thought');
 state.extras.guestbook=state.extras.guestbook||{};
 state.extras.guestbook[actor.id]={actorId:actor.id,text:action.text.trim()};return state;
}`;
const checks = `// Private test implementation marker.
export function runTests(api){
 const actor={id:'test-fresh-person',name:'Test guest'};
 const next=api.reduce(api.initialState,{type:'leave',text:'A little wonder'},actor);
 let blocked=false;try{api.reduce(api.initialState,{type:'leave',text:''},actor)}catch{blocked=true}
 return [
 {name:'Visitors can leave a thought',ok:next.extras.guestbook[actor.id].text==='A little wonder'},
 {name:'Empty thoughts are refused',ok:blocked},
 {name:'Other records remain intact',ok:Object.entries(api.initialState.extras.guestbook||{}).every(([id,record])=>JSON.stringify(next.extras.guestbook[id])===JSON.stringify(record))},
 {name:'Current data renders',ok:api.render(api.initialState,actor).includes('shared thoughts')}
 ];
}`;
let callId = 0;
const tool = (name, args) => ({ model: 'test-model', service_tier: 'ultrafast', output: [
  { type: 'function_call', call_id: `preview-call-${++callId}`, name, arguments: JSON.stringify(args) },
], metrics: { durationMs: 5, ttftMs: 1, outputTokens: 10, servedTier: 'ultrafast' } });
const published = () => tool('apply_change', { source, tests: checks, summary: 'A shared garden' });
const gate = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };

async function fixture(t, respond = async () => published()) {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-preview-'));
  let modelCalls = 0;
  const instance = await createApp({ dataDir, adapter: { keyAvailable: true, model: 'test-model', tier: 'ultrafast',
    respond: async (request) => { modelCalls++; return respond(request); } } });
  const server = instance.app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const request = (path, { token, json } = {}) => fetch(`${base}${path}`, {
    method: json === undefined ? 'GET' : 'POST',
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(json === undefined ? {} : { 'Content-Type': 'application/json' }) },
    ...(json === undefined ? {} : { body: JSON.stringify(json) }),
  });
  const signIn = async userId => (await request('/api/auth/sign-in', { json: { userId } })).json();
  const preview = async (token, spaceId = 'mira') => {
    const response = await request(`/api/spaces/${spaceId}/preview`, { token });
    assert.equal(response.status, 200);
    return response.json();
  };
  const publish = async () => { await instance.service.submit('Private builder request'); await instance.service.waitForIdle(); };
  t.after(async () => {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    await instance.close();
    await rm(dataDir, { recursive: true, force: true });
  });
  return { ...instance, dataDir, request, signIn, preview, publish, modelCalls: () => modelCalls };
}

test('space previews require authentication, scope the space, and represent blank canvases without side effects', async t => {
  const app = await fixture(t);
  assert.equal((await app.request('/api/spaces/mira/preview')).status, 401);
  assert.equal((await app.request('/api/spaces/mira/preview', { token: 'a'.repeat(43) })).status, 401);
  const leo = await app.signIn('leo');
  assert.equal((await app.request('/api/spaces/not-a-space/preview', { token: leo.token })).status, 404);
  const before = app.service.store.read();
  const response = await app.request('/api/spaces/mira/preview', { token: leo.token });
  assert.equal(response.headers.get('cache-control'), 'no-store');
  const preview = await response.json();
  assert.deepEqual(preview, { spaceId: 'mira', version: (await app.directory.metadata('mira')).previewVersion, html: '', hasBuilt: false });
  assert.match(preview.version, /^[a-f0-9]{24}$/);
  assert.deepEqual(app.service.store.read(), before);
  assert.equal(app.modelCalls(), 0);
});

test('space previews render for the authenticated viewer and expose no builder data even to owners', async t => {
  const app = await fixture(t);
  const mira = await app.signIn('mira');
  const leo = await app.signIn('leo');
  await app.publish();
  await app.service.store.emit({ type: 'draft.preview', title: 'Private title', data: { html: '<p>Secret draft</p>', source: 'Secret code' } });
  const before = app.service.store.read();
  const owner = await app.preview(mira.token);
  const visitor = await app.preview(leo.token);
  const ownerAgain = await app.preview(mira.token);
  assert.deepEqual(Object.keys(visitor).sort(), ['hasBuilt', 'html', 'spaceId', 'version']);
  assert.deepEqual(ownerAgain, owner);
  assert.equal(owner.version, visitor.version);
  assert.equal(visitor.hasBuilt, true);
  assert.match(owner.html, /Hello Mira/);
  assert.match(visitor.html, /Hello Leo/);
  assert.equal(visitor.html, (await app.service.snapshot('leo')).html);
  const forged = await (await app.request('/api/spaces/mira/preview?actor=mira', { token: leo.token })).json();
  assert.match(forged.html, /Hello Leo/);
  assert.doesNotMatch(JSON.stringify([owner, visitor]), /Private|Secret|source|tests|session|turns|events|checks/);
  assert.deepEqual(app.service.store.read(), before);
  assert.equal(app.modelCalls(), 1, 'previews never call the model');
});

test('unrenderable saved revisions keep owner recovery controls and safe visitor previews available', async t => {
  const failures = {
    compile: value => `${value}\nexport const PRIVATE_RENDER_DETAILS = ;`,
    render: value => value.replace("return '<section>", "throw Error('PRIVATE_RENDER_DETAILS');return '<section>"),
    markup: value => value.replace("return '<section>", "return '<style>p{color:red}PRIVATE_RENDER_DETAILS<section>"),
  };
  for (const [name, corrupt] of Object.entries(failures)) await t.test(name, async t => {
    const app = await fixture(t);
    const owner = await app.signIn('mira'), visitor = await app.signIn('leo');
    await app.publish();
    await app.service.action({ actor: 'leo', revisionId: 2, action: { type: 'leave', text: 'Keep this thought' } });
    // Simulate a revision saved by an older runtime; current publication must
    // never accept this source through its verification gate.
    await app.service.store.transact(data => {
      data.revisions.push({ ...data.revisions.at(-1), id: 3, source: corrupt(source) });
      data.currentRevisionId = 3;
    });
    const before = app.service.store.read();
    const ownerResponse = await app.request('/api/spaces/mira', { token: owner.token });
    const visitorResponse = await app.request('/api/spaces/mira', { token: visitor.token });
    assert.equal(ownerResponse.status, 200);
    assert.equal(visitorResponse.status, 200);
    const own = await ownerResponse.json(), visiting = await visitorResponse.json();
    assert.equal(own.revision.id, 3);
    assert.equal(own.revision.source, before.revisions.at(-1).source);
    assert.deepEqual(own.state, before.state);
    assert.equal(own.session.turnCount, before.session.turns.length);
    assert.equal(own.permissions.canEdit, true);
    assert.equal(own.config.keyAvailable, true, 'The owner can still submit a repair');
    assert.match(own.html, /Restore a version from History, or describe a fix below/);
    assert.equal(visiting.permissions.canEdit, false);
    assert.equal(visiting.revision.id, 3);
    assert.deepEqual(visiting.state, before.state);
    assert.match(visiting.html, /The owner can restore a version or repair this design/);
    assert.doesNotMatch(JSON.stringify(visiting), /PRIVATE_RENDER_DETAILS/);
    for (const [token, expected] of [[owner.token, own], [visitor.token, visiting]]) {
      const preview = await app.preview(token);
      assert.equal(preview.html, expected.html);
      assert.equal(preview.hasBuilt, true);
      assert.equal(preview.version, (await app.directory.metadata('mira')).previewVersion);
      assert.doesNotMatch(preview.html, /PRIVATE_RENDER_DETAILS|<(?:button|input|form|a|style)\b|data-action/);
    }
    const history = await app.request('/api/spaces/mira/revisions', { token: owner.token });
    assert.equal(history.status, 200);
    assert.deepEqual((await history.json()).map(revision => revision.id), [1, 2, 3]);
    assert.deepEqual(app.service.store.read(), before, 'Fallback rendering must not rewrite saved history or data');
    assert.equal(app.modelCalls(), 1, 'Fallback rendering must not call a model');
    const restore = await app.request('/api/spaces/mira/restore', { token: owner.token, json: { revisionId: 2 } });
    assert.equal(restore.status, 200);
    assert.equal((await restore.json()).revisionId, 4);
    const repaired = await app.service.snapshot();
    assert.match(repaired.html, /Published garden/);
    assert.deepEqual(repaired.state, before.state);
    assert.equal((await app.service.revisions()).length, 4);
  });
});

test('working files, streaming drafts, and private log pruning cannot replace or invalidate a published preview', async t => {
  const draftEntered = gate();
  const release = gate();
  // Register before fixture teardown so failures cannot leave its model waiting.
  t.after(() => release.resolve());
  let response = 0;
  const draftSource = source.replaceAll('Published garden', 'Unpublished secret garden');
  const app = await fixture(t, async () => {
    response++;
    if (response === 1) return published();
    if (response === 2) return tool('write_file', { path: 'space.js', content: draftSource });
    draftEntered.resolve();
    await release.promise;
    return { output: [] };
  });
  const leo = await app.signIn('leo');
  await app.publish();
  const before = await app.preview(leo.token);
  await app.service.submit('Private unpublished request');
  await draftEntered.promise;
  const turnId = app.service.store.read().session.turns.at(-1).id;
  assert.match(await readFile(join(app.dataDir, 'workspaces', turnId, 'space.js'), 'utf8'), /Unpublished secret garden/);
  await app.service.store.transact(data => {
    for (let index = 0; index < 170; index++) addEvent(data, { type: 'tool.completed', title: 'Private tool output', data: { index } });
    addEvent(data, { type: 'draft.preview', data: { html: '<p>Unpublished secret garden</p>' } });
  });
  assert.equal(app.service.store.read().events.some(event => event.type === 'revision.published'), false);
  assert.deepEqual(await app.preview(leo.token), before);
  assert.equal((await app.directory.metadata('mira')).previewVersion, before.version);
  await app.service.cancel();
  release.resolve();
  await app.service.waitForIdle();
  assert.deepEqual(await app.preview(leo.token), before);
});

test('preview versions follow public state, publication, restoration and reset', async t => {
  const app = await fixture(t);
  const leo = await app.signIn('leo');
  const blank = await app.preview(leo.token);
  await app.publish();
  const built = await app.preview(leo.token);
  assert.notEqual(built.version, blank.version);
  await app.service.action({ actor: 'leo', revisionId: 2, action: { type: 'leave', text: 'Hello garden' } });
  const joined = await app.preview(leo.token);
  assert.notEqual(joined.version, built.version);
  assert.match(joined.html, /1 shared thoughts/);
  assert.equal((await app.directory.metadata('mira')).previewVersion, joined.version);
  await app.publish();
  const republished = await app.preview(leo.token);
  assert.notEqual(republished.version, joined.version, 'a new published revision has its own version');
  await app.service.restore(2);
  const restored = await app.preview(leo.token);
  assert.notEqual(restored.version, republished.version);
  assert.equal(restored.html, joined.html);
  await app.service.reset();
  const reset = await app.preview(leo.token);
  assert.notEqual(reset.version, restored.version);
  assert.deepEqual(reset, blank, 'an identical blank canvas can reuse its original content identity');
});

test('a preview keeps its captured HTML and version consistent through concurrent public changes', async t => {
  const app = await fixture(t);
  const leo = await app.signIn('leo');
  await app.publish();
  const before = await app.preview(leo.token);
  const rendering = app.service.preview('leo');
  await app.service.action({ actor: 'leo', revisionId: 2, action: { type: 'leave', text: 'Changed during preview' } });
  assert.deepEqual(await rendering, { version: before.version, html: before.html, hasBuilt: true });
  const after = await app.preview(leo.token);
  assert.notEqual(after.version, before.version);
  assert.match(after.html, /1 shared thoughts/);
});
