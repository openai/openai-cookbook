import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createSpaceIconManager } from '../server/space-icons.mjs';
import { openStore, addEvent } from '../server/store.mjs';
import { blankSeedSource } from '../server/seed.mjs';
import { DEV_DAY_THEME_VERSION } from '../server/devday-theme.mjs';

const image = name => ({ data: Buffer.from(`normalized-image-${name}`).toString('base64'), mimeType: 'image/webp' });
const source = name => `export const meta={title:'${name}',accent:'#678a54'};\nexport function render(){return '<h1>${name}</h1>'}`;
const savedIcon = (name = 'old', extra = {}) => ({ ...image(name), status: 'ready', source: 'generated', version: `version-${name}`, ...extra });
const gate = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };

async function until(predicate) {
  for (let index = 0; index < 200; index++) {
    if (predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 2));
  }
  assert.fail('The expected icon operation did not complete.');
}

async function setup(t, { generate, concurrency, icon, blank = false } = {}) {
  const root = await mkdtemp(join(tmpdir(), 'little-worlds-icons-'));
  const manager = createSpaceIconManager({ generate, concurrency });
  let count = 0;
  async function space(options = {}) {
    const directory = join(root, String(++count));
    const empty = options.blank ?? blank;
    const initialIcon = options.icon ?? icon;
    const store = await openStore(directory, () => ({
      version: 1, ownerId: `owner-${count}`, kind: 'blank', sequence: 0,
      currentRevisionId: 1,
      revisions: [{ id: 1, title: 'Botanical garden', source: empty ? blankSeedSource : source('Botanical garden'), meta: { title: 'Botanical garden', accent: '#678a54' }, tests: 'private-test-marker' }],
      state: { extras: { privateState: 'visitor-state-marker' } },
      session: { items: ['private-conversation-marker'], turns: [{ message: 'private-draft-marker' }] },
      events: [], ...(initialIcon ? { icon: structuredClone(initialIcon) } : {}),
    }));
    const service = { store };
    const controller = manager.attach(service);
    const publish = (name = 'A new garden') => store.transact(data => {
      const id = data.currentRevisionId + 1;
      data.revisions.push({ id, title: name, source: source(name), meta: { title: name, accent: '#678a54' } });
      data.currentRevisionId = id;
      addEvent(data, { type: 'revision.published' });
    });
    return { service, store, controller, publish, directory };
  }
  t.after(async () => { await manager.close(); await rm(root, { recursive: true, force: true }); });
  return { manager, space, ...await space() };
}

test('blank canvases wait until publication, then generate from published material only', async t => {
  const descriptions = [];
  const app = await setup(t, { blank: true, generate: async ({ description }) => { descriptions.push(description); return image('garden'); } });
  assert.deepEqual(await app.controller.ensure(), { status: 'empty' });
  assert.equal(descriptions.length, 0);
  await app.publish();
  await until(() => app.controller.metadata().status === 'ready');
  assert.equal(descriptions.length, 1);
  assert.match(descriptions[0], /A new garden/);
  assert.doesNotMatch(descriptions[0], /private-conversation-marker|private-draft-marker|visitor-state-marker|private-test-marker/);
  assert.equal(app.controller.metadata().dataUrl, `data:image/webp;base64,${image('garden').data}`);
  const events = app.store.read().events.filter(event => event.type === 'icon.updated');
  assert.deepEqual(events.map(event => event.data.status), ['generating', 'ready']);
  assert.doesNotMatch(JSON.stringify(events), /dataUrl|fingerprint|requestId|base64|private-/);
  assert.equal(JSON.stringify(events).includes(image('garden').data), false);
});

test('concurrent ensures share one generation and a controller attaches only once', async t => {
  const pending = gate(); let calls = 0;
  const app = await setup(t, { generate: async () => { calls++; return pending.promise; } });
  assert.equal(app.manager.attach(app.service), app.controller);
  const first = app.controller.ensure();
  assert.equal(app.controller.metadata().status, 'generating');
  const second = app.controller.ensure();
  assert.equal(first, second);
  await until(() => calls === 1);
  assert.equal(app.controller.ensure(), first);
  pending.resolve(image('only'));
  const metadata = await first;
  assert.equal(metadata.status, 'ready');
  assert.equal(calls, 1);
  assert.deepEqual(await app.controller.ensure(), metadata);
});

test('generation concurrency is bounded globally across spaces', async t => {
  const pending = []; let running = 0; let peak = 0;
  const app = await setup(t, { concurrency: 2, generate: async () => {
    const next = gate(); pending.push(next); running++; peak = Math.max(peak, running);
    const result = await next.promise; running--; return result;
  } });
  const spaces = [app, await app.space(), await app.space(), await app.space()];
  const requests = spaces.map(item => item.controller.ensure());
  await until(() => pending.length === 2);
  assert.equal(spaces.every(item => item.controller.metadata().status === 'generating'), true);
  assert.equal(running, 2);
  pending[0].resolve(image('first'));
  await until(() => pending.length === 3);
  assert.equal(running, 2);
  pending[1].resolve(image('second'));
  await until(() => pending.length === 4);
  pending[2].resolve(image('third')); pending[3].resolve(image('fourth'));
  assert.equal((await Promise.all(requests)).every(metadata => metadata.status === 'ready'), true);
  assert.equal(peak, 2);
});

test('queued regenerations share one request and use the latest published definition', async t => {
  const pending = gate(); const descriptions = [];
  const app = await setup(t, { concurrency: 1, generate: async ({ description }) => {
    descriptions.push(description);
    return descriptions.length === 1 ? pending.promise : image('latest');
  } });
  const first = app.controller.ensure();
  await until(() => descriptions.length === 1);
  const next = await app.space();
  const superseded = [next.controller.ensure()];
  for (let index = 0; index < 15; index++) {
    await next.publish(`Newest garden ${index}`);
    superseded.push(next.controller.regenerate());
  }
  assert.equal(superseded.every(request => request === superseded[0]), true);
  assert.equal(descriptions.length, 1);
  pending.resolve(image('first'));
  await first;
  await Promise.all(superseded);
  assert.equal(descriptions.length, 2);
  assert.match(descriptions[1], /Newest garden 14/);
  assert.equal(next.controller.metadata().dataUrl, `data:image/webp;base64,${image('latest').data}`);
});

test('an uploaded image wins over a late generator even if it ignores cancellation', async t => {
  const pending = gate(); let signal;
  const app = await setup(t, { generate: async request => { signal = request.signal; return pending.promise; } });
  const original = app.controller.ensure();
  await until(() => signal);
  const custom = await app.controller.upload(image('custom'));
  assert.equal(signal.aborted, true);
  assert.equal(custom.source, 'upload');
  assert.equal(custom.status, 'ready');
  assert.equal((await original).status, 'empty');
  pending.resolve(image('late-result'));
  await new Promise(resolve => setImmediate(resolve));
  await app.store.flush();
  assert.deepEqual(app.controller.metadata(), custom);
  assert.equal(app.store.read().icon.data, image('custom').data);
});

test('failed regeneration preserves artwork, sanitizes errors, and does not retry on polls or publication', async t => {
  let calls = 0;
  const app = await setup(t, { icon: savedIcon(), generate: async () => { calls++; throw new Error('Secret provider key sk-test and private request body'); } });
  const before = app.controller.metadata();
  const after = await app.controller.regenerate();
  assert.equal(after.status, 'error');
  assert.equal(after.version, before.version);
  assert.equal(after.dataUrl, before.dataUrl);
  assert.doesNotMatch(after.error, /Secret|sk-test|private/);
  for (let index = 0; index < 5; index++) await app.controller.ensure();
  await app.publish('Updated garden');
  await app.store.flush();
  assert.equal(calls, 1);
  assert.doesNotMatch(JSON.stringify(app.store.read().icon), /Secret|sk-test|private request body/);
  await app.controller.regenerate();
  assert.equal(calls, 2, 'explicit retry is still available');
});

test('a failed first image is not retried automatically until explicitly requested', async t => {
  let calls = 0;
  const app = await setup(t, { generate: async () => { calls++; if (calls === 1) throw new Error('failed'); return image('retry'); } });
  assert.equal((await app.controller.ensure()).status, 'error');
  await app.controller.ensure();
  await app.publish('A new title');
  assert.equal(calls, 1);
  assert.equal((await app.controller.regenerate()).status, 'ready');
  assert.equal(calls, 2);
});

test('saved artwork survives reopening the store without another generation', async t => {
  let calls = 0;
  const app = await setup(t, { generate: async () => { calls++; return image('persisted'); } });
  const before = await app.controller.ensure();
  await app.controller.close();
  const store = await openStore(app.directory, () => { throw new Error('Saved data should load'); });
  const reopened = app.manager.attach({ store });
  assert.deepEqual(reopened.metadata(), before);
  assert.deepEqual(await reopened.ensure(), before);
  assert.equal(calls, 1);
});

test('a restarted interrupted first generation retries, while an existing image stays ready', async t => {
  let calls = 0;
  const app = await setup(t, { icon: { status: 'generating', requestId: 'old-process' }, generate: async () => { calls++; return image('recovered'); } });
  assert.deepEqual(app.controller.metadata(), { status: 'empty' });
  assert.equal((await app.controller.ensure()).status, 'ready');
  assert.equal(calls, 1);
  const oldImage = await app.space({ icon: savedIcon('previous', { status: 'generating', requestId: 'old-process' }) });
  assert.equal(oldImage.controller.metadata().status, 'ready');
  await oldImage.controller.ensure();
  assert.equal(calls, 1);
});

test('ordinary edits and interactions keep both generated and uploaded icons stable', async t => {
  let calls = 0;
  const app = await setup(t, { generate: async () => { calls++; return image('stable'); } });
  const original = await app.controller.ensure();
  await app.publish('An ordinary text edit');
  await app.store.emit({ type: 'space.updated' });
  assert.deepEqual(app.controller.metadata(), original);
  const custom = await app.controller.upload(image('my-upload'));
  await app.publish('A changed title');
  await app.controller.ensure();
  assert.deepEqual(app.controller.metadata(), custom);
  assert.equal(calls, 1);
});

test('legacy artwork stays visible until an explicit themed replacement succeeds', async t => {
  const pending = gate(); let calls = 0;
  const app = await setup(t, {
    icon: savedIcon('legacy', { fingerprint: 'a-pre-devday-source-fingerprint' }),
    generate: async () => { calls++; return pending.promise; },
  });
  const before = app.controller.metadata();
  await app.controller.ensure();
  await app.publish('Themed garden');
  await app.store.flush();
  assert.equal(calls, 0, 'a new theme and ordinary publication do not trigger a paid replacement');
  assert.deepEqual(app.controller.metadata(), before);

  const replacement = app.controller.regenerate();
  await until(() => calls === 1);
  assert.equal(app.controller.metadata().status, 'generating');
  assert.equal(app.controller.metadata().dataUrl, before.dataUrl);
  assert.equal(app.controller.metadata().version, before.version);
  pending.resolve(image('devday'));
  const after = await replacement;
  assert.equal(after.status, 'ready');
  assert.notEqual(after.dataUrl, before.dataUrl);
  assert.notEqual(after.version, before.version);
  assert.equal(app.store.read().icon.themeVersion, DEV_DAY_THEME_VERSION);
  assert.notEqual(app.store.read().icon.fingerprint, 'a-pre-devday-source-fingerprint');
  assert.equal(calls, 1);
});

test('reset clears uploaded artwork and prevents an old generation from reappearing', async t => {
  const pending = gate(); let signal;
  const app = await setup(t, { icon: savedIcon('uploaded', { source: 'upload' }), generate: async request => { signal = request.signal; return pending.promise; } });
  const generating = app.controller.regenerate();
  await until(() => signal);
  await app.store.transact(data => {
    data.currentRevisionId = 1;
    data.revisions = [{ id: 1, source: blankSeedSource }];
    addEvent(data, { type: 'space.updated', data: { reset: true } });
  });
  assert.deepEqual(app.controller.metadata(), { status: 'empty' });
  await app.store.flush();
  assert.equal(signal.aborted, true);
  assert.equal(app.store.read().icon, undefined);
  pending.resolve(image('obsolete'));
  await generating;
  await new Promise(resolve => setImmediate(resolve));
  assert.deepEqual(app.controller.metadata(), { status: 'empty' });
});

test('manager shutdown cancels running and queued requests without waiting for network completion', async t => {
  const pending = gate(); let calls = 0; let signal;
  const app = await setup(t, { concurrency: 1, generate: async request => { calls++; signal = request.signal; return pending.promise; } });
  const running = app.controller.ensure();
  const queuedSpace = await app.space();
  const queued = queuedSpace.controller.ensure();
  await until(() => calls === 1);
  await app.manager.close();
  await Promise.all([running, queued]);
  assert.equal(signal.aborted, true);
  assert.equal(calls, 1);
  const before = app.store.read();
  pending.resolve(image('too-late'));
  await new Promise(resolve => setImmediate(resolve));
  await app.store.flush();
  assert.deepEqual(app.store.read(), before);
  await app.publish();
  assert.equal(calls, 1);
  assert.throws(() => app.manager.attach({ store: app.store }), /closed/);
});

test('repeated regeneration clicks share an in-flight image request instead of starting extra calls', async t => {
  const calls = [];
  const app = await setup(t, { generate: async ({ signal }) => { const pending = gate(); calls.push({ ...pending, signal }); return pending.promise; } });
  const old = app.controller.ensure();
  await until(() => calls.length === 1);
  const latest = app.controller.regenerate();
  assert.equal(latest, old);
  for (let index = 0; index < 10; index++) assert.equal(app.controller.regenerate(), old);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].signal.aborted, false);
  calls[0].resolve(image('one-request'));
  const expected = await latest;
  assert.deepEqual(app.controller.metadata(), expected);
  const next = app.controller.regenerate();
  await until(() => calls.length === 2);
  calls[1].resolve(image('explicit-next-request'));
  assert.notEqual((await next).version, expected.version);
});

test('disabled generation never starts work, but custom images can still be uploaded', async t => {
  const app = await setup(t);
  assert.deepEqual(await app.controller.ensure(), { status: 'empty' });
  await app.publish();
  assert.equal(app.store.read().icon, undefined);
  await assert.rejects(app.controller.regenerate(), error => error.status === 503 && /not configured/.test(error.message));
  const custom = await app.controller.upload(image('custom'));
  assert.equal(custom.status, 'ready');
  assert.equal(custom.source, 'upload');
});

test('blank spaces accept custom artwork without generating and invalid image payloads preserve it', async t => {
  let calls = 0;
  const app = await setup(t, { blank: true, generate: async () => { calls++; return image('unused'); } });
  assert.deepEqual(await app.controller.regenerate(), { status: 'empty' });
  const custom = await app.controller.upload(image('custom'));
  await assert.rejects(app.controller.upload({ data: '<svg onload=evil>', mimeType: 'image/svg+xml' }), /normalized/);
  await assert.rejects(app.controller.upload({ data: 'a'.repeat(400_000), mimeType: 'image/webp' }), /normalized/);
  assert.deepEqual(await app.controller.ensure(), custom);
  assert.equal(calls, 0);
});
