import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, rm, readFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { once } from 'node:events';
import { createSpaceService } from '../server/harness.mjs';
import { createApp } from '../server/index.mjs';
import { createResponsesAdapter } from '../server/responses.mjs';
import { createDraftPreviewer } from '../server/draft-preview.mjs';
import { initialState, seedSource, seedTests } from '../server/seed.mjs';

function moduleSource(budget = 1) {
  return `export const meta={title:'Pick what grows',subtitle:'Make a little room for your favorite.',accent:'#d6ee96',budget:${budget}};
export function render(state,actor){return '<p>'+state.contributions.length+' contributions</p>'}
export function reduce(state,action,actor){
  if(action.type!=='support'||!state.projects.some(p=>p.id===action.projectId))throw Error('Unknown action');
  if(state.contributions.filter(c=>c.actorId===actor.id).reduce((s,c)=>s+c.points,0)>=meta.budget)throw Error('All points spent');
  const found=state.contributions.find(c=>c.actorId===actor.id&&c.projectId===action.projectId);
  if(found)found.points++;else state.contributions.push({id:actor.id+':'+action.projectId,actorId:actor.id,projectId:action.projectId,points:1});
  return state;
}`;
}
const behavioralTests = `export function runTests(api){
 const actor={id:'test-new-person',name:'Test guest'};
 const first=api.reduce(api.initialState,{type:'support',projectId:'tidepool'},actor);
 let filled=first;for(let i=1;i<api.meta.budget;i++)filled=api.reduce(filled,{type:'support',projectId:'afterhours'},actor);
 let blocked=false;try{api.reduce(filled,{type:'support',projectId:'smallhours'},actor)}catch{blocked=true}
 return [
 {name:'New visitor participates',ok:first.contributions.some(c=>c.actorId===actor.id&&c.points===1)},
 {name:'Budget enforced',ok:blocked},
 {name:'Existing people preserved',ok:api.initialState.contributions.every(c=>first.contributions.some(n=>JSON.stringify(n)===JSON.stringify(c)))},
 {name:'Current data renders',ok:typeof api.render(api.initialState,actor)==='string'}
 ];
}`;
function toolResponse(budget = 1, callId = 'call-first', tests = behavioralTests) {
  return { model: 'test-model', service_tier: 'ultrafast', output: [
    { type: 'reasoning', id: `reason-${callId}`, summary: [], encrypted_content: `opaque-${callId}` },
    { type: 'function_call', id: `fc-${callId}`, call_id: callId, name: 'apply_change', arguments: JSON.stringify({ source: moduleSource(budget), tests, summary: budget === 1 ? 'One little vote' : 'Three points to play with' }) },
  ], metrics: { durationMs: 9, ttftMs: 3, outputTokens: 10, servedTier: 'ultrafast' } };
}
const fake = (respond) => ({ keyAvailable: true, model: 'test-model', tier: 'ultrafast', respond });
async function setup(t, respond) {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-test-'));
  // These voting regressions intentionally exercise a saved legacy studio.
  // New-account behavior is covered independently by universal-seed tests.
  const service = await createSpaceService({ dataDir, adapter: fake(respond),
    seedOverride: { state: initialState, source: seedSource, tests: seedTests } });
  t.after(async () => { await service.close(); await rm(dataDir, { recursive: true, force: true }); });
  return { service, dataDir };
}
async function turn(service, message = 'Let visitors pick a project.') { await service.submit(message); await service.waitForIdle(); }
const gate = () => { let resolve; const promise = new Promise((r) => { resolve = r; }); return { promise, resolve }; };

// Production SSE callbacks only schedule work. Observe a real committed event
// instead of making token ingestion wait for optional draft rendering.
function nextEvent(store, type, timeoutMs = 3000) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { unsubscribe(); reject(new Error(`Timed out waiting for ${type}`)); }, timeoutMs);
    const unsubscribe = store.subscribe((event) => {
      if (event.type !== type) return;
      clearTimeout(timer); unsubscribe(); resolve(event);
    });
  });
}

test('real verify/publish tool loop preserves encrypted items, state and behavioral history', async (t) => {
  const inputs = [];
  const { service, dataDir } = await setup(t, async (request) => { inputs.push(request.input); return toolResponse(inputs.length === 1 ? 1 : 3, `call-${inputs.length}`); });
  await turn(service);
  const first = await service.snapshot('leo');
  assert.equal(first.revision.id, 2);
  assert.equal(first.session.status, 'idle');
  assert.ok(first.revision.checks.every((check) => check.ok));
  await service.action({ actor: 'leo', revisionId: 2, action: { type: 'support', projectId: 'tidepool' } });
  const contribution = (await service.snapshot()).state.contributions[0];
  await turn(service, 'Give each visitor three points; keep prior contributions.');
  const second = await service.snapshot('leo');
  assert.equal(second.revision.id, 3);
  assert.deepEqual(second.state.contributions[0], contribution);
  assert.equal(second.revision.meta.budget, 3);
  assert.ok(inputs[1].some((item) => item.encrypted_content === 'opaque-call-1'));
  assert.ok(inputs[1].some((item) => item.type === 'function_call_output' && item.call_id === 'call-1'));
  assert.equal(inputs.length, 2, 'no extra model call after publication');
  assert.ok(second.events.some((event) => event.type === 'revision.published' && event.data.preservedContributions === 1));
  const persisted = JSON.parse(await readFile(join(dataDir, 'space.json'), 'utf8'));
  assert.deepEqual(persisted.state, second.state);
  assert.equal(await readFile(join(dataDir, 'workspaces', persisted.session.turns[0].id, 'space.js'), 'utf8'), moduleSource(1));
});

test('failed generated test is repaired through feedback before publication', async (t) => {
  let attempts = 0;
  const { service } = await setup(t, async ({ input }) => {
    attempts++;
    if (attempts === 1) return toolResponse(1, 'bad', 'export function runTests(){return [{name:"Behavior is wrong",ok:false}]}');
    assert.ok(input.some((item) => item.type === 'function_call_output' && item.output.includes('Behavior is wrong')));
    assert.equal((await service.snapshot()).revision.id, 1);
    return toolResponse(1, 'repair');
  });
  await turn(service);
  assert.equal((await service.snapshot()).revision.id, 2);
  assert.equal(attempts, 2);
});

test('three failed verification attempts retain the last published source', async (t) => {
  let attempts = 0;
  const { service } = await setup(t, async () => toolResponse(1, `bad-${++attempts}`, 'export function runTests(){return [{name:"Wrong",ok:false}]}'));
  await turn(service);
  const snapshot = await service.snapshot();
  assert.equal(snapshot.revision.id, 1);
  assert.equal(snapshot.session.lastOutcome, 'failed');
  assert.equal(attempts, 3);
});

test('cancelling an in-flight model cannot publish even if it later returns', async (t) => {
  const entered = gate(); const release = gate();
  const { service } = await setup(t, async () => { entered.resolve(); await release.promise; return toolResponse(); });
  await service.submit('Make voting'); await entered.promise;
  assert.equal((await service.cancel()).cancelled, true);
  release.resolve(); await service.waitForIdle();
  const snapshot = await service.snapshot();
  assert.equal(snapshot.revision.id, 1);
  assert.equal(snapshot.session.lastOutcome, 'cancelled');
});

test('actual generated render appears as an inert draft before arguments and tests finish streaming', async (t) => {
  let observedDraft = false;
  const { service } = await setup(t, async ({ onEvent }) => {
    const response = toolResponse();
    const call = response.output[1];
    const args = JSON.parse(call.arguments);
    args.source = args.source.replace('export function render', `/*${'x'.repeat(740)}*/\nexport function render`);
    call.arguments = JSON.stringify(args);
    const cut = call.arguments.indexOf('export function reduce') + 31;
    const nextDraft = nextEvent(service.store, 'draft.preview');
    await onEvent({ type: 'response.output_item.added', output_index: 1, item: { type: 'function_call', name: 'apply_change', arguments: '' } });
    await onEvent({ type: 'response.function_call_arguments.delta', output_index: 1, delta: call.arguments.slice(0, cut) });
    const draft = await nextDraft;
    const during = await service.snapshot();
    assert.ok(draft, 'a real preview arrived before the full source/tests');
    assert.ok(!during.events.some(event => event.type === 'model.delta'), 'unused source-inspector deltas do not trigger durable writes');
    assert.match(draft.data.html, /0 contributions/);
    assert.equal(during.revision.id, 1, 'preview did not publish');
    await assert.rejects(service.action({ actor: 'leo', revisionId: 1, action: { type: 'support', projectId: 'tidepool' } }), /nothing to do/);
    observedDraft = true;
    await onEvent({ type: 'response.function_call_arguments.delta', output_index: 1, delta: call.arguments.slice(cut) });
    await onEvent({ type: 'response.function_call_arguments.done', output_index: 1, arguments: call.arguments });
    return response;
  });
  await turn(service);
  assert.equal(observedDraft, true);
  const snapshot = await service.snapshot();
  assert.equal(snapshot.revision.id, 2);
  assert.ok(!snapshot.events.some(event => event.type === 'model.delta'));
  assert.ok(snapshot.events.findIndex((event) => event.type === 'draft.preview') < snapshot.events.findIndex((event) => event.type === 'revision.published'));
});

test('a preview queued behind a transaction cannot commit after its generation is discarded', async (t) => {
  const { service } = await setup(t, async () => toolResponse());
  const transactionEntered = gate(); const releaseTransaction = gate(); const previewQueued = gate();
  const blocker = service.store.transact(async () => { transactionEntered.resolve(); await releaseTransaction.promise; });
  t.after(() => releaseTransaction.resolve());
  await transactionEntered.promise;
  const previews = createDraftPreviewer({
    getState: () => service.store.read().state,
    actor: { id: 'mira', name: 'Mira' }, isActive: () => true, intervalMs: 0,
    render: async (source) => ({ html: `<p>${source}</p>` }),
    emit: (event, current) => {
      const committed = service.store.emit(event, () => {
        if (!current()) throw new Error('Discarded draft');
      });
      previewQueued.resolve();
      return committed;
    },
  });
  t.after(() => previews.close());
  previews.schedule(JSON.stringify({ source: 'stale' }));
  await previewQueued.promise;
  previews.discard();
  releaseTransaction.resolve();
  await blocker;
  await previews.flush();
  assert.ok(!service.store.read().events.some(event => event.type === 'draft.preview'));
  previews.schedule(JSON.stringify({ source: 'current' }));
  await previews.flush();
  const drafts = service.store.read().events.filter(event => event.type === 'draft.preview');
  assert.deepEqual(drafts.map(event => event.data.html), ['<p>current</p>']);
});

test('steering received during generation blocks stale publication and enters the next model context', async (t) => {
  const entered = gate(); const release = gate(); let calls = 0;
  const { service } = await setup(t, async ({ input }) => {
    calls++;
    if (calls === 1) { entered.resolve(); await release.promise; return toolResponse(1, 'before-steer'); }
    assert.ok(input.some((item) => item.role === 'user' && item.content.includes('Actually give everyone three points')));
    assert.equal((await service.snapshot()).revision.id, 1);
    return toolResponse(3, 'after-steer');
  });
  await service.submit('Make voting'); await entered.promise;
  const reply = await service.submit('Actually give everyone three points');
  assert.equal(reply.steering, true); release.resolve(); await service.waitForIdle();
  const snapshot = await service.snapshot();
  assert.equal(snapshot.revision.id, 2); assert.equal(snapshot.revision.meta.budget, 3);
  assert.equal(calls, 2);
});

test('serialized visitor actions enforce budgets and reject stale revisions', async (t) => {
  const { service } = await setup(t, async () => toolResponse()); await turn(service);
  const action = { actor: 'leo', revisionId: 2, action: { type: 'support', projectId: 'tidepool' } };
  const results = await Promise.allSettled([service.action(action), service.action(action)]);
  assert.equal(results.filter((result) => result.status === 'fulfilled').length, 1);
  assert.equal((await service.snapshot()).state.contributions.length, 1);
  await assert.rejects(service.action({ ...action, revisionId: 1 }), (error) => error.status === 409);
  await service.action({ ...action, actor: 'mira' });
  assert.equal((await service.snapshot()).state.contributions.length, 2);
});

test('a visitor can participate during generation and their new contribution survives publication', async (t) => {
  const entered = gate(); const release = gate(); let calls = 0;
  const { service } = await setup(t, async () => {
    calls++;
    if (calls === 1) return toolResponse(1, 'initial-vote');
    entered.resolve(); await release.promise; return toolResponse(3, 'upgrade-with-visitor');
  });
  await turn(service);
  await service.submit('Give everyone three points'); await entered.promise;
  const latest = await service.action({ actor: 'leo', revisionId: 2, action: { type: 'support', projectId: 'afterhours' } });
  release.resolve(); await service.waitForIdle();
  const snapshot = await service.snapshot();
  assert.equal(snapshot.revision.meta.budget, 3);
  assert.deepEqual(snapshot.state.contributions, latest.state.contributions);
});

test('a message received immediately after commit becomes a new turn instead of disappearing', async (t) => {
  let calls = 0; let sent = false;
  const { service } = await setup(t, async () => toolResponse(++calls === 1 ? 1 : 3, `just-committed-${calls}`));
  const stop = service.store.subscribe((event) => {
    if (event.type === 'revision.published' && !sent) { sent = true; void service.submit('Now give everyone three points'); }
  });
  t.after(stop);
  await turn(service);
  const snapshot = await service.snapshot();
  assert.equal(calls, 2); assert.equal(snapshot.revision.id, 3); assert.equal(snapshot.revision.meta.budget, 3);
});

test('restoration creates a new revision while preserving live data; reset returns a fresh session', async (t) => {
  const { service } = await setup(t, async () => toolResponse()); await turn(service);
  await service.action({ actor: 'leo', revisionId: 2, action: { type: 'support', projectId: 'tidepool' } });
  const before = await service.snapshot();
  await service.restore(1);
  const restored = await service.snapshot();
  assert.equal(restored.revision.id, 3); assert.deepEqual(restored.state, before.state);
  await service.reset();
  const fresh = await service.snapshot();
  assert.equal(fresh.revision.id, 1); assert.equal(fresh.state.contributions.length, 0);
  assert.notEqual(fresh.session.id, before.session.id);
  assert.ok(Number(fresh.events[0].id) > Number(before.events.at(-1).id));
});

test('restore refuses an earlier budget when current contributions exceed it without removing data', async (t) => {
  let calls = 0;
  const { service } = await setup(t, async () => toolResponse(++calls === 1 ? 1 : 3, `restore-budget-${calls}`));
  await turn(service, 'Allow one vote');
  await turn(service, 'Allow three points');
  for (const projectId of ['tidepool', 'afterhours', 'smallhours']) {
    await service.action({ actor: 'leo', revisionId: 3, action: { type: 'support', projectId } });
  }
  const before = await service.snapshot();
  await assert.rejects(service.restore(2), (error) => {
    assert.equal(error.status, 400);
    assert.match(error.message, /earlier design allows 1 point per person/);
    assert.match(error.message, /current space.*3 points/);
    assert.match(error.message, /Choose another revision/);
    return true;
  });
  const after = await service.snapshot();
  assert.deepEqual(after.state, before.state);
  assert.deepEqual(after.revision, before.revision);
  assert.equal((await service.revisions()).length, 3);
});

test('restart recovers abandoned turn and closes unpaired tool calls in saved context', async (t) => {
  const { service, dataDir } = await setup(t, async () => toolResponse());
  await service.store.transact((data) => { data.session.status = 'running'; data.session.items.push({ type: 'function_call', id: 'fc-abandoned', call_id: 'abandoned', name: 'inspect_space', arguments: '{}' }); });
  const reopened = await createSpaceService({ dataDir, adapter: fake(async () => toolResponse()) });
  t.after(() => reopened.close());
  const snapshot = await reopened.snapshot();
  assert.equal(snapshot.session.status, 'idle'); assert.equal(snapshot.session.lastOutcome, 'interrupted');
  assert.ok(reopened.store.read().session.items.some((item) => item.type === 'function_call_output' && item.call_id === 'abandoned'));
});

const blankFeature = `export const meta={title:'A little guestbook',subtitle:'Leave one good thought.',accent:'#687957'};
export function render(state,actor){return '<p>Hello '+actor.id+'</p><p>'+Object.keys(state.extras.notes||{}).length+' thoughts</p>'}
export function reduce(state,action,actor){
 if(action.type!=='note'||typeof action.text!=='string'||!action.text.trim()||action.text.length>100)throw Error('Invalid note');
 state.extras.notes={...(state.extras.notes||{}),[actor.id]:{actorId:actor.id,text:action.text.trim()}};
 return state;
}`;
const blankFeatureTests = `export function runTests(api){
 const actor={id:'test-note',name:'Note maker'};
 const next=api.reduce(api.initialState,{type:'note',text:'A good day'},actor);
 let blocked=false;try{api.reduce(next,{type:'note',text:''},actor)}catch{blocked=true}
 return [
  {name:'A note is saved for its participant',ok:next.extras.notes[actor.id].text==='A good day'},
  {name:'Empty notes are refused',ok:blocked},
  {name:'Existing projects are preserved',ok:JSON.stringify(next.projects)===JSON.stringify(api.initialState.projects)},
  {name:'Current space renders',ok:api.render(api.initialState,actor).includes(actor.id)}
 ];
}`;
const blankResponse = id => ({ output: [{ type: 'function_call', call_id: id, name: 'apply_change', arguments: JSON.stringify({ source: blankFeature, tests: blankFeatureTests, summary: 'A little guestbook' }) }] });

test('personal spaces keep independent code, data, threads and reset seeds across restart', async (t) => {
  const root = await mkdtemp(join(tmpdir(), 'little-worlds-personal-'));
  const ava = { id: 'ava', name: 'Ava' }; const ben = { id: 'ben', name: 'Ben Registry Only' };
  const registry = [ava, ben]; const inputs = [];
  const adapter = fake(async request => { inputs.push(request); return blankResponse(`personal-${inputs.length}`); });
  const first = await createSpaceService({ dataDir: join(root, 'ava'), owner: ava, kind: 'blank', getActors: () => registry, adapter });
  const second = await createSpaceService({ dataDir: join(root, 'ben'), owner: ben, kind: 'blank', getActors: () => registry, adapter });
  let reopened;
  t.after(async () => { await first.close(); await second.close(); await reopened?.close(); await rm(root, { recursive: true, force: true }); });
  const original = await first.snapshot(); const neighbor = await second.snapshot();
  assert.deepEqual(original.state, { projects: [], contributions: [], extras: {} });
  assert.equal(original.html, ''); assert.equal(original.kind, 'blank'); assert.deepEqual(original.owner, ava);
  assert.notEqual(original.session.id, neighbor.session.id);
  await turn(first, 'Build a little guestbook.');
  await first.action({ actor: ben.id, revisionId: 2, action: { type: 'note', text: 'A thoughtful visitor' } });
  const built = await first.snapshot();
  assert.equal(built.revision.id, 2); assert.equal(built.session.turnCount, 1);
  assert.equal(built.session.lastMessage, 'Build a little guestbook.');
  assert.equal(built.session.turns[0].status, 'completed');
  assert.equal(built.state.extras.notes.ben.actorId, 'ben');
  assert.equal((await second.snapshot()).revision.id, 1);
  assert.deepEqual((await second.snapshot()).state, neighbor.state);
  assert.ok(inputs[0].instructions.includes('THE ENTIRE SPACE BODY'));
  assert.ok(!inputs[0].instructions.includes('Project ids are tidepool'));
  assert.ok(!JSON.stringify(inputs[0].input).includes('Ben Registry Only'), 'the account registry stays outside model context');
  await first.close();
  reopened = await createSpaceService({ dataDir: join(root, 'ava'), owner: ava, kind: 'blank', getActors: () => registry, adapter });
  const continued = await reopened.snapshot();
  assert.equal(continued.session.id, built.session.id); assert.deepEqual(continued.state, built.state);
  await turn(reopened, 'Keep the guestbook graceful.');
  assert.equal((await reopened.snapshot()).session.turnCount, 2);
  assert.ok(inputs[1].input.some(item => item.type === 'function_call_output' && item.call_id === 'personal-1'));
  await reopened.reset();
  const reset = await reopened.snapshot();
  assert.deepEqual(reset.state, original.state); assert.equal(reset.html, ''); assert.equal(reset.session.turnCount, 0);
  assert.notEqual(reset.session.id, built.session.id);
  assert.equal((await second.snapshot()).session.id, neighbor.session.id);
  await assert.rejects(createSpaceService({ dataDir: join(root, 'ava'), owner: ben, kind: 'blank', adapter }), /different space/);
});

test('trusted participant registry is resolved at action time and draft rendering uses the space owner', async (t) => {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-registry-'));
  const owner = { id: 'noor', name: 'Noor' }; const registry = [owner];
  let service;
  service = await createSpaceService({ dataDir, owner, kind: 'blank', getActors: () => registry, adapter: fake(async ({ onEvent }) => {
    const result = blankResponse('owner-draft');
    const call = result.output[0]; const args = JSON.parse(call.arguments);
    args.source = args.source.replace('export function render', `/*${'x'.repeat(740)}*/\nexport function render`);
    call.arguments = JSON.stringify(args);
    const nextDraft = nextEvent(service.store, 'draft.preview');
    await onEvent({ type: 'response.output_item.added', output_index: 0, item: { type: 'function_call', name: 'apply_change', arguments: '' } });
    await onEvent({ type: 'response.function_call_arguments.delta', output_index: 0, delta: call.arguments });
    await onEvent({ type: 'response.function_call_arguments.done', output_index: 0, arguments: call.arguments });
    const preview = await nextDraft;
    assert.equal(preview.data.actorId, owner.id); assert.match(preview.data.html, /Hello noor/);
    return result;
  }) });
  t.after(async () => { await service.close(); await rm(dataDir, { recursive: true, force: true }); });
  await assert.rejects(service.snapshot('new-person'), /Unknown participant/);
  await turn(service);
  assert.equal((await service.snapshot()).revision.id, 2);
  registry.push({ id: 'new-person', name: 'New person' });
  assert.equal((await service.snapshot('new-person')).actor.name, 'New person');
  await service.action({ actor: 'new-person', revisionId: 2, action: { type: 'note', text: 'I just arrived' } });
  assert.equal((await service.snapshot()).state.extras.notes['new-person'].actorId, 'new-person');
  await assert.rejects(service.action({ actor: 'outsider', revisionId: 2, action: { type: 'note', text: 'Denied' } }), /Unknown visitor/);
});

test('HTTP rejects cross-origin writes, handles errors, and replays events after Last-Event-ID', async (t) => {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-http-'));
  const { app, service, close } = await createApp({ dataDir, adapter: fake(async () => blankResponse('http-blank-canvas')) });
  const server = app.listen(0, '127.0.0.1'); await once(server, 'listening');
  t.after(async () => { server.closeAllConnections(); await new Promise((resolve) => server.close(resolve)); await close(); await rm(dataDir, { recursive: true, force: true }); });
  const base = `http://127.0.0.1:${server.address().port}`;
  const loginResponse = await fetch(`${base}/api/auth/sign-in`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ userId: 'mira' }) });
  assert.equal(loginResponse.status, 200);
  const login = await loginResponse.json();
  const headers = { Authorization: `Bearer ${login.token}` };
  const freshAbort = new AbortController();
  const freshStream = await fetch(`${base}/api/events`, { headers, signal: AbortSignal.any([freshAbort.signal, AbortSignal.timeout(2000)]) });
  const freshReader = freshStream.body.getReader();
  assert.match(new TextDecoder().decode((await freshReader.read()).value), /: connected/);
  await service.store.emit({ type: 'message', title: 'A later event' });
  assert.match(new TextDecoder().decode((await freshReader.read()).value), /A later event/);
  freshAbort.abort();
  const bad = await fetch(`${base}/api/reset`, { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json', Origin: 'https://attacker.example' }, body: '{}' });
  assert.equal(bad.status, 403);
  const good = await fetch(`${base}/api/space`, { headers }); assert.equal(good.status, 200);
  const start = await fetch(`${base}/api/turn`, { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify({ message: 'Enable votes' }) });
  assert.equal(start.status, 202); await service.waitForIdle();
  const events = service.store.read().events;
  const after = events.at(-2).id; const abort = new AbortController();
  const stream = await fetch(`${base}/api/events`, { headers: { ...headers, 'Last-Event-ID': after }, signal: AbortSignal.any([abort.signal, AbortSignal.timeout(3000)]) });
  const reader = stream.body.getReader(); let text = '';
  while (!text.includes('turn.completed')) text += new TextDecoder().decode((await reader.read()).value);
  abort.abort();
  assert.match(text, /turn.completed/); assert.ok(!text.includes(`id: ${after}\n`));
  const stale = await fetch(`${base}/api/action`, { method: 'POST', headers: { ...headers, 'Content-Type': 'application/json' }, body: JSON.stringify({ actor: 'leo', revisionId: 1, action: { type: 'support', projectId: 'tidepool' } }) });
  assert.equal(stale.status, 409);
});

test('Responses adapter requests stateless encrypted replay and reports actual served tier from streamed response', async () => {
  let request;
  const completed = { status: 'completed', model: 'gpt-6-astra', service_tier: 'priority', output: [{ type: 'reasoning', encrypted_content: 'opaque' }], usage: { output_tokens: 21, input_tokens: 120 } };
  const data = [
    { type: 'response.output_item.added', item: { type: 'function_call', name: 'apply_change' } },
    { type: 'response.function_call_arguments.delta', delta: '{"source":' },
    { type: 'response.completed', response: completed },
  ].map((event) => `data: ${JSON.stringify(event)}\r\n\r\n`).join('');
  const adapter = createResponsesAdapter({ apiKey: 'test-placeholder', fetchImpl: async (_url, options) => {
    request = options;
    return new Response(new ReadableStream({ start(controller) { for (const character of data) controller.enqueue(new TextEncoder().encode(character)); controller.close(); } }), { status: 200 });
  } });
  const events = [];
  const response = await adapter.respond({ input: [], instructions: 'Test', tools: [], signal: new AbortController().signal, onEvent: (event) => events.push(event.type) });
  const body = JSON.parse(request.body);
  assert.equal(body.store, false); assert.equal(body.stream, true); assert.ok(body.include.includes('reasoning.encrypted_content'));
  assert.equal(body.reasoning.effort, 'low'); assert.equal(adapter.reasoningEffort, 'low');
  assert.equal(body.parallel_tool_calls, false, 'a publishing tool must finish before another change is requested');
  assert.equal(body.service_tier, 'ultrafast');
  assert.equal(request.headers['OpenAI-Service-Tier'], undefined);
  assert.equal(response.metrics.servedTier, 'priority'); assert.equal(response.metrics.outputTokens, 21);
  assert.equal(response.output[0].encrypted_content, 'opaque'); assert.equal(events.length, 3);
});

const patchResponse = (edits, id = 'patch') => ({ output: [{ type: 'function_call', call_id: id, name: 'apply_patch', arguments: JSON.stringify({ edits, summary: 'A small visual edit' }) }] });

test('small source patches publish with all prior tests, contributions and history intact', async (t) => {
  let calls = 0;
  const { service } = await setup(t, async () => ++calls === 1 ? toolResponse() : patchResponse([{ path: 'space.js', search: "'<p>'", replace: "'<p style=\"color:blue\">'" }]));
  await turn(service);
  await service.action({ actor: 'leo', revisionId: 2, action: { type: 'support', projectId: 'tidepool' } });
  const before = await service.snapshot();
  await turn(service, 'Make the text blue');
  const after = await service.snapshot();
  assert.equal(after.revision.id, 3);
  assert.equal(after.revision.tests, before.revision.tests);
  assert.deepEqual(after.state, before.state);
  assert.match(after.html, /style="color:blue"/);
  assert.equal(after.revision.checks.length, before.revision.checks.length);
  assert.ok(after.revision.checks.every(check => check.ok));
  assert.equal(after.session.turnCount, 2);
  assert.equal(service.store.read().session.items.find(item => item.call_id === 'patch' && item.type === 'function_call').name, 'apply_patch');
});

test('invalid patches return actionable feedback and leave the workspace intact for repair', async (t) => {
  let calls = 0;
  const { service } = await setup(t, async ({ input }) => {
    calls++;
    if (calls === 1) return toolResponse();
    if (calls === 2) return patchResponse([{ path: 'space.js', search: "'<p>'", replace: "'<p style=\"color:red\">'" }, { path: 'space.js', search: 'missing-text', replace: 'unexpected' }], 'bad-patch');
    assert.ok(input.some(item => item.type === 'function_call_output' && item.call_id === 'bad-patch' && item.output.includes('did not match')));
    return patchResponse([{ path: 'space.js', search: "'<p>'", replace: "'<p style=\"color:blue\">'" }], 'repaired-patch');
  });
  await turn(service);
  await turn(service, 'Make the text blue');
  const after = await service.snapshot();
  assert.equal(after.revision.id, 3);
  assert.match(after.html, /style="color:blue"/);
  assert.doesNotMatch(after.revision.source, /color:red/);
  assert.equal(calls, 3);
});

test('patches run the same safety verification and cannot publish executable browser content', async (t) => {
  let calls = 0;
  const { service } = await setup(t, async () => ++calls === 1 ? toolResponse() : patchResponse([{ path: 'space.js', search: "'<p>'", replace: "'<script>alert(1)</script><p>'" }], `unsafe-${calls}`));
  await turn(service);
  const before = await service.snapshot();
  await turn(service, 'Make an unsafe change');
  const after = await service.snapshot();
  assert.equal(after.revision.id, before.revision.id);
  assert.equal(after.revision.source, before.revision.source);
  assert.deepEqual(after.state, before.state);
  assert.equal(after.session.lastOutcome, 'failed');
});

test('an unclosed style patch retains the working revision until a corrective patch passes verification', async t => {
  let calls = 0, before;
  const broken = "'<style>p{color:red}<p>'";
  const fixed = "'<style>p{color:blue}</style><p>'";
  const { service } = await setup(t, async ({ input }) => {
    if (++calls === 1) return toolResponse();
    if (calls === 2) return patchResponse([{ path: 'space.js', search: "'<p>'", replace: broken }], 'unclosed-style');
    const result = input.find(item => item.type === 'function_call_output' && item.call_id === 'unclosed-style');
    assert.ok(result, 'The invalid patch receives verification feedback');
    const feedback = JSON.parse(result.output);
    assert.equal(feedback.ok, false);
    assert.ok(feedback.checks.some(check => !check.ok));
    const current = await service.snapshot();
    assert.deepEqual(current.revision, before.revision);
    assert.deepEqual(current.state, before.state);
    assert.equal((await service.revisions()).length, 2, 'Invalid markup cannot append a published revision');
    return patchResponse([{ path: 'space.js', search: broken, replace: fixed }], 'closed-style');
  });
  await turn(service);
  await service.action({ actor: 'leo', revisionId: 2, action: { type: 'support', projectId: 'tidepool' } });
  before = await service.snapshot();
  await turn(service, 'Make the text blue');
  const after = await service.snapshot();
  assert.equal(calls, 3);
  assert.equal(after.revision.id, 3);
  assert.equal(after.revision.tests, before.revision.tests);
  assert.deepEqual(after.state, before.state);
  assert.match(after.html, /^<style>p\{color:blue\}<\/style><p>/);
  assert.ok(after.revision.checks.every(check => check.ok));
  assert.equal(after.session.lastOutcome, 'completed');
  assert.equal((await service.revisions()).length, 3);
});

test('a complete streamed patch previews the real edit before publication', async (t) => {
  let calls = 0;
  const { service } = await setup(t, async ({ onEvent }) => {
    if (++calls === 1) return toolResponse();
    const response = patchResponse([{ path: 'space.js', search: "'<p>'", replace: "'<p style=\"color:blue\">'" }]);
    const call = response.output[0];
    const nextDraft = nextEvent(service.store, 'draft.preview');
    await onEvent({ type: 'response.output_item.added', output_index: 0, item: call });
    await onEvent({ type: 'response.function_call_arguments.done', output_index: 0, arguments: call.arguments });
    const draft = await nextDraft;
    const during = await service.snapshot();
    assert.equal(during.revision.id, 2);
    assert.match(draft.data.html, /style="color:blue"/);
    return response;
  });
  await turn(service);
  await turn(service, 'Make the text blue');
  assert.equal((await service.snapshot()).revision.id, 3);
});
