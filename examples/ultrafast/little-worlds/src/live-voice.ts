import { authedFetch } from './api';

export interface VoiceControl {
  id: string;
  role: string;
  label: string;
  value?: string;
  disabled?: boolean;
  checked?: boolean;
  expanded?: boolean;
  type?: string;
  min?: number;
  max?: number;
  step?: number;
  options?: { value: string; label: string; disabled?: boolean }[];
  requiresConfirmation?: boolean;
  description?: string;
  group?: string;
}
export interface VoiceSurface {
  title: string;
  url?: string;
  context?: string;
  text?: string;
  controls: VoiceControl[];
}
export type VoiceAction =
  | { type: 'click'; target: string; message?: string }
  | { type: 'fill' | 'select'; target: string; value: string; message?: string }
  | { type: 'press'; target?: string; key: string; message?: string }
  | { type: 'scroll'; target?: string; direction: 'up' | 'down' | 'left' | 'right'; message?: string }
  | { type: 'done'; message: string };
export interface VoiceActionResult {
  ok: boolean;
  message: string;
  requiresConfirmation?: boolean;
  [key: string]: unknown;
}
export interface VoiceTranscript {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  startMs: number;
  endMs: number;
}
export type LiveVoiceStatus = 'idle' | 'connecting' | 'reconnecting' | 'listening' | 'working' | 'speaking' | 'muted' | 'error';
export interface LiveVoiceSnapshot {
  status: LiveVoiceStatus;
  connected: boolean;
  muted: boolean;
  mutePending: boolean;
  speaking: boolean;
  working: boolean;
  audioBlocked: boolean;
  error?: string;
  notice?: string;
}
interface Timings {
  connect: number;
  ice: number;
  close: number;
  disconnect: number;
  settle: number;
  transcriptWait: number;
  plan: number;
  plannerBusy: number;
  plannerRetry: number;
  mute: number;
  maxSession: number;
  renewGrace: number;
  reconnectBase: number;
  reconnectMax: number;
  reconnectAttempts: number;
  reconnectStable: number;
}
export interface LiveVoiceOptions {
  readSurface: () => Promise<VoiceSurface>;
  execute: (action: VoiceAction) => Promise<VoiceActionResult>;
  onState: (state: LiveVoiceSnapshot) => void;
  onTranscript: (transcript: VoiceTranscript[]) => void;
  onLevel?: (levels: { input: number; output: number }) => void;
  onNotice?: (notice: string) => void;
  fetch?: typeof authedFetch;
  /** Shorter deadlines may be injected by isolated transport tests. */
  timings?: Partial<Timings>;
}
export interface LiveVoiceController {
  start: (options?: { muted?: boolean }) => Promise<void>;
  stop: () => Promise<void>;
  /** Rotate the session after a signed-in identity changes, without carrying
   * speech or pending actions from the previous actor into the new account. */
  resetConversation: () => void;
  setMuted: (muted: boolean) => void;
  resumeAudio: () => Promise<void>;
  updateContext: (context?: string) => Promise<void>;
  destroy: () => void;
}
interface Fragment extends VoiceTranscript {
  receivedAt: number;
  /** Audio boundary of the latest explicit UI confirmation question. */
  userTurn?: number;
}
interface Delegation {
  id: string;
  offset: number;
  receivedAt: number;
  history: { action: VoiceAction; result: VoiceActionResult }[];
  steps: number;
  replans: number;
  attempts: Set<string>;
  awaitingSpeech?: { revision: number; since: number };
}
interface Connection {
  peer: RTCPeerConnection;
  channel: RTCDataChannel;
  audio: HTMLAudioElement;
  mic?: MediaStream;
  audioContext?: AudioContext;
  inputAnalyser?: AnalyserNode;
  outputAnalyser?: AnalyserNode;
  sessionId?: string;
  controlToken?: string;
  ended: boolean;
  closing: boolean;
  ready: boolean;
  readyAt: number;
  recovering: boolean;
  transcriptPrefix: string;
  finalized: boolean;
  abort: AbortController;
  planner?: AbortController;
  connectTimer?: ReturnType<typeof setTimeout>;
  disconnectTimer?: ReturnType<typeof setTimeout>;
  queueTimer?: ReturnType<typeof setTimeout>;
  muteTimer?: ReturnType<typeof setTimeout>;
  meterTimer?: ReturnType<typeof setInterval>;
  closeTimer?: ReturnType<typeof setTimeout>;
  sessionTimer?: ReturnType<typeof setTimeout>;
  closeResolve?: () => void;
  stopPromise?: Promise<void>;
  muteEvent?: { id: string; muted: boolean };
  greetingEvent?: string;
  queue: Delegation[];
  activeJob?: Delegation;
  revision: number;
  lastUserAt: number;
  lastMicAt: number;
  lastOutputAt: number;
  lastActivityAt: number;
  lastCompletedEnd: number;
  completedJob?: { job: Delegation; at: number; endMs: number };
  fragments: Fragment[];
  userTurnBoundaries: number[];
  seen: Set<string>;
  delegations: Set<string>;
  lastContext: string;
}
const defaults: Timings = { connect: 30_000, ice: 10_000, close: 1_250, disconnect: 7_000, settle: 450, transcriptWait: 6_000, plan: 35_000, plannerBusy: 8_000, plannerRetry: 150, mute: 5_000, maxSession: 29 * 60_000, renewGrace: 45_000, reconnectBase: 750, reconnectMax: 6_000, reconnectAttempts: 4, reconnectStable: 30_000 };
const abortError = () => new DOMException('Canceled', 'AbortError');
const isAbort = (error: unknown) => error instanceof Error && error.name === 'AbortError';
const boundedText = (value: unknown, limit: number) => typeof value === 'string' ? value.replace(/\u0000/g, '').slice(0, limit) : '';
class ConnectionError extends Error {
  constructor(message: string, readonly permanent = false) { super(message); }
}
const permanentMediaError = (error: unknown) => error instanceof Error && ['NotAllowedError', 'PermissionDeniedError', 'NotFoundError', 'DevicesNotFoundError', 'NotReadableError', 'SecurityError'].includes(error.name);
// UTF-8 bytes upper-bound the token count. Leave space below Live's 500-token
// append limit even for CJK, emoji, or unusually token-dense UI labels.
function appendText(value: string) {
  let output = '';
  let bytes = 0;
  for (const character of value) {
    bytes += new TextEncoder().encode(character).length;
    if (bytes > 460) break;
    output += character;
  }
  return output;
}
function remember(set: Set<string>, value: string, max = 1024) {
  set.add(value);
  if (set.size > max) set.delete(set.values().next().value!);
}
function validAction(value: unknown): value is VoiceAction {
  if (!value || typeof value !== 'object') return false;
  const action = value as Record<string, unknown>;
  const target = typeof action.target === 'string' && action.target.length > 0 && action.target.length < 250;
  if (action.type === 'done') return typeof action.message === 'string';
  if (action.type === 'click') return target;
  if (action.type === 'fill' || action.type === 'select') return target && typeof action.value === 'string' && action.value.length <= 12_000;
  if (action.type === 'press') return (action.target === undefined || target) && typeof action.key === 'string' && ['Enter', 'Escape', 'Tab', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', ' ', 'Space', 'Home', 'End', 'PageUp', 'PageDown'].includes(action.key);
  return action.type === 'scroll' && (action.target === undefined || target) && ['up', 'down', 'left', 'right'].includes(String(action.direction));
}
function actionSignature(action: VoiceAction, surface: VoiceSurface) {
  // Capture IDs intentionally change on every read to reject stale executions.
  // Compare semantic controls in their current DOM order, retaining all actual
  // state, and use the unmodified capture IDs only for the real execution.
  const controls = surface.controls.map(({ id: _id, ...control }, index) => ({ ...control, id: `control-${index}` }));
  const { message: _message, ...operation } = action;
  const normalized = { ...operation };
  if ('target' in normalized && normalized.target !== undefined) normalized.target = `control-${surface.controls.findIndex(control => control.id === normalized.target)}`;
  return JSON.stringify({ action: normalized, surface: { ...surface, controls } });
}
function repeatableNavigation(action: VoiceAction) {
  // Scroll position and keyboard focus are not represented in VoiceSurface.
  // Their unchanged text/control snapshots do not imply a duplicate submit.
  return action.type === 'scroll' || action.type === 'press' && ['Tab', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Home', 'End', 'PageUp', 'PageDown'].includes(action.key);
}
function compactTranscript(fragments: Fragment[]) {
  // Keep the newest timing samples intact for delegation/continuation checks.
  // Compact older pieces by utterance, so a long word-at-a-time dictation does
  // not lose its beginning merely because it arrived in many small packets.
  const recentStart = Math.max(0, fragments.length - 32);
  const compacted: Fragment[] = [];
  for (const part of fragments.slice(0, recentStart)) {
    const previous = compacted.at(-1);
    if (previous?.role === part.role && previous.userTurn === part.userTurn && part.startMs - previous.endMs < 2_500) {
      previous.text = (previous.text + part.text).slice(-12_000);
      previous.endMs = Math.max(previous.endMs, part.endMs);
      previous.receivedAt = Math.max(previous.receivedAt, part.receivedAt);
    } else compacted.push({ ...part });
  }
  compacted.push(...fragments.slice(recentStart));
  let characters = compacted.reduce((total, part) => total + part.text.length, 0);
  while (compacted.length > 96 || characters > 48_000) characters -= compacted.shift()!.text.length;
  return compacted;
}
function transcriptTurns(fragments: Fragment[]): VoiceTranscript[] {
  const turns: VoiceTranscript[] = [];
  let previousUserTurn: number | undefined;
  for (const part of fragments) {
    const previous = turns.at(-1);
    if (previous?.role === part.role && previousUserTurn === part.userTurn && part.startMs - previous.endMs < 2_500) {
      previous.text = (previous.text + part.text).slice(-12_000);
      previous.endMs = Math.max(previous.endMs, part.endMs);
    } else turns.push({ id: part.id, role: part.role, text: part.text, startMs: part.startMs, endMs: part.endMs });
    previousUserTurn = part.userTurn;
  }
  return turns.slice(-32);
}
function boundedTurns(turns: VoiceTranscript[]) {
  const result = turns.slice(-32);
  let characters = result.reduce((total, turn) => total + turn.text.length, 0);
  while (characters > 48_000) characters -= result.shift()!.text.length;
  return result;
}
function reconnectConversation(turns: VoiceTranscript[]) {
  const context: { role: 'user' | 'assistant'; text: string }[] = [];
  let remaining = 8_000;
  for (const turn of turns.slice(-16).reverse()) {
    let text = '';
    // Prefer recent context, including the end of a long dictation. These
    // messages provide memory only and never enter new-session action timing.
    for (const character of [...turn.text.slice(-6_000)].reverse()) {
      const bytes = new TextEncoder().encode(character).length;
      if (bytes > remaining) break;
      remaining -= bytes;
      text = character + text;
    }
    if (text) context.unshift({ role: turn.role, text });
    if (!remaining) break;
  }
  return context;
}

/** GPT-Live owns speech. The existing Astra-backed planner owns one UI action
 * at a time; actual UI controls still enforce application authorization. */
export function createLiveVoice(options: LiveVoiceOptions): LiveVoiceController {
  const request = options.fetch ?? authedFetch;
  const timing = { ...defaults, ...options.timings };
  let current: Connection | undefined;
  let disposed = false;
  let wanted = false;
  let hasConnected = false;
  let reconnecting = false;
  let reconnectAttempts = 0;
  let reconnectTimer: ReturnType<typeof setTimeout> | undefined;
  let generation = 0;
  let previousTurns: VoiceTranscript[] = [];
  let interruptedRequest = false;
  let serial = 0;
  let pendingContext: string | undefined;
  let state: LiveVoiceSnapshot = { status: 'idle', connected: false, muted: false, mutePending: false, speaking: false, working: false, audioBlocked: false };
  const eventId = () => `voice_${Date.now().toString(36)}_${(++serial).toString(36)}`;
  const alive = (connection: Connection) => current === connection && !connection.closing && !disposed;
  function report(patch: Partial<LiveVoiceSnapshot> = {}) {
    state = { ...state, ...patch };
    state.status = state.error ? 'error' : !wanted ? 'idle' : reconnecting && !state.connected ? 'reconnecting' : !current || current.closing ? 'idle' : !state.connected ? 'connecting' : state.muted ? 'muted' : state.speaking ? 'speaking' : state.working ? 'working' : 'listening';
    if (!disposed) options.onState({ ...state });
  }
  function notice(message: string) {
    report({ notice: message });
    if (!disposed) options.onNotice?.(message);
  }
  function send(connection: Connection, payload: Record<string, unknown>) {
    if (!alive(connection) || !connection.ready || connection.channel.readyState !== 'open') return false;
    try { connection.channel.send(JSON.stringify({ event_id: eventId(), ...payload })); return true; } catch { return false; }
  }
  function append(connection: Connection, kind: 'thinking' | 'commentary' | 'instructions', content: string, delegationId: string | null = null) {
    return send(connection, { type: `session.${kind}.append`, delegation_id: delegationId, content: appendText(content) });
  }
  function stopMicrophone(connection: Connection) {
    connection.mic?.getTracks().forEach(track => track.stop());
    connection.audio.pause();
    connection.audio.srcObject = null;
  }
  function endOnServer(connection: Connection) {
    if (connection.ended || !connection.sessionId || !connection.controlToken) return;
    connection.ended = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5_000);
    void request('/api/voice/end', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sessionId: connection.sessionId, controlToken: connection.controlToken }), keepalive: true, signal: controller.signal }).catch(() => {}).finally(() => clearTimeout(timeout));
  }
  function cleanup(connection: Connection) {
    connection.closing = true;
    connection.abort.abort();
    connection.planner?.abort();
    clearTimeout(connection.connectTimer); clearTimeout(connection.disconnectTimer); clearTimeout(connection.queueTimer); clearTimeout(connection.muteTimer); clearTimeout(connection.closeTimer); clearTimeout(connection.sessionTimer); clearInterval(connection.meterTimer);
    stopMicrophone(connection);
    connection.channel.close();
    connection.peer.close();
    void connection.audioContext?.close().catch(() => {});
    connection.queue.length = 0;
    connection.closeResolve?.();
    endOnServer(connection);
    if (current === connection) {
      current = undefined;
      if (!disposed) options.onLevel?.({ input: 0, output: 0 });
    }
  }
  function stopWithError(message: string) {
    wanted = false;
    reconnecting = false;
    clearTimeout(reconnectTimer);
    reconnectTimer = undefined;
    if (current) cleanup(current);
    report({ connected: false, working: false, speaking: false, mutePending: false, audioBlocked: false, error: message, notice: undefined });
  }
  function queueReconnect(expectedGeneration: number, immediate = false) {
    if (!wanted || disposed || generation !== expectedGeneration) return;
    if (navigator.onLine === false) {
      notice('You are offline. Live will reconnect when your connection returns.');
      return;
    }
    if (reconnectAttempts >= timing.reconnectAttempts) {
      stopWithError('Live could not reconnect after several attempts. Check your connection, then try Live again.');
      return;
    }
    clearTimeout(reconnectTimer);
    const delay = immediate ? 0 : Math.min(timing.reconnectBase * 2 ** reconnectAttempts, timing.reconnectMax);
    reconnectTimer = setTimeout(() => {
      reconnectTimer = undefined;
      if (!wanted || disposed || generation !== expectedGeneration) return;
      if (navigator.onLine === false) { queueReconnect(expectedGeneration); return; }
      reconnectAttempts++;
      void connect(true);
    }, delay);
  }
  function recover(connection: Connection, message: string, graceful = false) {
    if (!alive(connection) || !wanted) return;
    const expectedGeneration = generation;
    // Provider timestamps restart at zero. Archive only display/conversation
    // context; queues, completed actions, and eligibility all start empty.
    previousTurns = boundedTurns([...previousTurns, ...transcriptTurns(connection.fragments)]);
    interruptedRequest ||= Boolean(connection.activeJob || connection.queue.length);
    if (connection.ready && Date.now() - connection.readyAt >= timing.reconnectStable) reconnectAttempts = 0;
    reconnecting = true;
    report({ connected: false, working: false, speaking: false, mutePending: false, audioBlocked: false, error: undefined, notice: message });
    if (graceful) {
      void closeConnection(connection).then(() => queueReconnect(expectedGeneration, true));
    } else {
      if (connection.ready && connection.channel.readyState === 'open') {
        try { connection.channel.send(JSON.stringify({ type: 'session.close', event_id: eventId() })); } catch { /* A broken channel is released below. */ }
      }
      cleanup(connection);
      queueReconnect(expectedGeneration);
    }
  }
  function fail(connection: Connection, message: string, permanent = false) {
    if (!alive(connection)) return;
    if (hasConnected && wanted && !permanent) recover(connection, 'Live lost its connection. Reconnecting automatically…');
    else stopWithError(message);
  }
  function userError(error: unknown) {
    const name = error instanceof Error ? error.name : '';
    if (name === 'NotAllowedError' || name === 'PermissionDeniedError') return 'Microphone access is blocked. Allow the microphone in your browser, then try Live again.';
    if (name === 'NotFoundError' || name === 'DevicesNotFoundError') return 'No microphone was found. Connect a microphone, then try Live again.';
    if (name === 'NotReadableError') return 'Your microphone is unavailable. Check other apps using it, then try Live again.';
    return 'Live could not connect. Check your connection and try again.';
  }
  async function post(connection: Connection, path: string, body: unknown, signal: AbortSignal) {
    const encoded = JSON.stringify(body);
    const deadline = Date.now() + timing.plannerBusy;
    let retries = 0;
    while (true) {
      if (signal.aborted || !alive(connection)) throw abortError();
      const response = await request(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: encoded, signal });
      const data = await response.json().catch(() => ({}));
      if (signal.aborted || !alive(connection)) throw abortError();
      if (response.ok) return data;
      // A canceled HTTP request can finish in the browser before the server's
      // provider has released its slot. Retry only unadmitted planner work,
      // preserving the request ID; never replay arbitrary errors or UI actions.
      const busy = response.status === 429 && data.code === 'VOICE_PLANNER_BUSY' && data.retryable === true
        || response.status === 409 && data.error === 'A voice action is already in progress.';
      if (busy) {
        const remaining = deadline - Date.now();
        if (remaining <= 0) throw new Error('Voice is taking longer than expected. Please try your request again.');
        const suggested = typeof data.retryAfterMs === 'number' && Number.isFinite(data.retryAfterMs) && data.retryAfterMs > 0
          ? data.retryAfterMs : timing.plannerRetry * 2 ** Math.min(retries++, 4);
        await new Promise<void>((resolve, reject) => {
          const finish = () => { signal.removeEventListener('abort', cancel); resolve(); };
          const timer = setTimeout(finish, Math.min(remaining, Math.max(1, Math.min(1000, suggested))));
          const cancel = () => { clearTimeout(timer); signal.removeEventListener('abort', cancel); reject(abortError()); };
          signal.addEventListener('abort', cancel, { once: true });
          if (signal.aborted) cancel();
        });
        continue;
      }
      // Only our server's deliberate, bounded messages reach the interface.
      const message = boundedText(data.error, 240) || (response.status === 401 ? 'Your session expired. Sign in again to use Live.' : 'Live is temporarily unavailable. Please try again.');
      throw new Error(message);
    }
  }
  async function play(connection: Connection) {
    if (!alive(connection)) return;
    // The AudioContext only powers level meters. Its autoplay policy or a
    // pending resume must never prevent the audio element from playing.
    try { void connection.audioContext?.resume().catch(() => {}); } catch { /* Metering is optional. */ }
    try {
      await connection.audio.play();
      if (alive(connection)) report({ audioBlocked: false });
    } catch {
      if (alive(connection)) {
        report({ audioBlocked: true, speaking: false });
        notice('Tap Enable audio to hear Live. Your microphone is still connected.');
      }
    }
  }
  function analyser(connection: Connection, stream: MediaStream) {
    if (!connection.audioContext) return undefined;
    try {
      const source = connection.audioContext.createMediaStreamSource(stream);
      const meter = connection.audioContext.createAnalyser();
      meter.fftSize = 256;
      source.connect(meter);
      return meter;
    } catch { return undefined; }
  }
  function startMeters(connection: Connection) {
    const input = new Uint8Array(256);
    const output = new Uint8Array(256);
    const rms = (meter: AnalyserNode | undefined, samples: Uint8Array<ArrayBuffer>) => {
      if (!meter || connection.audioContext?.state !== 'running') return 0;
      meter.getByteTimeDomainData(samples);
      let total = 0;
      for (const sample of samples) total += ((sample - 128) / 128) ** 2;
      return Math.min(1, Math.sqrt(total / samples.length) * 4);
    };
    connection.meterTimer = setInterval(() => {
      if (!alive(connection)) return;
      const inputLevel = state.muted ? 0 : rms(connection.inputAnalyser, input);
      const outputLevel = connection.audio.paused || state.audioBlocked ? 0 : rms(connection.outputAnalyser, output);
      const now = Date.now();
      if (inputLevel > 0.07) connection.lastMicAt = now;
      if (outputLevel > 0.025) connection.lastOutputAt = now;
      if (inputLevel > 0.07 || outputLevel > 0.025) connection.lastActivityAt = now;
      const speaking = outputLevel > 0.025 || (connection.lastOutputAt > 0 && now - connection.lastOutputAt < 220 && !connection.audio.paused);
      if (state.speaking !== speaking) report({ speaking });
      options.onLevel?.({ input: inputLevel, output: outputLevel });
    }, 65);
  }
  function transcript(connection: Connection, event: Record<string, unknown>, role: 'user' | 'assistant') {
    const text = boundedText(event.delta, 4_000);
    if (!text || typeof event.start_ms !== 'number' || typeof event.end_ms !== 'number' || !Number.isFinite(event.start_ms) || !Number.isFinite(event.end_ms) || event.end_ms < event.start_ms) return;
    const fragment: Fragment = { id: `${connection.transcriptPrefix}:${typeof event.event_id === 'string' ? event.event_id : eventId()}`, role, text, startMs: event.start_ms, endMs: event.end_ms, receivedAt: Date.now() };
    if (role === 'user') {
      // A backend confirmation question ends the request turn, independently
      // of when (or whether) the spoken question's transcript arrives. Tag by
      // audio time so delayed earlier fragments cannot cross that boundary.
      for (let index = connection.userTurnBoundaries.length - 1; index >= 0; index--) {
        if (fragment.startMs >= connection.userTurnBoundaries[index]) {
          fragment.userTurn = connection.userTurnBoundaries[index];
          break;
        }
      }
    }
    connection.fragments.push(fragment);
    connection.fragments.sort((a, b) => a.startMs - b.startMs || a.receivedAt - b.receivedAt);
    connection.fragments = compactTranscript(connection.fragments);
    if (role === 'user') {
      connection.revision++;
      connection.lastUserAt = Date.now();
      connection.lastActivityAt = Date.now();
      // A correction must invalidate a returned plan before its next click.
      // Executions already dispatched finish and are recorded truthfully.
      connection.planner?.abort();
      schedule(connection);
    }
    if (!disposed) options.onTranscript(boundedTurns([...previousTurns, ...transcriptTurns(connection.fragments)]));
  }
  function schedule(connection: Connection, delay = timing.settle) {
    clearTimeout(connection.queueTimer);
    if (alive(connection)) connection.queueTimer = setTimeout(() => void drain(connection), Math.max(1, delay));
  }
  function latestUser(connection: Connection) { return connection.fragments.filter(part => part.role === 'user').at(-1); }
  function conversation(connection: Connection) {
    const recent = transcriptTurns(connection.fragments);
    const boundary: VoiceTranscript[] = previousTurns.length ? [{ id: 'reconnected', role: 'assistant', text: 'The Live connection restarted. Earlier app requests are closed. Only act on the new user request after this message; do not replay earlier actions.', startMs: 0, endMs: 0 }] : [];
    return boundedTurns([...previousTurns, ...boundary, ...recent]).map(({ role, text }) => ({ role, text }));
  }
  function inheritContinuation(connection: Connection, job: Delegation) {
    const completed = connection.completedJob;
    if (!completed || job.history.length || Date.now() - completed.at > 3_000 || completed.job.history.at(-1)?.result.requiresConfirmation) return;
    const added = connection.fragments.filter(part => part.role === 'user' && part.endMs > completed.endMs);
    const first = added[0];
    if (!first || first.startMs - completed.endMs > 750) return;
    // A reply after assistant speech is a new request. Only carry evidence
    // across contiguous user fragments that arrived after an early completion.
    if (connection.fragments.some(part => part.role === 'assistant' && part.endMs > completed.endMs && part.startMs < first.startMs)) return;
    for (let index = 1; index < added.length; index++) if (added[index].startMs - added[index - 1].endMs > 750) return;
    job.history = [...completed.job.history];
    job.steps = completed.job.steps;
    job.attempts = new Set(completed.job.attempts);
  }
  async function drain(connection: Connection) {
    if (!alive(connection) || !connection.ready || connection.activeJob || !connection.queue.length) return;
    const job = connection.queue[0];
    const user = latestUser(connection);
    const now = Date.now();
    if (job.awaitingSpeech) {
      if (connection.revision <= job.awaitingSpeech.revision) {
        if (now - job.awaitingSpeech.since < timing.transcriptWait) { schedule(connection); return; }
        connection.queue.shift();
        append(connection, 'commentary', 'I heard more speech and paused the pending app action, but could not understand the update. Please repeat what you would like me to do.', job.id);
        schedule(connection); return;
      }
      job.awaitingSpeech = undefined;
    }
    const nearby = user && user.text.trim() && user.endMs >= job.offset - 20_000 && user.startMs <= job.offset + 15_000;
    const settling = now - Math.max(connection.lastUserAt, connection.lastMicAt) < timing.settle;
    if (!nearby || settling) {
      if (now - job.receivedAt < timing.transcriptWait || settling && now - job.receivedAt < timing.transcriptWait * 3) { schedule(connection); return; }
      connection.queue.shift();
      append(connection, 'commentary', 'I could not identify the app request from the available speech. Please repeat what you would like me to do.', job.id);
      schedule(connection); return;
    }
    // Several notices for one stretch of speech must not submit it twice.
    if (!job.history.length && user.endMs <= connection.lastCompletedEnd) {
      // Delegations and transcript deltas travel independently. The previous
      // utterance may be the only one available when a new delegation arrives.
      // Keep the notice briefly so its own transcript can make it eligible.
      if (now - job.receivedAt < timing.transcriptWait) { schedule(connection); return; }
      connection.queue.shift();
      append(connection, 'thinking', 'This speech request has already been handled. Wait for a new user request before taking more app actions.', job.id);
      schedule(connection); return;
    }
    inheritContinuation(connection, job);
    connection.queue.shift();
    connection.activeJob = job;
    report({ working: true, notice: undefined });
    const revision = connection.revision;
    const microphoneAtStart = connection.lastMicAt;
    const changedRequest = () => {
      if (connection.revision !== revision) return true;
      if (connection.lastMicAt > microphoneAtStart) {
        job.awaitingSpeech = { revision, since: Date.now() };
        return true;
      }
      return false;
    };
    let interrupted = false;
    let completed = false;
    try {
      while (alive(connection) && job.steps < 10) {
        if (changedRequest()) { interrupted = true; break; }
        const surface = await options.readSurface();
        if (!alive(connection)) return;
        if (changedRequest()) { interrupted = true; break; }
        const controller = new AbortController();
        connection.planner = controller;
        const timeout = setTimeout(() => controller.abort(), timing.plan);
        let data: { action: unknown };
        try {
          data = await post(connection, '/api/voice/plan', { sessionId: connection.sessionId, controlToken: connection.controlToken, requestId: `${job.id}:${job.steps}:${job.replans}`, conversation: conversation(connection), surface, history: job.history.slice(-10) }, controller.signal);
        } catch (error) {
          // A superseded request can fail during cancellation with a network
          // or server error too. Its error must not discard the newer speech.
          if (changedRequest()) { interrupted = true; break; }
          if (isAbort(error) && alive(connection)) throw new Error('That app request took too long. Please try it again.');
          throw error;
        } finally {
          clearTimeout(timeout);
          if (connection.planner === controller) connection.planner = undefined;
        }
        if (!alive(connection)) return;
        if (changedRequest()) { interrupted = true; break; }
        if (!validAction(data.action)) throw new Error('Live could not interpret that app action. Please try rephrasing it.');
        const action = data.action;
        if (action.type === 'done') {
          append(connection, 'commentary', action.message || 'Ready for your next request.', job.id);
          completed = true; break;
        }
        const signature = actionSignature(action, surface);
        if (!repeatableNavigation(action)) {
          if (job.attempts.has(signature)) throw new Error('That control has not changed. Please check the app before trying again.');
          job.attempts.add(signature);
        }
        const result = await options.execute(action);
        job.steps++;
        job.history.push({ action, result: { ...result, message: boundedText(result.message, 1200) } });
        if (!alive(connection)) return;
        append(connection, 'thinking', result.message || (result.ok ? 'The app control was activated.' : 'The app control could not be activated.'), job.id);
        if (result.requiresConfirmation) {
          const userEnd = latestUser(connection)?.endMs;
          // Delegation can cover audio whose transcript is still arriving.
          // Keep that earlier audio in the original request too.
          const boundary = userEnd === undefined ? undefined : Math.max(userEnd, job.offset);
          if (boundary !== undefined && boundary > (connection.userTurnBoundaries.at(-1) ?? -Infinity)) {
            connection.userTurnBoundaries.push(boundary);
            connection.userTurnBoundaries = connection.userTurnBoundaries.slice(-96);
          }
          append(connection, 'commentary', result.message, job.id);
          completed = true; break;
        }
        if (changedRequest()) { interrupted = true; break; }
      }
      if (!completed && !interrupted && alive(connection)) append(connection, 'commentary', 'I reached the limit for this request. Please tell me the next step you would like to take.', job.id);
    } catch (error) {
      if (alive(connection) && !isAbort(error)) {
        const message = error instanceof Error ? boundedText(error.message, 240) : 'That app action could not be completed. Please try again.';
        notice(message);
        append(connection, 'commentary', message, job.id);
      }
    } finally {
      if (connection.activeJob === job) connection.activeJob = undefined;
      if (alive(connection)) {
        if (interrupted && job.replans < 8) {
          job.replans++;
          job.receivedAt = Date.now();
          job.offset = latestUser(connection)?.endMs ?? job.offset;
          connection.queue.unshift(job);
          append(connection, 'thinking', 'The user continued or corrected the request. Pending actions are paused; any recorded app actions already happened. Reconsider the newest speech before continuing.', job.id);
        } else if (interrupted) {
          const message = 'I paused because the request kept changing. Check the app, then repeat the full request.';
          notice(message);
          append(connection, 'commentary', message, job.id);
          connection.lastCompletedEnd = Math.max(connection.lastCompletedEnd, latestUser(connection)?.endMs ?? user.endMs);
          connection.completedJob = undefined;
        } else {
          connection.lastCompletedEnd = Math.max(connection.lastCompletedEnd, user.endMs);
          connection.completedJob = { job, at: Date.now(), endMs: user.endMs };
        }
        report({ working: false });
        schedule(connection);
      }
    }
  }
  async function updateContext(context?: string) {
    if (context !== undefined) pendingContext = context;
    const connection = current;
    if (!connection || !alive(connection) || !connection.ready || pendingContext === undefined) return;
    // A surface read captures the exact controls an ensuing action can use.
    // Background context must never replace that capture while a plan is in
    // flight, especially when a user is simultaneously editing an input.
    const compact = appendText(`Current app context: ${pendingContext}`);
    if (compact !== connection.lastContext && append(connection, 'thinking', compact)) {
      connection.lastContext = compact;
      connection.lastActivityAt = Date.now();
    }
  }
  function mute(connection: Connection, muted: boolean) {
    connection.mic?.getAudioTracks().forEach(track => { track.enabled = !muted; });
    report({ muted, mutePending: connection.ready });
    if (!connection.ready) return;
    clearTimeout(connection.muteTimer);
    const id = eventId();
    connection.muteEvent = { id, muted };
    if (!send(connection, { type: muted ? 'session.input_audio.mute' : 'session.input_audio.unmute', event_id: id })) {
      fail(connection, 'Live lost its connection. Please reconnect.'); return;
    }
    connection.muteTimer = setTimeout(() => {
      if (!alive(connection) || connection.muteEvent?.id !== id) return;
      // Local capture remains muted if the provider cannot acknowledge it.
      connection.mic?.getAudioTracks().forEach(track => { track.enabled = false; });
      report({ muted: true, mutePending: false });
      notice('Live did not confirm the microphone change. Reconnect to resume speaking.');
    }, timing.mute);
  }
  function renew(connection: Connection) {
    if (!alive(connection)) return;
    // Renew before the provider's limit, preferably between requests. Bound the
    // grace period so ongoing speech cannot run into a silently expired call.
    const busy = connection.activeJob || connection.queue.length || state.speaking || Date.now() - connection.lastMicAt < timing.settle;
    if (busy && Date.now() - connection.readyAt < timing.maxSession + timing.renewGrace) {
      connection.sessionTimer = setTimeout(() => renew(connection), Math.min(1_000, Math.max(1, timing.renewGrace)));
      return;
    }
    recover(connection, 'Refreshing the Live connection. Your conversation will continue automatically.', true);
  }
  function receive(connection: Connection, raw: unknown) {
    let event: Record<string, unknown>;
    try { event = JSON.parse(String(raw)); } catch { return; }
    if (!event || typeof event !== 'object') return;
    if (event.type === 'session.closed') {
      connection.finalized = true;
      if (alive(connection) && wanted && hasConnected) {
        recover(connection, event.reason === 'expired' ? 'Refreshing the Live connection. Your conversation will continue automatically.' : 'Live lost its connection. Reconnecting automatically…');
      } else if (alive(connection) && wanted) {
        fail(connection, 'Live closed before the connection was ready. Please try again.', true);
      } else {
        const wasCurrent = current === connection;
        cleanup(connection);
        if (wasCurrent) report({ connected: false, working: false, speaking: false, mutePending: false, audioBlocked: false, error: undefined });
      }
      return;
    }
    if (!alive(connection)) return;
    if (typeof event.event_id === 'string') {
      if (connection.seen.has(event.event_id)) return;
      remember(connection.seen, event.event_id);
    }
    if (event.type === 'session.started') {
      if (connection.ready) return;
      connection.ready = true;
      connection.readyAt = Date.now();
      hasConnected = true;
      reconnecting = false;
      clearTimeout(connection.connectTimer);
      connection.lastActivityAt = Date.now();
      connection.sessionTimer = setTimeout(() => renew(connection), timing.maxSession);
      report({ connected: true, error: undefined, notice: connection.recovering ? interruptedRequest ? 'Live reconnected. Please repeat your interrupted request.' : 'Live reconnected. Your conversation is ready to continue.' : undefined });
      if (state.muted) mute(connection, true);
      if (connection.recovering) {
        append(connection, 'instructions', `Live has reconnected. Earlier conversation is context only. Never restart old app actions. Wait for fresh user speech before delegating. ${interruptedRequest ? 'Briefly say you reconnected and ask the user to repeat the interrupted request.' : 'Continue listening without repeating the greeting.'}`);
      } else {
        // Ask for speech at the first documented readiness event, before app
        // context. An acknowledgment accepts the request; it is not playback.
        connection.greetingEvent = eventId();
        if (!send(connection, {
          type: 'session.instructions.append', event_id: connection.greetingEvent, delegation_id: null,
          content: 'Speak first, immediately, in English. Say: "Live is on. What would you like to create or explore?" Pronounce Live /laɪv/ (long i, rhymes with alive), never /lɪv/. Then pause and listen. Do not wait for the user to speak or for app context. This greeting requires no app action or delegation.',
        })) {
          connection.greetingEvent = undefined;
          notice('Live is connected, but could not start its greeting. You can speak now, or reconnect.');
        }
      }
      void updateContext();
      interruptedRequest = false;
      schedule(connection);
    } else if (event.type === 'session.instructions.appended') {
      if (event.client_event_id === connection.greetingEvent) connection.greetingEvent = undefined;
    } else if (event.type === 'session.input_transcript.delta') transcript(connection, event, 'user');
    else if (event.type === 'session.output_transcript.delta') transcript(connection, event, 'assistant');
    else if (event.type === 'session.delegation.created') {
      const delegation = event.delegation as { id?: unknown; target?: unknown } | undefined;
      if (delegation?.target !== 'client' || typeof delegation.id !== 'string' || !delegation.id || delegation.id.length > 250 || connection.delegations.has(delegation.id)) return;
      remember(connection.delegations, delegation.id);
      if (connection.queue.length >= 6) {
        append(connection, 'commentary', 'Please wait for the current app request, then tell me the next step.', delegation.id); return;
      }
      connection.queue.push({ id: delegation.id, offset: typeof event.offset_ms === 'number' && Number.isFinite(event.offset_ms) ? event.offset_ms : latestUser(connection)?.endMs ?? 0, receivedAt: Date.now(), history: [], steps: 0, replans: 0, attempts: new Set() });
      schedule(connection);
    } else if (event.type === 'session.input_audio.muted' || event.type === 'session.input_audio.unmuted') {
      const pending = connection.muteEvent;
      if (!pending || event.client_event_id !== pending.id || (event.type === 'session.input_audio.muted') !== pending.muted) return;
      clearTimeout(connection.muteTimer);
      connection.muteEvent = undefined;
      report({ mutePending: false });
    } else if (event.type === 'error') {
      const error = event.error as { client_event_id?: string; code?: string } | undefined;
      if (error?.code && ['invalid_api_key', 'authentication_error', 'permission_denied', 'model_not_found', 'invalid_model', 'invalid_configuration'].includes(error.code)) {
        fail(connection, 'Live is unavailable with the current server configuration. Check access and configuration, then try again.', true);
      } else if (error?.code === 'session_expired') {
        recover(connection, 'Refreshing the Live connection. Your conversation will continue automatically.');
      } else if (connection.greetingEvent && error?.client_event_id === connection.greetingEvent) {
        connection.greetingEvent = undefined;
        // Do not replay automatically: the caller may already be speaking.
        notice('Live is connected, but could not start its greeting. You can speak now, or reconnect.');
      } else if (connection.muteEvent && error?.client_event_id === connection.muteEvent.id) {
        clearTimeout(connection.muteTimer);
        connection.mic?.getAudioTracks().forEach(track => { track.enabled = false; });
        report({ muted: true, mutePending: false });
        notice('Live could not update the microphone. Reconnect to resume speaking.');
      } else notice('Live could not process an update. Please repeat your request, or reconnect if it continues.');
    }
  }
  function waitForIce(connection: Connection) {
    if (connection.peer.iceGatheringState === 'complete') return Promise.resolve();
    return new Promise<void>((resolve, reject) => {
      const finish = (error?: Error) => {
        clearTimeout(timeout);
        connection.peer.removeEventListener('icegatheringstatechange', changed);
        connection.abort.signal.removeEventListener('abort', aborted);
        if (error) reject(error); else resolve();
      };
      const changed = () => { if (connection.peer.iceGatheringState === 'complete') finish(); };
      const aborted = () => finish(abortError());
      const timeout = setTimeout(() => finish(new Error('Microphone connection timed out. Please try Live again.')), timing.ice);
      connection.peer.addEventListener('icegatheringstatechange', changed);
      connection.abort.signal.addEventListener('abort', aborted, { once: true });
      changed();
    });
  }
  async function start(initial: { muted?: boolean } = {}) {
    if (disposed || wanted) return;
    generation++;
    wanted = true;
    hasConnected = false;
    reconnecting = false;
    reconnectAttempts = 0;
    previousTurns = [];
    interruptedRequest = false;
    state = { status: 'connecting', connected: false, muted: Boolean(initial.muted), mutePending: false, speaking: false, working: false, audioBlocked: false };
    options.onTranscript([]);
    await connect(false);
  }
  async function connect(recovering: boolean) {
    if (disposed || !wanted) return;
    if (current) cleanup(current);
    if (!globalThis.navigator?.mediaDevices?.getUserMedia || typeof RTCPeerConnection === 'undefined') {
      stopWithError('Live needs a browser with microphone support on HTTPS or localhost.'); return;
    }
    let started: Connection | undefined;
    try {
      const peer = new RTCPeerConnection();
      const audio = new Audio();
      audio.autoplay = true;
      audio.setAttribute('playsinline', '');
      const channel = peer.createDataChannel('oai-events');
      const connection: Connection = { peer, channel, audio, ended: false, closing: false, ready: false, readyAt: 0, recovering, transcriptPrefix: eventId(), finalized: false, abort: new AbortController(), queue: [], revision: 0, lastUserAt: 0, lastMicAt: 0, lastOutputAt: 0, lastActivityAt: Date.now(), lastCompletedEnd: -1, fragments: [], userTurnBoundaries: [], seen: new Set(), delegations: new Set(), lastContext: '' };
      current = connection;
      started = connection;
      report();
      // Both construction and resume happen in the user's click gesture.
      try { connection.audioContext = new AudioContext(); void connection.audioContext.resume().catch(() => {}); } catch { /* Audio still works without visual level metering. */ }
      connection.connectTimer = setTimeout(() => fail(connection, 'Live connection timed out. Check microphone permissions and your connection, then try again.'), timing.connect);
      channel.addEventListener('message', event => receive(connection, event.data));
      channel.addEventListener('close', () => { if (alive(connection)) fail(connection, 'Live disconnected. Start Live again to continue.'); });
      channel.addEventListener('error', () => { if (alive(connection)) fail(connection, 'The Live connection failed. Please reconnect.'); });
      peer.addEventListener('track', event => {
        if (!alive(connection)) return;
        const stream = event.streams[0] ?? new MediaStream([event.track]);
        audio.srcObject = stream;
        connection.outputAnalyser = analyser(connection, stream);
        void play(connection);
      });
      peer.addEventListener('connectionstatechange', () => {
        if (!alive(connection)) return;
        if (peer.connectionState === 'failed' || peer.connectionState === 'closed') fail(connection, 'Live lost its audio connection. Please reconnect.');
        else if (peer.connectionState === 'disconnected') {
          if (!connection.disconnectTimer) connection.disconnectTimer = setTimeout(() => fail(connection, 'Live lost its audio connection. Please reconnect.'), timing.disconnect);
        } else if (peer.connectionState === 'connected') { clearTimeout(connection.disconnectTimer); connection.disconnectTimer = undefined; }
      });
      const microphone = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true } });
      if (!alive(connection)) { microphone.getTracks().forEach(track => track.stop()); return; }
      connection.mic = microphone;
      if (!microphone.getAudioTracks().length) throw new ConnectionError('No microphone audio track was available. Connect a microphone, then try Live again.', true);
      for (const track of microphone.getAudioTracks()) {
        track.enabled = !state.muted;
        peer.addTrack(track, microphone);
        track.addEventListener('ended', () => { if (alive(connection)) fail(connection, 'Your microphone disconnected. Reconnect it, then start Live again.', true); });
      }
      connection.inputAnalyser = analyser(connection, microphone);
      startMeters(connection);
      const offer = await peer.createOffer();
      if (!alive(connection)) return;
      await peer.setLocalDescription(offer);
      await waitForIce(connection);
      if (!alive(connection)) return;
      const sdp = peer.localDescription?.sdp;
      if (!sdp) throw new Error('Live could not prepare your microphone connection. Please try again.');
      // The server also owns request-disconnect cleanup. If a response races
      // cancellation and is still readable, release its returned session below.
      const conversation = recovering ? reconnectConversation(previousTurns) : [];
      const response = await request('/api/voice/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ sdp, ...(conversation.length ? { conversation } : {}) }), signal: connection.abort.signal });
      const data = await response.json().catch(() => ({}));
      if (typeof data.session?.id === 'string') connection.sessionId = data.session.id;
      if (typeof data.controlToken === 'string') connection.controlToken = data.controlToken;
      if (!alive(connection)) { endOnServer(connection); return; }
      if (!response.ok) throw new ConnectionError(boundedText(data.error, 240) || 'Live is unavailable. Check the server configuration and try again.', data.retryable === false || response.status >= 400 && response.status < 500 && response.status !== 408 && response.status !== 429);
      if (!connection.sessionId || !connection.controlToken || data.transport?.type !== 'webrtc' || typeof data.transport.sdp !== 'string') throw new ConnectionError('Live returned an incomplete connection. Please try again.', true);
      await peer.setRemoteDescription({ type: 'answer', sdp: data.transport.sdp });
      // POST starts GPT-Live. Never send the WebSocket-only session.start event.
    } catch (error) {
      if (!isAbort(error)) {
        const message = error instanceof Error && error.name === 'Error' ? boundedText(error.message, 240) : userError(error);
        if (started && alive(started)) fail(started, message || userError(error), permanentMediaError(error) || error instanceof ConnectionError && error.permanent);
        else if (!started && !current && !disposed) stopWithError(message || userError(error));
      }
    }
  }
  async function stop() {
    generation++;
    wanted = false;
    reconnecting = false;
    clearTimeout(reconnectTimer);
    reconnectTimer = undefined;
    const connection = current;
    report({ connected: false, working: false, speaking: false, muted: false, mutePending: false, audioBlocked: false, error: undefined, notice: undefined });
    if (!connection) return;
    return closeConnection(connection);
  }
  async function closeConnection(connection: Connection) {
    if (connection.stopPromise) return connection.stopPromise;
    const canClose = connection.ready && connection.channel.readyState === 'open';
    if (canClose) {
      try { connection.channel.send(JSON.stringify({ type: 'session.close', event_id: eventId() })); } catch { /* The fallback server hangup still runs. */ }
    }
    connection.closing = true;
    connection.abort.abort();
    connection.planner?.abort();
    stopMicrophone(connection);
    if (!disposed) options.onLevel?.({ input: 0, output: 0 });
    connection.stopPromise = new Promise<void>(resolve => {
      connection.closeResolve = resolve;
      if (!canClose || connection.finalized) { cleanup(connection); resolve(); return; }
      connection.closeTimer = setTimeout(() => { cleanup(connection); resolve(); }, timing.close);
    });
    return connection.stopPromise;
  }
  function resetConversation() {
    previousTurns = [];
    interruptedRequest = false;
    if (!disposed) options.onTranscript([]);
    if (!wanted || disposed) return;
    const expectedGeneration = ++generation;
    clearTimeout(reconnectTimer);
    reconnectTimer = undefined;
    reconnectAttempts = 0;
    reconnecting = true;
    report({ connected: false, working: false, speaking: false, mutePending: false, audioBlocked: false, error: undefined, notice: 'Continuing Live with your current account…' });
    const connection = current;
    if (connection) {
      connection.fragments = [];
      connection.queue.length = 0;
      void closeConnection(connection).then(() => queueReconnect(expectedGeneration, true));
    } else queueReconnect(expectedGeneration, true);
  }
  const online = () => {
    if (wanted && reconnecting && !current && !reconnectTimer) queueReconnect(generation, true);
  };
  const offline = () => {
    if (current && alive(current) && hasConnected) recover(current, 'You are offline. Live will reconnect when your connection returns.');
  };
  globalThis.addEventListener?.('online', online);
  globalThis.addEventListener?.('offline', offline);
  return {
    start,
    stop,
    resetConversation,
    setMuted: muted => { if (current && alive(current)) mute(current, muted); else if (wanted) report({ muted, mutePending: false }); },
    resumeAudio: async () => { if (current) await play(current); },
    updateContext,
    destroy: () => {
      disposed = true;
      globalThis.removeEventListener?.('online', online);
      globalThis.removeEventListener?.('offline', offline);
      void stop();
    },
  };
}
