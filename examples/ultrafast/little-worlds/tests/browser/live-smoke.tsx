import '../../src/fonts.css';
import React from 'react';
import { createRoot } from 'react-dom/client';
import App from '../../src/App';
import '../../src/styles.css';

/** Development-only fixture. No production entry imports this module.
 * It never calls the native getUserMedia, including as an error fallback.
 * Start/stop conversations with the app's real Live controls.
 */
const element = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const play = element<HTMLButtonElement>('smoke-play');
const stop = element<HTMLButtonElement>('smoke-stop');
const file = element<HTMLInputElement>('smoke-file');
const path = element<HTMLInputElement>('smoke-path');
const mute = element<HTMLInputElement>('smoke-mute');
const audioLabel = element<HTMLElement>('smoke-audio-label');
const micStatus = element<HTMLElement>('smoke-mic-status');
const connectionStatus = element<HTMLElement>('smoke-connection-status');
const logElement = element<HTMLElement>('smoke-log');
const logLines: string[] = [];
const log = (message: string) => {
  const time = new Date().toLocaleTimeString('en-US', { hour12: false });
  logLines.push(`${time} ${message.replace(/sk-[A-Za-z0-9_-]+/g, '[redacted]').slice(0, 700)}`);
  if (logLines.length > 250) logLines.splice(0, logLines.length - 250);
  logElement.textContent = logLines.join('\n');
  logElement.scrollTop = logElement.scrollHeight;
};
const failure = (error: unknown) => error instanceof Error ? error.message : String(error);

// A connected zero-valued source keeps the original stream alive between
// phrases. Each conversation gets cloned tracks, so stopping Live cannot stop
// the fixture's source or force access to the physical microphone.
const audioContext = new AudioContext({ sampleRate: 48_000 });
const destination = audioContext.createMediaStreamDestination();
const silence = audioContext.createConstantSource();
silence.offset.value = 0;
silence.connect(destination);
silence.start();
let microphoneCount = 0;
Object.defineProperty(navigator.mediaDevices, 'getUserMedia', {
  configurable: true,
  value: async (constraints?: MediaStreamConstraints): Promise<MediaStream> => {
    if (constraints?.video) throw new Error('The smoke test does not provide a camera or use hardware devices.');
    if (constraints?.audio === false) throw new Error('The smoke test provides only synthetic audio.');
    await audioContext.resume();
    const stream = new MediaStream(destination.stream.getAudioTracks().map(track => track.clone()));
    microphoneCount++;
    micStatus.textContent = `Synthetic microphone connected (${microphoneCount} request${microphoneCount === 1 ? '' : 's'}). No hardware access.`;
    log('App requested microphone: supplied cloned synthetic WebAudio track.');
    stream.getAudioTracks().forEach(track => track.addEventListener('ended', () => log('App released a synthetic microphone track.')));
    return stream;
  },
});
micStatus.textContent = 'Synthetic microphone ready. Hardware microphone is never opened.';

// Muting the HTML speaker element does not alter the received WebRTC stream,
// which the app independently analyses for its speaking indicator.
const NativeAudio = window.Audio;
const speakers = new Set<HTMLAudioElement>();
window.Audio = new Proxy(NativeAudio, {
  construct(Target, args) {
    const audio = Reflect.construct(Target, args) as HTMLAudioElement;
    audio.volume = mute.checked ? 0 : 1;
    speakers.add(audio);
    return audio;
  },
});
mute.addEventListener('change', () => {
  speakers.forEach(audio => { audio.volume = mute.checked ? 0 : 1; });
  log(`Test speaker output ${mute.checked ? 'muted' : 'audible'}; remote stream analysis is unchanged.`);
});

// Observe real browser transports without mocking the session or planner.
// Never print SDP, headers, session capability tokens, or entire responses.
const nativeFetch = window.fetch.bind(window);
window.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = new URL(input instanceof Request ? input.url : String(input), location.href);
  const observed = url.origin === location.origin && (url.pathname.startsWith('/api/voice/') || /^\/api\/spaces\/[^/]+\/turn$/.test(url.pathname));
  const started = performance.now();
  try {
    const response = await nativeFetch(input, init);
    if (observed) {
      log(`${init?.method || (input instanceof Request ? input.method : 'GET')} ${url.pathname}: HTTP ${response.status} (${Math.round(performance.now() - started)} ms)`);
      if (url.pathname === '/api/voice/plan') {
        void response.clone().json().then(body => {
          if (body.action) log(`Planner: ${body.action.type}${body.action.target ? ` ${body.action.target}` : ''}${body.action.message ? ` · ${body.action.message}` : ''}`);
          else if (body.error) log(`Planner error: ${body.error}`);
        }).catch(() => {});
      }
    }
    return response;
  } catch (error) {
    if (observed) log(`${url.pathname}: ${failure(error)}`);
    throw error;
  }
};

const nativeCreateDataChannel = RTCPeerConnection.prototype.createDataChannel;
const observedPeers = new WeakSet<RTCPeerConnection>();
RTCPeerConnection.prototype.createDataChannel = function (label: string, options?: RTCDataChannelInit): RTCDataChannel {
  const peer = this;
  if (!observedPeers.has(peer)) {
    observedPeers.add(peer);
    peer.addEventListener('connectionstatechange', () => {
      connectionStatus.textContent = `WebRTC: ${peer.connectionState}.`;
      log(`WebRTC connection: ${peer.connectionState}`);
    });
    peer.addEventListener('track', event => log(`Received real remote ${event.track.kind} track.`));
  }
  const channel = nativeCreateDataChannel.call(peer, label, options);
  channel.addEventListener('open', () => log(`Data channel ${label}: open.`));
  channel.addEventListener('close', () => log(`Data channel ${label}: closed.`));
  channel.addEventListener('message', ({ data }) => {
    if (typeof data !== 'string') return;
    try {
      const event = JSON.parse(data);
      if (event.type === 'session.input_transcript.delta') log(`User: ${event.delta || ''}`);
      else if (event.type === 'session.output_transcript.delta') log(`Live: ${event.delta || ''}`);
      else if (event.type === 'session.started') {
        connectionStatus.textContent = 'GPT Live session started. Ready for a phrase.';
        log('GPT Live session started.');
      } else if (event.type === 'session.closed') {
        connectionStatus.textContent = 'GPT Live session closed gracefully.';
        log('GPT Live session closed gracefully.');
      } else if (event.type === 'session.delegation.created') log(`Delegation requested: ${event.delegation?.target || 'unknown'}.`);
      else if (event.type === 'error' || event.type === 'session.error') log(`Live error: ${event.error?.message || event.message || 'Unknown error'}`);
    } catch { log('Ignored non-JSON data channel message.'); }
  });
  return channel;
};

let buffer: AudioBuffer | null = null;
let bufferName = '';
let playing: AudioBufferSourceNode | null = null;
const stopPhrase = () => {
  const source = playing;
  playing = null;
  if (source) { source.onended = null; source.stop(); source.disconnect(); }
  stop.disabled = true;
  play.disabled = !buffer;
};
async function loadPhrase(bytes: ArrayBuffer, name: string) {
  stopPhrase();
  play.disabled = true;
  buffer = null;
  audioLabel.textContent = `Decoding ${name}…`;
  try {
    const decoded = await audioContext.decodeAudioData(bytes);
    if (decoded.duration > 60) throw new Error('Use a spoken test phrase of at most 60 seconds.');
    buffer = decoded;
    bufferName = name;
    audioLabel.textContent = `${name} · ${decoded.duration.toFixed(2)} s · ${decoded.sampleRate} Hz. Ready.`;
    play.disabled = false;
    log(`Loaded phrase ${name} (${decoded.duration.toFixed(2)} s).`);
  } catch (error) {
    audioLabel.textContent = `Could not load phrase: ${failure(error)}`;
    log(audioLabel.textContent);
  }
}
file.addEventListener('change', () => {
  const selected = file.files?.[0];
  if (!selected) return;
  void selected.arrayBuffer().then(bytes => loadPhrase(bytes, selected.name)).catch(error => log(`File read failed: ${failure(error)}`));
});
element<HTMLButtonElement>('smoke-load-path').addEventListener('click', () => {
  const selected = path.value.trim();
  if (!/^\/test-results\/voice[\w.-]*\.wav$/i.test(selected)) { log('Use a same-origin path such as /test-results/voice-open-explore.wav.'); return; }
  void nativeFetch(selected, { cache: 'no-store' }).then(async response => {
    if (!response.ok) throw new Error(`HTTP ${response.status} loading the test WAV.`);
    await loadPhrase(await response.arrayBuffer(), selected.split('/').at(-1)!);
  }).catch(error => log(`Server WAV load failed: ${failure(error)}`));
});
play.addEventListener('click', () => {
  if (!buffer) return;
  void audioContext.resume().then(() => {
    stopPhrase();
    const source = audioContext.createBufferSource();
    source.buffer = buffer;
    source.connect(destination);
    playing = source;
    play.disabled = true;
    stop.disabled = false;
    audioLabel.textContent = `Playing ${bufferName} into the synthetic microphone…`;
    log(`Injecting phrase: ${bufferName}.`);
    source.onended = () => {
      if (playing !== source) return;
      playing = null;
      source.disconnect();
      play.disabled = false;
      stop.disabled = true;
      audioLabel.textContent = `${bufferName} finished. Synthetic microphone continues with silence.`;
      log('Phrase ended; continuous synthetic silence resumed.');
    };
    source.start();
  }).catch(error => log(`Phrase playback failed: ${failure(error)}`));
});
stop.addEventListener('click', () => { stopPhrase(); audioLabel.textContent = `${bufferName} stopped. Synthetic microphone continues with silence.`; log('Phrase stopped manually.'); });
element<HTMLButtonElement>('smoke-clear-log').addEventListener('click', () => { logLines.length = 0; logElement.textContent = ''; });
window.addEventListener('pagehide', () => {
  stopPhrase();
  silence.stop();
  destination.stream.getTracks().forEach(track => track.stop());
  void audioContext.close();
});

log('Test fixture installed. Native getUserMedia is never called.');
log('Use the app’s Live button to start genuine GPT Live and Astra calls.');
createRoot(element('root')).render(<React.StrictMode><App /></React.StrictMode>);
