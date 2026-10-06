import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { createSpaceService } from '../server/harness.mjs';

const source = (title = 'Progress notebook') => `export const meta={title:${JSON.stringify(title)},subtitle:'',accent:'#00b85a',layout:'canvas'};
export function render(state){return '<h1>'+meta.title+'</h1><p>'+Object.keys(state.extras.notes||{}).length+' notes</p>'}
export function reduce(state,action,actor){
 if(action.type!=='note'||typeof action.text!=='string'||!action.text.trim())throw Error('Write a note');
 state.extras.notes={...(state.extras.notes||{}),[actor.id]:{actorId:actor.id,text:action.text.trim()}};return state;
}`;
const checks = `// PROGRESS_TEST_SOURCE_MARKER
export function runTests(api){
 const actor={id:'progress-test-person',name:'Test visitor'};
 const next=api.reduce(api.initialState,{type:'note',text:'Hello'},actor);
 return [
 {name:'Visitors can leave a note',ok:next.extras.notes[actor.id].text==='Hello'},
 {name:'Existing notes survive',ok:Object.entries(api.initialState.extras.notes||{}).every(([id,note])=>JSON.stringify(next.extras.notes[id])===JSON.stringify(note))},
 {name:'The notebook renders',ok:api.render(next,actor).includes('notes')}
 ];
}`;
const seedOverride = { source: source(), tests: checks, state: { projects: [], contributions: [], extras: {
  notes: { leo: { actorId: 'leo', text: 'PUBLIC_RECORD_CONTENT_MUST_NOT_REACH_ESTIMATOR' } },
} } };
const addFile = (name, text) => `*** Add File: ${name}\n${text.split('\n').map(line => `+${line}`).join('\n')}`;
const response = title => ({ model: 'progress-fixture', output: [
  { type: 'custom_tool_call', id: `item-${title}`, call_id: `call-${title}`, name: 'apply_patch', input:
    ['*** Begin Patch', addFile('space.js', source(title)), addFile('tests.js', checks), '*** End Patch'].join('\n') },
] });
const gate = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const options = { timeout: 15000 };

async function until(read, predicate, message = 'Expected build progress state') {
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    const value = await read();
    if (predicate(value)) return value;
    await delay(5);
  }
  assert.fail(`${message}: ${JSON.stringify(await read())}`);
}

function builder(t, tier) {
  const calls = [];
  t.after(() => calls.forEach(call => call.release.resolve()));
  return { calls, adapter: { keyAvailable: true, model: 'progress-fixture', tier, respond: async request => {
    const release = gate();
    calls.push({ request, release });
    await Promise.race([release.promise, new Promise((_, reject) => {
      if (request.signal.aborted) reject(request.signal.reason);
      else request.signal.addEventListener('abort', () => reject(request.signal.reason), { once: true });
    })]);
    request.signal.throwIfAborted();
    return response(`${tier} notebook ${calls.length}`);
  } } };
}

function deferredEstimator(t) {
  const calls = [];
  t.after(() => calls.forEach(call => call.result.resolve({ expectedOutputTokens: 2048 })));
  return { calls, estimate: request => {
    const result = gate();
    calls.push({ ...request, result });
    // Deliberately ignore abort to model a provider whose result arrives late.
    return result.promise;
  } };
}

async function setup(t, extra = {}) {
  const fast = builder(t, 'ultrafast');
  const standard = builder(t, 'default');
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-build-progress-'));
  const service = await createSpaceService({ dataDir, seedOverride, adapter: fast.adapter, comparisonAdapter: standard.adapter, ...extra });
  t.after(async () => { await service.close(); await rm(dataDir, { recursive: true, force: true }); });
  return { service, fast, standard };
}
async function bothStarted(fast, standard, count = 1) {
  await until(() => [fast.calls.length, standard.calls.length], counts => counts[0] === count && counts[1] === count, 'Both builders must start');
}
const readProgress = service => () => service.comparison.read()?.progress;
const complete = lane => lane?.status === 'completed';
const flushLateResults = async () => { await delay(0); await delay(0); };
const assertValidDenominator = value => assert.ok(Number.isInteger(value) && value >= 128 && value <= 128000,
  'A fallback must use a finite, positive, bounded token estimate');

test('the real builder adapters send a 16,000-token allowance in both comparison lanes', options, async t => {
  const previousTransport = process.env.LITTLE_WORLDS_TRANSPORT;
  process.env.LITTLE_WORLDS_TRANSPORT = 'http';
  t.after(() => {
    if (previousTransport === undefined) delete process.env.LITTLE_WORLDS_TRANSPORT;
    else process.env.LITTLE_WORLDS_TRANSPORT = previousTransport;
  });
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    const body = JSON.parse(options.body);
    requests.push(body);
    return new Response(`data: ${JSON.stringify({ type: 'response.completed', response: {
      status: 'completed', ...response(`${body.service_tier} notebook`),
    } })}\n\n`);
  });
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-builder-budget-'));
  const service = await createSpaceService({ dataDir, seedOverride, apiKey: 'test-only',
    model: 'gpt-6-astra', progressEstimator: async () => ({ expectedOutputTokens: 2048 }) });
  t.after(async () => { await service.close(); await rm(dataDir, { recursive: true, force: true }); });
  await service.submit('Build a brighter notebook', { compare: true });
  await until(() => service.comparison.read(), value => complete(value?.ultrafast) && complete(value?.standard));
  assert.equal(requests.length, 2);
  assert.deepEqual(requests.map(request => request.service_tier).sort(), ['default', 'ultrafast']);
  for (const request of requests) {
    assert.equal(request.max_output_tokens, 16000);
    assert.deepEqual(request.reasoning, { effort: 'low' });
  }
});

test('progress estimation never blocks either builder and uses one bounded, record-free initial context', options, async t => {
  const estimator = deferredEstimator(t);
  const { service, fast, standard } = await setup(t, { progressEstimator: estimator.estimate });
  await service.store.transact(data => {
    data.session.turns = ['OLD_REQUEST_OUTSIDE_WINDOW', 'Create a notebook', 'A long owner request '.repeat(50), 'Make it glow'].map((message, index) =>
      ({ id: `earlier-turn-${index}`, message, status: 'completed', startedAt: new Date().toISOString() }));
    data.session.items = [{ role: 'assistant', content: 'PRIVATE_ASSISTANT_HISTORY_MUST_NOT_REACH_ESTIMATOR' }];
  });
  const prompt = 'Build a brighter shared notebook';
  const submitted = await service.submit(prompt, { compare: true });
  await bothStarted(fast, standard);
  await until(() => estimator.calls.length, count => count === 1);
  assert.equal(service.comparison.read().id, submitted.comparisonId);
  assert.equal(service.comparison.read().progress.status, 'pending');
  assert.equal(service.comparison.read().ultrafast.status, 'running');
  assert.equal(service.comparison.read().standard.status, 'running');
  const { context, signal } = estimator.calls[0];
  assert.equal(context.prompt, prompt);
  assert.equal(context.builder.model, 'progress-fixture');
  assert.equal(context.builder.reasoningEffort, 'low');
  assert.equal(context.builder.maxRounds, 8);
  assert.equal(context.builder.maxOutputTokensPerRound, 16000);
  assert.equal(typeof context.builder.requirements, 'string');
  assert.equal(context.workspace.source.sample, source());
  assert.equal(context.workspace.source.characters, source().length);
  assert.equal(context.workspace.tests.sample, checks);
  assert.equal(context.workspace.tests.characters, checks.length);
  assert.equal(context.workspace.source.truncated, false);
  assert.equal(context.workspace.tests.truncated, false);
  assert.equal(context.workspace.state.projectCount, 0);
  assert.equal(context.workspace.state.contributionCount, 0);
  assert.ok(context.workspace.state.extraRecordCount > 0);
  assert.equal(context.recentOwnerRequests.length, 3);
  assert.equal(context.recentOwnerRequests[0], 'Create a notebook');
  assert.equal(context.recentOwnerRequests[1].length, 600);
  assert.equal(context.recentOwnerRequests[2], 'Make it glow');
  assert.doesNotMatch(JSON.stringify(context), /OLD_REQUEST_OUTSIDE_WINDOW|PRIVATE_ASSISTANT_HISTORY_MUST_NOT_REACH_ESTIMATOR/);
  assert.doesNotMatch(JSON.stringify(context), /PUBLIC_RECORD_CONTENT_MUST_NOT_REACH_ESTIMATOR/);
  const capturedContext = structuredClone(context);
  await service.action({ actor: 'leo', revisionId: 1, action: { type: 'note', text: 'NEW_PUBLIC_RECORD_CONTENT' } });
  assert.deepEqual(context, capturedContext, 'Later visitor state cannot mutate the estimate context');
  assert.equal(signal.aborted, false);

  estimator.calls[0].result.resolve({ expectedOutputTokens: 4096 });
  const progress = await until(readProgress(service), value => value?.status === 'ready');
  assert.equal(progress.expectedOutputTokens, 4096);
  fast.calls[0].release.resolve(); standard.calls[0].release.resolve();
  await until(() => service.comparison.read(), value => complete(value?.ultrafast) && complete(value?.standard));
  assert.equal(estimator.calls.length, 1, 'The denominator is estimated once per comparison');
  assert.equal(service.comparison.read().progress.expectedOutputTokens, 4096);
});

test('an invalid estimate falls back without stopping the accepted builders', options, async t => {
  for (const expectedOutputTokens of [127, 128001, 2048.5, '2048', NaN, Infinity, null, undefined]) {
    await t.test(String(expectedOutputTokens), async subtest => {
      const { service, fast, standard } = await setup(subtest, { progressEstimator: async () => ({ expectedOutputTokens }) });
      await service.submit('Build a notebook', { compare: true });
      await bothStarted(fast, standard);
      const progress = await until(readProgress(service), value => value?.status === 'fallback');
      assertValidDenominator(progress.expectedOutputTokens);
      assert.equal(fast.calls[0].request.signal.aborted, false);
      assert.equal(standard.calls[0].request.signal.aborted, false);
    });
  }
});

test('the valid estimate bounds are accepted exactly', options, async t => {
  for (const expectedOutputTokens of [128, 128000]) {
    await t.test(String(expectedOutputTokens), async subtest => {
      const { service, fast, standard } = await setup(subtest, { progressEstimator: async () => ({ expectedOutputTokens }) });
      await service.submit('Build a notebook', { compare: true });
      await bothStarted(fast, standard);
      const progress = await until(readProgress(service), value => value?.status === 'ready');
      assert.equal(progress.expectedOutputTokens, expectedOutputTokens);
    });
  }
});

test('a failed or timed-out estimate falls back while both builders continue', options, async t => {
  await t.test('estimator failure', async subtest => {
    const { service, fast, standard } = await setup(subtest, { progressEstimator: async () => { throw new Error('Estimator fixture failed'); } });
    await service.submit('Build a notebook', { compare: true });
    await bothStarted(fast, standard);
    const progress = await until(readProgress(service), value => value?.status === 'fallback');
    assertValidDenominator(progress.expectedOutputTokens);
    assert.equal(fast.calls[0].request.signal.aborted, false);
    assert.equal(standard.calls[0].request.signal.aborted, false);
  });
  await t.test('deadline and late success', async subtest => {
    const estimator = deferredEstimator(subtest);
    const { service, fast, standard } = await setup(subtest, { progressEstimator: estimator.estimate, progressEstimateTimeoutMs: 25 });
    await service.submit('Build a notebook', { compare: true });
    await bothStarted(fast, standard);
    await until(() => estimator.calls.length, count => count === 1);
    await until(readProgress(service), value => value?.status === 'fallback');
    assertValidDenominator(service.comparison.read().progress.expectedOutputTokens);
    assert.equal(estimator.calls[0].signal.aborted, true);
    const fallback = structuredClone(service.comparison.read().progress);
    estimator.calls[0].result.resolve({ expectedOutputTokens: 4096 });
    await flushLateResults();
    assert.deepEqual(service.comparison.read().progress, fallback, 'A late provider result cannot replace the fallback');
    assert.equal(fast.calls[0].request.signal.aborted, false);
    assert.equal(standard.calls[0].request.signal.aborted, false);
  });
});

test('cancel, finish, shutdown and both terminal lanes abort estimation and reject its late result', options, async t => {
  for (const action of ['cancel', 'finish', 'close', 'completed']) {
    await t.test(action, async subtest => {
      const estimator = deferredEstimator(subtest);
      const { service, fast, standard } = await setup(subtest, { progressEstimator: estimator.estimate });
      const submitted = await service.submit('Build a notebook', { compare: true });
      await bothStarted(fast, standard);
      await until(() => estimator.calls.length, count => count === 1);
      if (action === 'finish' || action === 'completed') {
        fast.calls[0].release.resolve();
        await service.waitForIdle();
        await until(() => service.comparison.read(), value => complete(value?.ultrafast));
      }
      if (action === 'cancel') await service.cancel();
      else if (action === 'finish') await service.finishComparison(submitted.comparisonId);
      else if (action === 'close') await service.close();
      else {
        standard.calls[0].release.resolve();
        await until(() => service.comparison.read(), value => complete(value?.ultrafast) && complete(value?.standard));
      }
      await until(() => estimator.calls[0].signal.aborted, aborted => aborted);
      const progress = structuredClone(service.comparison.read()?.progress);
      estimator.calls[0].result.resolve({ expectedOutputTokens: 8192 });
      await flushLateResults();
      assert.deepEqual(service.comparison.read()?.progress, progress);
      if (action === 'close') assert.equal(service.comparison.read(), null);
    });
  }
});

test('an obsolete estimate cannot change the denominator of the next comparison', options, async t => {
  const estimator = deferredEstimator(t);
  const { service, fast, standard } = await setup(t, { progressEstimator: estimator.estimate });
  const first = await service.submit('Build the first notebook', { compare: true });
  await bothStarted(fast, standard);
  await until(() => estimator.calls.length, count => count === 1);
  fast.calls[0].release.resolve();
  await service.waitForIdle();
  const next = await service.submit('Refine the second notebook', { compare: true });
  await bothStarted(fast, standard, 2);
  await until(() => estimator.calls.length, count => count === 2);
  assert.notEqual(next.comparisonId, first.comparisonId);
  assert.equal(estimator.calls[0].signal.aborted, true);
  estimator.calls[0].result.resolve({ expectedOutputTokens: 128 });
  await flushLateResults();
  assert.equal(service.comparison.read().progress.status, 'pending');
  estimator.calls[1].result.resolve({ expectedOutputTokens: 5000 });
  const ready = await until(readProgress(service), value => value?.status === 'ready');
  assert.equal(ready.expectedOutputTokens, 5000);
  assert.equal(service.comparison.read().id, next.comparisonId);
  assert.equal(estimator.calls[1].context.prompt, 'Refine the second notebook');
  assert.match(estimator.calls[1].context.workspace.source.sample, /ultrafast notebook 1/);
});

test('injected builders without an estimator fall back without making an external request', options, async t => {
  const originalFetch = globalThis.fetch;
  let networkRequests = 0;
  globalThis.fetch = async () => { networkRequests++; throw new Error('Unexpected external request from a fixture'); };
  t.after(() => { globalThis.fetch = originalFetch; });
  const { service, fast, standard } = await setup(t, { apiKey: 'not-a-real-api-key' });
  await service.submit('Build entirely with fixtures', { compare: true });
  await bothStarted(fast, standard);
  const progress = await until(readProgress(service), value => value?.status === 'fallback');
  assertValidDenominator(progress.expectedOutputTokens);
  assert.equal(networkRequests, 0);
});
