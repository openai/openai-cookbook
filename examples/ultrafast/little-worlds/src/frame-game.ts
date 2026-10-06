import type { GameShape, GameView } from '../shared/game-schema.mjs';

export type FrameGameStatus = 'idle' | 'loading' | 'running' | 'paused' | 'finished' | 'error';
export type FrameGameEvent = { type: 'frame'; view: GameView; intervalMs?: number; kind?: 'tick' | 'action' | 'reset' } | { type: 'status'; status: FrameGameStatus; message?: string };

/** Trusted canvas rendering and native controls. Serialized into the opaque frame. */
export function installFrameGame(options: {
  isActive: () => boolean;
  send: (type: string, data: Record<string, unknown>) => void | Promise<boolean>;
  validateView: (value: unknown) => GameView;
  authoredDisabled?: WeakMap<HTMLButtonElement | HTMLInputElement, boolean>;
}) {
  let gameId: string | undefined;
  let root: HTMLElement | undefined;
  let view: GameView | undefined;
  let status: FrameGameStatus = 'idle';
  let message = '';
  let animation: number | undefined;
  let intervalMs = 50;
  let disposed = false;
  let scanQueued = false;
  let pulseId = 0;
  const held = new Map<HTMLElement, { action: Record<string, unknown>; release: Record<string, unknown>; tokens: Set<string>; accepted?: Promise<boolean> }>();
  const inputs = new Map<string, HTMLElement>();
  const pulses = new Map<string, ReturnType<typeof setTimeout>>();
  const pointerClicks = new WeakMap<HTMLElement, number>();
  const initiallyDisabled = options.authoredDisabled ?? new WeakMap<HTMLButtonElement | HTMLInputElement, boolean>();
  const paths = new Map<string, { d: string; path: Path2D }>();
  type Motion = {
    type: GameShape['type'];
    position: { fromX: number; fromY: number; x: number; y: number; at: number; duration: number };
    rotation: { from: number; to: number; at: number; duration: number };
  };
  const motions = new Map<string, Motion>();
  const media = window.matchMedia?.('(prefers-reduced-motion: reduce)');
  const commands = ['start', 'pause', 'resume', 'restart'];
  const statusNames = ['idle', 'loading', 'running', 'paused', 'finished', 'error'];
  const labels: Record<FrameGameStatus, string> = {
    idle: 'Ready to play.', loading: 'Preparing game…', running: 'Playing. Use the arrow keys or direction buttons.',
    paused: 'Paused.', finished: 'Game finished.', error: 'The game could not continue. Try starting it again.',
  };
  const owned = (selector: string) => root ? [...root.querySelectorAll<HTMLElement>(selector)].filter(node => node.closest('[data-game]') === root) : [];
  const visible = (node: HTMLElement) => node.isConnected && !node.closest('[hidden],[inert],[aria-hidden="true"]') && node.getClientRects().length > 0 && getComputedStyle(node).visibility !== 'hidden';
  const available = () => !disposed && options.isActive() && !!root && visible(root) && !document.hidden;
  const stopDrawing = () => { if (animation !== undefined) cancelAnimationFrame(animation); animation = undefined; };
  function text(node: HTMLElement, value: string) { if (node.textContent !== value) node.textContent = value; }
  function bindings() {
    if (!root) return;
    if (root.dataset.gameStatus !== status) root.dataset.gameStatus = status;
    const ready = view ? 'true' : 'false';
    if (root.dataset.gameReady !== ready) root.dataset.gameReady = ready;
    if (!root.hasAttribute('tabindex')) root.setAttribute('tabindex', '0');
    for (const node of view ? owned('[data-game-value]') : []) {
      // Values are readouts, never form fields or action labels.
      if (node.matches('input,textarea,select,button,form')) continue;
      const value = view?.values?.[node.dataset.gameValue || ''];
      text(node, value === undefined ? '' : String(value));
    }
    for (const node of owned('[data-game-runtime-status]')) {
      if (node.matches('input,textarea,select,button,form')) continue;
      text(node, message || node.getAttribute(`data-status-${status}`) || labels[status]);
    }
    for (const node of owned('button[data-game-command],input[data-game-command],button[data-game-action],input[data-game-action]')) {
      if (!(node instanceof HTMLButtonElement || node instanceof HTMLInputElement)) continue;
      if (node.hasAttribute('data-game-release')) node.style.touchAction = 'none';
      // Game commands are local runtime controls even if a page wraps them in
      // a form. This also makes voice use click rather than form submission.
      if (node.type !== 'button') node.type = 'button';
      if (!initiallyDisabled.has(node)) initiallyDisabled.set(node, node.disabled);
      const command = node.dataset.gameCommand;
      let enabled = status === 'running' && !!actionFor(node) && (!node.hasAttribute('data-game-release') || !!actionFor(node, 'gameRelease'));
      if (command === 'start') enabled = status === 'idle' || status === 'error';
      if (command === 'pause') enabled = status === 'running';
      if (command === 'resume') enabled = status === 'paused';
      if (command === 'restart') enabled = status === 'running' || status === 'paused' || status === 'finished' || status === 'error';
      if (command && !commands.includes(command)) enabled = false;
      node.disabled = !!initiallyDisabled.get(node) || !options.isActive() || !gameId || !enabled;
      if (command === 'start') node.hidden = status !== 'idle' && status !== 'error';
      if (command === 'pause') node.hidden = status !== 'running';
      if (command === 'resume') node.hidden = status !== 'paused';
      if (command === 'restart') node.hidden = status === 'idle' || status === 'loading';
    }
  }
  function pause() {
    stopDrawing();
    releaseInputs();
    if (!gameId || status !== 'running') return;
    status = 'paused';
    message = '';
    motions.clear();
    bindings();
    if (options.isActive()) options.send('game.command', { gameId, command: 'pause' });
  }
  const progressAt = (at: number, duration: number, now: number) => duration ? Math.min(1, Math.max(0, (now - at) / duration)) : 1;
  const angleChange = (from: number, to: number) => ((to - from) % 360 + 540) % 360 - 180;
  function poseAt(shape: GameShape, now: number) {
    const motion = motions.get(shape.id);
    if (!motion || media?.matches || status !== 'running') return { x: shape.x ?? 0, y: shape.y ?? 0, rotation: shape.rotation ?? 0, moving: false };
    const p = motion.position, r = motion.rotation;
    const translation = progressAt(p.at, p.duration, now), rotation = progressAt(r.at, r.duration, now);
    return {
      x: p.fromX + (p.x - p.fromX) * translation, y: p.fromY + (p.y - p.fromY) * translation,
      rotation: r.from + angleChange(r.from, r.to) * rotation,
      moving: translation < 1 && (p.fromX !== p.x || p.fromY !== p.y) || rotation < 1 && angleChange(r.from, r.to) !== 0,
    };
  }
  function updateMotions(next: GameView, now: number, kind: 'tick' | 'action' | 'reset' = 'tick') {
    if (kind === 'reset' || !view || view.width !== next.width || view.height !== next.height || view.background !== next.background) motions.clear();
    const ids = new Set(next.objects.map(shape => shape.id));
    for (const id of motions.keys()) if (!ids.has(id)) motions.delete(id);
    for (const shape of next.objects) {
      const x = shape.x ?? 0, y = shape.y ?? 0, rotation = shape.rotation ?? 0;
      const current = motions.get(shape.id);
      if (!current || current.type !== shape.type) {
        motions.set(shape.id, { type: shape.type, position: { fromX: x, fromY: y, x, y, at: now, duration: 0 }, rotation: { from: rotation, to: rotation, at: now, duration: 0 } });
        continue;
      }
      if (kind === 'action') {
        // Controls change their targets immediately without advancing game
        // time. Shift the whole path so eyes, mouth and body stay aligned.
        current.position.fromX += x - current.position.x;
        current.position.fromY += y - current.position.y;
        current.position.x = x; current.position.y = y;
        current.rotation.from += angleChange(current.rotation.to, rotation);
        current.rotation.to = rotation;
        continue;
      }
      const pose = poseAt(shape, now);
      // Input replies often contain the same positions as the preceding tick.
      // Keep each transform's clock, including when an eye or rotation changes.
      if (current.position.x !== x || current.position.y !== y) current.position = {
        fromX: pose.x, fromY: pose.y, x, y, at: now,
        duration: intervalMs,
      };
      if (current.rotation.to !== rotation) current.rotation = {
        from: pose.rotation, to: rotation, at: now,
        duration: intervalMs,
      };
    }
  }
  function drawObject(context: CanvasRenderingContext2D, shape: GameShape, pose: ReturnType<typeof poseAt>) {
    const { x, y, rotation } = pose;
    context.save();
    try {
      context.translate(x, y);
      if (rotation) context.rotate(rotation * Math.PI / 180);
      const fill = shape.fill ?? (shape.stroke ? undefined : '#253428');
      const stroke = shape.stroke;
      if (fill && fill !== 'none') context.fillStyle = fill;
      if (stroke && stroke !== 'none') context.strokeStyle = stroke;
      const lineWidth = shape.lineWidth ?? 1;
      if (lineWidth > 0) context.lineWidth = lineWidth;
      if (shape.type === 'text') {
        context.font = `${shape.fontSize ?? 16}px system-ui, sans-serif`;
        context.textAlign = shape.align ?? 'left';
        context.textBaseline = 'middle';
        if (fill && fill !== 'none') context.fillText(shape.text, 0, 0);
        if (stroke && stroke !== 'none' && lineWidth > 0) context.strokeText(shape.text, 0, 0);
        return;
      }
      let path: Path2D | undefined;
      if (shape.type === 'path') {
        let cached = paths.get(shape.id);
        if (!cached || cached.d !== shape.d) {
          cached = { d: shape.d, path: new Path2D(shape.d) };
          paths.set(shape.id, cached);
        }
        path = cached.path;
      } else {
        context.beginPath();
        if (shape.type === 'circle') context.arc(0, 0, shape.radius, 0, Math.PI * 2);
        else if (shape.radius && context.roundRect) context.roundRect(0, 0, shape.width, shape.height, Math.min(shape.radius, shape.width / 2, shape.height / 2));
        else context.rect(0, 0, shape.width, shape.height);
      }
      if (fill && fill !== 'none') { if (path) context.fill(path); else context.fill(); }
      if (stroke && stroke !== 'none' && lineWidth > 0) { if (path) context.stroke(path); else context.stroke(); }
    } finally { context.restore(); }
  }
  function draw(now: number) {
    animation = undefined;
    if (!view || !available()) { if (status === 'running') pause(); return; }
    let moving = false;
    for (const canvas of owned('canvas[data-game-canvas]').slice(0, 4)) {
      if (!(canvas instanceof HTMLCanvasElement)) continue;
      if (canvas.width !== view.width) canvas.width = view.width;
      if (canvas.height !== view.height) canvas.height = view.height;
      const context = canvas.getContext('2d');
      if (!context) continue;
      context.clearRect(0, 0, view.width, view.height);
      if (view.background && view.background !== 'none') { context.fillStyle = view.background; context.fillRect(0, 0, view.width, view.height); }
      try {
        for (const shape of view.objects) {
          const pose = poseAt(shape, now);
          moving ||= pose.moving;
          drawObject(context, shape, pose);
        }
      } catch {
        pause();
        status = 'error'; message = 'This game could not draw its current scene. Try starting it again.'; bindings();
        return;
      }
    }
    if (moving && status === 'running') animation = requestAnimationFrame(draw);
  }
  const schedule = () => { if (animation === undefined && view && available()) animation = requestAnimationFrame(draw); };
  function reapply() {
    if (disposed) return;
    const content = document.getElementById('living-space-content');
    const next = gameId ? [...content?.querySelectorAll<HTMLElement>('[data-game]') || []].find(node => node.dataset.game === gameId && !node.closest('[data-service]')) : undefined;
    const replaced = root !== next;
    if (replaced) releaseInputs();
    root = next;
    if (!root) { pause(); return; }
    bindings();
    if (!available()) { pause(); return; }
    // A normal same-revision HTML patch can clear a canvas or replace its node.
    // Keep the current local scene; never replace the document for a game tick.
    if (replaced && view) updateMotions(view, performance.now(), 'reset');
    schedule();
  }
  function configure(value: unknown) {
    const id = value && typeof value === 'object' ? (value as { id?: unknown }).id : undefined;
    const next = typeof id === 'string' && /^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(id) && !['constructor', 'prototype', '__proto__'].includes(id) ? id : undefined;
    if (gameId !== next) {
      releaseInputs();
      stopDrawing(); gameId = undefined; status = 'idle'; message = ''; view = undefined; intervalMs = 50; motions.clear(); paths.clear(); bindings();
      gameId = next;
    }
    reapply();
  }
  function receive(id: unknown, event: unknown) {
    if (disposed || !options.isActive() || !gameId || id !== gameId || !event || typeof event !== 'object') return;
    const data = event as { type?: unknown; view?: unknown; status?: unknown; message?: unknown; intervalMs?: unknown; kind?: unknown };
    if (data.type === 'status' && typeof data.status === 'string' && statusNames.includes(data.status)) {
      if (data.status !== 'running') releaseInputs();
      status = data.status as FrameGameStatus;
      message = typeof data.message === 'string' ? data.message.slice(0, 500) : '';
      if (status !== 'running') { stopDrawing(); motions.clear(); }
      if (status === 'running' && !available()) { pause(); return; }
      reapply();
    } else if (data.type === 'frame') {
      let next: GameView;
      try { next = options.validateView(data.view); }
      catch { pause(); status = 'error'; message = 'This game returned an invalid scene. Try starting it again.'; bindings(); return; }
      // The controller supplies the published cadence. Input replies and
      // delivery jitter must never become a guessed animation interval.
      if (typeof data.intervalMs === 'number' && Number.isInteger(data.intervalMs) && data.intervalMs >= 16 && data.intervalMs <= 100) intervalMs = data.intervalMs;
      const now = performance.now();
      updateMotions(next, now, data.kind === 'action' || data.kind === 'reset' ? data.kind : 'tick');
      view = next;
      const pathIds = new Set(next.objects.filter(shape => shape.type === 'path').map(shape => shape.id));
      for (const key of paths.keys()) if (!pathIds.has(key)) paths.delete(key);
      reapply();
    }
  }
  function actionFor(control: HTMLElement, attribute: 'gameAction' | 'gameRelease' = 'gameAction'): Record<string, unknown> | undefined {
    const raw = control.dataset[attribute];
    if (!raw || raw.length > 4096) return;
    try {
      const value = JSON.parse(raw);
      if (!value || typeof value !== 'object' || Array.isArray(value) || typeof value.type !== 'string' || !/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(value.type) || value.type === 'tick') return;
      const safe = (item: unknown, depth = 0): boolean => {
        if (depth > 12) return false;
        if (item === null || typeof item === 'string' || typeof item === 'boolean') return true;
        if (typeof item === 'number') return Number.isFinite(item);
        if (!item || typeof item !== 'object') return false;
        return Object.entries(item).every(([key, child]) => !['constructor', 'prototype', '__proto__'].includes(key) && safe(child, depth + 1));
      };
      return safe(value) ? value : undefined;
    } catch { return; }
  }
  function sendAction(action: Record<string, unknown>, release = false): Promise<boolean> | undefined {
    if (gameId && !disposed && options.isActive() && (status === 'running' || release && status === 'paused')) {
      return options.send('game.command', { gameId, command: 'action', action, ...(release ? { release: true } : {}) }) || undefined;
    }
  }
  function releaseInput(token: string, reassert = true) {
    const timeout = pulses.get(token);
    if (timeout !== undefined) { clearTimeout(timeout); pulses.delete(token); }
    const control = inputs.get(token);
    if (!control) return;
    inputs.delete(token);
    const press = held.get(control);
    if (!press) return;
    press.tokens.delete(token);
    if (press.tokens.size) return;
    held.delete(control);
    sendAction(press.release, true);
    // Axis-based games may share a neutral release action between opposing
    // directions. Reassert remaining physical holds so the other key wins.
    if (reassert) for (const other of held.values()) sendAction(other.action);
  }
  function releaseInputs() {
    for (const token of [...inputs.keys()]) releaseInput(token, false);
  }
  function holdInput(control: HTMLElement, token: string) {
    if (inputs.has(token)) return true;
    const release = actionFor(control, 'gameRelease');
    const action = actionFor(control);
    if (!release || !action || control.dataset.gameCommand) return false;
    if (!held.has(control)) {
      let accepted: Promise<boolean> | undefined;
      if (!activate(control, result => { accepted = result; })) return false;
      held.set(control, { action, release, tokens: new Set(), accepted });
    }
    held.get(control)!.tokens.add(token);
    inputs.set(token, control);
    return true;
  }
  function activate(control: HTMLElement, onAccepted?: (result: Promise<boolean> | undefined) => void) {
    if (!gameId || !available() || control.closest('[data-game]') !== root || !visible(control) || control.matches(':disabled,[aria-disabled="true"]')) return false;
    const command = control.dataset.gameCommand;
    if (command && commands.includes(command)) {
      if ((command === 'start' && status !== 'idle' && status !== 'error') || (command === 'resume' && status !== 'paused') || (command === 'pause' && status !== 'running') || (command === 'restart' && (status === 'idle' || status === 'loading'))) return false;
      if (command === 'start' || command === 'resume' || command === 'restart') root?.focus({ preventScroll: true });
      if (command === 'pause' || command === 'restart') releaseInputs();
      options.send('game.command', { gameId, command });
      return true;
    }
    if (!command && status === 'running') {
      const action = actionFor(control);
      if (action && (!control.hasAttribute('data-game-release') || actionFor(control, 'gameRelease'))) {
        const accepted = sendAction(action);
        onAccepted?.(accepted);
        return true;
      }
    }
    return false;
  }
  const click = (event: MouseEvent) => {
    if (event.defaultPrevented || !(event.target instanceof Element)) return;
    const control = event.target.closest<HTMLElement>('button[data-game-command],input[data-game-command],button[data-game-action],input[data-game-action]');
    if (!control || !root || control.closest('[data-game]') !== root) return;
    // Do not submit a surrounding form or also invoke a persistent data-action.
    event.preventDefault();
    event.stopImmediatePropagation();
    // Pointer presses already dispatch on down/up. The compatibility click
    // must not start a second action. Programmatic/voice clicks have detail 0.
    if (event.detail > 0 && (pointerClicks.get(control) ?? -Infinity) >= performance.now()) return;
    if (!control.hasAttribute('data-game-release')) { activate(control); return; }
    const token = `pulse:${++pulseId}`;
    if (holdInput(control, token)) {
      const schedule = () => { if (inputs.has(token)) pulses.set(token, setTimeout(() => releaseInput(token), 150)); };
      const accepted = held.get(control)?.accepted;
      // Wait for worker admission so a busy worker still gives a spoken tap
      // real simulation time between its press and release.
      if (accepted) void accepted.then(ok => { if (ok) schedule(); else releaseInput(token); }, () => releaseInput(token));
      else schedule();
    }
  };
  const keydown = (event: KeyboardEvent) => {
    if (event.defaultPrevented || event.altKey || event.ctrlKey || event.metaKey || event.isComposing || !(event.target instanceof Element) || !root || !available() || status !== 'running') return;
    const editable = event.target.closest('[contenteditable]');
    if (event.target.closest('[data-game]') !== root || event.target.closest('input,textarea,select') || editable && editable.getAttribute('contenteditable') !== 'false') return;
    const control = owned('button[data-game-action][data-game-keys],input[data-game-action][data-game-keys]').find(node => {
      const keys = (node.dataset.gameKeys || '').split(/\s+/);
      return (keys.includes(event.key) || event.key === ' ' && keys.includes('Space')) && !node.matches(':disabled,[aria-disabled="true"]');
    });
    if (!control) return;
    const accepted = control.hasAttribute('data-game-release') ? holdInput(control, `key:${event.code || event.key}`) : activate(control);
    if (accepted) event.preventDefault();
  };
  const keyup = (event: KeyboardEvent) => {
    const token = `key:${event.code || event.key}`;
    if (!inputs.has(token)) return;
    event.preventDefault();
    releaseInput(token);
  };
  const pointerdown = (event: PointerEvent) => {
    if (event.defaultPrevented || event.button !== 0 || !(event.target instanceof Element)) return;
    const control = event.target.closest<HTMLElement>('button[data-game-release],input[data-game-release]');
    if (!control || !holdInput(control, `pointer:${event.pointerId}`)) return;
    event.preventDefault(); event.stopImmediatePropagation();
    pointerClicks.set(control, performance.now() + 800);
    root?.focus({ preventScroll: true });
    try { control.setPointerCapture(event.pointerId); } catch { /* Capture is optional on older browsers. */ }
  };
  const pointerup = (event: PointerEvent) => {
    const token = `pointer:${event.pointerId}`;
    const control = inputs.get(token);
    if (!control) return;
    event.preventDefault(); event.stopImmediatePropagation();
    pointerClicks.set(control, performance.now() + 800);
    releaseInput(token);
  };
  const blur = () => pause();
  const visibility = () => { if (document.hidden) pause(); };
  const focusout = (event: FocusEvent) => { if (root && event.target instanceof Element && event.target.closest('[data-game]') === root && event.relatedTarget instanceof Element && event.relatedTarget.closest('[data-game]') !== root) pause(); };
  const mediaChange = () => { if (view) updateMotions(view, performance.now(), 'reset'); schedule(); };
  document.addEventListener('click', click, true);
  document.addEventListener('keydown', keydown);
  document.addEventListener('keyup', keyup);
  document.addEventListener('pointerdown', pointerdown, true);
  document.addEventListener('pointerup', pointerup, true);
  document.addEventListener('pointercancel', pointerup, true);
  document.addEventListener('lostpointercapture', pointerup, true);
  document.addEventListener('visibilitychange', visibility);
  document.addEventListener('focusout', focusout);
  window.addEventListener('blur', blur);
  window.addEventListener('pagehide', blur);
  media?.addEventListener?.('change', mediaChange);
  const observer = typeof MutationObserver === 'undefined' ? undefined : new MutationObserver(() => {
    if (scanQueued || disposed || !gameId) return;
    scanQueued = true;
    queueMicrotask(() => { scanQueued = false; reapply(); });
  });
  const content = document.getElementById('living-space-content');
  if (content) observer?.observe(content, { childList: true, subtree: true, attributes: true, attributeFilter: ['data-game'] });
  function cancel() { releaseInputs(); stopDrawing(); status = 'idle'; message = ''; motions.clear(); bindings(); }
  function dispose() {
    releaseInputs();
    disposed = true; stopDrawing(); observer?.disconnect(); paths.clear(); motions.clear();
    document.removeEventListener('click', click, true);
    document.removeEventListener('keydown', keydown);
    document.removeEventListener('keyup', keyup);
    document.removeEventListener('pointerdown', pointerdown, true);
    document.removeEventListener('pointerup', pointerup, true);
    document.removeEventListener('pointercancel', pointerup, true);
    document.removeEventListener('lostpointercapture', pointerup, true);
    document.removeEventListener('visibilitychange', visibility);
    document.removeEventListener('focusout', focusout);
    window.removeEventListener('blur', blur); window.removeEventListener('pagehide', blur);
    media?.removeEventListener?.('change', mediaChange);
  }
  return { configure, receive, reapply, cancel, dispose };
}
