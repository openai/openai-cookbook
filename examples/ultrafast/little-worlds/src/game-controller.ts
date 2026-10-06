import { validateGameConfig, validateGameState, validateGameView } from '../shared/game-schema.mjs';
import type { GamePayload, GameState, GameView } from '../shared/game-schema.mjs';
import type { GameWorkerCommand, GameWorkerMessage, GameWorkerRequest } from './game-worker';

export type { GamePayload } from '../shared/game-schema.mjs';
export type GameStatus = 'idle' | 'loading' | 'running' | 'paused' | 'finished' | 'error';
export type GameEvent = { type: 'frame'; view: GameView; intervalMs?: number; kind?: 'tick' | 'action' | 'reset' } | { type: 'status'; status: GameStatus; message?: string };
export type GameCommand = { command: 'start' | 'pause' | 'resume' | 'restart' | 'action'; action?: unknown; release?: boolean };
export type GameWorker = Pick<Worker, 'postMessage' | 'terminate' | 'onmessage' | 'onerror' | 'onmessageerror'>;
type Timer = ReturnType<typeof setTimeout>;

export type GameControllerOptions = {
  load(): Promise<GamePayload>;
  save(action: { type: string; game: GameState }): Promise<boolean>;
  emit(event: GameEvent): void;
  createWorker?: () => GameWorker;
  setTimer?: (callback: () => void, delay: number) => Timer;
  clearTimer?: (timer: Timer) => void;
  now?: () => number;
  visibility?: Pick<Document, 'hidden' | 'addEventListener' | 'removeEventListener'>;
};

/** One controller belongs to one mounted published revision and one identity. */
export function createGameController(options: GameControllerOptions) {
  const createWorker = options.createWorker ?? (() => new Worker(new URL('./game-worker.ts', import.meta.url), { type: 'module' }));
  const setTimer = options.setTimer ?? setTimeout;
  const clearTimer = options.clearTimer ?? clearTimeout;
  const now = options.now ?? Date.now;
  const visibility = options.visibility ?? (typeof document === 'undefined' ? undefined : document);
  let worker: GameWorker | undefined;
  let payload: GamePayload | undefined;
  let latest: GameState | undefined;
  let status: GameStatus = 'idle';
  let watchdog: Timer | undefined;
  let checkpointTimer: Timer | undefined;
  let epoch = 0;
  let saveGeneration = 0;
  let requestId = 0;
  let pendingRequest: number | undefined;
  let pendingCommand: GameWorkerCommand['command'] | 'init' | undefined;
  let pendingRelease = false;
  let commands: { value: GameWorkerCommand; requiredRelease: boolean; resolve: (ok: boolean) => void }[] = [];
  let resolvePending: ((ok: boolean) => void) | undefined;
  let startWaiters: ((ok: boolean) => void)[] = [];
  let disposed = false;
  let saving = false;
  let queuedSave: { type: string; game: GameState; signature: string; epoch: number; generation: number } | undefined;
  let savedSignature = '';
  let savingSignature = '';
  let lastSave = -Infinity;
  let saveFailure = false;

  function setStatus(next: GameStatus, message?: string) {
    if (disposed) return;
    if (status === next && !message) return;
    status = next;
    options.emit({ type: 'status', status: next, ...(message ? { message } : {}) });
  }

  function cancelWatchdog() { if (watchdog !== undefined) clearTimer(watchdog); watchdog = undefined; }
  function cancelCheckpoint() { if (checkpointTimer !== undefined) clearTimer(checkpointTimer); checkpointTimer = undefined; }
  function settleStart(ok: boolean) { for (const resolve of startWaiters) resolve(ok); startWaiters = []; }
  function terminate() {
    cancelWatchdog(); cancelCheckpoint();
    if (worker) {
      worker.onmessage = null; worker.onerror = null; worker.onmessageerror = null;
      worker.terminate(); worker = undefined;
    }
    pendingRequest = undefined;
    pendingCommand = undefined;
    pendingRelease = false;
    resolvePending?.(false); resolvePending = undefined;
    for (const command of commands) command.resolve(false);
    commands = [];
    settleStart(false);
  }

  function fail(message: string) {
    checkpoint(true);
    epoch++; terminate();
    setStatus('error', message.slice(0, 240));
  }

  function armWatchdog(delay = 3000) {
    cancelWatchdog();
    watchdog = setTimer(() => fail('This game stopped responding. Start it again to continue.'), delay);
  }

  async function drainSaves() {
    if (saving || !queuedSave) return;
    saving = true;
    const next = queuedSave; queuedSave = undefined;
    savingSignature = next.signature;
    lastSave = now();
    try {
      const ok = await options.save({ type: next.type, game: next.game });
      if (!ok) throw new Error('Progress was not saved.');
      if (next.epoch === epoch && next.generation === saveGeneration) { savedSignature = next.signature; saveFailure = false; }
    } catch {
      if (next.epoch === epoch && next.generation === saveGeneration) {
        queuedSave = undefined;
        saveFailure = true;
        cancelCheckpoint();
        if (!disposed && worker) {
          void queueCommand({ command: 'pause' });
          setStatus('paused', 'Your game is paused because progress could not be saved. Resume to try again.');
        }
      }
    } finally {
      saving = false;
      savingSignature = '';
      if (queuedSave && !saveFailure) void drainSaves();
    }
  }

  function checkpoint(force = false) {
    if (!payload?.config.saveAction || !latest || saveFailure) return;
    const signature = JSON.stringify(latest);
    if (signature === savedSignature || signature === savingSignature) return;
    if (!force && now() - lastSave < 2000) return;
    queuedSave = { type: payload.config.saveAction, game: structuredClone(latest), signature, epoch, generation: saveGeneration };
    void drainSaves();
  }

  function scheduleCheckpoint() {
    cancelCheckpoint();
    if (disposed || status !== 'running' || !payload?.config.saveAction) return;
    checkpointTimer = setTimer(() => {
      checkpointTimer = undefined;
      checkpoint();
      scheduleCheckpoint();
    }, 2000);
  }

  function flushCommands() {
    if (!worker || pendingRequest !== undefined || !commands.length) return;
    const { value, requiredRelease, resolve } = commands.shift()!;
    resolvePending = resolve;
    pendingRelease = requiredRelease;
    pendingRequest = ++requestId;
    pendingCommand = value.command;
    armWatchdog();
    worker.postMessage({ type: 'command', requestId: pendingRequest, value } satisfies GameWorkerRequest);
  }

  function queueCommand(value: GameWorkerCommand, requiredRelease = false): Promise<boolean> {
    if (!worker) return Promise.resolve(false);
    // Bound browser input while a slow worker is responding. Lifecycle commands
    // supersede queued controls. Releases must run before pause/resume so a
    // pending press cannot leave input latched when the game resumes.
    if (value.command !== 'action') commands = commands.filter(command => {
      if (command.requiredRelease && (value.command === 'pause' || value.command === 'resume')) return true;
      command.resolve(false); return false;
    });
    if (commands.length >= 32) {
      const obsolete = requiredRelease ? commands.findIndex(command => !command.requiredRelease && command.value.command === 'action') : -1;
      if (obsolete === -1) return Promise.resolve(false);
      commands.splice(obsolete, 1)[0].resolve(false);
    }
    if (value.command === 'restart') saveGeneration++;
    return new Promise(resolve => {
      // The parent's visibility event can arrive before the frame releases its
      // held keys. If pause is still queued, neutralize those keys first.
      const lifecycle = requiredRelease ? commands.findIndex(command => command.value.command === 'pause' || command.value.command === 'resume') : -1;
      commands.splice(lifecycle < 0 ? commands.length : lifecycle, 0, { value, requiredRelease, resolve });
      flushCommands();
    });
  }

  function receive(message: GameWorkerMessage, workerEpoch: number) {
    if (disposed || workerEpoch !== epoch || !worker || !payload) return;
    try {
      if (message.type === 'error') {
        if (message.diagnostic) console.warn('Game runtime stopped', JSON.stringify(message.diagnostic));
        fail(message.message || 'This game could not run.'); return;
      }
      if (message.type !== 'frame' && message.type !== 'ready') throw new Error('The game returned an invalid update.');
      validateGameState(message.state, payload.actor);
      validateGameView(message.view);
      if (!['running', 'paused', 'finished'].includes(message.status)) throw new Error('The game returned an invalid status.');
      if (message.requestId !== undefined && message.requestId !== pendingRequest) return;
      const complete = message.requestId !== undefined ? resolvePending : undefined;
      const released = message.requestId !== undefined && pendingRelease;
      const kind = message.requestId === undefined ? 'tick' : pendingCommand === 'action' ? 'action' : 'reset';
      if (message.requestId !== undefined) { pendingRequest = undefined; pendingCommand = undefined; pendingRelease = false; resolvePending = undefined; }
      latest = message.state;
      const previous = status;
      const nextStatus = saveFailure && message.status === 'running' ? 'paused' : message.status;
      setStatus(nextStatus);
      options.emit({ type: 'frame', view: message.view, intervalMs: payload.config.tickMs ?? 50, kind });
      if (nextStatus === 'paused' || nextStatus === 'finished') {
        cancelCheckpoint();
        // A visibility pause may already be in flight when the frame sends a
        // release. Persist its neutral state even though we are already paused.
        if (previous !== nextStatus || released) checkpoint(true);
      } else if (previous !== 'running') scheduleCheckpoint();
      // A stream of ordinary ticks must not hide a command that never replies.
      if (pendingRequest === undefined) {
        if (message.status === 'running') armWatchdog();
        else cancelWatchdog();
      }
      if (visibility?.hidden && message.status === 'running') void queueCommand({ command: 'pause' });
      flushCommands();
      complete?.(true);
    } catch (error) { fail(error instanceof Error ? error.message : 'The game returned an invalid update.'); }
  }

  async function start(restart = false) {
    if (disposed || status === 'loading') return;
    const loadingEpoch = ++epoch;
    setStatus('loading');
    armWatchdog(15_000);
    try {
      const loaded = await options.load();
      if (disposed || loadingEpoch !== epoch) return;
      const next = restart ? { ...loaded, saved: null } : loaded;
      validateGameConfig(next.config);
      if (next.saved !== null) validateGameState(next.saved, next.actor);
      payload = next; latest = undefined; savedSignature = JSON.stringify(next.saved); saveFailure = false;
      worker = createWorker();
      worker.onmessage = event => receive(event.data as GameWorkerMessage, loadingEpoch);
      worker.onerror = () => fail('This game could not start. You can try again.');
      worker.onmessageerror = () => fail('This game returned an unreadable update.');
      pendingRequest = ++requestId;
      pendingCommand = 'init';
      resolvePending = settleStart;
      armWatchdog(10_000);
      worker.postMessage({ type: 'init', requestId: pendingRequest, payload: next } satisfies GameWorkerRequest);
    } catch (error) { if (!disposed && loadingEpoch === epoch) fail(error instanceof Error ? error.message : 'This game could not start.'); }
  }

  function handle(value: GameCommand): Promise<boolean> {
    if (disposed || !value || typeof value !== 'object') return Promise.resolve(false);
    if (value.command === 'start' || (value.command === 'restart' && !worker)) {
      if (worker && status !== 'loading') return handle({ command: status === 'finished' ? 'restart' : 'resume' });
      const result = new Promise<boolean>(resolve => { startWaiters.push(resolve); });
      if (status !== 'loading') void start(value.command === 'restart');
      return result;
    }
    if (!worker || status === 'loading' || status === 'error') return Promise.resolve(false);
    if (value.command === 'resume' || value.command === 'restart') saveFailure = false;
    if (value.command === 'action') {
      const action = value.action;
      if (!action || typeof action !== 'object' || Array.isArray(action)) return Promise.resolve(false);
      const type = (action as { type?: unknown }).type;
      if (typeof type !== 'string' || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(type) || type === 'tick') return Promise.resolve(false);
      try { if (JSON.stringify(action).length > 4096) return Promise.resolve(false); } catch { return Promise.resolve(false); }
    } else if (!['pause', 'resume', 'restart'].includes(value.command)) return Promise.resolve(false);
    return queueCommand(value as GameWorkerCommand, value.command === 'action' && value.release === true);
  }

  function onVisibility() {
    if (visibility?.hidden && status === 'running') void queueCommand({ command: 'pause' });
  }
  visibility?.addEventListener('visibilitychange', onVisibility);

  return {
    handle,
    dispose() {
      if (disposed) return;
      checkpoint(true);
      disposed = true; epoch++; terminate();
      visibility?.removeEventListener('visibilitychange', onVisibility);
    },
  };
}
