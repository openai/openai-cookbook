import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { createSpaceService } from '../server/harness.mjs';

const source = (heading = 'Shared notebook') => `export const meta={title:${JSON.stringify(heading)},subtitle:'',accent:'#00b85a',layout:'canvas'};
export function render(state){return '<h1>'+meta.title+'</h1><p>'+Object.keys(state.extras.notes||{}).length+' notes</p>'}
export function reduce(state,action,actor){
 if(action.type!=='note'||typeof action.text!=='string'||!action.text.trim())throw Error('Write a note');
 state.extras.notes={...(state.extras.notes||{}),[actor.id]:{actorId:actor.id,text:action.text.trim()}};return state;
}`;
const checks = `export function runTests(api){
 const actor={id:'comparison-test-person',name:'Test visitor'};
 const next=api.reduce(api.initialState,{type:'note',text:'Hello'},actor);
 return [
 {name:'Visitors can leave a note',ok:next.extras.notes[actor.id].text==='Hello'},
 {name:'Existing notes survive',ok:Object.entries(api.initialState.extras.notes||{}).every(([id,note])=>JSON.stringify(next.extras.notes[id])===JSON.stringify(note))},
 {name:'The notebook renders',ok:api.render(next,actor).includes('notes')}
 ];
}`;
const seedOverride = { source: source(), tests: checks, state: { projects: [], contributions: [], extras: {} } };
const addFile = (name, text) => `*** Add File: ${name}\n${text.split('\n').map(line => `+${line}`).join('\n')}`;
const patch = heading => ['*** Begin Patch', addFile('space.js', source(heading)), addFile('tests.js', checks), '*** End Patch'].join('\n');
const response = (heading, tier = 'ultrafast') => ({ model: 'comparison-fixture', service_tier: tier, output: [
  { type: 'custom_tool_call', id: `item-${heading}`, call_id: `call-${heading}`, name: 'apply_patch', input: patch(heading) },
], metrics: { durationMs: 12, ttftMs: 1, outputTokens: 120, servedTier: tier } });
const adapter = (respond, tier = 'ultrafast') => ({ keyAvailable: true, model: 'comparison-fixture', tier, respond });
const gate = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const options = { timeout: 15000 };

async function until(read, predicate, message = 'Expected comparison state') {
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    const value = await read();
    if (predicate(value)) return value;
    await delay(5);
  }
  assert.fail(`${message}: ${JSON.stringify(await read())}`);
}

function gatedProvider(t, heading, tier = 'ultrafast') {
  const entered = gate(); const release = gate(); const requests = [];
  let closeCalls = 0;
  t.after(() => release.resolve());
  const configured = adapter(async request => {
    requests.push(request);
    request.onEvent({ type: 'response.output_item.added', output_index: 0, item: { type: 'message', id: `text-${heading}`, role: 'assistant', content: [] } });
    request.onEvent({ type: 'response.output_text.delta', output_index: 0, item_id: `text-${heading}`, content_index: 0, delta: `Building ${heading}.` });
    entered.resolve();
    await Promise.race([release.promise, new Promise((_, reject) => {
      if (request.signal.aborted) reject(request.signal.reason);
      else request.signal.addEventListener('abort', () => reject(request.signal.reason), { once: true });
    })]);
    request.signal.throwIfAborted();
    return response(heading, tier);
  }, tier);
  configured.close = async () => { closeCalls++; };
  return { entered, release, requests, adapter: configured, get closeCalls() { return closeCalls; } };
}

async function setup(t, primaryAdapter, comparisonAdapter) {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-comparison-'));
  const service = await createSpaceService({ dataDir, seedOverride, adapter: primaryAdapter, comparisonAdapter });
  t.after(async () => { await service.close(); await rm(dataDir, { recursive: true, force: true }); });
  return { service, dataDir };
}
const state = service => () => service.comparison.read();
const complete = lane => lane?.status === 'completed';

test('comparison starts both providers before either finishes and supplies identical full context', options, async t => {
  const fast = gatedProvider(t, 'Fast notebook');
  const standard = gatedProvider(t, 'Standard notebook', 'default');
  let first = true;
  let initialRequest;
  const primary = adapter(request => {
    if (first) { first = false; initialRequest = request; return response('Previous notebook'); }
    return fast.adapter.respond(request);
  }, 'default');
  let connectionResets = 0;
  primary.resetConnection = () => { connectionResets++; };
  const { service } = await setup(t, primary, standard.adapter);
  await service.submit('Make the first notebook');
  await service.waitForIdle();
  assert.equal(connectionResets, 0, 'Ordinary builds retain their connection reuse');
  await service.action({ actor: 'leo', revisionId: 2, action: { type: 'note', text: 'Already here' } });
  const history = structuredClone(service.store.read().session.items);
  const submitted = await service.submit('Brighten the notebook', { compare: true });
  await Promise.all([fast.entered.promise, standard.entered.promise]);
  assert.equal(connectionResets, 1, 'Comparisons remove any warm-connection advantage for the primary');
  assert.ok(submitted.comparisonId);
  const comparison = service.comparison.read();
  assert.equal(comparison.id, submitted.comparisonId);
  assert.equal(comparison.primaryTurnId, submitted.turnId);
  assert.equal(comparison.finished, false);
  assert.equal(comparison.model, 'comparison-fixture');
  assert.equal(comparison.ultrafast.status, 'running');
  assert.equal(comparison.standard.status, 'running');
  const left = fast.requests[0]; const right = standard.requests[0];
  assert.equal(left.tier, 'ultrafast', 'Comparison overrides the primary adapter default tier');
  assert.equal(right.tier, 'default');
  assert.equal(left.timeoutMs, 300_000, 'Both lanes get enough time for standard generation');
  assert.equal(right.timeoutMs, left.timeoutMs);
  assert.equal(initialRequest.timeoutMs, undefined, 'Normal builds retain their adapter timeout');
  assert.deepEqual(left.input, right.input, 'Both lanes receive exactly the same conversation and initial source/state');
  assert.deepEqual(left.input.slice(0, history.length), history, 'Prior tool calls and outputs remain in context');
  assert.deepEqual(left.tools, right.tools);
  assert.equal(left.instructions, right.instructions);
  assert.equal(left.cacheKey, right.cacheKey);
  assert.notEqual(left.signal, right.signal, 'Each lane can be cancelled independently');
  assert.match(JSON.stringify(left.input), /Already here/);
  fast.release.resolve(); standard.release.resolve();
  await until(state(service), value => complete(value?.ultrafast) && complete(value?.standard));
  assert.equal(fast.requests.length, 1);
  assert.equal(standard.requests.length, 1);
});

test('the standard build never publishes to the live world and live visitor edits survive primary publication', options, async t => {
  const fast = gatedProvider(t, 'FAST_PUBLISHED_WORLD');
  const standard = gatedProvider(t, 'STANDARD_PRIVATE_WORLD', 'default');
  const { service, dataDir } = await setup(t, fast.adapter, standard.adapter);
  const submitted = await service.submit('Make both notebooks', { compare: true });
  await Promise.all([fast.entered.promise, standard.entered.promise]);
  await service.action({ actor: 'leo', revisionId: 1, action: { type: 'note', text: 'Arrived while building' } });
  standard.release.resolve();
  await until(state(service), value => complete(value?.standard));
  let live = await service.snapshot('leo');
  assert.equal(live.revision.id, 1, 'Standard completing first cannot change the live revision');
  assert.doesNotMatch(live.html, /STANDARD_PRIVATE_WORLD/);
  await assert.rejects(service.finishComparison(submitted.comparisonId), error => error.status === 409);
  fast.release.resolve();
  await service.waitForIdle();
  await until(state(service), value => complete(value?.ultrafast));
  live = await service.snapshot('leo');
  assert.equal(live.revision.id, 2);
  assert.match(live.html, /FAST_PUBLISHED_WORLD/);
  assert.equal(live.state.extras.notes.leo.text, 'Arrived while building');
  assert.doesNotMatch(JSON.stringify(live), /STANDARD_PRIVATE_WORLD/);
  assert.doesNotMatch(await readFile(join(dataDir, 'space.json'), 'utf8'), /STANDARD_PRIVATE_WORLD/);
  await until(state(service), value => value?.standard.html?.includes('STANDARD_PRIVATE_WORLD'));
  await until(() => standard.closeCalls, count => count === 1, 'Completed companion closes automatically');
  assert.equal(service.comparison.read().standard.status, 'completed', 'Cleanup keeps comparison metadata');
  assert.match(JSON.stringify(service.getComparisonActivity(submitted.comparisonId).read()), /STANDARD_PRIVATE_WORLD/);
  assert.doesNotMatch(JSON.stringify(service.activity.read()), /STANDARD_PRIVATE_WORLD/);
});

test('Finish build cancels only unfinished standard work and preserves the completed primary', options, async t => {
  const fast = gatedProvider(t, 'Finished fast');
  const standard = gatedProvider(t, 'Still standard', 'default');
  const { service } = await setup(t, fast.adapter, standard.adapter);
  const submitted = await service.submit('Create a notebook', { compare: true });
  await Promise.all([fast.entered.promise, standard.entered.promise]);
  fast.release.resolve();
  await until(state(service), value => complete(value?.ultrafast));
  const before = await service.snapshot();
  await service.finishComparison(submitted.comparisonId);
  const finished = await until(state(service), value => value?.finished && value.standard.status === 'cancelled');
  await until(() => standard.closeCalls, count => count === 1, 'Finish closes the standard companion');
  assert.equal(finished.ultrafast.status, 'completed');
  assert.equal(standard.requests[0].signal.aborted, true);
  assert.equal(fast.requests[0].signal.aborted, false);
  assert.deepEqual((await service.snapshot()).revision, before.revision);
  assert.match(JSON.stringify(service.getComparisonActivity(submitted.comparisonId).read()), /Still standard/, 'Sanitized replay survives companion cleanup');
  await service.finishComparison(submitted.comparisonId);
  assert.deepEqual((await service.snapshot()).revision, before.revision, 'Repeated finish is harmless');
  await assert.rejects(service.finishComparison('not-this-comparison'), error => error.status === 404);
});

test('active comparisons reject one-sided steering and a new build replaces leftover standard work after ultrafast finishes', options, async t => {
  const fast = gatedProvider(t, 'First fast');
  const standard = gatedProvider(t, 'First standard', 'default');
  const { service } = await setup(t, fast.adapter, standard.adapter);
  const submitted = await service.submit('Original comparison request', { compare: true });
  await Promise.all([fast.entered.promise, standard.entered.promise]);
  for (const submitOptions of [{ compare: true }, {}]) {
    await assert.rejects(service.submit('FOLLOW_UP_MUST_NOT_BE_CONSUMED', submitOptions), error => error.status === 409);
  }
  assert.equal(service.comparison.read().id, submitted.comparisonId);
  assert.equal(service.store.read().session.turns.length, 1);
  assert.doesNotMatch(JSON.stringify(service.store.read()), /FOLLOW_UP_MUST_NOT_BE_CONSUMED/);
  fast.release.resolve();
  await until(state(service), value => complete(value?.ultrafast));
  await service.waitForIdle();
  const replacement = await service.submit('Another prompt while standard runs', { compare: true });
  await until(() => [fast.requests.length, standard.requests.length], value => value[0] === 2 && value[1] === 2);
  assert.notEqual(replacement.comparisonId, submitted.comparisonId);
  assert.equal(standard.requests[0].signal.aborted, true);
  assert.equal(standard.requests[1].signal.aborted, false);
  assert.deepEqual(fast.requests[1].input, standard.requests[1].input);
  assert.match(JSON.stringify(standard.requests[1].input), /First fast/);
  assert.throws(() => service.getComparisonActivity(submitted.comparisonId), error => error.status === 404);
  standard.release.resolve();
  await until(state(service), value => complete(value?.ultrafast) && complete(value?.standard));
});

test('a plain submit waiting on cleanup cannot erase or steer a newer comparison', options, async t => {
  const fast = gatedProvider(t, 'Primary result before cleanup');
  const standard = gatedProvider(t, 'Standard waiting during cleanup', 'default');
  const closing = gate(); const releaseClose = gate();
  let closeCount = 0;
  standard.adapter.close = async () => {
    if (++closeCount === 1) { closing.resolve(); await releaseClose.promise; }
  };
  t.after(() => releaseClose.resolve());
  const { service } = await setup(t, fast.adapter, standard.adapter);
  await service.submit('The initial comparison', { compare: true });
  await Promise.all([fast.entered.promise, standard.entered.promise]);
  fast.release.resolve();
  await service.waitForIdle();
  await until(state(service), value => complete(value?.ultrafast));
  const before = structuredClone(service.store.read());

  // The plain submit has passed its first guard and is now waiting for an
  // asynchronous provider close. A comparison acquires the slot while it waits.
  const plainOutcome = service.submit('PLAIN_REQUEST_MUST_NOT_ENTER_CONTEXT').then(result => ({ result }), error => ({ error }));
  await closing.promise;
  const nextComparison = service.submit('The next comparison', { compare: true });
  assert.equal(service.busy, true);
  await assert.rejects(service.reset(), error => error.status === 409);
  await assert.rejects(service.restore(1), error => error.status === 409);
  assert.deepEqual(service.store.read(), before, 'Reset and restore cannot mutate the captured baseline during preparation');

  releaseClose.resolve();
  const [{ error }, accepted] = await Promise.all([plainOutcome, nextComparison]);
  assert.ok(error, 'The stale plain submission is rejected');
  assert.equal(error.status, 409);
  await until(() => [fast.requests.length, standard.requests.length], counts => counts[0] === 2 && counts[1] === 2);
  assert.equal(service.comparison.read().id, accepted.comparisonId);
  assert.equal(service.comparison.read().primaryTurnId, accepted.turnId);
  assert.deepEqual(fast.requests[1].input, standard.requests[1].input);
  assert.doesNotMatch(JSON.stringify(fast.requests[1].input), /PLAIN_REQUEST_MUST_NOT_ENTER_CONTEXT/);
  assert.doesNotMatch(JSON.stringify(service.store.read()), /PLAIN_REQUEST_MUST_NOT_ENTER_CONTEXT/);
  assert.match(JSON.stringify(standard.requests[1].input), /Primary result before cleanup/);
  assert.equal(standard.requests[0].signal.aborted, true);
  assert.equal(standard.requests[1].signal.aborted, false);
  standard.release.resolve();
  await until(state(service), value => complete(value?.ultrafast) && complete(value?.standard));
});

test('a failed standard build does not fail a successful primary', options, async t => {
  const fast = gatedProvider(t, 'Fast survived');
  const { service } = await setup(t, fast.adapter, adapter(async () => { throw new Error('Standard fixture unavailable'); }, 'default'));
  const submitted = await service.submit('Build a notebook', { compare: true });
  await fast.entered.promise;
  const failed = await until(state(service), value => value?.standard.status === 'failed');
  assert.match(failed.standard.error, /Standard fixture unavailable/);
  fast.release.resolve();
  await until(state(service), value => complete(value?.ultrafast));
  assert.equal((await service.snapshot()).session.lastOutcome, 'completed');
  assert.match((await service.snapshot()).html, /Fast survived/);
  await service.finishComparison(submitted.comparisonId);
});

test('a failed primary never substitutes the standard world into the live revision', options, async t => {
  const standard = gatedProvider(t, 'Standard cannot replace primary', 'default');
  const { service } = await setup(t, adapter(async () => { throw new Error('Primary fixture unavailable'); }), standard.adapter);
  const submitted = await service.submit('Build a notebook', { compare: true });
  await standard.entered.promise;
  standard.release.resolve();
  const failed = await until(state(service), value => value?.ultrafast.status === 'failed' && complete(value.standard));
  assert.match(failed.ultrafast.error, /Primary fixture unavailable/);
  assert.equal((await service.snapshot()).revision.id, 1);
  await service.finishComparison(submitted.comparisonId);
  assert.equal(service.comparison.read().finished, true, 'A failed comparison can be dismissed');
  assert.equal((await service.snapshot()).revision.id, 1, 'Dismissing failure preserves the last working world');
});

test('cancelling the active build cancels both comparison lanes', options, async t => {
  const fast = gatedProvider(t, 'Cancelled fast');
  const standard = gatedProvider(t, 'Cancelled standard', 'default');
  const { service } = await setup(t, fast.adapter, standard.adapter);
  await service.submit('Build a notebook', { compare: true });
  await Promise.all([fast.entered.promise, standard.entered.promise]);
  await service.cancel();
  const cancelled = await until(state(service), value => value?.ultrafast.status === 'cancelled' && value.standard.status === 'cancelled');
  assert.ok(cancelled.ultrafast.endedAt);
  assert.ok(cancelled.standard.endedAt);
  assert.equal(fast.requests[0].signal.aborted, true);
  assert.equal(standard.requests[0].signal.aborted, true);
  assert.equal((await service.snapshot()).revision.id, 1);
});

test('cancelling synchronously at comparison preparation closes the unused companion immediately', options, async t => {
  const fast = gatedProvider(t, 'Never started fast');
  const standard = gatedProvider(t, 'Never started standard', 'default');
  const { service } = await setup(t, fast.adapter, standard.adapter);
  let cancelResult;
  let cancelled = false;
  const unsubscribe = service.comparison.subscribe(event => {
    const comparison = event.data?.comparison;
    if (cancelled || comparison?.ultrafast.status !== 'preparing') return;
    cancelled = true;
    cancelResult = service.cancel();
  });
  t.after(unsubscribe);

  await assert.rejects(service.submit('Cancel before either provider starts', { compare: true }), error => error.name === 'AbortError');
  assert.equal((await cancelResult).cancelled, true);
  const comparison = service.comparison.read();
  assert.equal(comparison.ultrafast.status, 'cancelled');
  assert.equal(comparison.standard.status, 'cancelled');
  assert.equal(fast.requests.length, 0);
  assert.equal(standard.requests.length, 0);
  assert.equal(standard.closeCalls, 1, 'Cleanup happens before another build or service.close is needed');
  assert.equal(fast.closeCalls, 0, 'The primary service remains usable');
  assert.equal(service.busy, false);
  assert.equal(service.store.read().session.turns.length, 0);
  assert.equal((await service.snapshot()).revision.id, 1);
});

test('closing a space stops both providers and cannot publish delayed output', options, async t => {
  const fast = gatedProvider(t, 'Closed fast');
  const standard = gatedProvider(t, 'Closed standard', 'default');
  const { service } = await setup(t, fast.adapter, standard.adapter);
  await service.submit('Build a notebook', { compare: true });
  await Promise.all([fast.entered.promise, standard.entered.promise]);
  await service.close();
  assert.equal(fast.requests[0].signal.aborted, true);
  assert.equal(standard.requests[0].signal.aborted, true);
  fast.release.resolve(); standard.release.resolve();
  assert.equal(service.store.read().currentRevisionId, 1);
});

test('plain builds retain the original single-provider behavior', options, async t => {
  let standardCalls = 0;
  let request;
  const { service } = await setup(t, adapter(async value => { request = value; return response('Single build'); }), adapter(async () => { standardCalls++; return response('Unused', 'default'); }, 'default'));
  const submitted = await service.submit('Make a notebook');
  await service.waitForIdle();
  assert.equal(submitted.comparisonId, undefined);
  assert.equal(standardCalls, 0);
  assert.equal(service.comparison.read(), null);
  assert.equal(request.timeoutMs, undefined);
  assert.equal((await service.snapshot()).revision.id, 2);
});

test('an injected primary adapter never falls back to a paid standard provider implicitly', options, async t => {
  let calls = 0;
  const { service } = await setup(t, adapter(async () => { calls++; return response('Offline fixture'); }), undefined);
  const submitted = await service.submit('Build using only the test adapter', { compare: true });
  const result = await until(state(service), value => complete(value?.ultrafast) && value.standard.status === 'failed');
  assert.match(result.standard.error, /adapter is not configured/i);
  assert.equal(calls, 1);
  assert.equal((await service.snapshot()).revision.id, 2);
  await service.finishComparison(submitted.comparisonId);
});
