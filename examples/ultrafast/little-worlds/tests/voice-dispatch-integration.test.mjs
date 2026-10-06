import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { once } from 'node:events';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { build } from 'esbuild';
import { createApp } from '../server/index.mjs';

const bundled = await build({
  entryPoints: [new URL('../src/live-voice.ts', import.meta.url).pathname],
  bundle: true, write: false, format: 'iife', globalName: 'LiveVoice', target: 'es2022',
});
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; };
const toolResult = action => ({ output: [{ type: 'function_call', name: 'control_app', arguments: JSON.stringify(action) }] });
async function until(predicate, description, timeout = 3000) {
  const deadline = Date.now() + timeout;
  while (!predicate()) { assert.ok(Date.now() < deadline, `Timed out waiting for ${description}`); await delay(5); }
}

/** Browser primitives stay inside this VM. The client uses real HTTP fetch to
 * the app router, so request abort and server cleanup race as they do in Chrome. */
function browserClient(base, trace) {
  class Channel extends EventTarget {
    readyState = 'open';
    send(raw) {
      const event = JSON.parse(raw); trace.sent.push(event);
      if (event.type === 'session.close') setTimeout(() => this.message({ type: 'session.closed', reason: 'close_requested' }), 0);
    }
    message(event) { this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) })); }
    close() { if (this.readyState !== 'closed') { this.readyState = 'closed'; this.dispatchEvent(new Event('close')); } }
  }
  class Peer extends EventTarget {
    channel = new Channel();
    connectionState = 'new';
    iceGatheringState = 'complete';
    constructor() { super(); trace.peer = this; }
    createDataChannel() { return this.channel; }
    addTrack() {}
    async createOffer() { return { type: 'offer', sdp: 'v=0\r\na=fixture-offer' }; }
    async setLocalDescription(value) { this.localDescription = value; }
    async setRemoteDescription() { this.connectionState = 'connected'; }
    close() { this.connectionState = 'closed'; this.dispatchEvent(new Event('connectionstatechange')); }
  }
  class Audio {
    paused = true;
    setAttribute() {}
    async play() { this.paused = false; }
    pause() { this.paused = true; }
  }
  class Track extends EventTarget { enabled = true; stop() { trace.microphoneStopped = true; } }
  const track = new Track();
  const browserEvents = new EventTarget();
  const context = vm.createContext({
    RTCPeerConnection: Peer, Audio, AbortController, DOMException, Error, TypeError,
    TextEncoder, Headers, Response, setTimeout, clearTimeout, setInterval, clearInterval,
    navigator: { onLine: true, mediaDevices: { getUserMedia: async () => ({ getTracks: () => [track], getAudioTracks: () => [track] }) } },
    addEventListener: browserEvents.addEventListener.bind(browserEvents), removeEventListener: browserEvents.removeEventListener.bind(browserEvents),
  });
  vm.runInContext(bundled.outputFiles[0].text, context);
  let currentPage = 'Home';
  return context.LiveVoice.createLiveVoice({
    timings: { settle: 8, transcriptWait: 500, plan: 2500, connect: 1500, close: 40 },
    readSurface: async () => ({ title: currentPage, url: '/', context: `The ${currentPage} screen is open.`, text: currentPage, controls: [
      { id: 'community', role: 'button', label: 'Community' }, { id: 'stale', role: 'button', label: 'Obsolete destination' },
    ] }),
    execute: async action => {
      trace.actions.push(action);
      if (action.type === 'click' && action.target === 'community') currentPage = 'Community';
      return { ok: true, message: `${currentPage} is open.` };
    },
    onState: value => trace.states.push(value), onTranscript() {}, onNotice: value => trace.notices.push(value),
    fetch: async (path, init) => {
      trace.requests.push({ path, body: JSON.parse(init.body) });
      const headers = new Headers(init.headers); headers.set('Origin', base);
      const response = await fetch(base + path, { ...init, headers });
      trace.responses.push({ path, status: response.status });
      return response;
    },
  });
}

test('a transcript correction waits for the aborted HTTP planner to release its slot, then navigates once', { timeout: 10_000 }, async t => {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-voice-dispatch-'));
  const trace = { sent: [], states: [], notices: [], actions: [], requests: [], responses: [], providers: [], concurrent: 0, maxConcurrent: 0, staleResultReturned: false };
  const firstStarted = deferred(), firstAborted = deferred(), staleFinished = deferred();
  const instance = await createApp({
    dataDir, apiKey: 'test-server-key',
    adapter: { keyAvailable: false, respond: async () => { throw new Error('The builder is not part of this fixture.'); } },
    voiceFetchImpl: async () => Response.json({ session: { id: 'live_dispatch_fixture' }, transport: { type: 'webrtc', sdp: 'v=0\r\na=fixture-answer' } }),
    voiceAdapter: { keyAvailable: true, respond: async ({ input, signal }) => {
      const request = JSON.parse(input[0].content);
      const index = trace.providers.length;
      trace.providers.push(request);
      trace.concurrent++; trace.maxConcurrent = Math.max(trace.maxConcurrent, trace.concurrent);
      try {
        if (index === 0) {
          firstStarted.resolve();
          // Some provider transports finish cancellation asynchronously. Return
          // an obsolete tool result after the abort to prove it cannot execute.
          return await new Promise(resolve => signal.addEventListener('abort', () => {
            firstAborted.resolve();
            setTimeout(() => {
              trace.staleResultReturned = true; staleFinished.resolve();
              resolve(toolResult({ type: 'click', target: 'stale' }));
            }, 100);
          }, { once: true }));
        }
        assert.equal(trace.staleResultReturned, true, 'the corrected request started before canceled provider cleanup finished');
        assert.equal(request.conversation.at(-1).text, 'could you go to community');
        return toolResult(request.history.length ? { type: 'done', message: 'Community is open.' } : { type: 'click', target: 'community' });
      } finally { trace.concurrent--; }
    } },
  });
  const server = instance.app.listen(0, '127.0.0.1');
  await once(server, 'listening');
  const base = `http://127.0.0.1:${server.address().port}`;
  const client = browserClient(base, trace);
  t.after(async () => {
    await client.stop(); client.destroy();
    server.closeAllConnections(); await new Promise(resolve => server.close(resolve));
    await instance.close(); await rm(dataDir, { recursive: true, force: true });
  });

  await client.start();
  trace.peer.channel.message({ type: 'session.started', session: { id: 'live_dispatch_fixture' } });
  trace.peer.channel.message({ type: 'session.input_transcript.delta', event_id: 'speech-1', delta: 'could you go', start_ms: 100, end_ms: 1000 });
  trace.peer.channel.message({ type: 'session.delegation.created', offset_ms: 1000, delegation: { id: 'navigation', target: 'client' } });
  await firstStarted.promise;
  trace.peer.channel.message({ type: 'session.input_transcript.delta', event_id: 'speech-2', delta: ' to community', start_ms: 1100, end_ms: 2000 });
  await firstAborted.promise;
  await staleFinished.promise;
  await until(() => trace.sent.some(event => event.type === 'session.commentary.append' && event.content === 'Community is open.'), 'the corrected request to finish');

  assert.deepEqual(trace.actions.map(action => ({ type: action.type, target: action.target })), [{ type: 'click', target: 'community' }]);
  assert.equal(trace.maxConcurrent, 1, 'only one provider call may own a voice session at a time');
  assert.equal(trace.providers.length, 3, 'one canceled plan, one corrected action, and one completion check');
  assert.equal(trace.providers[0].conversation.at(-1).text, 'could you go');
  assert.equal(trace.providers[2].surface.title, 'Community');
  assert.equal(trace.providers[2].history[0].action.target, 'community');
  assert.equal(trace.requests.filter(request => request.path === '/api/voice/session').length, 1, 'an interrupted app action must not reconnect audio');
  assert.equal(trace.states.at(-1).status, 'listening');
  assert.doesNotMatch(JSON.stringify([trace.notices, trace.states, trace.sent]), /already in progress|VOICE_PLANNER_BUSY/i);
  const statuses = trace.responses.filter(response => response.path === '/api/voice/plan').map(response => response.status);
  assert.ok(statuses.every(status => status === 200), `the real HTTP router must queue the correction instead of returning a busy error; received ${statuses.join(', ')}`);
});
