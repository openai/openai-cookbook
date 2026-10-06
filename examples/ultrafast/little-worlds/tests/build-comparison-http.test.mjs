import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { setTimeout as delay } from 'node:timers/promises';
import { createApp } from '../server/index.mjs';

const source = title => `export const meta={title:${JSON.stringify(title)},subtitle:'',accent:'#00b85a'};
export function render(){return '<p>'+meta.title+' notebook</p>'}
export function reduce(state,action,actor){
 if(action.type!=='note'||typeof action.text!=='string'||!action.text.trim())throw Error('Invalid note');
 state.extras.notes={...(state.extras.notes||{}),[actor.id]:{actorId:actor.id,text:action.text.trim()}};return state;
}`;
const checks = `export function runTests(api){
 const actor={id:'comparison-http-test-person',name:'Test visitor'};
 const next=api.reduce(api.initialState,{type:'note',text:'Hello'},actor);
 return [
 {name:'A visitor can add a note',ok:next.extras.notes[actor.id].text==='Hello'},
 {name:'Previous notes survive',ok:Object.entries(api.initialState.extras.notes||{}).every(([id,note])=>JSON.stringify(next.extras.notes[id])===JSON.stringify(note))},
 {name:'The notebook renders',ok:api.render(next,actor).includes('notebook')}
 ];
}`;
const seedOverride = { source: source('Original'), tests: checks, state: { projects: [], contributions: [], extras: {} } };
const addFile = (name, text) => `*** Add File: ${name}\n${text.split('\n').map(line => `+${line}`).join('\n')}`;
const gate = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const endpoint = '/api/spaces/mira/comparison';
const privateValues = ['PRIVATE_COMPARISON_INPUT', 'PRIVATE_COMPARISON_CREDENTIAL', 'PRIVATE_COMPARISON_REASONING', 'PRIVATE_COMPARISON_SUMMARY', 'PRIVATE_COMPARISON_DELTA'];

function provider(t, name, tier) {
  const entered = gate(); const release = gate();
  const requests = [];
  t.after(() => release.resolve());
  return {
    entered, release, requests,
    adapter: { model: 'comparison-http-fixture', tier, keyAvailable: true, respond: async request => {
      requests.push(request);
      const { onEvent, signal } = request;
      const call = { type: 'custom_tool_call', id: `item-${name}`, call_id: `call-${name}`, name: 'apply_patch',
        input: ['*** Begin Patch', addFile('space.js', source(name)), addFile('tests.js', checks), '*** End Patch'].join('\n') };
      const reasoning = { type: 'reasoning', id: `reasoning-${name}`, encrypted_content: privateValues[2], summary: [{ type: 'summary_text', text: privateValues[3] }] };
      onEvent({ type: 'response.created', response: { id: `response-${name}`, input: [{ role: 'system', content: privateValues[0] }], metadata: { authorization: privateValues[1] } } });
      onEvent({ type: 'response.output_item.added', output_index: 0, item: { type: 'message', id: `message-${name}`, role: 'assistant', content: [] } });
      onEvent({ type: 'response.output_text.delta', output_index: 0, item_id: `message-${name}`, content_index: 0, delta: `Building ${name}.` });
      onEvent({ type: 'response.output_item.added', output_index: 1, item: reasoning });
      onEvent({ type: 'response.reasoning_summary_text.delta', output_index: 1, delta: privateValues[4] });
      entered.resolve();
      await Promise.race([release.promise, new Promise((_, reject) => {
        if (signal.aborted) reject(signal.reason);
        else signal.addEventListener('abort', () => reject(signal.reason), { once: true });
      })]);
      signal.throwIfAborted();
      onEvent({ type: 'response.output_item.added', output_index: 2, item: { ...call, input: '' } });
      onEvent({ type: 'response.custom_tool_call_input.delta', output_index: 2, item_id: call.id, delta: call.input });
      onEvent({ type: 'response.custom_tool_call_input.done', output_index: 2, item_id: call.id, input: call.input });
      return { model: 'comparison-http-fixture', service_tier: tier, output: [reasoning, call], metrics: { durationMs: 12, outputTokens: 120, servedTier: tier } };
    } },
  };
}

async function fixture(t) {
  const fast = provider(t, 'Ultrafast world', 'ultrafast');
  const standard = provider(t, 'Standard world', 'default');
  const directory = await mkdtemp(join(tmpdir(), 'little-worlds-comparison-http-'));
  const instance = await createApp({ dataDir: directory, seedOverride, adapter: fast.adapter, comparisonAdapter: standard.adapter });
  const server = instance.app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const request = (path, { token, json, headers, signal = AbortSignal.timeout(10000) } = {}) => fetch(`${base}${path}`, {
    method: json === undefined ? 'GET' : 'POST', signal,
    headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(json === undefined ? {} : { 'Content-Type': 'application/json', Origin: base }), ...headers },
    ...(json === undefined ? {} : { body: JSON.stringify(json) }),
  });
  const signIn = async (userId = 'mira') => {
    const result = await request('/api/auth/sign-in', { json: { userId } });
    assert.equal(result.status, 200);
    return result.json();
  };
  const signOut = async token => assert.equal((await request('/api/auth/sign-out', { token, json: {} })).status, 200);
  const start = async token => {
    const result = await request('/api/spaces/mira/turn', { token, json: { message: 'Build a shared notebook', compare: true } });
    assert.equal(result.status, 202);
    const submitted = await result.json();
    assert.ok(submitted.comparisonId);
    await Promise.all([fast.entered.promise, standard.entered.promise]);
    return submitted;
  };
  t.after(async () => {
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
    await instance.close();
    await rm(directory, { recursive: true, force: true });
  });
  return { instance, request, signIn, signOut, start, fast, standard };
}

function parseEvents(text) {
  return text.split(/\r?\n\r?\n/).flatMap(block => {
    const data = block.split(/\r?\n/).filter(line => line.startsWith('data:')).map(line => line.slice(5).trimStart()).join('\n');
    return data ? [JSON.parse(data)] : [];
  });
}
function openStream(response) {
  assert.equal(response.status, 200);
  assert.match(response.headers.get('content-type'), /text\/event-stream/);
  assert.match(response.headers.get('cache-control'), /no-store/);
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let text = '';
  return {
    get events() { return parseEvents(text.slice(0, text.lastIndexOf('\n\n') + 2)); },
    async until(predicate) {
      while (!predicate(this.events)) {
        const chunk = await reader.read();
        assert.equal(chunk.done, false, 'Comparison stream ended before the expected update');
        text += decoder.decode(chunk.value, { stream: true });
      }
      return this.events;
    },
    async end() {
      while (true) {
        const chunk = await reader.read();
        if (chunk.done) return parseEvents(text + decoder.decode());
        text += decoder.decode(chunk.value, { stream: true });
      }
    },
  };
}
const entries = events => events.filter(event => event.type === 'activity.entry');
async function until(read, predicate) {
  for (let attempts = 0; attempts < 1000; attempts++) {
    const value = await read();
    if (predicate(value)) return value;
    await delay(5);
  }
  assert.fail(`Comparison did not reach its expected state: ${JSON.stringify(await read())}`);
}

test('comparison metadata, streams and finish are restricted to the authenticated owner', { timeout: 15000 }, async t => {
  const { request, signIn, start } = await fixture(t);
  const paths = [endpoint, `${endpoint}/events`, `${endpoint}/missing/activity`];
  for (const path of paths) assert.equal((await request(path)).status, 401);
  assert.equal((await request(`${endpoint}/missing/finish`, { json: {} })).status, 401);
  const { token } = await signIn();
  const visitor = await signIn('leo');
  assert.deepEqual(await (await request(endpoint, { token })).json(), { comparison: null });
  const submitted = await start(token);
  for (const path of [endpoint, `${endpoint}/events`, `${endpoint}/${submitted.comparisonId}/activity`]) {
    assert.equal((await request(path, { token: visitor.token })).status, 403);
    assert.equal((await request(`${path}?actor=mira`, { token: visitor.token })).status, 403);
  }
  assert.equal((await request(`${endpoint}/${submitted.comparisonId}/finish`, { token: visitor.token, json: {} })).status, 403);
  assert.equal((await request(`${endpoint}/missing/activity`, { token })).status, 404);
  assert.equal((await request(`${endpoint}/missing/finish`, { token, json: {} })).status, 404);
  assert.equal((await request('/api/spaces/unknown/comparison', { token })).status, 404);
});

test('comparison status and standard Activity stream during generation and replay safely after reconnect', { timeout: 15000 }, async t => {
  const { instance, request, signIn, signOut, start, fast, standard } = await fixture(t);
  const { token } = await signIn();
  const states = openStream(await request(`${endpoint}/events`, { token }));
  await states.until(events => events.some(event => event.type === 'comparison.state' && event.data.comparison === null));
  const submitted = await start(token);
  await states.until(events => events.some(event => event.data?.comparison?.id === submitted.comparisonId && event.data.comparison.standard.status === 'running'));
  const activityPath = `${endpoint}/${submitted.comparisonId}/activity`;
  const activity = openStream(await request(activityPath, { token }));
  await activity.until(events => entries(events).some(event => event.data.text === 'Building Standard world.'));
  assert.equal(instance.service.busy, true);
  fast.release.resolve(); standard.release.resolve();
  const finishedStates = await states.until(events => events.some(event => event.data?.comparison?.ultrafast.status === 'completed'
    && event.data.comparison.standard.status === 'completed' && event.data.comparison.standard.html?.includes('Standard world')));
  const completed = finishedStates.findLast(event => event.data?.comparison?.ultrafast.status === 'completed'
    && event.data.comparison.standard.status === 'completed' && event.data.comparison.standard.html?.includes('Standard world')).data.comparison;
  assert.ok(completed.standard.outputTokens > 0);
  assert.ok(completed.ultrafast.outputTokens > 0);
  assert.match(completed.standard.html, /Standard world/);
  const expected = instance.service.getComparisonActivity(submitted.comparisonId).read();
  const replay = openStream(await request(activityPath, { token, headers: { 'Last-Event-ID': '999999999' } }));
  const statusReplay = openStream(await request(`${endpoint}/events`, { token, headers: { 'Last-Event-ID': '999999999' } }));
  await statusReplay.until(events => events.some(event => event.data?.comparison?.standard.status === 'completed'));
  await signOut(token);
  const activityWire = await activity.end();
  const replayWire = await replay.end();
  const statusWire = await statusReplay.end();
  await states.end();
  assert.equal(replayWire[0].type, 'activity.reset');
  assert.deepEqual(entries(replayWire), expected);
  const wire = JSON.stringify([activityWire, replayWire, statusWire, completed]);
  for (const privateValue of privateValues) assert.ok(!wire.includes(privateValue), privateValue);
  assert.doesNotMatch(wire, /encrypted_content/);
  assert.match(wire, /apply_patch/);
  assert.match((await instance.service.snapshot()).html, /Ultrafast world/);
});

test('HTTP finish waits for ultrafast success, aborts standard, and blocks ambiguous follow-up submissions', { timeout: 15000 }, async t => {
  const { instance, request, signIn, start, fast, standard } = await fixture(t);
  const { token } = await signIn();
  const submitted = await start(token);
  const finishPath = `${endpoint}/${submitted.comparisonId}/finish`;
  assert.equal((await request(finishPath, { token, json: {} })).status, 409);
  assert.equal((await request('/api/spaces/mira/turn', { token, json: { message: 'Not a one-sided follow-up', compare: true } })).status, 409);
  fast.release.resolve();
  await until(() => instance.service.comparison.read(), value => value.ultrafast.status === 'completed');
  const finishResponse = await request(finishPath, { token, json: {} });
  assert.equal(finishResponse.status, 200);
  assert.equal((await finishResponse.json()).comparison.finished, true);
  await until(() => instance.service.comparison.read(), value => value.standard.status === 'cancelled');
  assert.equal(standard.requests[0].signal.aborted, true);
  assert.equal(fast.requests[0].signal.aborted, false);
  const live = await instance.service.snapshot();
  assert.equal(live.revision.id, 2);
  assert.match(live.html, /Ultrafast world/);
  assert.equal((await request(finishPath, { token, json: {} })).status, 200);
});

test('revoking a session closes both comparison streams while accepted work can finish', { timeout: 15000 }, async t => {
  const { instance, request, signIn, signOut, start, fast, standard } = await fixture(t);
  const { token } = await signIn();
  const submitted = await start(token);
  const status = openStream(await request(`${endpoint}/events`, { token }));
  const activity = openStream(await request(`${endpoint}/${submitted.comparisonId}/activity`, { token }));
  await status.until(events => events.some(event => event.data?.comparison?.id === submitted.comparisonId));
  await activity.until(events => entries(events).length > 0);
  await signOut(token);
  await Promise.all([status.end(), activity.end()]);
  assert.equal((await request(endpoint, { token })).status, 401);
  assert.equal(instance.service.busy, true);
  fast.release.resolve(); standard.release.resolve();
  await until(() => instance.service.comparison.read(), value => value.ultrafast.status === 'completed' && value.standard.status === 'completed');
  assert.equal((await instance.service.snapshot()).revision.id, 2);
});

test('starting another comparison closes the old activity stream without revoking its viewer', { timeout: 15000 }, async t => {
  const { instance, request, signIn, signOut, start, fast, standard } = await fixture(t);
  const { token } = await signIn();
  const first = await start(token);
  fast.release.resolve(); standard.release.resolve();
  await until(() => instance.service.comparison.read(), value => value.ultrafast.status === 'completed' && value.standard.status === 'completed');
  await instance.service.waitForIdle();

  const oldActivityPath = `${endpoint}/${first.comparisonId}/activity`;
  const oldActivity = openStream(await request(oldActivityPath, { token }));
  await oldActivity.until(events => entries(events).length > 0);
  const states = openStream(await request(`${endpoint}/events`, { token }));
  await states.until(events => events.some(event => event.data?.comparison?.id === first.comparisonId));

  // Replacing the comparison ends its old feed while the same authenticated
  // viewer and status stream remain live. No sign-out closes it for us.
  const second = await start(token);
  assert.notEqual(second.comparisonId, first.comparisonId);
  assert.ok(entries(await oldActivity.end()).length > 0);
  assert.equal((await request('/api/auth/session', { token })).status, 200);
  assert.equal((await request(oldActivityPath, { token })).status, 404);

  const updatedStates = await states.until(events => events.some(event => event.data?.comparison?.id === second.comparisonId
    && event.data.comparison.ultrafast.status === 'completed' && event.data.comparison.standard.status === 'completed'));
  const completed = updatedStates.findLast(event => event.data?.comparison?.id === second.comparisonId).data.comparison;
  const newActivity = openStream(await request(`${endpoint}/${second.comparisonId}/activity`, { token }));
  const replay = await newActivity.until(events => entries(events).some(event => event.turnId === completed.standard.turnId));
  assert.equal(replay[0].type, 'activity.reset');
  assert.ok(entries(replay).every(event => event.turnId === completed.standard.turnId));
  assert.equal((await request('/api/auth/session', { token })).status, 200);

  await signOut(token);
  await Promise.all([states.end(), newActivity.end()]);
});

test('a compact update queued behind a large preview retains both previews under SSE backpressure', { timeout: 15000 }, async t => {
  const { instance, request, signIn, signOut, fast, standard } = await fixture(t);
  const { token } = await signIn();
  const feed = instance.service.comparison;
  const comparison = feed.begin({ model: 'comparison-http-fixture', primaryTurnId: 'backpressure-fast', standardTurnId: 'backpressure-standard' });
  const stream = openStream(await request(`${endpoint}/events`, { token }));
  await stream.until(events => events.some(event => event.data?.comparison?.id === comparison.id));

  const fastHtml = `<main>ULTRAFAST_PREVIEW_${'f'.repeat(170_000)}</main>`;
  const standardHtml = `<main>STANDARD_PREVIEW_${'s'.repeat(170_000)}</main>`;
  feed.html(comparison.id, 'ultrafast', comparison.primaryTurnId, fastHtml);
  feed.html(comparison.id, 'standard', comparison.standard.turnId, standardHtml);
  // A write larger than the socket's high-water mark cannot drain until the
  // event loop resumes. Queue a normally compact metric update in that window.
  feed.finish(comparison.id);
  feed.activity(comparison.id, 'standard', { type: 'activity.entry', turnId: comparison.standard.turnId,
    data: { entryId: 'backpressure-throughput', throughput: { tokens: 123 } } });
  feed.finish(comparison.id);

  const events = await stream.until(values => values.some(event => event.data?.comparison?.standard.outputTokens === 123));
  const latest = events.findLast(event => event.data?.comparison?.standard.outputTokens === 123);
  assert.equal(latest.data.retainPreviews, undefined, 'A coalesced replacement is a complete snapshot');
  assert.equal(latest.data.comparison.ultrafast.html, fastHtml);
  assert.equal(latest.data.comparison.standard.html, standardHtml);
  assert.equal(fast.requests.length, 0);
  assert.equal(standard.requests.length, 0);
  await signOut(token);
  await stream.end();
});
