import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import type { Root } from 'react-dom/client';
import type { RuntimeEvent, SavedTurn, Snapshot, SpaceSummary } from '../../src/types';
import type { VoiceActionResult, VoiceControl } from '../../src/live-voice';
import type { BuildComparisonState } from '../../src/useBuildComparison';
import '../../src/styles.css';
import '../../src/theme.css';
import '../../src/presentation.css';

// Everything below is local to this standalone browser fixture. In particular,
// never forward an API request to the demo server or open a hardware microphone.
const originalHref = location.href;
const originalHistory = history.state;
const savedStorage = new Map<string, string>();
for (let index = 0; index < sessionStorage.length; index++) {
  const key = sessionStorage.key(index)!;
  if (/^(little-worlds|living-spaces)[:.]/.test(key)) savedStorage.set(key, sessionStorage.getItem(key)!);
}
function clearAppStorage() {
  for (const key of Object.keys(sessionStorage)) if (/^(little-worlds|living-spaces)[:.]/.test(key)) sessionStorage.removeItem(key);
}

const stats = { microphones: 0, trackStops: 0, sessions: 0, ends: 0, permissionQueries: 0, turnRequests: 0, finishes: 0, peers: [] as FixturePeer[], requests: [] as string[], unexpected: [] as string[], builds: [] as { spaceId: string; turn: SavedTurn }[], planHistories: [] as { result: VoiceActionResult }[][] };
const eventStreams = new Map<string, Set<ReadableStreamDefaultController<Uint8Array>>>();
const comparisonStreams = new Map<string, Set<ReadableStreamDefaultController<Uint8Array>>>();
const comparisons = new Map<string, BuildComparisonState>();
const runtimeEvents = new Map<string, RuntimeEvent[]>();
let activeSessions = 1;
let plannedDraft = '';
let plannedSubmit = true;
let plannedFinish = false;
let plannedWorldNote = '';
let turnAcceptanceGate: Promise<void> | undefined;
let speechSerial = 0;
let signedInId: string | null = null;
let permissionMode: 'granted' | 'denied' | 'unsupported' = 'granted';
let restorationGate: Promise<void> | undefined;
let root: Root | undefined;
let failed = false;
let passed = 0;
let running = false;

class FixtureTrack extends EventTarget {
  enabled = true;
  readyState = 'live';
  stop() { if (this.readyState === 'live') { stats.trackStops++; this.readyState = 'ended'; } }
}
class FixtureStream {
  track = new FixtureTrack();
  getTracks() { return [this.track]; }
  getAudioTracks() { return [this.track]; }
}
class FixtureChannel extends EventTarget {
  readyState = 'open';
  messages: Record<string, unknown>[] = [];
  message(event: Record<string, unknown>) { this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) })); }
  send(raw: string) {
    const event = JSON.parse(raw);
    this.messages.push(event);
    if (event.type === 'session.close') setTimeout(() => this.message({ type: 'session.closed', reason: 'close_requested' }), 0);
    if (event.type === 'session.input_audio.mute' || event.type === 'session.input_audio.unmute')
      setTimeout(() => this.message({ type: event.type === 'session.input_audio.mute' ? 'session.input_audio.muted' : 'session.input_audio.unmuted', client_event_id: event.event_id }), 0);
  }
  close() { if (this.readyState !== 'closed') { this.readyState = 'closed'; this.dispatchEvent(new Event('close')); } }
}
class FixturePeer extends EventTarget {
  channel = new FixtureChannel();
  connectionState = 'new';
  iceGatheringState = 'complete';
  localDescription?: RTCSessionDescriptionInit;
  constructor() { super(); stats.peers.push(this); }
  createDataChannel() { return this.channel; }
  addTrack() {}
  async createOffer() { return { type: 'offer', sdp: 'fixture-offer' }; }
  async setLocalDescription(value: RTCSessionDescriptionInit) { this.localDescription = value; }
  async setRemoteDescription() {
    this.connectionState = 'connected'; this.dispatchEvent(new Event('connectionstatechange'));
    setTimeout(() => this.channel.message({ type: 'session.started', session: { id: `fixture-live-${stats.sessions}` } }), 0);
  }
  close() { if (this.connectionState !== 'closed') { this.connectionState = 'closed'; this.dispatchEvent(new Event('connectionstatechange')); } }
}
class FixtureAudio {
  paused = true;
  autoplay = false;
  srcObject: unknown = null;
  setAttribute() {}
  async play() { this.paused = false; }
  pause() { this.paused = true; }
}
class FixtureAudioContext {
  state = 'running';
  async resume() { this.state = 'running'; }
  async close() { this.state = 'closed'; }
  createMediaStreamSource() { return { connect() {} }; }
  createAnalyser() { return { fftSize: 256, getByteTimeDomainData(samples: Uint8Array) { samples.fill(128); } }; }
}
class FixtureBroadcastChannel {
  onmessage: unknown = null;
  postMessage() {}
  close() {}
}
const globals = new Map<string, PropertyDescriptor | undefined>();
function replaceGlobal(key: string, value: unknown) {
  globals.set(key, Object.getOwnPropertyDescriptor(window, key));
  Object.defineProperty(window, key, { configurable: true, writable: true, value });
}
replaceGlobal('RTCPeerConnection', FixturePeer);
replaceGlobal('Audio', FixtureAudio);
replaceGlobal('AudioContext', FixtureAudioContext);
replaceGlobal('BroadcastChannel', FixtureBroadcastChannel);
const mediaDescriptor = Object.getOwnPropertyDescriptor(navigator.mediaDevices, 'getUserMedia');
Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true, value: async () => { stats.microphones++; return new FixtureStream(); } });
const permissionDescriptor = Object.getOwnPropertyDescriptor(navigator, 'permissions');
Object.defineProperty(navigator, 'permissions', { configurable: true, value: { query: async () => {
  stats.permissionQueries++;
  if (permissionMode === 'unsupported') throw new TypeError('Microphone permission query is unsupported in this fixture.');
  return { state: permissionMode };
} } });

const people = [{ id: 'mira', name: 'Mira', ownSpaceId: 'mira' }, { id: 'sol', name: 'Sol', ownSpaceId: 'sol' }];
const spaces: SpaceSummary[] = people.map(person => ({ id: person.ownSpaceId, owner: person, kind: 'blank', revisionId: 1, hasBuilt: true, icon: { status: 'empty' } }));
const revision = { id: 1, title: 'Fixture canvas', createdAt: '2026-09-20T12:00:00Z', source: '', tests: '', checks: [], meta: { layout: 'canvas' } };
function snapshot(id: string): Snapshot {
  const turns = stats.builds.filter(build => build.spaceId === id).map(build => build.turn);
  return {
    state: { projects: [], contributions: [], extras: {} }, revision,
    html: '<h1>A small fixture garden</h1><label>Garden note <input name="note" /></label><button type="button">Water the garden</button>',
    actor: people.find(person => person.id === signedInId)!,
    session: { id: 'fixture-space', status: turns.some(turn => turn.status === 'running') ? 'running' : 'idle', turnCount: turns.length, turns },
    config: { model: 'gpt-6-astra', requestedTier: 'ultrafast', reasoningEffort: 'low', keyAvailable: true, adapter: 'fixture' },
    events: runtimeEvents.get(id) || [], space: spaces.find(space => space.id === id)!, permissions: { canEdit: id === signedInId, canViewRuntime: id === signedInId },
  };
}
function publish(spaceId: string, type: string, turnId: string) {
  const events = runtimeEvents.get(spaceId) || [];
  const event: RuntimeEvent = { id: String(events.length + 1), type, turnId, time: new Date().toISOString(), title: 'Fixture build' };
  events.push(event); runtimeEvents.set(spaceId, events);
  const chunk = new TextEncoder().encode(`id: ${event.id}\ndata: ${JSON.stringify(event)}\n\n`);
  for (const stream of eventStreams.get(spaceId) || []) stream.enqueue(chunk);
}
function comparisonEvent(spaceId: string) {
  return { type: 'comparison.state', time: new Date().toISOString(), data: { comparison: comparisons.get(spaceId) || null } };
}
function publishComparison(spaceId: string) {
  const chunk = new TextEncoder().encode(`data: ${JSON.stringify(comparisonEvent(spaceId))}\n\n`);
  for (const stream of comparisonStreams.get(spaceId) || []) stream.enqueue(chunk);
}
function completePrimary() {
  const build = stats.builds.at(-1)!;
  const comparison = comparisons.get(build.spaceId)!;
  build.turn.status = 'completed';
  build.turn.revisionId = revision.id;
  comparison.ultrafast = { ...comparison.ultrafast, status: 'completed', endedAt: new Date().toISOString(), outputTokens: 1200 };
  comparison.standard.outputTokens = 400;
  publish(build.spaceId, 'turn.completed', build.turn.id);
  publishComparison(build.spaceId);
}
function streamResponse(init: RequestInit, streams: Set<ReadableStreamDefaultController<Uint8Array>>, replay: unknown[] = []) {
  let cancel: (() => void) | undefined;
  const stream = new ReadableStream<Uint8Array>({ start(controller) {
    streams.add(controller);
    for (const event of replay) controller.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`));
    cancel = () => { streams.delete(controller); try { controller.close(); } catch { /* Already canceled. */ } };
  }, cancel() { cancel?.(); cancel = undefined; } });
  init.signal?.addEventListener('abort', () => cancel?.(), { once: true });
  if (init.signal?.aborted) cancel?.();
  return new Response(stream, { headers: { 'Content-Type': 'text/event-stream' } });
}
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
replaceGlobal('fetch', async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const path = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, location.href).pathname;
  stats.requests.push(path);
  const body = typeof init.body === 'string' ? JSON.parse(init.body) : {};
  if (path === '/api/auth/people') return json({ users: people });
  if (path === '/api/auth/sign-in') {
    signedInId = body.userId || String(body.name).toLowerCase().replace(/[^a-z]/g, '');
    if (!people.some(person => person.id === signedInId)) {
      const person = { id: signedInId!, name: String(body.name), ownSpaceId: signedInId! };
      people.push(person); spaces.push({ id: person.ownSpaceId, owner: person, kind: 'blank', revisionId: 1, hasBuilt: true, icon: { status: 'empty' } });
    }
    const user = people.find(person => person.id === signedInId)!;
    return json({ user, ownSpaceId: user.ownSpaceId, token: `fixture-${user.id}`, simulated: true });
  }
  if (path === '/api/auth/session') {
    await restorationGate;
    const user = people.find(person => person.id === signedInId);
    return user ? json({ user, ownSpaceId: user.ownSpaceId, simulated: true }) : json({ error: 'No fixture session.' }, 401);
  }
  if (path === '/api/auth/sign-out') { signedInId = null; return json({ ok: true }); }
  if (path === '/api/spaces') return json({ spaces });
  if (path === '/api/community') return json({ spaces, connections: [], requests: { incoming: [], outgoing: [] } });
  if (/^\/api\/spaces\/[^/]+$/.test(path)) return json(snapshot(path.split('/')[3]));
  if (path.endsWith('/icon')) return json({ icon: { status: 'empty' } });
  if (path.endsWith('/revisions')) return json({ revisions: [revision] });
  if (path.endsWith('/turn')) {
    stats.turnRequests++;
    await turnAcceptanceGate;
    assert(body.compare === true, 'The real composer must request a parallel comparison.');
    const spaceId = path.split('/')[3];
    const turn = { id: `fixture-turn-${stats.builds.length + 1}`, message: body.message, status: 'running', startedAt: new Date().toISOString() };
    stats.builds.push({ spaceId, turn }); publish(spaceId, 'turn.started', turn.id);
    const comparison: BuildComparisonState = { id: `comparison-${turn.id}`, primaryTurnId: turn.id, model: 'gpt-6-astra', reasoningEffort: 'low', startedAt: turn.startedAt, finished: false,
      ultrafast: { turnId: turn.id, status: 'running', startedAt: turn.startedAt, outputTokens: 100, requestedTier: 'ultrafast' },
      standard: { turnId: `standard-${turn.id}`, status: 'running', startedAt: turn.startedAt, outputTokens: 20, requestedTier: 'default' } };
    comparisons.set(spaceId, comparison); publishComparison(spaceId);
    return json({ turnId: turn.id, comparisonId: comparison.id }, 202);
  }
  if (path.endsWith('/comparison/events')) {
    const spaceId = path.split('/')[3];
    const streams = comparisonStreams.get(spaceId) || new Set(); comparisonStreams.set(spaceId, streams);
    return streamResponse(init, streams, [comparisonEvent(spaceId)]);
  }
  if (path.endsWith('/comparison')) return json({ comparison: comparisons.get(path.split('/')[3]) || null });
  if (/\/comparison\/[^/]+\/finish$/.test(path)) {
    const spaceId = path.split('/')[3], comparison = comparisons.get(spaceId);
    if (!comparison || !['completed', 'failed', 'cancelled'].includes(comparison.ultrafast.status)) return json({ error: 'Ultrafast has not finished.' }, 409);
    comparison.finished = true;
    comparison.standard = { ...comparison.standard, status: 'cancelled', endedAt: new Date().toISOString() };
    stats.finishes++; publishComparison(spaceId);
    return json({ comparison });
  }
  if (path.endsWith('/activity')) {
    // Both lane panels use the real activity hook and real SSE parser. These
    // isolated streams remain empty; comparison state controls lane progress.
    return streamResponse(init, new Set(), [{ type: 'activity.reset', time: new Date().toISOString(), data: { reason: 'replay' } }]);
  }
  if (path.endsWith('/events')) {
    const spaceId = path.split('/')[3];
    const streams = eventStreams.get(spaceId) || new Set(); eventStreams.set(spaceId, streams);
    return streamResponse(init, streams);
  }
  if (path === '/api/voice/status') return json({ available: true, model: 'gpt-live-1', plannerModel: 'gpt-6-astra', tier: 'ultrafast', reasoningEffort: 'low' });
  if (path === '/api/voice/session') { stats.sessions++; return json({ session: { id: `fixture-live-${stats.sessions}` }, transport: { type: 'webrtc', sdp: 'fixture-answer' }, controlToken: 'fixture-control' }, 201); }
  if (path === '/api/voice/end') { stats.ends++; return json({ ok: true }); }
  if (path === '/api/voice/plan' && plannedWorldNote) {
    const controls = body.surface.controls as VoiceControl[];
    const target = controls.find(control => control.label === 'Garden note' && !control.disabled);
    if (!target) return json({ error: 'Published Ultrafast controls are missing from the voice surface.' }, 400);
    if (!body.history.length) return json({ action: { type: 'fill', target: target.id, value: plannedWorldNote } });
    if (target.value !== plannedWorldNote) return json({ error: 'The generated-page voice action did not update its actual field.' }, 400);
    return json({ action: { type: 'done', message: 'Fixture world updated while Standard builds.' } });
  }
  if (path === '/api/voice/plan' && plannedFinish) {
    const controls = body.surface.controls as VoiceControl[];
    if (!body.history.length) {
      const target = controls.find(control => control.label === 'Enter your world' && !control.disabled);
      return target ? json({ action: { type: 'click', target: target.id } }) : json({ error: 'Enter your world is not voice-accessible.' }, 400);
    }
    return json({ action: { type: 'done', message: 'Fixture comparison finished.' } });
  }
  if (path === '/api/voice/plan' && plannedDraft) {
    stats.planHistories.push(structuredClone(body.history));
    const controls = body.surface.controls as VoiceControl[];
    if (!body.history.length) {
      const target = controls.find(control => control.label === 'Describe a change to your space');
      return target ? json({ action: { type: 'fill', target: target.id, value: plannedDraft } }) : json({ error: 'Host composer missing from voice surface.' }, 400);
    }
    if (!plannedSubmit) return json({ action: { type: 'done', message: 'Fixture draft ready.' } });
    if (body.history.length === 1) {
      const target = controls.find(control => ['Make it real', 'Send a follow-up'].includes(control.label) && !control.disabled);
      return target ? json({ action: { type: 'click', target: target.id } }) : json({ error: 'Enabled host build control missing from voice surface.' }, 400);
    }
    return json({ action: { type: 'done', message: `Fixture build ${stats.builds.length} submitted.` } });
  }
  // Any accidental request is an assertion failure rather than a paid fallback.
  stats.unexpected.push(path);
  return json({ error: `Unexpected fixture request: ${path}` }, 500);
});

const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
function assert(value: unknown, message: string): asserts value { if (!value) throw new Error(message); }
async function until(predicate: () => unknown, description: string, timeout = 4000) {
  const deadline = Date.now() + timeout;
  while (!predicate()) { assert(Date.now() < deadline, `Timed out: ${description}`); await delay(20); }
}
function visible(element: Element) {
  const style = getComputedStyle(element);
  return !element.closest('[inert],[hidden]') && style.display !== 'none' && style.visibility !== 'hidden' && !!element.getClientRects().length;
}
function button(label: string): HTMLButtonElement {
  const match = [...document.querySelectorAll<HTMLButtonElement>('button')].find(element => visible(element) && (element.getAttribute('aria-label') === label || element.textContent?.trim() === label));
  assert(match, `Missing visible button: ${label}`);
  assert(!match.disabled, `Button is disabled: ${label}`);
  return match;
}
async function click(label: string) { button(label).click(); await delay(45); }
const status = () => document.querySelector<HTMLElement>('.voice-controls')?.dataset.status;
function assertLive() {
  assert(status() === 'listening' || status() === 'muted', `Live went off or stalled: ${status()}`);
  assert(stats.sessions === activeSessions, `Expected ${activeSessions} Live session(s); found ${stats.sessions}.`);
  assert(stats.microphones === activeSessions, `Microphone was acquired ${stats.microphones} times.`);
  assert(stats.trackStops === activeSessions - 1 && stats.ends === activeSessions - 1, 'Navigation stopped the active microphone or closed its session.');
  assert(stats.peers.length === activeSessions && stats.peers.at(-1)!.connectionState === 'connected', 'Navigation replaced or closed WebRTC.');
  assert(document.querySelectorAll('.voice-controls').length === 1, 'Expected exactly one persistent Live control.');
  assert(visible(document.querySelector('.voice-controls')!), 'The Live control became hidden.');
}
function assertDockInScope(selector: string) {
  assert(document.querySelector(selector)?.contains(document.querySelector('.voice-controls')), `Live controls did not move into ${selector}.`);
}
async function check(name: string, work: () => Promise<void>) {
  const row = document.createElement('li'); row.textContent = `Running: ${name}`;
  document.querySelector('#navigation-results')!.append(row);
  try { await work(); passed++; row.textContent = `Pass: ${name}`; row.dataset.status = 'pass'; }
  catch (error) { failed = true; row.textContent = `Fail: ${name}: ${error instanceof Error ? error.message : String(error)}`; row.dataset.status = 'fail'; throw error; }
  document.querySelector('#navigation-summary')!.textContent = `${passed} checks passed so far.`;
}
async function dialog(label: string, close: string) {
  await click(label); await until(() => document.querySelector('dialog[open] .voice-controls'), `dock inside ${label}`);
  assertLive(); assertDockInScope('dialog[open]');
  await click(close); await until(() => !document.querySelector('dialog[open]'), `${label} closed`); assertLive();
}
async function voiceRequest(message: string, delegationFirst = false) {
  const channel = stats.peers.at(-1)!.channel;
  const start = ++speechSerial * 10_000;
  const transcript = () => channel.message({ type: 'session.input_transcript.delta', event_id: `fixture-speech-${speechSerial}`, delta: message, start_ms: start, end_ms: start + 1000 });
  const delegate = () => channel.message({ type: 'session.delegation.created', offset_ms: start + 1000, delegation: { id: `fixture-delegation-${speechSerial}`, target: 'client' } });
  if (delegationFirst) { delegate(); await delay(650); transcript(); }
  else { transcript(); delegate(); }
  return channel;
}
async function voiceBuild(message: string, expectedCount: number, delegationFirst = false, concurrentDraft?: string) {
  plannedDraft = message;
  const priorRequests = stats.turnRequests;
  const priorPlans = stats.planHistories.length;
  let release!: () => void;
  turnAcceptanceGate = new Promise<void>(resolve => { release = resolve; });
  try {
    const channel = await voiceRequest(message, delegationFirst);
    await until(() => stats.turnRequests === priorRequests + 1, 'voice request reaches the turn endpoint', 8000);
    await delay(100);
    assert(stats.builds.length === expectedCount - 1, 'The delayed endpoint already accepted a turn.');
    assert(!channel.messages.some(event => event.type === 'session.commentary.append' && event.content === `Fixture build ${expectedCount} submitted.`), 'Live claimed submission before the endpoint accepted it.');
    assert(!stats.planHistories.slice(priorPlans).some(history => history.some(entry => entry.result.submitted === true)), 'Planner received submission success before acceptance.');
    if (concurrentDraft) {
      const field = document.querySelector<HTMLTextAreaElement>('.composer textarea')!;
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(field, concurrentDraft);
      field.dispatchEvent(new Event('input', { bubbles: true })); await delay(30);
    }
    release();
    await until(() => stats.builds.length === expectedCount && channel.messages.some(event => event.type === 'session.commentary.append' && event.content === `Fixture build ${expectedCount} submitted.`), `voice build ${expectedCount}`, 8000);
    const submitted = stats.planHistories.slice(priorPlans).flat().find(entry => entry.result.submitted === true)?.result;
    assert(submitted?.ok === true && submitted.turnId === stats.builds.at(-1)?.turn.id, 'Planner did not receive the real accepted turn ID.');
    assert(stats.turnRequests === priorRequests + 1, 'Voice submitted the same request more than once.');
  } finally { release(); turnAcceptanceGate = undefined; plannedDraft = ''; }
  assert(stats.builds.at(-1)?.turn.message === message, 'The build did not receive the exact voice draft.');
  assert(document.querySelector<HTMLTextAreaElement>('.composer textarea')?.value === (concurrentDraft || ''), concurrentDraft ? 'Acceptance erased a newer manual draft.' : 'Submitting the voice build did not clear the composer.');
  assertLive();
}
async function voiceFinish() {
  const prior = stats.finishes;
  plannedFinish = true;
  try {
    const channel = await voiceRequest('Finish build and open my world.');
    await until(() => stats.finishes === prior + 1 && channel.messages.some(event => event.type === 'session.commentary.append' && event.content === 'Fixture comparison finished.'), 'voice finishes comparison', 8000);
    await until(() => document.querySelector('.build-comparison[data-comparing="false"]:not([data-morphing])'), 'single world after morph');
    assert(!document.querySelector('.build-comparison-primary .build-comparison-world[inert],.build-comparison-primary iframe[inert]'), 'Finished world stayed inert.');
    assert(!document.querySelector('.finish-build-button'), 'Finish control remained after completion.');
    assertLive();
  } finally { plannedFinish = false; }
}
async function run() {
  if (running) return;
  running = true;
  (document.querySelector('#run-navigation-checks') as HTMLButtonElement).disabled = true;
  try {
    clearAppStorage();
    const { default: App } = await import('../../src/App');
    const mountApp = () => {
      root = createRoot(document.querySelector('#root')!);
      root.render(<StrictMode><App /></StrictMode>);
    };
    const unmountApp = async () => { root?.unmount(); root = undefined; await delay(80); };
    mountApp();
    await check('The real app connects Live once from the welcome screen', async () => {
      await until(() => document.querySelector('.account-login-link') && !document.querySelector<HTMLButtonElement>('.account-login-link')!.disabled, 'welcome ready');
      await click('Start live voice'); await until(() => status() === 'listening', 'Live listening'); assertLive();
    });
    await check('Welcome → login → owner canvas keeps the same microphone and session', async () => {
      await click('Log in'); assertLive();
      await click('Continue as Mira'); await until(() => document.querySelector('.composer textarea'), 'owner canvas'); assertLive();
    });
    await check('Typing a draft leaves Live connected and updates the real React form', async () => {
      const field = document.querySelector<HTMLTextAreaElement>('.composer textarea')!;
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')!.set!.call(field, 'Make a quiet garden with a blue gate.');
      field.dispatchEvent(new Event('input', { bubbles: true })); await delay(50);
      assert(!button('Make it real').disabled, 'React did not receive the manual draft.'); assertLive();
    });
    await check('Thread dialog preserves Live, draft, and usable microphone controls', async () => {
      await dialog('Thread', 'Close thread');
      assert(document.querySelector<HTMLTextAreaElement>('.composer textarea')?.value === 'Make a quiet garden with a blue gate.', 'Opening the thread lost the draft.');
    });
    await check('History and guide dialogs preserve the session and top-layer controls', async () => {
      await dialog('History', 'Close history'); await dialog('Demo guide', 'Close demo guide');
    });
    await check('Icon and account dialogs preserve the session and top-layer controls', async () => {
      await dialog('Change your space icon', 'Close space icon settings'); await dialog('Account for Mira', 'Close account');
    });
    await check('Community and its request panel keep Live reachable', async () => {
      await click('Community'); await until(() => document.querySelector('.community-overlay .voice-controls'), 'community dock'); assertLive(); assertDockInScope('.community-overlay');
      await click('Friend requests'); assertLive(); await click('Close friend requests'); assertLive();
    });
    await check('Visiting another person remounts the workspace without remounting Live', async () => {
      await click('Meet Sol'); await click('Visit Sol’s space');
      await until(() => document.querySelector('.visitor-note')?.textContent?.includes('visiting Sol'), 'visitor canvas'); assertLive();
    });
    await check('Returning to the owner canvas preserves Live', async () => {
      await click('My space'); await until(() => document.querySelector('.composer textarea'), 'owner canvas'); assertLive();
    });
    await check('Browser back and forward preserve Live across visitor and owner views', async () => {
      history.back(); await until(() => document.querySelector('.visitor-note'), 'browser back'); assertLive();
      history.forward(); await until(() => document.querySelector('.composer textarea'), 'browser forward'); assertLive();
    });
    await check('Home → login → the same person preserves Live', async () => {
      await click('Home'); await until(() => document.querySelector('.account-gate'), 'Home'); assertLive();
      await click('Log in'); await click('Continue as Mira'); await until(() => document.querySelector('.composer textarea'), 'same account'); assertLive();
    });
    await check('Mute stays muted across community, Home, and returning to the canvas', async () => {
      await click('Mute microphone'); await until(() => status() === 'muted' && !button('Unmute microphone').disabled, 'mute acknowledgment');
      await click('Community'); await until(() => document.querySelector('.community-overlay'), 'community'); assertLive(); assert(status() === 'muted', 'Navigation unmuted Live.');
      await click('Home'); await click('Log in'); await click('Continue as Mira'); await until(() => document.querySelector('.composer textarea'), 'owner canvas');
      assertLive(); assert(status() === 'muted', 'Home/account navigation unmuted Live.');
      await click('Unmute microphone'); await until(() => status() === 'listening', 'unmute'); assertLive();
    });
    await check('A draft-only voice request fills the real composer without starting a build', async () => {
      const priorRequests = stats.turnRequests;
      const priorPlans = stats.planHistories.length;
      plannedDraft = 'Draft a floating island idea, but do not build it yet.';
      plannedSubmit = false;
      try {
        const channel = await voiceRequest(plannedDraft);
        await until(() => channel.messages.some(event => event.type === 'session.commentary.append' && event.content === 'Fixture draft ready.'), 'draft-only voice result', 8000);
        assert(document.querySelector<HTMLTextAreaElement>('.composer textarea')?.value === plannedDraft, 'The voice draft was not retained in the real composer.');
        assert(stats.turnRequests === priorRequests, 'Draft-only voice unexpectedly called the build endpoint.');
        const filled = stats.planHistories.slice(priorPlans).flat().find(entry => entry.result.submitted === false)?.result;
        assert(filled?.ok === true, 'The planner did not receive explicit draft-only feedback.');
        assertLive();
      } finally { plannedDraft = ''; plannedSubmit = true; }
    });
    await check('A voice build waits for acceptance and returns the real turn ID without duplicate submission', async () => {
      await voiceBuild('Add a tile showing the first idea.', 1);
      await until(() => document.querySelector('.composer.is-building'), 'first build in progress');
      await until(() => document.querySelectorAll('.build-activity-panel.is-embedded').length === 2, 'both automatic activity panels');
      assert(!document.querySelector('.finish-build-button'), 'Finish was exposed before ultrafast completed.');
    });
    await check('A running comparison survives navigating away and returns with both streams', async () => {
      await click('Community'); await until(() => document.querySelector('.community-overlay'), 'community during comparison'); assertLive();
      await click('Home'); await click('Log in'); await click('Continue as Mira');
      await until(() => document.querySelectorAll('.build-activity-panel.is-embedded').length === 2, 'comparison replay after returning');
      assert(comparisons.get('mira')?.standard.status === 'running', 'Navigation stopped the standard run.');
      assertLive();
    });
    await check('Published Ultrafast controls work through Live while Standard keeps building', async () => {
      completePrimary();
      await until(() => document.querySelector('.finish-build-button'), 'finish after ultrafast completion');
      await until(() => !document.querySelector('.build-comparison-primary .build-comparison-world[inert],.build-comparison-primary iframe[inert]'), 'published ultrafast controls become interactive');
      assert(button('Enter your world'), 'The exit still uses the old visible label.');
      const priorFinishes = stats.finishes;
      plannedWorldNote = 'The ultrafast garden is already open.';
      try {
        const channel = await voiceRequest(`Set the garden note to: ${plannedWorldNote}`);
        await until(() => channel.messages.some(event => event.type === 'session.commentary.append' && event.content === 'Fixture world updated while Standard builds.'), 'generated-page voice interaction', 8000);
        assert(stats.finishes === priorFinishes, 'Using a generated control exited the comparison.');
        assert(comparisons.get('mira')?.standard.status === 'running', 'Using Ultrafast stopped Standard.');
        assertLive();
      } finally { plannedWorldNote = ''; }
    });
    await check('Enter your world accepts the legacy Finish build voice request and preserves Live', async () => {
      assert(comparisons.get('mira')?.standard.status === 'running', 'Standard should still be running before Finish.');
      await voiceFinish();
      assert(comparisons.get('mira')?.standard.status === 'cancelled', 'Finish did not cancel unfinished standard work.');
    });
    await check('A second voice build survives delegation arriving first after the previous comparison finishes', async () => {
      await voiceBuild('Add a second tile with a different idea.', 2, true, 'A new manual draft typed while the request was being accepted.');
      completePrimary();
      await until(() => !document.querySelector('.composer.is-building'), 'completed builder');
      await voiceFinish();
      assert(stats.builds.length === 2, 'The follow-up was lost or submitted more than once.');
    });
    await check('Creating an account from Home keeps Live on with a fresh conversation', async () => {
      await click('Home');
      const field = document.querySelector<HTMLInputElement>('input[aria-label="Your name"]')!;
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!.call(field, 'Luna');
      field.dispatchEvent(new Event('input', { bubbles: true })); await delay(30);
      await click('Create a space'); activeSessions++;
      await until(() => status() === 'listening' && stats.sessions === activeSessions && document.querySelector('.composer textarea'), 'new account with Live'); assertLive();
      assert(!document.querySelector('.voice-captions')?.textContent?.includes('second tile'), 'The new account inherited the old voice transcript.');
    });
    await check('Selecting a different saved person keeps Live on with a fresh conversation', async () => {
      await click('Home'); await click('Log in'); await click('Continue as Mira'); activeSessions++;
      await until(() => status() === 'listening' && stats.sessions === activeSessions && document.querySelector('.composer textarea'), 'saved account with Live'); assertLive();
    });
    await check('Explicit sign-out ends Live and releases the microphone', async () => {
      await click('Account for Mira'); await click('Sign out');
      await until(() => status() === 'idle' && stats.ends === activeSessions, 'explicit sign-out closes Live');
      assert(stats.trackStops === activeSessions, `Sign-out did not release the microphone; stopped ${stats.trackStops}.`);
      assert(stats.peers.every(peer => peer.connectionState === 'closed'), 'Sign-out left WebRTC open.');
    });
    await check('The next person does not inherit a live microphone or prior session', async () => {
      await click('Log in'); await click('Continue as Sol'); await until(() => document.querySelector('.composer textarea'), 'second account');
      await delay(250); assert(status() === 'idle', `New account unexpectedly started Live: ${status()}.`);
      assert(stats.microphones === activeSessions && stats.sessions === activeSessions, 'A new account inherited Live intent after explicit sign-out.');
      assert(stats.unexpected.length === 0, `Unexpected API requests: ${stats.unexpected.join(', ')}`);
    });
    await check('A full App remount waits for account restoration and resumes the same person muted', async () => {
      await click('Start live voice'); activeSessions++;
      await until(() => status() === 'listening', 'explicit new-person session');
      await click('Mute microphone'); await until(() => status() === 'muted', 'mute before reload');
      window.dispatchEvent(new PageTransitionEvent('pagehide'));
      const handoff = JSON.parse(sessionStorage.getItem('little-worlds:live-resume') || 'null');
      assert(handoff?.identity === 'sol' && handoff.muted === true, 'Page hide did not save the correct account and mute state.');
      assert(Object.keys(handoff).sort().join(',') === 'identity,muted,savedAt,version', 'Reload handoff unexpectedly persisted conversation content or credentials.');
      await unmountApp();
      let release!: () => void;
      restorationGate = new Promise<void>(resolve => { release = resolve; });
      mountApp(); await delay(160);
      assert(stats.microphones === activeSessions && stats.sessions === activeSessions, 'Live resumed before the saved account was restored.');
      release(); restorationGate = undefined; activeSessions++;
      await until(() => status() === 'muted' && stats.sessions === activeSessions, 'muted Live after account restoration'); assertLive();
      assert(stats.permissionQueries > 0, 'Automatic resume did not check the existing microphone grant.');
      assert(!sessionStorage.getItem('little-worlds:live-resume'), 'Reload intent was not consumed.');
    });
    for (const mode of ['denied', 'unsupported'] as const) {
      await check(`A ${mode} microphone permission check offers manual resume without opening the mic`, async () => {
        permissionMode = mode;
        await unmountApp(); mountApp();
        await until(() => document.querySelector('.voice-controls [role="status"]')?.textContent?.includes('Tap Go live'), `${mode} permission fallback`);
        assert(!document.querySelector('.voice-panel'), 'Manual resume opened the conversation panel without a click.');
        assert(status() === 'idle' && stats.microphones === activeSessions && stats.sessions === activeSessions, 'A denied or unknown permission triggered automatic microphone access.');
        assert(stats.ends === activeSessions && stats.trackStops === activeSessions, 'The previous page did not release its microphone.');
        await click('Start live voice'); activeSessions++;
        await until(() => status() === 'muted' && stats.sessions === activeSessions, 'manual resume preserving mute'); assertLive();
      });
    }
    await check('Ending Live remains off after a remount even when permission is granted', async () => {
      permissionMode = 'granted';
      await click('End live voice'); await until(() => status() === 'idle' && stats.ends === activeSessions, 'manual end');
      await unmountApp(); mountApp(); await until(() => document.querySelector('.composer textarea'), 'account restored after end'); await delay(160);
      assert(status() === 'idle' && stats.microphones === activeSessions, 'An explicitly ended session resumed itself.');
    });
    await check('A reload into a different restored account never auto-opens the old conversation', async () => {
      await click('Start live voice'); activeSessions++;
      await until(() => status() === 'listening' && stats.sessions === activeSessions, 'last explicit session');
      await unmountApp(); signedInId = 'mira';
      const queries = stats.permissionQueries;
      mountApp(); await until(() => document.querySelector('.visitor-note')?.textContent?.includes('as Mira'), 'different restored account'); await delay(180);
      assert(status() === 'idle' && stats.sessions === activeSessions && stats.microphones === activeSessions, 'The different account inherited live microphone access.');
      assert(stats.permissionQueries === queries, 'A mismatched account proceeded to the microphone permission check.');
      assert(!sessionStorage.getItem('little-worlds:live-resume'), 'A mismatched handoff was left reusable.');
      assert(stats.unexpected.length === 0, `Unexpected API requests: ${stats.unexpected.join(', ')}`);
    });
  } catch (error) { console.error('Live navigation regression:', error); }
  finally {
    root?.unmount(); await delay(60);
    clearAppStorage(); for (const [key, value] of savedStorage) sessionStorage.setItem(key, value);
    history.replaceState(originalHistory, '', originalHref);
    for (const [key, descriptor] of globals) { if (descriptor) Object.defineProperty(window, key, descriptor); else Reflect.deleteProperty(window, key); }
    if (mediaDescriptor) Object.defineProperty(navigator.mediaDevices, 'getUserMedia', mediaDescriptor); else Reflect.deleteProperty(navigator.mediaDevices, 'getUserMedia');
    if (permissionDescriptor) Object.defineProperty(navigator, 'permissions', permissionDescriptor); else Reflect.deleteProperty(navigator, 'permissions');
    const summary = document.querySelector<HTMLElement>('#navigation-summary')!;
    summary.textContent = `${failed ? 'Failed after' : 'Passed'} ${passed} navigation checks. Microphones: ${stats.microphones}; sessions: ${stats.sessions}; explicit closes: ${stats.ends}.`;
    summary.dataset.status = failed ? 'fail' : 'pass';
  }
}
document.querySelector('#run-navigation-checks')!.addEventListener('click', () => void run());
