/// <reference types="vite/client" />
import RELEASE_SYNC from '@jitl/quickjs-wasmfile-release-sync';
import wasmUrl from '@jitl/quickjs-wasmfile-release-sync/wasm?url';
import { DefaultIntrinsics, newQuickJSWASMModuleFromVariant, newVariant } from 'quickjs-emscripten-core';
import type { QuickJSContext, QuickJSHandle, QuickJSRuntime, QuickJSWASMModule } from 'quickjs-emscripten-core';
import { gameValidationCode, validateGameConfig, validateGameState, validateGameView } from '../shared/game-schema.mjs';
import type { GamePayload, GameState, GameView } from '../shared/game-schema.mjs';

export type GameWorkerStatus = 'running' | 'paused' | 'finished';
export type GameWorkerCommand = { command: 'pause' | 'resume' | 'restart' | 'action'; action?: unknown };
export type GameWorkerRequest = ({ type: 'init'; payload: GamePayload } | { type: 'command'; value: GameWorkerCommand } | { type: 'dispose' }) & { requestId: number };
export type GameWorkerMessage =
  | { type: 'ready' | 'frame'; requestId?: number; view: GameView; state: GameState; status: GameWorkerStatus }
  | { type: 'error'; requestId?: number; message: string; diagnostic?: { phase: string; elapsedMs: number; cycles: number; interruption: string } };

type Timer = ReturnType<typeof setTimeout>;
type WorkerRuntimeOptions = {
  post(message: GameWorkerMessage): void;
  loadQuickJS?: () => Promise<QuickJSWASMModule>;
  setTimer?: (callback: () => void, delay: number) => Timer;
  clearTimer?: (timer: Timer) => void;
  now?: () => number;
};

/** Only trusted bridge code runs in this worker. Authored code runs inside WASM. */
export function createGameWorkerRuntime(options: WorkerRuntimeOptions) {
  const setTimer = options.setTimer ?? setTimeout;
  const clearTimer = options.clearTimer ?? clearTimeout;
  const now = options.now ?? (() => performance.now());
  const loadQuickJS = options.loadQuickJS ?? (() => newQuickJSWASMModuleFromVariant(newVariant(RELEASE_SYNC, { wasmLocation: wasmUrl })));
  let runtime: QuickJSRuntime | undefined;
  let context: QuickJSContext | undefined;
  let invoke: QuickJSHandle | undefined;
  let payload: GamePayload | undefined;
  let state: GameState | undefined;
  let view: GameView | undefined;
  let timer: Timer | undefined;
  let nextTickAt: number | undefined;
  let status: GameWorkerStatus = 'paused';
  let deadline = 0;
  let interruptCycles = 0;
  let invocationStarted = 0;
  let phase = 'loading';
  let interruption = '';
  let epoch = 0;
  let disposed = false;

  function stopClock() {
    if (timer !== undefined) clearTimer(timer);
    timer = undefined;
  }

  function release() {
    stopClock();
    nextTickAt = undefined;
    invoke?.dispose(); invoke = undefined;
    context?.dispose(); context = undefined;
    runtime?.dispose(); runtime = undefined;
  }

  function fail(error: unknown, requestId?: number) {
    release();
    epoch++;
    const raw = error instanceof Error ? error.message : String(error);
    const message = /interrupted|execution time/i.test(raw) ? 'This game took too long to respond. You can start it again.'
      : /out of memory/i.test(raw) ? 'This game exceeded its memory limit. You can start it again.'
        : raw.slice(0, 240) || 'This game could not run.';
    options.post({ type: 'error', requestId, message, diagnostic: { phase, elapsedMs: Math.round(performance.now() - invocationStarted), cycles: interruptCycles, interruption } });
  }

  function resultValue(result: ReturnType<QuickJSContext['evalCode']>) {
    if (!context) throw new Error('The game is not ready.');
    if (result.error) {
      const error = context.dump(result.error);
      result.error.dispose();
      throw new Error(typeof error?.message === 'string' ? error.message : 'This game could not run.');
    }
    return result.value;
  }

  function execute(command: string, action: unknown = null) {
    if (!context || !invoke || !payload) throw new Error('The game is not ready.');
    // A dense scene may occasionally trigger WASM garbage collection. Keep a
    // bounded allowance for that pause; the independent parent watchdog also
    // terminates a worker that cannot deliver its next frame or command reply.
    deadline = Date.now() + 250;
    interruptCycles = 0;
    invocationStarted = performance.now(); phase = command; interruption = '';
    const operation = context.newString(command);
    const serialized = context.newString(JSON.stringify(action));
    let result: QuickJSHandle | undefined;
    try {
      result = resultValue(context.callFunction(invoke, context.undefined, operation, serialized));
      const json = context.getString(result);
      if (json.length > 300_000) throw new Error('This game returned too much data.');
      const output = JSON.parse(json) as { state: GameState; view: GameView };
      validateGameState(output.state, payload.actor);
      validateGameView(output.view);
      state = output.state;
      view = output.view;
      if (view.finished) status = 'finished';
    } finally {
      operation.dispose(); serialized.dispose(); result?.dispose();
    }
  }

  function sendFrame(type: 'ready' | 'frame', requestId?: number) {
    if (state && view) options.post({ type, requestId, state, view, status });
  }

  function schedule() {
    stopClock();
    if (disposed || status !== 'running' || !payload) return;
    const interval = payload.config.tickMs ?? 50;
    nextTickAt ??= now() + interval;
    const scheduledAt = nextTickAt;
    // Keep small scheduling delays from slowing the simulation clock. After a
    // full missed interval, start a new deadline instead of replaying ticks.
    timer = setTimer(() => {
      timer = undefined;
      const started = now();
      try {
        execute('step', { type: 'tick', deltaMs: interval });
        sendFrame('frame');
        nextTickAt = scheduledAt + interval;
        if (nextTickAt <= started) nextTickAt = started + interval;
        schedule();
      } catch (error) { fail(error); }
    }, Math.max(0, nextTickAt - now()));
  }

  async function initialize(next: GamePayload, requestId: number) {
    if (payload || disposed) throw new Error('A game worker cannot change its published game.');
    validateGameConfig(next.config);
    if (typeof next.bundle !== 'string' || next.bundle.length > 300_000 || !next.bundle.trim()) throw new Error('Invalid published game code.');
    if (!next.actor || typeof next.actor.id !== 'string' || !next.actor.id || typeof next.actor.name !== 'string') throw new Error('Invalid game participant.');
    if (next.saved !== null) validateGameState(next.saved, next.actor);
    payload = next;
    const initializingEpoch = ++epoch;
    const quickjs = await loadQuickJS();
    if (disposed || initializingEpoch !== epoch) return;
    runtime = quickjs.newRuntime();
    runtime.setMemoryLimit(16 * 1024 * 1024);
    runtime.setMaxStackSize(512 * 1024);
    runtime.setInterruptHandler(() => {
      if (Date.now() > deadline) { interruption = 'deadline'; return true; }
      if (++interruptCycles > 6250) { interruption = 'instructions'; return true; }
      return false;
    });
    context = runtime.newContext({ intrinsics: { ...DefaultIntrinsics, Date: false, Promise: false } });
    deadline = Date.now() + 120;
    interruptCycles = 0;
    invocationStarted = performance.now(); phase = 'compile'; interruption = '';
    resultValue(context.evalCode(`
      Object.defineProperty(Object.getPrototypeOf(function () {}), 'constructor', {value: undefined, writable: false, configurable: false});
      globalThis.eval = undefined;
      globalThis.Function = undefined;
      ${next.bundle}
    `, 'published-game.js')).dispose();
    // Evaluate authored code separately so its functions cannot close over the
    // private state below. JSON detaches returned objects and retained aliases.
    // No native host APIs are ever exposed to the interpreter.
    invoke = resultValue(context.evalCode(`((authored) => {
      ${gameValidationCode}
      const parse = JSON.parse, stringify = JSON.stringify;
      const actor = Object.freeze(parse(${JSON.stringify(JSON.stringify(next.actor))}));
      const saved = parse(${JSON.stringify(JSON.stringify(next.saved))});
      if (!authored || ['init', 'step', 'view'].some(key => typeof authored[key] !== 'function')) throw new Error('This game is missing its controls.');
      let state;
      return (operation, serialized) => {
        if (operation === 'init' || operation === 'restart') {
          const initial = operation === 'restart' ? null : parse(stringify(saved));
          const before = stringify(initial);
          state = authored.init(initial, actor);
          if (stringify(initial) !== before) throw new Error('Game initialization must preserve saved progress.');
        } else if (operation === 'step') {
          state = authored.step(parse(stringify(state)), parse(serialized), actor);
        }
        validateGameState(state, actor);
        const before = stringify(state);
        state = parse(before);
        const rendering = parse(before);
        const view = authored.view(rendering, actor);
        // Serialize while still inside the bounded interpreter. The trusted
        // worker validates the resulting JSON scene before posting any frame;
        // traversing every drawing object twice in WASM would delay each tick.
        const outputJson = stringify({state, view});
        if (stringify(rendering) !== before || stringify(state) !== before) throw new Error('Drawing a game must preserve its progress.');
        return outputJson;
      };
    })(GameModule.game)`, 'game-controller.js'));
    status = 'running';
    execute('init');
    sendFrame('ready', requestId);
    schedule();
  }

  async function receive(message: GameWorkerRequest) {
    if (disposed) return;
    try {
      if (message.type === 'dispose') {
        disposed = true; epoch++; release(); return;
      }
      if (message.type === 'init') { await initialize(message.payload, message.requestId); return; }
      if (!context || !state) throw new Error('The game is not ready.');
      const { command, action } = message.value;
      stopClock();
      if (command === 'pause') { status = view?.finished ? 'finished' : 'paused'; nextTickAt = undefined; }
      else if (command === 'resume') { if (status !== 'running') nextTickAt = undefined; status = view?.finished ? 'finished' : 'running'; }
      else if (command === 'restart') { status = 'running'; nextTickAt = undefined; execute('restart'); }
      else if (command === 'action') {
        if (!action || typeof action !== 'object' || Array.isArray(action)) throw new Error('Invalid game control.');
        const type = (action as { type?: unknown }).type;
        if (typeof type !== 'string' || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(type) || type === 'tick' || JSON.stringify(action).length > 4096) throw new Error('Invalid game control.');
        if (status !== 'finished') execute('step', action);
      } else throw new Error('Unknown game control.');
      sendFrame('frame', message.requestId);
      schedule();
    } catch (error) { if (!disposed) fail(error, message.requestId); }
  }

  return { receive, dispose() { disposed = true; epoch++; release(); } };
}

// This module is also imported by isolated tests; only bootstrap in a worker.
if (typeof self !== 'undefined' && typeof document === 'undefined' && 'postMessage' in self) {
  const host = self as unknown as { postMessage(message: GameWorkerMessage): void; onmessage: ((event: MessageEvent<GameWorkerRequest>) => void) | null };
  const runtime = createGameWorkerRuntime({ post: message => host.postMessage(message) });
  host.onmessage = event => { void runtime.receive(event.data); };
}
