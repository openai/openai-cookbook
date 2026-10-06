import { StrictMode, useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';

const fixtureKey = 'voice-refresh-fixture:v1';
const tokenKey = 'little-worlds:demo-session';
const resumeKey = 'little-worlds:live-resume';
const legacyTokenKey = 'living-spaces:demo-session';
const legacyResumeKey = 'living-spaces:live-resume';
const token = 'fixture-refresh-mira';
type FixtureState = {
  phase: 'fresh' | 'prepared' | 'passed';
  previousDocument?: string;
  originalToken: string | null;
  originalResume: string | null;
  originalLegacyToken?: string | null;
  originalLegacyResume?: string | null;
};
const oldState = sessionStorage.getItem(fixtureKey);
const fixture: FixtureState = oldState ? JSON.parse(oldState) : {
  phase: 'fresh', originalToken: sessionStorage.getItem(tokenKey), originalResume: sessionStorage.getItem(resumeKey),
  originalLegacyToken: sessionStorage.getItem(legacyTokenKey), originalLegacyResume: sessionStorage.getItem(legacyResumeKey),
};
const thisDocument = crypto.randomUUID();
const reloaded = fixture.phase === 'prepared';
const persistedTokenBeforeImport = sessionStorage.getItem(tokenKey);
const handoffBeforeImport = sessionStorage.getItem(resumeKey);
const persist = () => sessionStorage.setItem(fixtureKey, JSON.stringify(fixture));
if (!oldState) {
  sessionStorage.removeItem(legacyTokenKey);
  sessionStorage.removeItem(legacyResumeKey);
  sessionStorage.setItem(tokenKey, token);
  sessionStorage.removeItem(resumeKey);
  persist();
}

const stats = { microphones: 0, sessions: 0, authReads: 0, authorizedReads: 0, permissions: 0, ended: 0 };
let authReady = false;
let identity: string | null = null;
class Track extends EventTarget {
  enabled = true;
  readyState = 'live';
  stop() { this.readyState = 'ended'; }
}
class Stream {
  track = new Track();
  getTracks() { return [this.track]; }
  getAudioTracks() { return [this.track]; }
}
class Channel extends EventTarget {
  readyState = 'open';
  message(event: Record<string, unknown>) { this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) })); }
  send(raw: string) {
    const event = JSON.parse(raw);
    if (event.type === 'session.close') setTimeout(() => this.message({ type: 'session.closed', reason: 'close_requested' }), 0);
    if (event.type === 'session.input_audio.mute' || event.type === 'session.input_audio.unmute') setTimeout(() => this.message({
      type: event.type === 'session.input_audio.mute' ? 'session.input_audio.muted' : 'session.input_audio.unmuted', client_event_id: event.event_id,
    }), 0);
  }
  close() { if (this.readyState !== 'closed') { this.readyState = 'closed'; this.dispatchEvent(new Event('close')); } }
}
class Peer extends EventTarget {
  channel = new Channel();
  connectionState = 'new';
  iceGatheringState = 'complete';
  localDescription?: RTCSessionDescriptionInit;
  createDataChannel() { return this.channel; }
  addTrack() {}
  async createOffer() { return { type: 'offer', sdp: 'fixture-refresh-offer' }; }
  async setLocalDescription(value: RTCSessionDescriptionInit) { this.localDescription = value; }
  async setRemoteDescription() {
    this.connectionState = 'connected'; this.dispatchEvent(new Event('connectionstatechange'));
    setTimeout(() => this.channel.message({ type: 'session.started', session: { id: 'fixture-refresh-live' } }), 0);
  }
  close() { if (this.connectionState !== 'closed') { this.connectionState = 'closed'; this.dispatchEvent(new Event('connectionstatechange')); } }
}
class Audio {
  paused = true;
  autoplay = false;
  srcObject: unknown = null;
  setAttribute() {}
  async play() { this.paused = false; }
  pause() { this.paused = true; }
}
class AudioContext {
  state = 'running';
  async resume() { this.state = 'running'; }
  async close() { this.state = 'closed'; }
  createMediaStreamSource() { return { connect() {} }; }
  createAnalyser() { return { fftSize: 256, getByteTimeDomainData(samples: Uint8Array) { samples.fill(128); } }; }
}
for (const [key, value] of Object.entries({ RTCPeerConnection: Peer, Audio, AudioContext })) Object.defineProperty(window, key, { configurable: true, writable: true, value });
Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true, value: async () => { stats.microphones++; return new Stream(); } });
Object.defineProperty(navigator, 'permissions', { configurable: true, value: { query: async () => { stats.permissions++; return { state: 'granted' }; } } });
const json = (data: unknown, status = 200) => new Response(JSON.stringify(data), { status, headers: { 'Content-Type': 'application/json' } });
Object.defineProperty(window, 'fetch', { configurable: true, writable: true, value: async (input: RequestInfo | URL, init: RequestInit = {}) => {
  const path = new URL(typeof input === 'string' ? input : input instanceof URL ? input.href : input.url, location.href).pathname;
  if (path === '/api/auth/session') {
    stats.authReads++;
    const authorized = new Headers(init.headers).get('Authorization') === `Bearer ${token}`;
    if (authorized) stats.authorizedReads++;
    // Voice must wait for this identity, even when the handoff is already read.
    await new Promise(resolve => setTimeout(resolve, 180));
    return authorized ? json({ user: { id: 'mira', name: 'Mira' }, ownSpaceId: 'mira' }) : json({ error: 'Missing fixture token.' }, 401);
  }
  if (path === '/api/voice/session') {
    if (!authReady || identity !== 'mira') return json({ error: 'Voice started before the fixture account was restored.' }, 409);
    stats.sessions++;
    return json({ session: { id: 'fixture-refresh-live' }, transport: { type: 'webrtc', sdp: 'fixture-refresh-answer' }, controlToken: 'fixture-refresh-control' }, 201);
  }
  if (path === '/api/voice/end') { stats.ended++; return json({ ok: true }); }
  return json({ error: `No server fallback exists for ${path}.` }, 500);
} });

// Import after storage and fakes are installed. An actual page reload reruns
// api.ts's module initializer, which must recover this token from storage.
const [{ default: VoiceLayer }, { api, hasSessionToken }] = await Promise.all([import('../../src/VoiceLayer'), import('../../src/api')]);
function FixtureApp() {
  const [restored, setRestored] = useState<{ ready: boolean; id: string | null }>({ ready: false, id: null });
  useEffect(() => {
    let active = true;
    if (!hasSessionToken()) {
      document.querySelector('#auth-summary')!.textContent = 'Failed: the API module did not restore the fixture token.';
      return () => { active = false; };
    }
    void api<{ user: { id: string } }>('/api/auth/session').then(result => {
      if (!active) return;
      identity = result.user.id; authReady = true;
      setRestored({ ready: true, id: identity });
      document.querySelector('#auth-summary')!.textContent = `Fixture account restored: ${identity}.`;
    }).catch(error => { if (active) document.querySelector('#auth-summary')!.textContent = `Account restore failed: ${String(error)}`; });
    return () => { active = false; };
  }, []);
  return <VoiceLayer identity={restored.id} ready={restored.ready} context="Fixture canvas for Mira. Reload persistence check." />;
}
const root = createRoot(document.querySelector('#root')!);
root.render(<StrictMode><FixtureApp /></StrictMode>);
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
function assert(value: unknown, message: string): asserts value { if (!value) throw new Error(message); }
async function until(predicate: () => unknown, message: string) {
  const deadline = Date.now() + 6000;
  while (!predicate()) { assert(Date.now() < deadline, message); await delay(20); }
}
const status = () => document.querySelector<HTMLElement>('.voice-controls')?.dataset.status;
function click(label: string) {
  const target = document.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`);
  assert(target && !target.disabled, `Missing enabled control: ${label}`); target.click();
}
function result(message: string) { const item = document.createElement('li'); item.textContent = message; document.querySelector('#refresh-results')!.append(item); }
function summary(message: string, status?: string) {
  const element = document.querySelector<HTMLElement>('#refresh-summary')!; element.textContent = message;
  if (status) element.dataset.status = status;
}
document.querySelector('#prepare-refresh')!.addEventListener('click', () => {
  (document.querySelector('#prepare-refresh') as HTMLButtonElement).disabled = true;
  void (async () => {
    await until(() => authReady, 'The fixture account did not restore.');
    click('Start live voice'); await until(() => status() === 'listening', 'Live did not connect.');
    click('Mute microphone'); await until(() => status() === 'muted', 'Live did not mute.');
    fixture.phase = 'prepared'; fixture.previousDocument = thisDocument; persist();
    summary('Ready. Live is muted as Mira. Reload this tab through Chrome now.');
    result('One local fake microphone and one Live connection opened.');
    result('The reload handoff will be saved by the production pagehide handler.');
  })().catch(error => summary(String(error), 'fail'));
});

if (reloaded) {
  (document.querySelector('#prepare-refresh') as HTMLButtonElement).hidden = true;
  summary('A new document loaded. Checking automatic muted resume…');
  void (async () => {
    assert(fixture.previousDocument && fixture.previousDocument !== thisDocument, 'A new browser document was not created.');
    result('Actual new browser document confirmed.');
    assert(persistedTokenBeforeImport === token, 'The persisted fixture token was not present before api.ts initialized.');
    result('The fixture token survived the reload before the authentication module initialized.');
    const handoff = JSON.parse(handoffBeforeImport || 'null');
    assert(handoff?.identity === 'mira' && handoff.muted === true, 'The production pagehide handler did not persist Mira’s muted Live intent.');
    result('Production pagehide saved the same identity and muted state.');
    await until(() => status() === 'muted', 'Live did not automatically resume muted after the real reload.');
    assert(authReady && identity === 'mira' && stats.authorizedReads > 0, 'Reload did not restore the account using the production API helper’s stored token.');
    result('The production authentication helper restored Mira before voice connected.');
    assert(stats.microphones === 1 && stats.sessions === 1, `Expected exactly one new connection; microphones=${stats.microphones}, sessions=${stats.sessions}.`);
    assert(stats.permissions > 0, 'No check for an existing microphone grant occurred.');
    result('Exactly one new microphone and Live session opened after checking the existing permission grant.');
    assert(!sessionStorage.getItem(resumeKey), 'The one-use Live handoff was not consumed.');
    result('Live resumed muted and consumed its one-use handoff.');
    fixture.phase = 'passed'; persist();
    summary('PASS: real Chrome reload restored Mira and resumed Live muted automatically.', 'pass');
    (document.querySelector('#clean-refresh') as HTMLButtonElement).hidden = false;
  })().catch(error => { summary(String(error), 'fail'); (document.querySelector('#clean-refresh') as HTMLButtonElement).hidden = false; });
}
document.querySelector('#clean-refresh')!.addEventListener('click', () => {
  root.unmount();
  for (const [key, value] of [[tokenKey, fixture.originalToken], [resumeKey, fixture.originalResume], [legacyTokenKey, fixture.originalLegacyToken ?? null], [legacyResumeKey, fixture.originalLegacyResume ?? null]]) {
    if (value === null) sessionStorage.removeItem(key!); else sessionStorage.setItem(key!, value!);
  }
  sessionStorage.removeItem(fixtureKey);
  (document.querySelector('#clean-refresh') as HTMLButtonElement).disabled = true;
  summary('Finished. The fake microphone is closed and this tab’s previous storage is restored.', 'pass');
});
