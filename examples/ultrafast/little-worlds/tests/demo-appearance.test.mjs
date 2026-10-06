import test from 'node:test';
import assert from 'node:assert/strict';
import { once } from 'node:events';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import sharp from 'sharp';
import { createApp } from '../server/index.mjs';
import { communityBoardSource, communityBoardSeed } from '../server/community-board.mjs';
import { demoAppearanceFor, withDemoIconAppearance } from '../server/demo-appearance.mjs';
import { normalizeSpaceIcon } from '../server/space-icon-image.mjs';
import { paintingProposal } from '../server/painting/index.mjs';
import { arcadeProposal } from '../server/arcade/index.mjs';

const originalIcon = {
  status: 'ready', source: 'upload', version: 'any-revision-id',
  dataUrl: `data:image/webp;base64,${communityBoardSeed.icon.data}`,
};
const lightIcon = '/space-icons/light/nora.webp';

async function fixture(t, options = {}) {
  const parent = await mkdtemp(join(tmpdir(), 'little-worlds-appearance-'));
  const dataDir = join(parent, 'data');
  let modelCalls = 0;
  const adapter = { keyAvailable: false, respond() { modelCalls++; assert.fail('Appearance must not call the model.'); } };
  const instance = await createApp({ dataDir, adapter, ...options });
  const server = instance.app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const request = async (path, { token, json } = {}) => {
    const response = await fetch(`${base}${path}`, {
      method: json === undefined ? 'GET' : 'POST',
      headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(json === undefined ? {} : { 'Content-Type': 'application/json', Origin: base }) },
      ...(json === undefined ? {} : { body: JSON.stringify(json) }),
    });
    assert.equal(response.status, 200, await response.clone().text());
    return response.json();
  };
  t.after(async () => {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    await instance.close();
    await rm(parent, { recursive: true, force: true });
  });
  return { ...instance, request, dataDir, modelCalls: () => modelCalls,
    signIn: userId => request('/api/auth/sign-in', { json: { userId } }) };
}

test('prepared appearance matches source content and persona, without mutating the original', () => {
  const appearance = demoAppearanceFor('nora', communityBoardSource);
  assert.ok(appearance.lightCss.includes('.square'));
  assert.deepEqual(Object.keys(appearance), ['lightCss', 'presentationCss']);
  assert.match(appearance.presentationCss, /--world-body/);
  assert.equal(demoAppearanceFor('nora', `${communityBoardSource}\n// Owner edit`), undefined);
  assert.equal(demoAppearanceFor('mira', communityBoardSource), undefined);
  assert.equal(demoAppearanceFor('person_new-owner', communityBoardSource), undefined);
  assert.equal(demoAppearanceFor('__proto__', communityBoardSource), undefined);
  assert.equal(demoAppearanceFor('nora', undefined), undefined);
  appearance.lightCss = 'Modified response';
  appearance.presentationCss = 'Modified typography';
  assert.notEqual(demoAppearanceFor('nora', communityBoardSource).lightCss, appearance.lightCss);
  assert.notEqual(demoAppearanceFor('nora', communityBoardSource).presentationCss, appearance.presentationCss);
});

test('icon matching uses original artwork bytes, not the mutable version or status', () => {
  const before = structuredClone(originalIcon);
  assert.equal(withDemoIconAppearance('nora', originalIcon).lightDataUrl, lightIcon);
  assert.equal(withDemoIconAppearance('nora', { ...originalIcon, version: 'new-version', status: 'generating' }).lightDataUrl, lightIcon);
  assert.equal(withDemoIconAppearance('james', originalIcon).lightDataUrl, undefined);
  assert.equal(withDemoIconAppearance('person_new-owner', originalIcon).lightDataUrl, undefined);
  assert.equal(withDemoIconAppearance('nora', { ...originalIcon, dataUrl: 'data:image/webp;base64,YWJjZA==' }).lightDataUrl, undefined);
  assert.deepEqual(withDemoIconAppearance('nora', { status: 'empty' }), { status: 'empty' });
  assert.deepEqual(originalIcon, before);
});

test('resolution-only painting edits retain both prepared themes and TV typography', async () => {
  const original = await paintingProposal();
  const appearance = demoAppearanceFor('iris', original.source);
  assert.ok(appearance);
  for (const [columns, rows] of [[96,64], [192,128], [256,256]]) {
    const resized = await paintingProposal({ columns, rows });
    assert.deepEqual(demoAppearanceFor('iris', resized.source), appearance);
    assert.equal(demoAppearanceFor('iris', resized.source + '\n// Custom design'), undefined);
  }
  assert.equal(demoAppearanceFor('iris', original.source.replace('COLUMNS = 48', 'COLUMNS = 999')), undefined);
  assert.equal(demoAppearanceFor('karen', original.source), undefined);
});

test('the bundled arcade retains its prepared theme and typography until the owner edits its source', async () => {
  const { source } = await arcadeProposal();
  const appearance = demoAppearanceFor('karen', source);
  assert.ok(appearance);
  assert.match(appearance.lightCss, /\.arcade-world/);
  assert.match(appearance.presentationCss, /--world-body/);
  assert.equal(demoAppearanceFor('karen', `${source}\n// Owner edit`), undefined);
  assert.equal(demoAppearanceFor('iris', source), undefined);
});

test('all prepared worlds have independent local light styles', async () => {
  const ids = ['mira', 'james', 'jake', 'erica', 'iris', 'luca', 'karen', 'nora'];
  const styles = await Promise.all(ids.map(id => readFile(new URL(`../server/demo-appearance/${id}.css`, import.meta.url), 'utf8')));
  assert.equal(new Set(styles).size, ids.length);
  for (let index = 0; index < styles.length; index++) {
    assert.ok(styles[index].trim().length > 100, ids[index]);
    assert.doesNotMatch(styles[index], /<\/?style|@import|url\s*\(/i, `${ids[index]} uses only local stylesheet declarations`);
  }
});

test('owner, visitor, community, sign-in, and preview surfaces share light assets without store writes', async t => {
  const app = await fixture(t);
  const nora = await app.signIn('nora');
  const leo = await app.signIn('leo');
  const service = await app.directory.serviceFor('nora');
  const before = service.store.read();
  const diskBefore = await readFile(join(app.dataDir, 'spaces/nora/space.json'), 'utf8');
  const expected = demoAppearanceFor('nora', communityBoardSource);
  for (const token of [nora.token, leo.token]) {
    const snapshot = await app.request('/api/spaces/nora', { token });
    assert.deepEqual(snapshot.space.appearance, expected);
    assert.equal(snapshot.space.icon.lightDataUrl, lightIcon);
    const preview = await app.request('/api/spaces/nora/preview', { token });
    assert.deepEqual(preview.appearance, expected);
    assert.equal(preview.html, snapshot.html);
    assert.equal(preview.version, snapshot.space.previewVersion);
    assert.deepEqual(Object.keys(preview).sort(), ['appearance', 'hasBuilt', 'html', 'spaceId', 'version']);
    const community = await app.request('/api/community', { token });
    assert.deepEqual(community.spaces.find(space => space.id === 'nora').appearance, expected);
  }
  const people = await app.request('/api/auth/people');
  assert.equal(people.users.find(person => person.id === 'nora').icon.lightDataUrl, lightIcon);
  assert.equal((await app.request('/api/spaces/nora/icon', { token: leo.token })).icon.lightDataUrl, lightIcon);
  assert.deepEqual(service.store.read(), before);
  assert.equal(await readFile(join(app.dataDir, 'spaces/nora/space.json'), 'utf8'), diskBefore);
  assert.equal(app.modelCalls(), 0);
});

test('participation preserves appearance while source edits and replacement artwork invalidate independently', async t => {
  const app = await fixture(t);
  const nora = await app.signIn('nora');
  const leo = await app.signIn('leo');
  const service = await app.directory.serviceFor('nora');
  await app.request('/api/spaces/nora/action', { token: leo.token, json: {
    revisionId: 1, action: { type: 'post_message', topicId: 'ideas', body: 'Keep my shared message in both themes.' },
  } });
  const participated = service.store.read();
  assert.ok((await app.directory.metadata('nora')).appearance);
  assert.match((await service.preview('leo')).html, /Keep my shared message/);
  const replacement = await normalizeSpaceIcon(await sharp({ create: { width: 32, height: 32, channels: 3, background: '#336699' } }).png().toBuffer());
  const uploaded = await app.directory.uploadIcon('nora', replacement);
  assert.equal(uploaded.lightDataUrl, undefined);
  assert.equal((await app.directory.iconFor('nora')).lightDataUrl, undefined);
  assert.ok((await app.directory.metadata('nora')).appearance, 'an icon upload does not alter the page variant');
  assert.deepEqual(service.store.read().state, participated.state);
  await service.store.transact(data => { data.revisions.find(item => item.id === data.currentRevisionId).source += '\n// Owner customized the page'; });
  assert.equal((await app.directory.metadata('nora')).appearance, undefined);
  assert.equal((await service.preview('leo')).appearance, undefined);
  assert.equal((await app.request('/api/spaces/nora', { token: nora.token })).space.appearance, undefined);
  assert.deepEqual(service.store.read().state, participated.state);
});

test('regenerating a preset icon retains its light variant only while the original artwork remains visible', async t => {
  let release;
  const ready = new Promise(resolve => { release = resolve; });
  const replacement = await normalizeSpaceIcon(await sharp({ create: { width: 32, height: 32, channels: 3, background: '#773355' } }).png().toBuffer());
  const app = await fixture(t, { iconGenerator: async () => { await ready; return replacement; } });
  t.after(release);
  await app.signIn('nora');
  const pending = await app.directory.regenerateIcon('nora');
  assert.equal(pending.status, 'generating');
  assert.equal(pending.lightDataUrl, lightIcon);
  release();
  let icon;
  for (let attempt = 0; attempt < 100; attempt++) {
    icon = await app.directory.iconFor('nora');
    if (icon.status === 'ready') break;
    await delay(10);
  }
  assert.equal(icon.status, 'ready');
  assert.equal(icon.lightDataUrl, undefined);
  assert.equal(icon.dataUrl, `data:image/webp;base64,${replacement.data}`);
});

test('full demo reset and repeated reset restore the matching built-in appearance without storing a theme', async t => {
  const app = await fixture(t);
  await app.signIn('nora');
  const expected = demoAppearanceFor('nora', communityBoardSource);
  const requestReset = () => app.request('/api/demo/reset', { json: { confirmation: 'reset-demo' } });
  for (let pass = 0; pass < 2; pass++) {
    await requestReset();
    const nora = await app.signIn('nora');
    const snapshot = await app.request('/api/spaces/nora', { token: nora.token });
    assert.deepEqual(snapshot.space.appearance, expected);
    assert.equal(snapshot.space.icon.lightDataUrl, lightIcon);
    const disk = JSON.parse(await readFile(join(app.dataDir, 'spaces/nora/space.json'), 'utf8'));
    assert.equal(disk.appearance, undefined);
    assert.equal(disk.icon.lightDataUrl, undefined);
  }
  assert.equal(app.modelCalls(), 0);
});
