import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { getQuickJS } from 'quickjs-emscripten';

const require = createRequire(import.meta.url);
async function load(path, worker = false) {
  const result = await build({
    entryPoints: [new URL(path, import.meta.url).pathname], bundle: true, format: 'esm', write: false, platform: 'node', target: 'es2022',
    plugins: worker ? [{ name: 'worker-test-host', setup(build) {
      build.onResolve({ filter: /\/wasm\?url$/ }, () => ({ path: 'test-wasm', namespace: 'test-wasm' }));
      build.onLoad({ filter: /.*/, namespace: 'test-wasm' }, () => ({ contents: 'export default "unused-in-tests"' }));
      build.onResolve({ filter: /^(quickjs-emscripten-core|@jitl\/quickjs-wasmfile-release-sync)$/ }, args => ({
        path: pathToFileURL(require.resolve(args.path).replace(/\.js$/, '.mjs')).href, external: true,
      }));
    } }] : [],
  });
  return import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString('base64')}`);
}
const { createGameController } = await load('../src/game-controller.ts');
const { createGameWorkerRuntime } = await load('../src/game-worker.ts', true);

const actor = { id: 'jo', name: 'Jo' };
const scene = count => ({ width: 260, height: 260, background: '#112233', objects: [{ type: 'circle', id: 'player', x: count, y: 20, radius: 6, fill: '#ffcc00' }], values: { score: count } });
const gameBundle = `var GameModule = { game: {
  init(saved, actor) { return saved ? {...saved} : { actorId: actor.id, count: 0 }; },
  step(state, action) { return { ...state, count: state.count + (action.type === 'tick' ? 1 : 10) }; },
  view(state) { return { width: 260, height: 260, objects: [{ type: 'circle', id: 'player', x: state.count, y: 20, radius: 6 }], values: { score: state.count }, finished: state.count >= 30 }; }
} };`;
const payload = (overrides = {}) => ({ revisionId: 7, config: { id: 'pacman', tickMs: 50, saveAction: 'save_game' }, actor, saved: null, bundle: gameBundle, ...overrides });
const turn = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }

function clock() {
  let time = 0, id = 0;
  const jobs = new Map();
  return {
    now: () => time,
    setTimer(fn, delay) { jobs.set(++id, { fn, due: time + delay }); return id; },
    clearTimer(id) { jobs.delete(id); },
    tick(ms) {
      const end = time + ms;
      for (;;) {
        const next = [...jobs].filter(([, job]) => job.due <= end).sort((a, b) => a[1].due - b[1].due)[0];
        if (!next) break;
        time = next[1].due; jobs.delete(next[0]); next[1].fn();
      }
      time = end;
    },
    jobs,
  };
}

function fixture(overrides = {}) {
  const timer = clock(), events = [], saves = [], workers = [];
  const visibility = { hidden: false, addEventListener(_, fn) { this.listener = fn; }, removeEventListener() { this.listener = undefined; } };
  const controller = createGameController({
    ...timer, visibility, load: async () => payload(), emit: event => events.push(event),
    save: async action => { saves.push(action); return true; },
    createWorker() {
      const worker = {
        sent: [], terminated: false,
        postMessage(message) { this.sent.push(message); },
        terminate() { this.terminated = true; },
        respond(message) { this.onmessage?.({ data: message }); },
        frame(count, status = 'running', requestId) { this.respond({ type: 'frame', view: scene(count), state: { actorId: actor.id, count }, status, ...(requestId ? { requestId } : {}) }); },
        ack(count, status = 'running') { this.frame(count, status, this.sent.at(-1).requestId); },
      };
      workers.push(worker); return worker;
    },
    ...overrides,
  });
  return { controller, timer, events, saves, workers, visibility, async start() { controller.handle({ command: 'start' }); await turn(); workers.at(-1).ack(0); return workers.at(-1); } };
}

test('game controller starts lazily, loads once, emits validated frames and serializes controls', async () => {
  const f = fixture();
  assert.equal(f.workers.length, 0);
  const w = await f.start();
  assert.equal(w.sent[0].type, 'init');
  assert.equal(f.events.at(-1).view.values.score, 0);
  assert.equal(f.events.at(-1).intervalMs, 50);
  assert.equal(f.events.at(-1).kind, 'reset');
  f.controller.handle({ command: 'action', action: { type: 'direction', direction: 'left' } });
  f.controller.handle({ command: 'action', action: { type: 'direction', direction: 'up' } });
  assert.equal(w.sent.length, 2);
  w.ack(10);
  assert.equal(f.events.at(-1).kind, 'action');
  assert.equal(w.sent.at(-1).value.action.direction, 'up');
  w.ack(20);
  f.controller.dispose();
  assert.equal(w.terminated, true);
});

test('frame animation cadence comes from the published game configuration', async () => {
  const f = fixture({ load: async () => payload({ config: { id: 'slow', tickMs: 80 } }) });
  const w = await f.start();
  assert.equal(f.events.at(-1).intervalMs, 80);
  w.respond({ type: 'frame', view: scene(1), state: { actorId: actor.id, count: 1 }, status: 'running', intervalMs: 1, kind: 'reset' });
  assert.equal(f.events.at(-1).intervalMs, 80, 'worker data cannot override the trusted cadence');
  assert.equal(f.events.at(-1).kind, 'tick', 'only a real pending command can classify an action or reset');
  f.controller.dispose();
});

test('handle acknowledges completed controls and returns false for rejected or cancelled commands', async () => {
  const f = fixture();
  let started = false;
  const starting = f.controller.handle({ command: 'start' }).then(ok => { started = ok; return ok; });
  await turn(); assert.equal(started, false);
  const w = f.workers[0]; w.ack(0); assert.equal(await starting, true);
  let complete = false;
  const action = f.controller.handle({ command: 'action', action: { type: 'direction', direction: 'left' } }).then(ok => { complete = ok; return ok; });
  await turn(); assert.equal(complete, false); w.ack(10); assert.equal(await action, true);
  assert.equal(await f.controller.handle({ command: 'action', action: { type: 'tick' } }), false);
  const pending = f.controller.handle({ command: 'pause' }); f.controller.dispose(); assert.equal(await pending, false);
  assert.equal(await f.controller.handle({ command: 'start' }), false);
});

test('a queued release survives pause while ordinary queued presses are cancelled', async () => {
  const f=fixture(), w=await f.start();
  const press=f.controller.handle({command:'action',action:{type:'move',axis:-1}});
  const obsolete=f.controller.handle({command:'action',action:{type:'move',axis:1}});
  const release=f.controller.handle({command:'action',action:{type:'move',axis:0},release:true});
  const pause=f.controller.handle({command:'pause'});
  assert.equal(await obsolete,false);
  w.ack(1); assert.equal(await press,true);
  assert.equal(w.sent.at(-1).value.action.axis,0,'required release executes before pause');
  w.ack(2); assert.equal(await release,true);
  assert.equal(w.sent.at(-1).value.command,'pause');
  w.ack(2,'paused'); assert.equal(await pause,true);
  assert.equal(f.saves.at(-1).game.count,2,'checkpoint includes the release result');
  f.controller.dispose();
});

test('a full input queue makes room for releases and later resume cannot discard them', async () => {
  const f=fixture(), w=await f.start();
  f.controller.handle({command:'action',action:{type:'move',axis:1}});
  for(let index=0;index<32;index++) f.controller.handle({command:'action',action:{type:'move',axis:1}});
  const release=f.controller.handle({command:'action',action:{type:'move',axis:0},release:true});
  f.controller.handle({command:'pause'});
  const resume=f.controller.handle({command:'resume'});
  w.ack(1);
  assert.equal(w.sent.at(-1).value.action.axis,0);
  w.ack(2); assert.equal(await release,true);
  assert.equal(w.sent.at(-1).value.command,'resume');
  w.ack(2); assert.equal(await resume,true);
  f.controller.dispose();
});

test('a late frame release moves ahead of an already queued visibility pause', async () => {
  const f=fixture(), w=await f.start();
  const press=f.controller.handle({command:'action',action:{type:'move',axis:1}});
  f.visibility.hidden=true;f.visibility.listener();
  const release=f.controller.handle({command:'action',action:{type:'move',axis:0},release:true});
  w.ack(1);assert.equal(await press,true);
  assert.equal(w.sent.at(-1).value.action.axis,0,'release runs before a queued visibility pause');
  w.ack(0);assert.equal(await release,true);
  assert.equal(w.sent.at(-1).value.command,'pause');
  w.ack(0,'paused');
  assert.equal(f.saves.at(-1).game.count,0,'the pause checkpoint is neutral');
  f.controller.dispose();
});

test('a release arriving after an in-flight visibility pause checkpoints its neutral state', async () => {
  const f=fixture(), w=await f.start();
  const press=f.controller.handle({command:'action',action:{type:'move',axis:1}});
  w.ack(1);assert.equal(await press,true);
  f.visibility.hidden=true;f.visibility.listener();
  assert.equal(w.sent.at(-1).value.command,'pause','the parent pauses before the frame sends release');
  const release=f.controller.handle({command:'action',action:{type:'move',axis:0},release:true});
  w.ack(1,'paused');
  assert.equal(f.saves.at(-1).game.count,1,'the first pause still has the held input');
  assert.equal(w.sent.at(-1).value.action.axis,0);
  w.ack(0,'paused');assert.equal(await release,true);await turn();
  assert.equal(f.saves.at(-1).game.count,0,'release refreshes the paused checkpoint before reload');
  f.controller.dispose();
});

test('restarting before initialization discards old saved progress', async () => {
  const f = fixture({ load: async () => payload({ saved: { actorId: actor.id, count: 20 } }) });
  const starting = f.controller.handle({ command: 'restart' }); await turn();
  assert.equal(f.workers[0].sent[0].payload.saved, null);
  f.workers[0].ack(0); assert.equal(await starting, true); f.controller.dispose();
});

test('checkpoint saves are throttled, coalesced during slow requests, and include final progress', async () => {
  const first = deferred(), saves = [];
  const f = fixture({ save: async action => { saves.push(action); if (saves.length === 1) await first.promise; return true; } });
  const w = await f.start();
  w.frame(1); f.timer.tick(1900); assert.equal(saves.length, 0);
  w.frame(2); f.timer.tick(100); assert.equal(saves.length, 1);
  assert.equal(saves[0].game.count, 2);
  for (let i = 0; i < 4; i++) { w.frame(3 + i); f.timer.tick(1000); }
  assert.equal(saves.length, 1, 'only one checkpoint request in flight');
  w.frame(9); f.controller.dispose();
  first.resolve(); await turn();
  assert.equal(saves.length, 2);
  assert.equal(saves[1].game.count, 9, 'departure coalesces to the newest progress');
});

test('unchanged frames and duplicate final checkpoints do not write again', async () => {
  const f = fixture(), w = await f.start();
  w.frame(3); f.timer.tick(2000); await turn();
  w.frame(3); f.timer.tick(2000); await turn();
  f.controller.handle({ command: 'pause' }); w.ack(3, 'paused'); await turn();
  f.controller.dispose(); await turn();
  assert.equal(f.saves.length, 1);
});

test('pausing checkpoints immediately and disables the idle watchdog until resumed', async () => {
  const f = fixture(), w = await f.start();
  f.controller.handle({ command: 'pause' }); w.ack(4, 'paused'); await turn();
  assert.equal(f.saves[0].game.count, 4);
  f.timer.tick(60_000);
  assert.equal(w.terminated, false);
  f.controller.handle({ command: 'resume' }); w.ack(4);
  f.timer.tick(3001);
  assert.equal(w.terminated, true);
  assert.equal(f.events.at(-1).status, 'error');
  f.controller.dispose();
});

test('hidden pages pause and never resume automatically', async () => {
  const f = fixture(), w = await f.start();
  f.visibility.hidden = true; f.visibility.listener();
  assert.equal(w.sent.at(-1).value.command, 'pause'); w.ack(1, 'paused');
  const sent = w.sent.length;
  f.visibility.hidden = false; f.visibility.listener();
  assert.equal(w.sent.length, sent);
  f.controller.dispose(); assert.equal(f.visibility.listener, undefined);
});

test('hung commands cannot be hidden by ordinary tick frames', async () => {
  const f = fixture(), w = await f.start();
  f.controller.handle({ command: 'action', action: { type: 'direction', direction: 'left' } });
  for (let i = 1; i <= 3; i++) { f.timer.tick(900); w.frame(i); }
  f.timer.tick(301);
  assert.equal(w.terminated, true);
  f.controller.dispose();
});

test('disposal and load timeout invalidate late loads and worker events', async () => {
  const pending = deferred(), f = fixture({ load: () => pending.promise });
  f.controller.handle({ command: 'start' }); f.controller.dispose(); pending.resolve(payload()); await turn();
  assert.equal(f.workers.length, 0);
  const later = deferred(), g = fixture({ load: () => later.promise });
  g.controller.handle({ command: 'start' }); g.timer.tick(15_001);
  later.resolve(payload()); await turn();
  assert.equal(g.workers.length, 0); assert.equal(g.events.at(-1).status, 'error'); g.controller.dispose();
});

test('invalid ownership, scene geometry, and worker failures stop the game', async () => {
  for (const mutation of [
    message => { message.state.actorId = 'james'; },
    message => { message.view.objects[0].radius = Infinity; },
    message => { message.view.objects.push(message.view.objects[0]); },
  ]) {
    const f = fixture(), w = await f.start();
    const message = { type: 'frame', state: { actorId: actor.id, count: 3 }, view: scene(3), status: 'running' }; mutation(message); w.respond(message);
    assert.equal(w.terminated, true); assert.equal(f.events.at(-1).status, 'error'); f.controller.dispose();
  }
  const f = fixture(), w = await f.start(); w.onerror(); assert.equal(w.terminated, true); f.controller.dispose();
});

test('reserved and oversized controls are rejected and queued input stays bounded', async () => {
  const f = fixture(), w = await f.start();
  for (const action of [null, [], { type: 'tick' }, { type: '' }, { type: 'direction', content: 'x'.repeat(5000) }]) f.controller.handle({ command: 'action', action });
  assert.equal(w.sent.length, 1);
  for (let i = 0; i < 100; i++) f.controller.handle({ command: 'action', action: { type: 'direction', direction: 'left' } });
  for (let i = 0; i < 100; i++) w.ack(i);
  assert.equal(w.sent.length, 34, 'one in flight plus 32 queued controls');
  f.controller.dispose();
});

test('checkpoint rejection pauses with a recoverable message and does not retry every tick', async () => {
  let count = 0;
  const f = fixture({ save: async () => { count++; return false; } }), w = await f.start();
  w.frame(3); f.timer.tick(2000); await turn();
  assert.equal(w.sent.at(-1).value.command, 'pause');
  assert.match(f.events.at(-1).message, /could not be saved/);
  w.ack(3, 'paused'); f.timer.tick(60_000); await turn();
  assert.equal(count, 1); f.controller.dispose();
});

test('an old checkpoint failure cannot pause or discard saves from a replacement run', async () => {
  const saving = deferred(); let requests = 0;
  const f = fixture({ save: async () => { if (++requests === 1) await saving.promise; return true; } });
  const first = await f.start(); first.frame(3); f.timer.tick(2000);
  first.onerror(); const second = await f.start(); second.frame(4);
  saving.reject(new Error('Old network failure')); await turn();
  assert.equal(second.sent.some(message => message.value?.command === 'pause'), false);
  assert.equal(f.events.filter(event => event.type === 'status').at(-1).status, 'running');
  f.timer.tick(2000); await turn(); assert.equal(requests >= 2, true);
  f.controller.dispose();
});

test('an old checkpoint failure cannot pause a restarted game in the same worker', async () => {
  const saving = deferred();
  const f = fixture({ save: () => saving.promise }), w = await f.start();
  w.frame(4); f.timer.tick(2000);
  const restarting = f.controller.handle({ command: 'restart' }); w.ack(0); assert.equal(await restarting, true);
  saving.reject(new Error('Old checkpoint failed')); await turn();
  assert.equal(w.sent.some(message => message.value?.command === 'pause'), false);
  assert.equal(f.events.filter(event => event.type === 'status').at(-1).status, 'running');
  f.controller.dispose();
});

test('a game without saveAction performs no persistent writes', async () => {
  const f = fixture({ load: async () => payload({ config: { id: 'preview', tickMs: 50 } }) }), w = await f.start();
  for (let i = 0; i < 5; i++) { w.frame(i); f.timer.tick(1000); }
  f.controller.dispose(); assert.equal(f.saves.length, 0);
});

async function engine(bundle = gameBundle, saved = null) {
  const timer = clock(), messages = [];
  const runtime = createGameWorkerRuntime({ ...timer, post: message => messages.push(message), loadQuickJS: getQuickJS });
  await runtime.receive({ type: 'init', requestId: 1, payload: payload({ bundle, saved }) });
  return { runtime, timer, messages, command: (command, action) => runtime.receive({ type: 'command', requestId: 2, value: { command, action } }) };
}

test('real held movement releases before queued pause and resumes neutral after a delayed worker', async () => {
  const bundle = `var GameModule={game:{
    init(saved,actor){return {actorId:actor.id,x:saved?saved.x:30,axis:0}},
    step(state,action){return action.type==='move'?{...state,axis:action.axis}:{...state,x:state.x+state.axis}},
    view(state){return {width:260,height:260,objects:[{id:'player',type:'circle',x:state.x,y:30,radius:5}]}}
  }};`;
  const messages=[], engineTimer=clock();
  let bridge;
  const runtime=createGameWorkerRuntime({...engineTimer,loadQuickJS:getQuickJS,post:message=>bridge.onmessage?.({data:message})});
  const f=fixture({
    load:async()=>payload({bundle,saved:{actorId:actor.id,x:30,axis:1}}),
    createWorker(){bridge={postMessage:message=>messages.push(message),terminate:()=>runtime.dispose()};return bridge;},
  });
  const starting=f.controller.handle({command:'start'});await turn();
  await runtime.receive(messages.shift());assert.equal(await starting,true);
  const press=f.controller.handle({command:'action',action:{type:'move',axis:-1}});
  const release=f.controller.handle({command:'action',action:{type:'move',axis:0},release:true});
  const pausing=f.controller.handle({command:'pause'});
  await runtime.receive(messages.shift());assert.equal(await press,true);
  engineTimer.tick(100);
  assert.equal(f.events.at(-1).view.objects[0].x,28,'physical hold advances actual simulation');
  await runtime.receive(messages.shift());assert.equal(await release,true);
  await runtime.receive(messages.shift());assert.equal(await pausing,true);
  assert.equal(f.saves.at(-1).game.axis,0,'paused checkpoint has released movement');
  const resuming=f.controller.handle({command:'resume'});
  await runtime.receive(messages.shift());assert.equal(await resuming,true);
  engineTimer.tick(100);
  assert.equal(f.events.at(-1).view.objects[0].x,28,'resuming does not restore the released key');
  f.controller.dispose();
});

test('real QuickJS worker ticks, accepts controls, pauses, resumes, finishes, and restarts', async () => {
  const e = await engine();
  assert.equal(e.messages[0].type, 'ready'); assert.equal(e.messages[0].state.count, 0);
  e.timer.tick(100); assert.equal(e.messages.at(-1).state.count, 2);
  await e.command('action', { type: 'direction', direction: 'left' }); assert.equal(e.messages.at(-1).state.count, 12);
  await e.command('pause'); e.timer.tick(1000); assert.equal(e.messages.at(-1).state.count, 12); assert.equal(e.messages.at(-1).status, 'paused');
  await e.command('resume'); e.timer.tick(900); assert.equal(e.messages.at(-1).status, 'finished'); assert.equal(e.messages.at(-1).state.count, 30);
  const before = e.messages.length; e.timer.tick(10000); assert.equal(e.messages.length, before);
  await e.command('restart'); assert.equal(e.messages.at(-1).state.count, 0); assert.equal(e.messages.at(-1).status, 'running');
  e.runtime.dispose(); e.timer.tick(10000); assert.equal(e.timer.jobs.size, 0);
});

test('real QuickJS resumes only the supplied actor-owned saved progress', async () => {
  const e = await engine(gameBundle, { actorId: actor.id, count: 9 });
  assert.equal(e.messages[0].state.count, 9); e.runtime.dispose();
  const wrong = await engine(gameBundle, { actorId: 'james', count: 9 });
  assert.equal(wrong.messages[0].type, 'error'); assert.match(wrong.messages[0].message, /participant/); wrong.runtime.dispose();
});

test('game tick cadence includes computation time and steering preserves the pending deadline', async () => {
  const messages = [], delays = [];
  let time = 0, callback;
  const runtime = createGameWorkerRuntime({
    now: () => time, loadQuickJS: getQuickJS,
    post(message) { messages.push(message); if (message.type === 'frame' && message.requestId === undefined) time += 20; },
    setTimer(fn, delay) { callback = fn; delays.push(delay); return 1; }, clearTimer() {},
  });
  await runtime.receive({ type: 'init', requestId: 1, payload: payload() });
  assert.equal(delays.at(-1), 50);
  time = 50; callback();
  assert.equal(delays.at(-1), 30, '20ms computation leaves 30ms before the next tick');
  time = 80;
  await runtime.receive({ type: 'command', requestId: 2, value: { command: 'action', action: { type: 'direction', direction: 'left' } } });
  assert.equal(delays.at(-1), 20, 'steering keeps the original 100ms tick deadline');
  time = 1000; callback();
  assert.equal(delays.at(-1), 30, 'a long scheduling delay never queues missed ticks');
  runtime.dispose();
});

test('short scheduling delays do not accumulate into slower game time', async () => {
  const messages = [], tickTimes = [];
  let time = 0, scheduled;
  const runtime = createGameWorkerRuntime({
    now: () => time, loadQuickJS: getQuickJS,
    post(message) {
      messages.push(message);
      if (message.type === 'frame' && message.requestId === undefined) tickTimes.push(time);
    },
    setTimer(fn, delay) { scheduled = { fn, due: time + delay }; return 1; },
    clearTimer() { scheduled = undefined; },
  });
  try {
    await runtime.receive({ type: 'init', requestId: 1, payload: payload() });
    for (let tick = 0; tick < 10; tick++) {
      const job = scheduled;
      time = job.due + 10;
      job.fn();
    }
    assert.deepEqual(tickTimes, [60, 110, 160, 210, 260, 310, 360, 410, 460, 510]);
    assert.equal(messages.at(-1).state.count, 10, 'ten ticks advance once each despite timer jitter');
    assert.equal(scheduled.due, 550, 'the next tick retains the original clock phase');

    const late = scheduled;
    time = late.due + 50;
    late.fn();
    assert.equal(messages.at(-1).state.count, 11, 'a full missed interval does not replay extra ticks');
    assert.equal(scheduled.due, 650, 'a full missed interval starts a fresh deadline');
  } finally { runtime.dispose(); }
});

test('real QuickJS cannot access browser, network, wall clock, dynamic evaluation, or host process', async () => {
  const bundle = gameBundle.replace('count: 0', `count: 0, globals: [typeof window, typeof document, typeof fetch, typeof XMLHttpRequest, typeof WebSocket, typeof process, typeof Date, typeof eval, typeof Function, typeof setTimeout, typeof Promise]`);
  const e = await engine(bundle);
  assert.equal(e.messages[0].type, 'ready');
  assert.ok(e.messages[0].state.globals.every(value => value === 'undefined'), JSON.stringify(e.messages[0].state.globals));
  e.runtime.dispose();
});

test('real QuickJS interrupts infinite loops and rejects mutation, invalid ownership, and unsafe views', async () => {
  for (const [bundle, expected] of [
    [gameBundle.replace('return saved ?', 'while (true) {} return saved ?'), /too long/],
    [gameBundle.replace('actorId: actor.id', 'actorId: "james"'), /participant/],
    [gameBundle.replace('view(state) { return', 'view(state) { state.count++; return'), /preserve/],
    [gameBundle.replace('radius: 6', 'radius: Infinity'), /JSON|finite/],
  ]) {
    const e = await engine(bundle); assert.equal(e.messages[0].type, 'error'); assert.match(e.messages[0].message, expected); assert.equal(e.timer.jobs.size, 0); e.runtime.dispose();
  }
  const e = await engine(gameBundle.replace('return saved ?', 'if (saved) saved.count++; return saved ?'), { actorId: actor.id, count: 9 });
  assert.equal(e.messages[0].type, 'error'); assert.match(e.messages[0].message, /preserve/); e.runtime.dispose();
});

test('disposing during WASM loading never initializes or emits later frames', async () => {
  const loading = deferred(), messages = [], timer = clock();
  const runtime = createGameWorkerRuntime({ ...timer, post: message => messages.push(message), loadQuickJS: () => loading.promise });
  const starting = runtime.receive({ type: 'init', requestId: 1, payload: payload() });
  runtime.dispose(); loading.resolve(await getQuickJS()); await starting;
  assert.equal(messages.length, 0); assert.equal(timer.jobs.size, 0);
});

test('authored views cannot capture private worker state or mutate retained state aliases', async () => {
  const capture = await engine(gameBundle.replace('view(state) { return', 'view(input) { state.count++; return').replaceAll('x: state.count', 'x: input.count').replaceAll('score: state.count', 'score: input.count').replaceAll('finished: state.count', 'finished: input.count'));
  assert.equal(capture.messages[0].type, 'error'); capture.runtime.dispose();
  const alias = await engine(gameBundle.replace('var GameModule', 'var retained; var GameModule').replace('return saved ?', 'return retained = saved ?').replace('view(state) { return', 'view(state) { retained.count++; return'));
  assert.equal(alias.messages[0].type, 'ready');
  assert.equal(alias.messages[0].state.count, 0);
  alias.timer.tick(50); assert.equal(alias.messages.at(-1).state.count, 1);
  alias.runtime.dispose();
});

test('dense scenes keep ticking and every serialized scene is validated before it leaves the worker', async () => {
  const dense = gameBundle.replace("objects: [{ type: 'circle', id: 'player', x: state.count, y: 20, radius: 6 }]", "objects: Array.from({length: 200}, (_,i)=>({type:'circle',id:'dot-'+i,x:i,y:20,radius:3}))").replace('finished: state.count >= 30', 'finished: false');
  const e = await engine(dense);
  for (let i = 0; i < 200; i++) e.timer.tick(50);
  assert.equal(e.messages.length, 201);
  assert.ok(e.messages.every(message => message.type !== 'error'));
  assert.equal(e.messages.at(-1).state.count, 200);
  assert.equal(e.messages.at(-1).view.objects.length, 200);
  e.runtime.dispose();
  for (const unsafe of [
    gameBundle.replace('radius: 6', "radius: 6, fill: 'url(https://untrusted.invalid/image)'"),
    gameBundle.replace('radius: 6', 'radius: NaN'),
    gameBundle.replace("type: 'circle'", "type: 'script'"),
  ]) {
    const rejected = await engine(unsafe);
    assert.equal(rejected.messages.length, 1);
    assert.equal(rejected.messages[0].type, 'error');
    rejected.runtime.dispose();
  }
});

test('scene serialization cannot mutate the state that was passed to view', async () => {
  const bundle = gameBundle.replace('view(state) { return', 'view(state) { return {toJSON(){ state.count++; return').replace('finished: state.count >= 30 }; }', 'finished: state.count >= 30 }; }}; }');
  const e = await engine(bundle);
  assert.equal(e.messages[0].type, 'error');
  assert.match(e.messages[0].message, /preserve/);
  e.runtime.dispose();
});
