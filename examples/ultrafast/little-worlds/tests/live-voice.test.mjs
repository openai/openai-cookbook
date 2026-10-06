import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

const bundled = await build({ entryPoints: [new URL('../src/live-voice.ts', import.meta.url).pathname], bundle: true, format: 'esm', write: false, target: 'es2022' });
const { createLiveVoice } = await import(`data:text/javascript;base64,${Buffer.from(bundled.outputFiles[0].text).toString('base64')}`);
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(check, message = 'condition', timeout = 1200) {
  const deadline = Date.now() + timeout;
  while (!check()) { if (Date.now() > deadline) assert.fail(`Timed out waiting for ${message}`); await delay(3); }
}
function deferred() { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; }
class Events {
  listeners = new Map();
  addEventListener(type, fn) { if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(fn); }
  removeEventListener(type, fn) { this.listeners.get(type)?.delete(fn); }
  emit(type, fields = {}) { for (const fn of [...(this.listeners.get(type) ?? [])]) fn({ type, ...fields }); }
}
class Track extends Events { enabled = true; stopped = false; stop() { this.stopped = true; } }
class Stream { constructor(tracks = [new Track()]) { this.tracks = tracks; } getTracks() { return this.tracks; } getAudioTracks() { return this.tracks; } }
const surface = (title = 'Home') => ({ title, context: 'Current app screen', controls: [{ id: 'home', label: 'Home', role: 'button' }, { id: 'request', label: 'What would you like to create?', role: 'textbox', value: '' }] });
function harness(t, config = {}) {
  const env = { peers: [], audios: [], streams: [], requests: [], plans: [], actions: [], states: [], captions: [], levels: [], notices: [], meters: [], calls: [], controllers: [], mediaCount: 0 };
  const browserEvents = new Events();
  class Channel extends Events {
    readyState = 'open'; sent = [];
    send(raw) { this.sent.push(JSON.parse(raw)); }
    close() { this.readyState = 'closed'; this.emit('close'); }
    message(event) { this.emit('message', { data: JSON.stringify(event) }); }
  }
  class Peer extends Events {
    iceGatheringState = config.icePending ? 'gathering' : 'complete';
    connectionState = 'new';
    tracks = [];
    addedTrackEnabled = [];
    constructor() { super(); env.peers.push(this); }
    createDataChannel(label) { env.calls.push('channel'); assert.equal(label, 'oai-events'); return this.channel = new Channel(); }
    addTrack(track) { this.tracks.push(track); this.addedTrackEnabled.push(track.enabled); }
    async createOffer() { assert.ok(this.channel.listeners.get('message')?.size); assert.ok(this.listeners.get('track')?.size); env.calls.push('offer'); return { type: 'offer', sdp: 'offer-sdp' }; }
    async setLocalDescription(description) { this.localDescription = description; env.calls.push('local'); }
    async setRemoteDescription(description) { this.remoteDescription = description; env.calls.push('remote'); }
    close() { this.closed = true; this.connectionState = 'closed'; this.emit('connectionstatechange'); }
  }
  class Audio {
    paused = true;
    constructor() { env.audios.push(this); }
    setAttribute() {}
    async play() { if (env.playBlocked) throw new DOMException('Blocked', 'NotAllowedError'); this.paused = false; }
    pause() { this.paused = true; }
  }
  class Context {
    state = 'running';
    resume() { if (config.resumeAudioContext) return config.resumeAudioContext(this); this.state = 'running'; return Promise.resolve(); }
    async close() { this.state = 'closed'; }
    createMediaStreamSource() { return { connect() {} }; }
    createAnalyser() { const meter = { amplitude: 0, getByteTimeDomainData(samples) { for (let i = 0; i < samples.length; i++) samples[i] = 128 + (i % 2 ? 1 : -1) * this.amplitude; } }; env.meters.push(meter); return meter; }
  }
  const replacements = { RTCPeerConnection: Peer, Audio, AudioContext: Context, MediaStream: Stream, addEventListener: browserEvents.addEventListener.bind(browserEvents), removeEventListener: browserEvents.removeEventListener.bind(browserEvents), navigator: { onLine: true, mediaDevices: { getUserMedia: async constraints => {
    env.constraints = constraints;
    env.mediaCount++;
    if (config.media) return config.media(env);
    const stream = new Stream(); env.streams.push(stream); return stream;
  } } } };
  const originals = new Map(Object.keys(replacements).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const [key, value] of Object.entries(replacements)) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  let reads = 0;
  const options = {
    timings: { connect: 1000, ice: 500, settle: 8, transcriptWait: 70, plan: 250, plannerBusy: 90, plannerRetry: 5, close: 15, disconnect: 25, mute: 40, reconnectBase: 8, reconnectMax: 30, reconnectAttempts: 4, reconnectStable: 200 },
    readSurface: async () => config.readSurface?.(++reads) ?? surface(),
    execute: async action => { env.actions.push(action); return config.execute?.(action, env) ?? { ok: true, message: 'The app is now on Home.' }; },
    onState: state => env.states.push(state),
    onTranscript: transcript => env.captions.push(transcript),
    onLevel: levels => env.levels.push(levels),
    onNotice: message => env.notices.push(message),
    fetch: async (path, init) => {
      const body = JSON.parse(init.body); env.requests.push({ path, body, init });
      if (path === '/api/voice/session') return config.sessionResponse?.(body, env) ?? new Response(JSON.stringify(config.session ?? { session: { id: 'live_test' }, transport: { type: 'webrtc', sdp: 'answer-sdp' }, controlToken: 'private-controller-token' }));
      if (path === '/api/voice/end') return new Response('{}');
      assert.equal(path, '/api/voice/plan'); env.plans.push(body);
      if (config.planResponse) return config.planResponse(body, env, init.signal);
      const action = await (config.plan?.(body, env, init.signal) ?? { type: 'done', message: 'Ready.' });
      return new Response(JSON.stringify({ action }));
    },
  };
  env.make = extra => { const controller = createLiveVoice({ ...options, ...extra, timings: { ...options.timings, ...extra?.timings } }); env.controllers.push(controller); return controller; };
  env.controller = env.make();
  env.latest = () => env.states.at(-1);
  env.network = online => { navigator.onLine = online; browserEvents.emit(online ? 'online' : 'offline'); };
  env.channel = () => env.peers.at(-1).channel;
  env.started = () => env.channel().message({ type: 'session.started', session: { id: 'live_test' } });
  let id = 0;
  env.input = (delta, start = 100, end = 1000) => env.channel().message({ type: 'session.input_transcript.delta', event_id: `input_${++id}`, delta, start_ms: start, end_ms: end });
  env.delegation = (id = 'task', offset = 1000) => env.channel().message({ type: 'session.delegation.created', offset_ms: offset, delegation: { id, target: 'client' } });
  t.after(async () => {
    for (const controller of env.controllers) { await controller.stop(); controller.destroy(); }
    for (const [key, descriptor] of originals) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]; }
  });
  return env;
}

test('WebRTC waits for ICE and session.started, then closes while releasing microphone immediately', async t => {
  const env = harness(t, { icePending: true });
  await env.controller.updateContext('On the welcome screen.');
  const starting = env.controller.start();
  await until(() => env.calls.includes('local'));
  assert.equal(env.requests.length, 0);
  assert.equal(env.latest().status, 'connecting');
  env.peers[0].iceGatheringState = 'complete';
  env.peers[0].emit('icegatheringstatechange');
  await starting;
  assert.deepEqual(env.constraints, { audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
  assert.deepEqual(env.requests[0].body, { sdp: 'offer-sdp' });
  assert.deepEqual(env.peers[0].remoteDescription, { type: 'answer', sdp: 'answer-sdp' });
  assert.equal(env.channel().sent.length, 0);
  env.started();
  await until(() => env.channel().sent.length >= 2);
  assert.equal(env.latest().status, 'listening');
  assert.ok(env.channel().sent.every(event => event.type !== 'session.start'));
  const stopping = env.controller.stop();
  assert.equal(env.streams[0].tracks[0].stopped, true);
  assert.equal(env.latest().status, 'idle');
  assert.equal(env.channel().readyState, 'open');
  assert.ok(env.channel().sent.some(event => event.type === 'session.close'));
  env.channel().message({ type: 'session.closed', reason: 'close_requested' });
  await stopping;
  assert.equal(env.channel().readyState, 'closed');
  assert.equal(env.requests.filter(request => request.path === '/api/voice/end').length, 1);
});

test('fresh startup requests speech immediately before context, once, without inspecting or acting on the app', async t => {
  for (const muted of [false, true]) await t.test(muted ? 'muted microphone' : 'open microphone', async t => {
    const env = harness(t, { readSurface: () => assert.fail('A greeting must not inspect the app') });
    await env.controller.updateContext('Signed in and viewing my world.');
    await env.controller.start({ muted });
    assert.equal(env.channel().sent.length, 0, 'Wait for Live readiness before sending commands');
    env.started();
    const commands = env.channel().sent.filter(event => event.type.endsWith('.append'));
    assert.deepEqual(commands.map(event => event.type), ['session.instructions.append', 'session.thinking.append']);
    const greeting = commands[0];
    assert.equal(greeting.delegation_id, null);
    assert.match(greeting.content, /Speak first, immediately, in English/);
    assert.match(greeting.content, /rhymes with alive/);
    assert.match(greeting.content, /Then pause and listen/);
    assert.ok(new TextEncoder().encode(greeting.content).length <= 460);
    assert.equal(env.streams[0].tracks[0].enabled, !muted);
    env.channel().message({ type: 'session.instructions.appended', client_event_id: greeting.event_id });
    env.started();
    assert.equal(env.channel().sent.filter(event => event.type === 'session.instructions.append').length, 1);
    assert.equal(env.latest().speaking, false, 'Acceptance is not audible playback');
    assert.equal(env.plans.length, 0);
    assert.equal(env.actions.length, 0);
    assert.deepEqual(env.notices, []);
  });
});

test('a rejected greeting is reported without replay, while Live remains usable', async t => {
  const env = harness(t);
  await env.controller.start(); env.started();
  const greeting = env.channel().sent.find(event => event.type === 'session.instructions.append');
  env.channel().message({ type: 'session.instructions.appended', client_event_id: 'unrelated-context-event' });
  env.channel().message({ type: 'error', error: { code: 'invalid_request_error', client_event_id: greeting.event_id } });
  assert.match(env.notices.at(-1), /could not start its greeting.*speak now/);
  assert.equal(env.latest().connected, true);
  assert.equal(env.streams[0].tracks[0].enabled, true);
  env.started();
  assert.equal(env.channel().sent.filter(event => event.type === 'session.instructions.append').length, 1);
  env.input('Go home.'); env.delegation();
  await until(() => env.plans.length > 0);
});

test('stopping before microphone permission resolves releases the late microphone without connecting', async t => {
  const media = deferred();
  const env = harness(t, { media: () => media.promise });
  const starting = env.controller.start();
  await env.controller.stop();
  const late = new Stream(); media.resolve(late);
  await starting;
  assert.equal(late.tracks[0].stopped, true);
  assert.equal(env.requests.length, 0);
  assert.equal(env.latest().status, 'idle');
});

test('a stale microphone rejection cannot tear down a newer connection', async t => {
  const first = deferred();
  const env = harness(t, { media: env => env.mediaCount === 1 ? first.promise : Promise.resolve(new Stream()) });
  const stale = env.controller.start();
  await env.controller.stop();
  await env.controller.start(); env.started();
  first.reject(new DOMException('Denied', 'NotAllowedError')); await stale;
  assert.equal(env.latest().connected, true);
  assert.equal(env.peers[1].closed, undefined);
});

test('delegations wait for transcript fragments, preserve speakers and spacing, and use fresh surfaces', async t => {
  const env = harness(t, { readSurface: n => surface(`View ${n}`), plan: (_body, env) => env.plans.length === 1 ? { type: 'click', target: 'home' } : { type: 'done', message: 'Home is open.' } });
  await env.controller.start(); env.started();
  env.delegation();
  await delay(20); assert.equal(env.plans.length, 0);
  env.input('Go ', 100, 500); env.input('home', 500, 1000);
  env.channel().message({ type: 'session.output_transcript.delta', event_id: 'out1', delta: 'Opening it.', start_ms: 1000, end_ms: 1500 });
  env.delegation();
  await until(() => env.plans.length === 2 && !env.latest().working);
  assert.equal(env.actions.length, 1);
  assert.deepEqual(env.plans[0].conversation, [{ role: 'user', text: 'Go home' }, { role: 'assistant', text: 'Opening it.' }]);
  assert.notEqual(env.plans[0].surface.title, env.plans[1].surface.title);
  assert.deepEqual(env.plans[1].history, [{ action: { type: 'click', target: 'home' }, result: { ok: true, message: 'The app is now on Home.' } }]);
  assert.deepEqual(env.captions.at(-1).map(item => item.text), ['Go home', 'Opening it.']);
  assert.ok(env.channel().sent.some(event => event.type === 'session.commentary.append' && event.delegation_id === 'task' && event.content === 'Home is open.'));
  env.delegation('duplicate-notice');
  await delay(35);
  assert.equal(env.plans.length, 2);
});

test('compound disclosure requests keep fresh state and all results until both panels are open', async t => {
  const cases = [
    { name: 'both closed', initial: [false, false] },
    { name: 'Files already open', initial: [true, false] },
    { name: 'Activity already open', initial: [false, true] },
    { name: 'both already open', initial: [true, true] },
  ];
  for (const { name, initial } of cases) await t.test(name, async t => {
    const labels = ['Files', 'Activity'];
    const expanded = [...initial];
    const observedStates = [[...initial]];
    const results = [];
    let capture = 0;
    const env = harness(t, {
      readSurface: version => {
        capture = version;
        return {
          title: 'Workspace',
          context: 'Use either side panel while editing the space.',
          controls: labels.map((label, index) => ({ id: `panel-${index}-capture-${version}`, role: 'button', label, expanded: expanded[index] })),
        };
      },
      // A deterministic provider isolates the controller's multi-action loop:
      // every decision must use the latest disclosure state, not stale IDs or
      // the fact that a previous click merely returned successfully.
      plan: body => {
        const next = body.surface.controls.find(control => control.expanded === false);
        return next ? { type: 'click', target: next.id } : { type: 'done', message: 'Files and Activity are both open.' };
      },
      execute: async action => {
        assert.equal(action.type, 'click');
        const match = /^panel-([01])-capture-(\d+)$/.exec(action.target);
        assert.ok(match, 'execute only a control from the current capture');
        assert.equal(Number(match[2]), capture, 'a second action cannot reuse the first capture');
        const index = Number(match[1]);
        assert.equal(expanded[index], false, 'do not close a panel that is already open');
        await delay(2);
        expanded[index] = !expanded[index];
        observedStates.push([...expanded]);
        const result = { ok: true, message: `${labels[index]} is now open.` };
        results.push(result);
        return result;
      },
    });
    await env.controller.start(); env.started(); env.input('Open both side panels, Files and Activity.'); env.delegation();
    await until(() => env.channel().sent.some(event => event.type === 'session.commentary.append' && event.content === 'Files and Activity are both open.') && !env.latest().working);

    assert.equal(env.actions.length, initial.filter(value => !value).length);
    assert.equal(env.plans.length, env.actions.length + 1, 'read the final surface before reporting completion');
    assert.deepEqual(env.plans.map(body => body.surface.controls.map(control => control.expanded)), observedStates);
    for (const [index, body] of env.plans.entries()) {
      assert.deepEqual(body.conversation, [{ role: 'user', text: 'Open both side panels, Files and Activity.' }]);
      assert.deepEqual(body.history, env.actions.slice(0, index).map((action, actionIndex) => ({ action, result: results[actionIndex] })), 'each plan retains every completed action and result');
      if (index > 0) assert.notEqual(body.surface.controls[0].id, env.plans[index - 1].surface.controls[0].id);
    }
    assert.equal(new Set(env.plans.map(body => body.requestId)).size, env.plans.length);
    assert.deepEqual(env.plans.at(-1).surface.controls.map(control => control.expanded), [true, true]);
    assert.deepEqual(expanded, [true, true]);
    assert.deepEqual(env.notices, []);
  });
});

test('new user speech aborts a stale planner before it can change the UI', async t => {
  const env = harness(t, { plan: (_body, env, signal) => env.plans.length === 1 ? new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('Canceled', 'AbortError')), { once: true })) : { type: 'done', message: 'Paused.' } });
  await env.controller.start(); env.started(); env.input('Create a page.', 10, 1000); env.delegation();
  await until(() => env.plans.length === 1);
  env.input(' Actually, stop.', 1100, 2000);
  await until(() => env.plans.length === 2 && !env.latest().working);
  assert.equal(env.actions.length, 0);
  assert.match(env.plans[1].conversation[0].text, /Actually, stop/);
  assert.notEqual(env.plans[0].requestId, env.plans[1].requestId);
});

test('temporary planner contention waits quietly and executes the request exactly once', async t => {
  for (const legacy of [false, true]) await t.test(legacy ? 'older server conflict' : 'typed admission backpressure', async t => {
    const env = harness(t, { planResponse: (body, env) => {
      if (env.plans.length <= 2) return Response.json(legacy
        ? { error: 'A voice action is already in progress.' }
        : { error: 'Voice is catching up.', code: 'VOICE_PLANNER_BUSY', retryable: true, retryAfterMs: 5 }, { status: legacy ? 409 : 429 });
      return Response.json({ action: body.history.length ? { type: 'done', message: 'Home is open.' } : { type: 'click', target: 'home' } });
    } });
    await env.controller.start(); env.started(); env.input('Go home.'); env.delegation();
    await until(() => env.actions.length === 1 && !env.latest().working);
    assert.equal(env.plans.length, 4);
    assert.deepEqual(env.plans[0], env.plans[1]);
    assert.deepEqual(env.plans[0], env.plans[2]);
    assert.deepEqual(env.notices, []);
    assert.ok(env.channel().sent.some(event => event.type === 'session.commentary.append' && event.content === 'Home is open.'));
    assert.ok(env.channel().sent.every(event => !/already in progress|catching up/.test(event.content || '')));
  });
});

test('new speech cancels planner backpressure wait and only the corrected request acts', async t => {
  const env = harness(t, { planResponse: (body, env) => {
    if (env.plans.length === 1) return Response.json({ code: 'VOICE_PLANNER_BUSY', retryable: true, retryAfterMs: 80 }, { status: 429 });
    assert.match(body.conversation.filter(turn => turn.role === 'user').at(-1).text, /Actually, go home/);
    return Response.json({ action: body.history.length ? { type: 'done', message: 'Home is open.' } : { type: 'click', target: 'home' } });
  } });
  await env.controller.start(); env.started(); env.input('Open the community.', 10, 1000); env.delegation();
  await until(() => env.plans.length === 1);
  env.input(' Actually, go home.', 1100, 2000);
  await until(() => env.actions.length === 1 && !env.latest().working);
  await delay(100);
  assert.equal(env.actions.length, 1);
  assert.equal(env.plans.length, 3);
  assert.notEqual(env.plans[0].requestId, env.plans[1].requestId);
  assert.deepEqual(env.notices, []);
});

test('ending Live during a planner wait cancels every retry', async t => {
  const env = harness(t, { planResponse: () => Response.json({ code: 'VOICE_PLANNER_BUSY', retryable: true, retryAfterMs: 80 }, { status: 429 }) });
  await env.controller.start(); env.started(); env.input('Go home.'); env.delegation();
  await until(() => env.plans.length === 1);
  await env.controller.stop();
  await delay(100);
  assert.equal(env.plans.length, 1);
  assert.equal(env.actions.length, 0);
  assert.deepEqual(env.notices, []);
  assert.equal(env.latest().status, 'idle');
});

test('planner contention has a bounded wait and an actionable result if it never clears', async t => {
  const env = harness(t, { planResponse: () => Response.json({ code: 'VOICE_PLANNER_BUSY', retryable: true, retryAfterMs: 10 }, { status: 429 }) });
  await env.controller.start(); env.started(); env.input('Go home.'); env.delegation();
  await until(() => env.notices.length > 0 && !env.latest().working);
  assert.equal(env.actions.length, 0);
  assert.match(env.notices[0], /taking longer than expected.*try your request again/);
  const calls = env.plans.length;
  await delay(100);
  assert.equal(env.plans.length, calls);
  assert.ok(calls > 1 && calls < 15);
});

test('unrelated conflicts and rate limits are not automatically replayed', async t => {
  for (const status of [409, 429]) await t.test(String(status), async t => {
    const env = harness(t, { planResponse: () => Response.json({ error: 'This request needs attention.' }, { status }) });
    await env.controller.start(); env.started(); env.input('Go home.'); env.delegation();
    await until(() => env.notices.length === 1 && !env.latest().working);
    assert.equal(env.plans.length, 1);
    assert.equal(env.actions.length, 0);
  });
});

test('a correction during an already dispatched action retains its factual result', async t => {
  const execution = deferred();
  const env = harness(t, { execute: () => execution.promise, plan: (_body, env) => env.plans.length === 1 ? { type: 'click', target: 'home' } : { type: 'done', message: 'Home already opened; I have paused.' } });
  await env.controller.start(); env.started(); env.input('Go home.', 10, 1000); env.delegation();
  await until(() => env.actions.length === 1);
  env.input(' Actually, wait.', 1100, 2000);
  execution.resolve({ ok: true, message: 'Home opened before the correction arrived.' });
  await until(() => env.plans.length === 2);
  assert.equal(env.actions.length, 1);
  assert.equal(env.plans[1].history[0].result.message, 'Home opened before the correction arrived.');
});

test('a late non-abort error from a superseded plan cannot discard newer speech', async t => {
  const stale = deferred();
  const env = harness(t, { plan: (_body, env) => env.plans.length === 1 ? stale.promise : { type: 'done', message: 'Following the corrected request.' } });
  await env.controller.start(); env.started(); env.input('Open my space.', 10, 1000); env.delegation();
  await until(() => env.plans.length === 1);
  env.input(' Actually, open community.', 1100, 2200);
  stale.reject(new Error('The old network request failed while closing.'));
  await until(() => env.plans.length === 2 && !env.latest().working);
  assert.match(env.plans[1].conversation[0].text, /Actually, open community/);
  assert.deepEqual(env.notices, []);
});

test('a delegation with no user transcript requests clarification and never guesses an action', async t => {
  const env = harness(t);
  await env.controller.start(); env.started(); env.delegation();
  await until(() => env.channel().sent.some(event => event.type === 'session.commentary.append'));
  assert.equal(env.plans.length, 0);
  assert.equal(env.actions.length, 0);
  assert.match(env.channel().sent.find(event => event.type === 'session.commentary.append').content, /Please repeat/);
});

test('destructive confirmation stops the loop until new speech and never reports success', async t => {
  const env = harness(t, { execute: () => ({ ok: false, requiresConfirmation: true, message: 'Do you want to delete this space?' }), plan: () => ({ type: 'click', target: 'home' }) });
  await env.controller.start(); env.started(); env.input('Delete it.'); env.delegation();
  await until(() => env.actions.length === 1 && !env.latest().working);
  assert.equal(env.plans.length, 1);
  assert.ok(env.channel().sent.some(event => event.type === 'session.commentary.append' && event.content === 'Do you want to delete this space?'));
  await delay(25); assert.equal(env.actions.length, 1);
});

test('a prompt confirmation reply forms a stable user turn before a delayed assistant transcript', async t => {
  let requestTurn;
  let confirmed = 0;
  const env = harness(t, {
    execute: (_action, env) => {
      const latest = env.captions.at(-1).filter(turn => turn.role === 'user').at(-1);
      if (!requestTurn) {
        requestTurn = { ...latest };
        return { ok: false, requiresConfirmation: true, message: 'Please say yes to confirm the reset.' };
      }
      assert.notEqual(latest.id, requestTurn.id, 'a fresh answer must not share the original request ID');
      assert.ok(latest.startMs >= requestTurn.endMs);
      assert.equal(latest.text, 'Yes, please do.');
      confirmed++;
      return { ok: true, message: 'The fixture was reset.' };
    },
    plan: body => body.history.length ? { type: 'done', message: 'The fixture was reset.' } : { type: 'click', target: 'home' },
  });
  await env.controller.start(); env.started();
  env.input('Reset ', 0, 400); env.input('the demo.', 400, 1000); env.delegation('reset', 1000);
  await until(() => env.actions.length === 1 && !env.latest().working);
  assert.equal(requestTurn.text, 'Reset the demo.', 'ordinary fragments still group before a question');

  env.delegation('duplicate-reset', 1000);
  await delay(100);
  assert.equal(env.actions.length, 1, 'a duplicate request cannot confirm or repeat the action');
  env.input('Yes, ', 1100, 1250); env.input('please do.', 1250, 1500);
  const answer = { ...env.captions.at(-1).filter(turn => turn.role === 'user').at(-1) };
  assert.equal(answer.text, 'Yes, please do.');
  assert.notEqual(answer.id, requestTurn.id);
  assert.equal(env.captions.at(-1).some(turn => turn.role === 'assistant'), false, 'the boundary does not fabricate assistant speech');
  await delay(20);
  assert.equal(env.actions.length, 1, 'new speech alone does not bypass normal delegation');

  env.channel().message({ type: 'session.output_transcript.delta', event_id: 'late-reset-question', delta: 'Please say yes to confirm.', start_ms: 1010, end_ms: 1090 });
  const afterQuestion = env.captions.at(-1).filter(turn => turn.role === 'user').at(-1);
  assert.equal(afterQuestion.id, answer.id, 'late assistant speech cannot change the answer identity');
  assert.equal(afterQuestion.text, answer.text);
  env.delegation('confirm-reset', 1500);
  await until(() => confirmed === 1 && !env.latest().working);
  assert.deepEqual(env.plans[1].conversation.filter(turn => turn.role === 'user').map(turn => turn.text), ['Reset the demo.', 'Yes, please do.']);
  assert.deepEqual(env.plans[1].history, [], 'confirmation begins a new request, without replaying the opener');
  env.delegation('duplicate-confirmation', 1500);
  await delay(100);
  assert.equal(confirmed, 1);
  assert.equal(env.actions.length, 2, 'only the opener and a single confirmed action execute');
});

test('confirmation turn boundaries survive fragment compaction without an assistant transcript', async t => {
  const env = harness(t, { execute: () => ({ ok: false, requiresConfirmation: true, message: 'Please confirm.' }), plan: () => ({ type: 'click', target: 'home' }) });
  await env.controller.start(); env.started();
  env.input('Reset the demo.', 0, 1000); env.delegation('reset', 1000);
  await until(() => env.actions.length === 1 && !env.latest().working);
  const requestId = env.captions.at(-1)[0].id;
  env.input('Yes', 1100, 1120);
  const replyId = env.captions.at(-1).at(-1).id;
  let expected = 'Yes';
  for (let index = 0; index < 130; index++) {
    const text = ` word${index}`;
    expected += text;
    env.input(text, 1120 + index * 20, 1140 + index * 20);
  }
  const turns = env.captions.at(-1);
  assert.equal(turns.length, 2, 'compaction never rejoins the answer with the original request');
  assert.deepEqual(turns.map(turn => turn.role), ['user', 'user']);
  assert.equal(turns[0].id, requestId);
  assert.equal(turns[0].text, 'Reset the demo.');
  assert.equal(turns[1].id, replyId);
  assert.equal(turns[1].text, expected, 'ordinary answer fragments still group into one complete turn');
  await delay(20);
  assert.equal(env.actions.length, 1, 'compaction and new speech do not automatically run an action');
  assert.equal(env.plans.length, 1);
});

test('late fragments from before a confirmation question stay in the original request turn', async t => {
  const env = harness(t, { execute: () => ({ ok: false, requiresConfirmation: true, message: 'Please confirm.' }), plan: () => ({ type: 'click', target: 'home' }) });
  await env.controller.start(); env.started();
  env.input('Reset the demo', 0, 1000); env.delegation('reset', 1000);
  await until(() => env.actions.length === 1 && !env.latest().working);
  const requestId = env.captions.at(-1)[0].id;
  env.input('.', 950, 1000);
  assert.equal(env.captions.at(-1).length, 1);
  assert.equal(env.captions.at(-1)[0].id, requestId, 'a delayed original fragment is not fresh confirmation');
  assert.equal(env.captions.at(-1)[0].text, 'Reset the demo.');
  env.input('Yes.', 1100, 1300);
  assert.equal(env.captions.at(-1).length, 2);
  assert.notEqual(env.captions.at(-1)[1].id, requestId);
  assert.equal(env.captions.at(-1)[1].text, 'Yes.');
  await delay(20);
  assert.equal(env.actions.length, 1);
});

test('confirmation boundaries include delegated audio whose transcript arrives late', async t => {
  const env = harness(t, { execute: () => ({ ok: false, requiresConfirmation: true, message: 'Please confirm.' }), plan: () => ({ type: 'click', target: 'home' }) });
  await env.controller.start(); env.started();
  env.input('Reset the demo.', 0, 1000); env.delegation('reset', 1800);
  await until(() => env.actions.length === 1 && !env.latest().working);
  const requestId = env.captions.at(-1)[0].id;
  env.input(' Yes, reset it.', 1200, 1600);
  assert.equal(env.captions.at(-1).length, 1, 'audio already covered by the opening delegation is not fresh consent');
  assert.equal(env.captions.at(-1)[0].id, requestId);
  env.input('Yes.', 2000, 2200);
  assert.equal(env.captions.at(-1).length, 2, 'audio after the original delegation can form a fresh reply');
  assert.notEqual(env.captions.at(-1)[1].id, requestId);
  assert.equal(env.captions.at(-1)[1].text, 'Yes.');
  await delay(20);
  assert.equal(env.actions.length, 1, 'late audio alone does not dispatch an action');
});

test('microphone mute waits for the matching acknowledgment and fails locally closed', async t => {
  const env = harness(t);
  await env.controller.start(); env.started();
  env.controller.setMuted(true);
  assert.equal(env.streams[0].tracks[0].enabled, false);
  assert.equal(env.latest().mutePending, true);
  const command = env.channel().sent.find(event => event.type === 'session.input_audio.mute');
  env.channel().message({ type: 'session.input_audio.muted', client_event_id: 'wrong' });
  assert.equal(env.latest().mutePending, true);
  env.channel().message({ type: 'session.input_audio.muted', client_event_id: command.event_id });
  assert.equal(env.latest().mutePending, false);
  env.controller.setMuted(false);
  assert.equal(env.streams[0].tracks[0].enabled, true);
  await until(() => env.latest().muted === true && env.latest().mutePending === false);
  assert.equal(env.streams[0].tracks[0].enabled, false);
  assert.match(env.notices.at(-1), /did not confirm/);
});

test('speaking comes from actual playback levels and blocked autoplay can recover', async t => {
  const env = harness(t);
  env.playBlocked = true;
  await env.controller.start(); env.started();
  env.peers[0].emit('track', { streams: [new Stream()], track: new Track() });
  await until(() => env.latest().audioBlocked);
  env.meters[1].amplitude = 20;
  env.channel().message({ type: 'session.output_transcript.delta', event_id: 'out1', delta: 'Hello', start_ms: 1, end_ms: 100 });
  await delay(75);
  assert.equal(env.latest().speaking, false);
  env.playBlocked = false;
  await env.controller.resumeAudio();
  await until(() => env.latest().speaking);
  assert.equal(env.latest().audioBlocked, false);
  assert.ok(env.levels.at(-1).output > 0);
  env.meters[1].amplitude = 0;
  await until(() => !env.latest().speaking);
});

test('stopping aborts pending plans and ignores late responses', async t => {
  const plan = deferred();
  const env = harness(t, { plan: () => plan.promise });
  await env.controller.start(); env.started(); env.input('Go home.'); env.delegation();
  await until(() => env.plans.length === 1);
  const signal = env.requests.find(request => request.path === '/api/voice/plan').init.signal;
  await env.controller.stop();
  assert.equal(signal.aborted, true);
  plan.resolve({ type: 'click', target: 'home' });
  await delay(25);
  assert.equal(env.actions.length, 0);
  assert.equal(env.latest().status, 'idle');
});

test('audio playback does not wait for optional level metering to resume', async t => {
  const cases = [
    { name: 'pending', resume: () => deferred().promise },
    { name: 'rejected', resume: () => Promise.reject(new DOMException('Meter blocked', 'NotAllowedError')) },
    { name: 'throws synchronously', resume: () => { throw new Error('Meter unavailable'); } },
  ];
  for (const scenario of cases) await t.test(scenario.name, async t => {
    const env = harness(t, { resumeAudioContext: context => { context.state = 'suspended'; return scenario.resume(); } });
    await env.controller.start(); env.started();
    env.peers[0].emit('track', { streams: [new Stream()] });
    assert.equal(env.audios[0].paused, false, 'Playback starts without awaiting the meter');
    await env.controller.resumeAudio();
    assert.equal(env.latest().audioBlocked, false);
    assert.equal(env.notices.length, 0, 'A meter failure is not an audio playback failure');
    assert.equal(env.latest().connected, true);
  });
});

test('blocked playback still requires Enable audio when level metering cannot resume', async t => {
  const env = harness(t, { resumeAudioContext: () => deferred().promise });
  env.playBlocked = true;
  await env.controller.start(); env.started();
  env.peers[0].emit('track', { streams: [new Stream()] });
  await until(() => env.latest().audioBlocked);
  assert.equal(env.audios[0].paused, true);
  assert.match(env.notices.at(-1), /Enable audio/);
  env.playBlocked = false;
  await env.controller.resumeAudio();
  assert.equal(env.audios[0].paused, false);
  assert.equal(env.latest().audioBlocked, false);
});

test('track loss requires a new device while sustained peer disconnect recovers automatically', async t => {
  const env = harness(t);
  await env.controller.start(); env.started();
  env.peers[0].connectionState = 'disconnected'; env.peers[0].emit('connectionstatechange');
  env.peers[0].connectionState = 'connected'; env.peers[0].emit('connectionstatechange');
  await delay(35); assert.equal(env.latest().connected, true);
  env.streams[0].tracks[0].emit('ended');
  assert.equal(env.latest().status, 'error');
  assert.match(env.latest().error, /microphone disconnected/);
  assert.equal(env.peers[0].closed, true);
  await env.controller.start(); env.started();
  env.peers[1].connectionState = 'disconnected'; env.peers[1].emit('connectionstatechange');
  await until(() => env.latest().status === 'reconnecting');
  assert.equal(env.peers[1].closed, true);
  await until(() => env.peers.length === 3 && env.peers[2].remoteDescription);
  env.started();
  assert.equal(env.latest().status, 'listening');
});

test('malformed and duplicate transport events cannot repeat actions or crash a session', async t => {
  const env = harness(t);
  await env.controller.start(); env.started();
  env.channel().emit('message', { data: 'not json' });
  env.channel().message(null);
  env.channel().message({ type: 'session.input_transcript.delta', delta: 'Bad', start_ms: '0', end_ms: 100 });
  const event = { type: 'session.input_transcript.delta', event_id: 'same', delta: 'Hello', start_ms: 0, end_ms: 100 };
  env.channel().message(event); env.channel().message(event);
  assert.equal(env.captions.at(-1)[0].text, 'Hello');
  assert.equal(env.latest().connected, true);
});

test('context updates stay quiet, deduplicate, and stay below the append byte limit', async t => {
  const env = harness(t);
  await env.controller.start();
  await env.controller.updateContext('🪐'.repeat(600));
  assert.equal(env.channel().sent.length, 0);
  env.started();
  await until(() => env.channel().sent.some(event => event.type === 'session.thinking.append'));
  const count = env.channel().sent.length;
  await env.controller.updateContext();
  assert.equal(env.channel().sent.length, count);
  for (const event of env.channel().sent.filter(event => event.content)) assert.ok(Buffer.byteLength(event.content) <= 460);
  assert.ok(env.channel().sent.filter(event => event.type === 'session.thinking.append').every(event => event.delegation_id === null));
});

test('maximum session duration renews the connection without switching Live off', async t => {
  const env = harness(t);
  env.controller = env.make({ timings: { maxSession: 30, close: 5 } });
  await env.controller.start(); env.started();
  await until(() => env.latest().status === 'reconnecting');
  assert.equal(env.streams[0].tracks[0].stopped, true);
  await until(() => env.peers.length === 2 && env.peers[1].remoteDescription);
  assert.equal(env.peers[0].closed, true);
  assert.ok(env.peers[0].channel.sent.some(event => event.type === 'session.close'));
  env.started();
  assert.equal(env.latest().status, 'listening');
  assert.match(env.latest().notice, /reconnected/);
});

test('quiet time and completed work leave Live on until the user ends it', async t => {
  const pending = deferred();
  const env = harness(t, { plan: () => pending.promise });
  env.controller = env.make({ timings: { idle: 25, settle: 3, close: 5 } });
  await env.controller.start(); env.started(); env.input('Go home.'); env.delegation();
  await until(() => env.plans.length === 1);
  await delay(65);
  assert.equal(env.latest().connected, true);
  pending.resolve({ type: 'done', message: 'Ready.' });
  await until(() => !env.latest().working);
  await delay(75);
  assert.equal(env.latest().connected, true);
  assert.equal(env.streams[0].tracks[0].stopped, false);
  await env.controller.stop();
  assert.equal(env.streams[0].tracks[0].stopped, true);
});

test('keyboard actions accept the same names as the server planner', async t => {
  const keys = ['Space', 'Home', 'End', 'PageUp', 'PageDown'];
  const env = harness(t, { plan: (_body, env) => keys[env.plans.length - 1] ? { type: 'press', target: 'home', key: keys[env.plans.length - 1] } : { type: 'done', message: 'Ready.' } });
  await env.controller.start(); env.started(); env.input('Use the keyboard.'); env.delegation();
  await until(() => env.actions.length === keys.length && !env.latest().working);
  assert.deepEqual(env.actions.map(action => action.key), keys);
});

test('a repeated unchanged action is blocked before a second submit', async t => {
  const env = harness(t, { plan: () => ({ type: 'click', target: 'home' }) });
  await env.controller.start(); env.started(); env.input('Submit the form.'); env.delegation();
  await until(() => env.notices.some(message => /has not changed/.test(message)));
  assert.equal(env.actions.length, 1);
  assert.equal(env.plans.length, 2);
});

test('the ten-step action budget ends a runaway UI loop', async t => {
  const env = harness(t, { readSurface: n => surface(`View ${n}`), plan: () => ({ type: 'click', target: 'home' }) });
  await env.controller.start(); env.started(); env.input('Visit the pages.'); env.delegation();
  await until(() => env.actions.length === 10 && !env.latest().working);
  assert.equal(env.plans.length, 10);
  assert.match(env.channel().sent.filter(event => event.type === 'session.commentary.append').at(-1).content, /limit for this request/);
});

test('startup without a session token releases microphone and never enters listening', async t => {
  const env = harness(t, { session: { session: { id: 'live_test' }, transport: { type: 'webrtc', sdp: 'answer-sdp' } } });
  await env.controller.start();
  assert.equal(env.latest().status, 'error');
  assert.match(env.latest().error, /incomplete connection/);
  assert.equal(env.streams[0].tracks[0].stopped, true);
  assert.equal(env.peers[0].closed, true);
});

test('destroy sends close and cancels pending plans without callback updates after unmount', async t => {
  const env = harness(t);
  await env.controller.start(); env.started();
  const updates = env.states.length;
  env.controller.destroy();
  assert.equal(env.streams[0].tracks[0].stopped, true);
  assert.ok(env.channel().sent.some(event => event.type === 'session.close'));
  await delay(25);
  assert.equal(env.states.length, updates);
  assert.equal(env.peers[0].closed, true);
});

test('a generic Live error does not silently mute the microphone', async t => {
  const env = harness(t);
  await env.controller.start(); env.started();
  env.channel().message({ type: 'error', error: { code: 'temporary_error' } });
  assert.equal(env.latest().muted, false);
  assert.equal(env.streams[0].tracks[0].enabled, true);
  assert.match(env.notices.at(-1), /could not process an update/);
});

test('muting before microphone permission resolves prevents the new track from transmitting', async t => {
  const media = deferred();
  const env = harness(t, { media: () => media.promise });
  const starting = env.controller.start();
  env.controller.setMuted(true);
  const microphone = new Stream(); media.resolve(microphone);
  await starting;
  assert.equal(microphone.tracks[0].enabled, false);
  env.started();
  assert.equal(microphone.tracks[0].enabled, false);
  assert.ok(env.channel().sent.some(event => event.type === 'session.input_audio.mute'));
});

test('background context updates never replace the control capture for a pending plan', async t => {
  let reads = 0;
  const pending = deferred();
  const env = harness(t, { readSurface: () => { reads++; return surface(); }, plan: () => pending.promise });
  await env.controller.updateContext('The builder is open.');
  await env.controller.start(); env.started();
  assert.equal(reads, 0);
  env.input('Fill in a new title.'); env.delegation();
  await until(() => env.plans.length === 1);
  assert.equal(reads, 1);
  await env.controller.updateContext('The user typed a different title.');
  await env.controller.updateContext();
  assert.equal(reads, 1);
  pending.resolve({ type: 'done', message: 'The existing draft is still in place.' });
  await until(() => !env.latest().working);
  assert.equal(reads, 1);
});

test('volatile capture IDs and cosmetic planner messages cannot bypass duplicate-submit protection', async t => {
  const env = harness(t, {
    readSurface: version => ({ ...surface(), controls: [{ id: `ui-1-v${version}`, role: 'button', label: 'Submit' }, { id: `frame:field-v${version}`, role: 'textbox', label: 'Draft', value: 'Hello' }] }),
    plan: (body, env) => ({ type: 'click', target: body.surface.controls[0].id, message: `Step ${env.plans.length}` }),
  });
  await env.controller.start(); env.started(); env.input('Submit the form.'); env.delegation();
  await until(() => env.notices.some(message => /has not changed/.test(message)));
  assert.equal(env.plans.length, 2);
  assert.notEqual(env.plans[0].surface.controls[0].id, env.plans[1].surface.controls[0].id);
  assert.equal(env.actions.length, 1);
  assert.equal(env.actions[0].target, env.plans[0].surface.controls[0].id);
});

test('semantically identical controls at different positions remain distinct actions', async t => {
  const env = harness(t, {
    readSurface: version => ({ ...surface(), controls: [0, 1].map(index => ({ id: `ui-${index}-v${version}`, role: 'button', label: 'Like' })) }),
    plan: (body, env) => env.plans.length <= 2 ? { type: 'click', target: body.surface.controls[env.plans.length - 1].id } : { type: 'done', message: 'Both items are liked.' },
  });
  await env.controller.start(); env.started(); env.input('Like both items.'); env.delegation();
  await until(() => env.actions.length === 2 && !env.latest().working);
  assert.equal(env.notices.length, 0);
  assert.notEqual(env.actions[0].target, env.actions[1].target);
});

test('an interrupted submit retains duplicate protection when a delayed fragment causes replanning', async t => {
  const execution = deferred();
  const env = harness(t, {
    readSurface: version => ({ ...surface(), controls: [{ id: `frame:submit-v${version}`, role: 'button', label: 'Submit' }] }),
    plan: body => ({ type: 'click', target: body.surface.controls[0].id }),
    execute: () => execution.promise,
  });
  await env.controller.start(); env.started(); env.input('Submit ', 0, 500); env.delegation('first', 500);
  await until(() => env.actions.length === 1);
  env.input('the form.', 500, 1000);
  execution.resolve({ ok: true, message: 'The form was submitted.' });
  await until(() => env.notices.some(message => /has not changed/.test(message)));
  assert.equal(env.plans.length, 2);
  assert.equal(env.actions.length, 1);
  assert.equal(env.plans[1].history[0].result.message, 'The form was submitted.');
});

test('a continuation fragment after completion inherits prior submit evidence across delegation IDs', async t => {
  const env = harness(t, {
    readSurface: version => ({ ...surface(), controls: [{ id: `ui-1-v${version}`, role: 'button', label: 'Submit' }] }),
    plan: (body, env) => env.plans.length === 2 ? { type: 'done', message: 'Submitted.' } : { type: 'click', target: body.surface.controls[0].id },
  });
  await env.controller.start(); env.started(); env.input('Submit ', 0, 500); env.delegation('first', 500);
  await until(() => env.plans.length === 2 && !env.latest().working);
  env.input('the form.', 500, 1000); env.delegation('continuation', 1000);
  await until(() => env.notices.some(message => /has not changed/.test(message)));
  assert.equal(env.actions.length, 1);
  assert.equal(env.plans[2].history.length, 1);
  assert.match(env.plans[2].conversation[0].text, /Submit the form/);
});

test('a new user turn after assistant speech can intentionally repeat a prior action', async t => {
  const env = harness(t, {
    readSurface: version => ({ ...surface(), controls: [{ id: `ui-1-v${version}`, role: 'button', label: 'Submit' }] }),
    plan: (body, env) => env.plans.length % 2 === 0 ? { type: 'done', message: 'Submitted.' } : { type: 'click', target: body.surface.controls[0].id },
  });
  await env.controller.start(); env.started(); env.input('Submit it.', 0, 1000); env.delegation('first', 1000);
  await until(() => env.plans.length === 2 && !env.latest().working);
  env.channel().message({ type: 'session.output_transcript.delta', event_id: 'reply', delta: 'Submitted.', start_ms: 1100, end_ms: 1500 });
  env.input('Again, please.', 1600, 2000); env.delegation('again', 2000);
  await until(() => env.plans.length === 4 && !env.latest().working);
  assert.equal(env.actions.length, 2);
  assert.equal(env.plans[2].history.length, 0);
});

test('repeated scrolling and navigation keys remain available when text does not change', async t => {
  const sequence = [
    { type: 'scroll', direction: 'down' }, { type: 'scroll', direction: 'down' },
    { type: 'press', key: 'ArrowRight' }, { type: 'press', key: 'ArrowRight' },
  ];
  const env = harness(t, {
    readSurface: version => ({ ...surface(), controls: [{ id: `ui-1-v${version}`, role: 'button', label: 'Globe' }] }),
    plan: (body, env) => sequence[env.plans.length - 1] ? { ...sequence[env.plans.length - 1], target: body.surface.controls[0].id } : { type: 'done', message: 'Moved.' },
  });
  await env.controller.start(); env.started(); env.input('Scroll down twice, then rotate right twice.'); env.delegation();
  await until(() => env.actions.length === 4 && !env.latest().working);
  assert.equal(env.notices.length, 0);
});

test('audible user interruption pauses dispatch until its delayed transcript arrives', async t => {
  const pending = deferred();
  const env = harness(t, { plan: (_body, env) => env.plans.length === 1 ? pending.promise : { type: 'done', message: 'Paused.' } });
  await env.controller.start(); env.started(); env.input('Submit the form.'); env.delegation();
  await until(() => env.plans.length === 1);
  env.meters[0].amplitude = 30;
  await until(() => env.levels.some(level => level.input > .07));
  env.meters[0].amplitude = 0;
  pending.resolve({ type: 'click', target: 'home' });
  await delay(25);
  assert.equal(env.actions.length, 0);
  assert.equal(env.plans.length, 1);
  env.input('Actually, wait.', 1100, 1500);
  await until(() => env.plans.length === 2 && !env.latest().working);
  assert.equal(env.actions.length, 0);
  assert.match(env.plans[1].conversation[0].text, /Actually, wait/);
});

test('an audible interruption without a transcript asks again instead of dispatching old work', async t => {
  const pending = deferred();
  const env = harness(t, { plan: () => pending.promise });
  await env.controller.start(); env.started(); env.input('Submit the form.'); env.delegation();
  await until(() => env.plans.length === 1);
  env.meters[0].amplitude = 30;
  await until(() => env.levels.some(level => level.input > .07));
  env.meters[0].amplitude = 0;
  pending.resolve({ type: 'click', target: 'home' });
  await until(() => env.channel().sent.some(event => event.type === 'session.commentary.append' && /heard more speech/.test(event.content)));
  assert.equal(env.actions.length, 0);
  assert.equal(env.plans.length, 1);
});

test('long word-fragmented creative dictation keeps its opening instructions and complete recent utterance', async t => {
  const env = harness(t);
  await env.controller.start(); env.started();
  const expected = `Keep the original canvas size and do not publish. ${Array.from({ length: 500 }, (_, index) => `Use color${index} gently. `).join('')}End with a small moon.`;
  assert.ok(expected.length > 9_000 && expected.length < 12_000);
  const words = expected.match(/\S+\s*/g);
  assert.ok(words.length > 160);
  words.forEach((word, index) => env.input(word, index * 20, (index + 1) * 20));
  const end = words.length * 20;
  env.delegation('long-dictation', end);
  await until(() => env.plans.length === 1 && !env.latest().working);
  assert.deepEqual(env.plans[0].conversation, [{ role: 'user', text: expected }]);
  assert.equal(env.captions.at(-1)[0].text, expected);
  assert.equal(env.captions.at(-1)[0].startMs, 0);
  assert.equal(env.captions.at(-1)[0].endMs, end);
});

test('long conversations keep bounded recent turns instead of partial older fragment tails', async t => {
  const env = harness(t);
  await env.controller.start(); env.started();
  for (let index = 0; index < 80; index++) {
    const text = `Turn ${index}. ${'detail '.repeat(400)}`;
    if (index % 2 === 0) env.input(text, index * 3000, index * 3000 + 1000);
    else env.channel().message({ type: 'session.output_transcript.delta', event_id: `long-reply-${index}`, delta: text, start_ms: index * 3000, end_ms: index * 3000 + 1000 });
  }
  env.input('Please continue with the newest idea.', 240000, 241000);
  env.delegation('latest', 241000);
  await until(() => env.plans.length === 1 && !env.latest().working);
  const conversation = env.plans[0].conversation;
  assert.ok(conversation.length <= 32);
  assert.ok(conversation.reduce((total, turn) => total + turn.text.length, 0) <= 48_000);
  assert.ok(conversation.every(turn => turn.text.length <= 12_000));
  assert.equal(conversation.at(-1).text, 'Please continue with the newest idea.');
  assert.ok(conversation.slice(0, -1).every(turn => /^Turn \d+\./.test(turn.text)));
});

test('a channel failure reconnects automatically and preserves the local mute preference', async t => {
  const env = harness(t);
  await env.controller.start(); env.started();
  env.input('Remember the blue theme.', 10, 1000);
  env.controller.setMuted(true);
  const firstChannel = env.channel();
  firstChannel.close();
  assert.equal(env.latest().status, 'reconnecting');
  assert.equal(env.latest().muted, true);
  assert.equal(env.streams[0].tracks[0].stopped, true);
  await env.controller.start(); // Clicking again must not race the scheduled retry.
  await until(() => env.peers.length === 2 && env.peers[1].remoteDescription);
  assert.equal(env.streams[1].tracks[0].enabled, false);
  env.started();
  assert.equal(env.latest().status, 'muted');
  assert.ok(env.channel().sent.some(event => event.type === 'session.input_audio.mute'));
  const request = env.requests.filter(request => request.path === '/api/voice/session').at(-1);
  assert.deepEqual(request.body.conversation, [{ role: 'user', text: 'Remember the blue theme.' }]);
  assert.match(env.channel().sent.find(event => event.type === 'session.instructions.append').content, /Never restart old app actions/);
  firstChannel.message({ type: 'session.closed' });
  assert.equal(env.latest().connected, true);
  assert.equal(env.peers[1].closed, undefined);
});

test('recovery cancels old plans and requires fresh speech with independent transcript timing', async t => {
  const pending = deferred();
  const env = harness(t, { plan: (_body, env) => env.plans.length === 1 ? pending.promise : { type: 'done', message: 'Ready for the new request.' } });
  await env.controller.start(); env.started(); env.input('Submit my page.', 5000, 6000); env.delegation('old', 6000);
  await until(() => env.plans.length === 1);
  const oldChannel = env.channel();
  const oldSignal = env.requests.find(request => request.path === '/api/voice/plan').init.signal;
  oldChannel.close();
  assert.equal(oldSignal.aborted, true);
  await until(() => env.peers.length === 2 && env.peers[1].remoteDescription);
  env.started();
  assert.match(env.latest().notice, /repeat your interrupted request/);
  pending.resolve({ type: 'click', target: 'home' });
  oldChannel.message({ type: 'session.input_transcript.delta', event_id: 'late', delta: 'Old late speech.', start_ms: 6000, end_ms: 7000 });
  env.delegation('stale-memory', 6000);
  await delay(100);
  assert.equal(env.actions.length, 0);
  assert.equal(env.plans.length, 1);
  env.input('Open the help screen.', 0, 500); env.delegation('new', 500);
  await until(() => env.plans.length === 2 && !env.latest().working);
  assert.deepEqual(env.plans[1].history, []);
  assert.equal(env.plans[1].conversation.at(-1).text, 'Open the help screen.');
  assert.ok(env.plans[1].conversation.some(turn => /Earlier app requests are closed/.test(turn.text)));
  assert.deepEqual(env.captions.at(-1).map(turn => turn.text), ['Submit my page.', 'Open the help screen.']);
  assert.notEqual(env.captions.at(-1)[0].id, env.captions.at(-1)[1].id);
});

test('automatic retries are bounded and leave an actionable error after repeated server failures', async t => {
  const env = harness(t, { sessionResponse: (_body, env) => env.requests.filter(request => request.path === '/api/voice/session').length > 1 ? new Response(JSON.stringify({ error: 'Temporarily unavailable' }), { status: 503 }) : undefined });
  await env.controller.start(); env.started(); env.channel().close();
  await until(() => env.latest().status === 'error');
  assert.match(env.latest().error, /could not reconnect after several attempts/);
  assert.equal(env.peers.length, 5);
  assert.ok(env.streams.every(stream => stream.tracks[0].stopped));
  await delay(80);
  assert.equal(env.peers.length, 5);
});

test('manual stop cancels a scheduled retry and never turns the microphone back on', async t => {
  const env = harness(t);
  await env.controller.start(); env.started(); env.channel().close();
  assert.equal(env.latest().status, 'reconnecting');
  await env.controller.stop();
  await delay(60);
  assert.equal(env.latest().status, 'idle');
  assert.equal(env.mediaCount, 1);
  env.network(false); env.network(true);
  await delay(30);
  assert.equal(env.mediaCount, 1);
});

test('destroy during a retry releases late microphone permission without callbacks or another connection', async t => {
  const pending = deferred();
  const env = harness(t, { media: env => env.mediaCount === 1 ? Promise.resolve(new Stream()) : pending.promise });
  await env.controller.start(); env.started(); env.channel().close();
  await until(() => env.mediaCount === 2);
  env.controller.destroy();
  const stateCount = env.states.length;
  const lateStream = new Stream(); pending.resolve(lateStream);
  await delay(70);
  assert.equal(lateStream.tracks[0].stopped, true);
  assert.equal(env.states.length, stateCount);
  assert.equal(env.requests.filter(request => request.path === '/api/voice/session').length, 1);
  env.network(false); env.network(true);
  assert.equal(env.mediaCount, 2);
});

test('initial permission denial and recovery authentication failure never enter retry loops', async t => {
  const permission = harness(t, { media: () => Promise.reject(new DOMException('Denied', 'NotAllowedError')) });
  await permission.controller.start();
  assert.match(permission.latest().error, /Microphone access is blocked/);
  await delay(40);
  assert.equal(permission.mediaCount, 1);
  permission.controller.destroy();

  const auth = harness(t, { sessionResponse: (_body, env) => env.requests.filter(request => request.path === '/api/voice/session').length > 1 ? new Response(JSON.stringify({ error: 'Check the configured key.' }), { status: 401 }) : undefined });
  await auth.controller.start(); auth.started(); auth.channel().close();
  await until(() => auth.latest().status === 'error');
  assert.equal(auth.latest().error, 'Check the configured key.');
  await delay(70);
  assert.equal(auth.mediaCount, 2);
});

test('offline recovery waits without reacquiring the microphone and resumes when online', async t => {
  const env = harness(t);
  await env.controller.start(); env.started();
  env.network(false);
  assert.equal(env.latest().status, 'reconnecting');
  assert.match(env.latest().notice, /offline/);
  assert.equal(env.streams[0].tracks[0].stopped, true);
  await delay(80);
  assert.equal(env.mediaCount, 1);
  env.network(true);
  await until(() => env.peers.length === 2 && env.peers[1].remoteDescription);
  env.started();
  assert.equal(env.latest().status, 'listening');
});

test('provider session expiration recovers and carries bounded conversation memory', async t => {
  const env = harness(t);
  await env.controller.start(); env.started();
  for (let index = 0; index < 30; index++) env.input(`Idea ${index}: ${'🌱'.repeat(1600)}`, index * 5000, index * 5000 + 1000);
  env.channel().message({ type: 'session.closed', reason: 'expired' });
  assert.equal(env.latest().status, 'reconnecting');
  await until(() => env.peers.length === 2 && env.peers[1].remoteDescription);
  env.started();
  const memory = env.requests.filter(request => request.path === '/api/voice/session').at(-1).body.conversation;
  assert.ok(memory.length <= 16);
  assert.ok(memory.every(turn => turn.text.length <= 6000));
  assert.ok(memory.reduce((total, turn) => total + Buffer.byteLength(turn.text), 0) <= 8000);
  assert.match(memory.at(-1).text, /^Idea 29:/);
  assert.equal(env.latest().connected, true);
});

test('renewal waits for pending work within its grace period and then reconnects cleanly', async t => {
  const pending = deferred();
  const env = harness(t, { plan: () => pending.promise });
  env.controller = env.make({ timings: { maxSession: 30, renewGrace: 100, close: 5 } });
  await env.controller.start(); env.started(); env.input('Open Home.'); env.delegation();
  await until(() => env.plans.length === 1);
  await delay(50);
  assert.equal(env.peers.length, 1);
  assert.equal(env.latest().working, true);
  pending.resolve({ type: 'done', message: 'Home is open.' });
  await until(() => env.peers.length === 2 && env.peers[1].remoteDescription);
  env.started();
  assert.equal(env.latest().status, 'listening');
  assert.doesNotMatch(env.latest().notice, /interrupted/);
});

test('renewal deadline cancels an unfinished request without replaying it', async t => {
  const pending = deferred();
  const env = harness(t, { plan: () => pending.promise });
  env.controller = env.make({ timings: { maxSession: 20, renewGrace: 25, close: 5 } });
  await env.controller.start(); env.started(); env.input('Publish the page.'); env.delegation();
  await until(() => env.plans.length === 1);
  await until(() => env.peers.length === 2 && env.peers[1].remoteDescription);
  env.started();
  assert.match(env.latest().notice, /repeat your interrupted request/);
  pending.resolve({ type: 'click', target: 'home' });
  await delay(10);
  assert.equal(env.actions.length, 0);
  assert.equal(env.plans.length, 1);
});

test('account changes keep Live on while clearing the old actor speech and pending actions', async t => {
  const pending = deferred();
  const env = harness(t, { plan: (_body, env) => env.plans.length === 1 ? pending.promise : { type: 'done', message: 'Ready with the new account.' } });
  await env.controller.start(); env.started(); env.input('Submit my private draft.', 0, 1000); env.delegation('old-account');
  await until(() => env.plans.length === 1);
  env.controller.setMuted(true);
  const oldChannel = env.channel();
  env.controller.resetConversation();
  assert.equal(env.latest().status, 'reconnecting');
  assert.deepEqual(env.captions.at(-1), []);
  assert.equal(env.requests.find(request => request.path === '/api/voice/plan').init.signal.aborted, true);
  await until(() => env.peers.length === 2 && env.peers[1].remoteDescription);
  const sessionRequest = env.requests.filter(request => request.path === '/api/voice/session').at(-1);
  assert.equal(sessionRequest.body.conversation, undefined);
  assert.equal(env.streams[1].tracks[0].enabled, false);
  env.started();
  assert.equal(env.latest().status, 'muted');
  pending.resolve({ type: 'click', target: 'home' });
  oldChannel.message({ type: 'session.input_transcript.delta', event_id: 'late-old-account', delta: 'Publish it.', start_ms: 1000, end_ms: 2000 });
  env.delegation('replayed', 1000);
  await delay(100);
  assert.equal(env.actions.length, 0);
  assert.equal(env.plans.length, 1);
  env.controller.setMuted(false);
  env.input('Open this account profile.', 0, 500); env.delegation('new-account', 500);
  await until(() => env.plans.length === 2);
  assert.deepEqual(env.plans[1].conversation, [{ role: 'user', text: 'Open this account profile.' }]);
  assert.deepEqual(env.plans[1].history, []);
  assert.deepEqual(env.captions.at(-1).map(turn => turn.text), ['Open this account profile.']);
});

test('account reset while Live is off does not acquire the microphone', async t => {
  const env = harness(t);
  env.controller.resetConversation();
  await delay(20);
  assert.equal(env.mediaCount, 0);
  await env.controller.start(); env.started();
  env.controller.resetConversation();
  await env.controller.stop();
  await delay(40);
  assert.equal(env.mediaCount, 1);
  assert.equal(env.latest().status, 'idle');
});

test('starting from saved mute intent never adds an enabled microphone track', async t => {
  const env = harness(t);
  await env.controller.start({ muted: true });
  assert.deepEqual(env.peers[0].addedTrackEnabled, [false]);
  assert.equal(env.streams[0].tracks[0].enabled, false);
  env.started();
  assert.equal(env.latest().status, 'muted');
  assert.ok(env.channel().sent.some(event => event.type === 'session.input_audio.mute'));
});

test('explicit permanent configuration errors stop even when the server uses HTTP503', async t => {
  const env = harness(t, { sessionResponse: (_body, env) => env.requests.filter(request => request.path === '/api/voice/session').length > 1 ? new Response(JSON.stringify({ error: 'The configured model is unavailable.', retryable: false }), { status: 503 }) : undefined });
  await env.controller.start(); env.started(); env.channel().close();
  await until(() => env.latest().status === 'error');
  assert.equal(env.latest().error, 'The configured model is unavailable.');
  await delay(70);
  assert.equal(env.mediaCount, 2);
});

test('a second request is not lost when its delegation arrives before its transcript', async t => {
  const env = harness(t, { readSurface: version => surface(`Version ${version}`), plan: (_body, env) => env.plans.length % 2 ? { type: 'click', target: 'home' } : { type: 'done', message: 'Tile created.' } });
  await env.controller.start(); env.started();
  env.input('Create the first tile.', 0, 1000); env.delegation('first-tile', 1000);
  await until(() => env.plans.length === 2 && !env.latest().working);
  env.channel().message({ type: 'session.output_transcript.delta', event_id: 'first-reply', delta: 'First tile created.', start_ms: 1100, end_ms: 1700 });
  env.delegation('second-tile', 4000);
  await delay(25);
  assert.equal(env.plans.length, 2);
  env.input('Create the second tile.', 3000, 4000);
  await until(() => env.plans.length === 4 && !env.latest().working);
  assert.equal(env.actions.length, 2);
  assert.equal(env.plans[2].conversation.at(-1).text, 'Create the second tile.');
  assert.deepEqual(env.plans[2].history, []);
  assert.match(env.plans[2].requestId, /^second-tile:/);
  env.delegation('duplicate-second-tile', 4000);
  await delay(100);
  assert.equal(env.actions.length, 2);
  assert.equal(env.plans.length, 4);
});

test('exhausted correction retries explain the pause instead of silently dropping the request', async t => {
  const env = harness(t, { plan: (_body, env, signal) => env.plans.length <= 9 ? new Promise((_resolve, reject) => signal.addEventListener('abort', () => reject(new DOMException('Canceled', 'AbortError')), { once: true })) : { type: 'done', message: 'Understood.' } });
  await env.controller.start(); env.started(); env.input('Make a page.', 0, 1000); env.delegation('changing', 1000);
  for (let correction = 1; correction <= 9; correction++) {
    await until(() => env.plans.length === correction);
    env.input(`Correction ${correction}.`, correction * 1000, (correction + 1) * 1000);
  }
  await until(() => !env.latest().working && env.notices.some(notice => /request kept changing/.test(notice)));
  assert.equal(env.actions.length, 0);
  assert.ok(env.channel().sent.some(event => event.type === 'session.commentary.append' && /repeat the full request/.test(event.content)));
  env.input('Here is my complete new request.', 15000, 16000); env.delegation('new-clear-request', 16000);
  await until(() => env.plans.length === 10 && !env.latest().working);
  assert.deepEqual(env.plans[9].history, []);
});
