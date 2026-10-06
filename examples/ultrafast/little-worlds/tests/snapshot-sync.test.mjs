import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { transform } from 'esbuild';

const { code } = await transform(await readFile(new URL('../src/snapshot-sync.ts', import.meta.url), 'utf8'), { loader: 'ts', format: 'esm' });
const { createSnapshotRefresher, mergeCanvasEvents, selectCanvasUpdate } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const event = (id, type = 'turn.started', data = {}, turnId = 'turn-1') => ({ id: String(id), type, data, turnId, time: new Date().toISOString(), title: type });
const snapshot = (events = [], revision = 1, status = 'running', turnId = 'turn-1') => ({ events, revision: { id: revision }, session: { status, turns: turnId ? [{ id: turnId, status }] : [] } });
const deferred = () => { let resolve; let reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };

test('ledger replay and duplicate invalidations coalesce into one snapshot load', async () => {
  const pending = deferred(); let loads = 0; const applied = [];
  const refresher = createSnapshotRefresher(() => { loads++; return pending.promise; }, value => applied.push(value), assert.fail);
  const done = refresher.request();
  for (let id = 1; id <= 150; id++) refresher.request(id);
  await Promise.resolve();
  assert.equal(loads, 1);
  pending.resolve(snapshot([event(150)])); await done;
  await refresher.request(149);
  assert.equal(loads, 1);
  assert.equal(applied.length, 1);
});

test('an event arriving during a snapshot load cannot be lost', async () => {
  const first = deferred(); const second = deferred(); let loads = 0; const applied = [];
  const refresher = createSnapshotRefresher(() => ++loads === 1 ? first.promise : second.promise, value => applied.push(value), assert.fail);
  const done = refresher.request(10); await Promise.resolve();
  refresher.request(11); refresher.request(12);
  first.resolve(snapshot([event(10)])); await Promise.resolve();
  assert.equal(loads, 2);
  second.resolve(snapshot([event(12)])); await done;
  assert.deepEqual(applied.map(value => value.events[0].id), ['10', '12']);
});

test('a response that already includes the latest commit skips a trailing load', async () => {
  const pending = deferred(); let loads = 0;
  const refresher = createSnapshotRefresher(() => { loads++; return pending.promise; }, () => {}, assert.fail);
  const done = refresher.request(10); await Promise.resolve();
  refresher.request(11); refresher.request(12);
  pending.resolve(snapshot([event(12)])); await done;
  assert.equal(loads, 1);
});

test('explicit actions during a pending read receive a fresh follow-up snapshot', async () => {
  const first = deferred(); const second = deferred(); let loads = 0;
  const refresher = createSnapshotRefresher(() => ++loads === 1 ? first.promise : second.promise, () => {}, assert.fail);
  const done = refresher.request(); await Promise.resolve();
  refresher.request();
  first.resolve(snapshot()); await Promise.resolve();
  assert.equal(loads, 2);
  second.resolve(snapshot()); await done;
});

test('failed loads stop retrying until invalidated, and disposal ignores pending results', async () => {
  const pending = deferred(); let loads = 0; let applied = 0; const errors = [];
  const refresher = createSnapshotRefresher(() => ++loads === 1 ? Promise.reject(new Error('offline')) : pending.promise, () => applied++, error => errors.push(error.message));
  await refresher.request(10);
  assert.equal(loads, 1); assert.deepEqual(errors, ['offline']);
  const retry = refresher.request(); await Promise.resolve();
  assert.equal(loads, 2);
  refresher.dispose(); pending.resolve(snapshot([event(10)])); await retry;
  await refresher.request(11);
  assert.equal(applied, 0); assert.equal(loads, 2);
});

test('a published draft stays visible until the matching rendered revision arrives', () => {
  const started = event(1); const draft = event(2, 'draft.preview', { html: '<p>Blue spaceship</p>' });
  const published = event(3, 'revision.published', { revisionId: 2 });
  const completed = event(4, 'turn.completed', { revisionId: 2 });
  const stale = snapshot([started]);
  assert.equal(selectCanvasUpdate(stale, [started, draft, published]).draft, draft);
  const completedBeforeRender = selectCanvasUpdate(stale, [started, draft, published, completed]);
  assert.equal(completedBeforeRender.running, false);
  assert.equal(completedBeforeRender.draft, draft);
  // The completion record may arrive after an already-current published render.
  const current = snapshot([started, draft, published], 2);
  assert.equal(selectCanvasUpdate(current, [started, draft, published, completed]).draft, undefined);
});

test('failed, cancelled, reset, and restart-recovered turns discard unpublished previews', () => {
  const started = event(1); const draft = event(2, 'draft.preview', { html: '<p>Unverified</p>' });
  for (const terminal of [event(3, 'turn.failed'), event(3, 'turn.cancelled'), { ...event(3, 'turn.cancelled'), turnId: undefined }, event(3, 'space.updated', { reset: true })]) {
    const result = selectCanvasUpdate(snapshot([started]), [started, draft, terminal]);
    assert.equal(result.draft, undefined, terminal.type);
    assert.equal(result.running, false, terminal.type);
  }
});

test('accepted turns and steering remain busy before their next snapshot arrives', () => {
  const before = snapshot([], 1, 'idle', null);
  assert.equal(selectCanvasUpdate(before, [], 'turn-1').running, true);
  const started = event(1); const draft = event(2, 'draft.preview', { html: '<p>Working</p>' });
  assert.equal(selectCanvasUpdate(before, [started, draft], 'turn-1').running, true);
  assert.equal(selectCanvasUpdate(before, [started, draft], 'turn-1').draft, draft);
  const completed = event(3, 'turn.completed', { revisionId: 2 });
  assert.equal(selectCanvasUpdate(snapshot([completed], 2, 'idle'), [started, draft, completed], 'turn-1').running, false);
});

test('a reset snapshot cannot revive an earlier published draft from the retained event history', () => {
  const old = [event(1), event(2, 'draft.preview', { html: '<p>Previous page</p>' }), event(3, 'revision.published', { revisionId: 5 }), event(4, 'turn.completed', { revisionId: 5 })];
  const reset = event(5, 'space.updated', { reset: true });
  assert.equal(selectCanvasUpdate(snapshot([reset], 1, 'idle', null), [...old, reset]).draft, undefined);
  const fresh = event(6, 'turn.started', {}, 'turn-2');
  const draft = event(7, 'draft.preview', { html: '<p>Fresh page</p>' }, 'turn-2');
  const result = selectCanvasUpdate(snapshot([reset], 1, 'idle', null), [...old, reset, fresh, draft]);
  assert.equal(result.running, true);
  assert.equal(result.draft, draft);
});

test('starting the next turn retains the preceding published draft until its snapshot arrives', () => {
  const started = event(1); const draft = event(2, 'draft.preview', { html: '<p>Published blue ship</p>' });
  const published = event(3, 'revision.published', { revisionId: 2 });
  const completed = event(4, 'turn.completed', { revisionId: 2 });
  const next = event(5, 'turn.started', {}, 'turn-2');
  const history = [started, draft, published, completed, next];
  assert.equal(selectCanvasUpdate(snapshot([started]), history).draft, draft);
  const nextDraft = event(6, 'draft.preview', { html: '<p>Newer purple ship</p>' }, 'turn-2');
  assert.equal(selectCanvasUpdate(snapshot([started]), [...history, nextDraft]).draft, nextDraft);
  assert.equal(selectCanvasUpdate(snapshot([published], 2), history).draft, undefined);
});

test('accepting a new turn never revives the prior rejected draft', () => {
  const started = event(1); const draft = event(2, 'draft.preview', { html: '<p>Rejected page</p>' });
  for (const type of ['turn.failed', 'turn.cancelled']) {
    const result = selectCanvasUpdate(snapshot([started]), [started, draft, event(3, type)], 'turn-2');
    assert.equal(result.running, true);
    assert.equal(result.draft, undefined);
  }
});

test('event batches deduplicate and sort only canvas-affecting events', () => {
  const started = event(1); const draft = event(3, 'draft.preview', { html: '<p>New</p>' });
  assert.deepEqual(mergeCanvasEvents([started], [draft, event(2, 'model.delta'), started]), [started, draft]);
});
