import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { build } from 'esbuild';
import { gameValidationCode } from '../shared/game-schema.mjs';

async function load(path) {
  const result = await build({ entryPoints: [new URL(path, import.meta.url).pathname], bundle: true, format: 'esm', write: false, minify: true, target: 'es2020' });
  return import(`data:text/javascript;base64,${Buffer.from(result.outputFiles[0].text).toString('base64')}`);
}
const { installFrameGame } = await load('../src/frame-game.ts');
const { frameBridgeScript } = await load('../src/frame-service-bridge.ts');

function fixture({ reducedMotion = false, active = true, bridge = false, disabledLeft = false, heldInputs = false, gameIds } = {}) {
  const listeners = { document: new Map(), window: new Map() }, sent = [], frames = new Map(), pathData = [], timers = new Map();
  let nextFrame = 0, nextTimer = 0, now = 0, observer, rootAvailable = true, document;
  const add = (where, type, handler, capture) => {
    if (!listeners[where].has(type)) listeners[where].set(type, []);
    listeners[where].get(type).push({ handler, capture: !!capture });
  };
  const remove = (where, type, handler) => listeners[where].set(type, (listeners[where].get(type) || []).filter(item => item.handler !== handler));
  class Element {
    constructor(tag = 'div', attributes = {}, text = '') {
      this.tagName = tag.toUpperCase(); this.attributes = {}; this.dataset = {}; this.children = []; this._text = text;
      this.textWrites = 0; this.isConnected = true; this.disabled = false; this.hidden = false; this.style = {}; this.display = 'block'; this.visibility = 'visible';
      this.scrollHeight = this.clientHeight = 0; this.scrollWidth = this.clientWidth = 0;
      for (const [name, value] of Object.entries(attributes)) this.setAttribute(name, value);
    }
    setAttribute(name, value) {
      this.attributes[name] = String(value);
      if (name.startsWith('data-')) this.dataset[name.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = String(value);
      if (['type', 'name', 'id'].includes(name)) this[name] = String(value);
      if (name === 'hidden') this.hidden = true;
    }
    getAttribute(name) { return this.attributes[name] ?? null; }
    hasAttribute(name) { return name === 'hidden' ? this.hidden : Object.hasOwn(this.attributes, name); }
    removeAttribute(name) { delete this.attributes[name]; if (name === 'hidden') this.hidden = false; }
    append(...children) { for (const child of children) { child.parent = this; this.children.push(child); } return this; }
    matches(selector) {
      return selector.split(',').some(part => {
        part = part.trim();
        if (part === ':disabled') return this.disabled;
        const tag = part.match(/^[a-z0-9-]+/i)?.[0];
        if (tag && this.tagName.toLowerCase() !== tag) return false;
        const attributes = [...part.matchAll(/\[([^\]=]+)(?:="([^"]*)")?\]/g)];
        return (tag || attributes.length) && attributes.every(([, name, value]) => this.hasAttribute(name) && (value === undefined || this.getAttribute(name) === value));
      });
    }
    closest(selector) { for (let node = this; node; node = node.parent) if (node.matches(selector)) return node; return null; }
    querySelectorAll(selector) { return this.children.flatMap(child => [...(child.matches(selector) ? [child] : []), ...child.querySelectorAll(selector)]); }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    contains(other) { for (let node = other; node; node = node.parent) if (node === this) return true; return false; }
    getClientRects() { for (let node = this; node; node = node.parent) if (!node.isConnected || node.display === 'none' || node.hidden) return []; return [{ width: 300, height: 300 }]; }
    focus() { document.activeElement = this; }
    setPointerCapture(id) { this.capturedPointer = id; }
    get textContent() { return this._text; }
    set textContent(value) { this._text = String(value); this.textWrites++; }
    get innerText() { return [this._text, ...this.children.filter(child => !child.hidden).map(child => child.innerText)].join(' '); }
    get labels() { return []; }
    get form() { return this.closest('form'); }
    click() { if (!this.disabled) fire('document', 'click', this); }
    scrollIntoView() {}
  }
  class HTMLElement extends Element {}
  class HTMLButtonElement extends HTMLElement { constructor(attributes = {}, text = '') { super('button', { type: 'button', ...attributes }, text); } }
  class HTMLInputElement extends HTMLElement { constructor(attributes = {}) { super('input', attributes); this.type ||= 'text'; this.value = ''; this.readOnly = false; this.maxLength = -1; } }
  class HTMLTextAreaElement extends HTMLElement {}
  class HTMLSelectElement extends HTMLElement {}
  class HTMLFormElement extends HTMLElement {}
  class HTMLAnchorElement extends HTMLElement {}
  class CanvasContext {
    constructor() { this.calls = []; }
  }
  for (const method of ['save', 'restore', 'translate', 'rotate', 'beginPath', 'arc', 'roundRect', 'rect', 'fill', 'stroke', 'fillText', 'strokeText', 'clearRect', 'fillRect']) {
    CanvasContext.prototype[method] = function (...args) { this.calls.push([method, ...args.map(value => value?.d ?? value)]); };
  }
  class HTMLCanvasElement extends HTMLElement {
    constructor() { super('canvas', { 'data-game-canvas': '', 'aria-label': 'Maze' }); this.width = 300; this.height = 150; this.context = new CanvasContext(); }
    getContext() { return this.context; }
  }
  class Event {
    constructor(type, options = {}) { this.type = type; Object.assign(this, options); this.defaultPrevented = false; }
    preventDefault() { this.defaultPrevented = true; }
    stopImmediatePropagation() { this.stopped = true; }
  }
  const content = new HTMLElement('div', { id: 'living-space-content' });
  const buildRoot = (id = 'maze') => {
    const root = new HTMLElement('section', { 'data-game': id, 'aria-label': `${id} game` });
    const canvas = new HTMLCanvasElement(), score = new HTMLElement('span', { 'data-game-value': 'score' });
    const status = new HTMLElement('p', { 'data-game-runtime-status': '' });
    const start = new HTMLButtonElement({ 'data-game-command': 'start' }, 'Start game');
    const pause = new HTMLButtonElement({ 'data-game-command': 'pause' }, 'Pause game');
    const resume = new HTMLButtonElement({ 'data-game-command': 'resume' }, 'Resume game');
    const restart = new HTMLButtonElement({ 'data-game-command': 'restart' }, 'New game');
    const left = new HTMLButtonElement({ 'data-game-action': '{"type":"direction","direction":"left"}', 'data-game-keys': 'ArrowLeft a A' }, 'Move left');
    const right = new HTMLButtonElement({ 'data-game-action': '{"type":"direction","direction":"right"}', 'data-game-keys': 'ArrowRight d D' }, 'Move right');
    if (heldInputs) for (const [node, axis] of [[left, -1], [right, 1]]) {
      node.setAttribute('data-game-action', JSON.stringify({type:'move',axis}));
      node.setAttribute('data-game-release', '{"type":"move","axis":0}');
    }
    const input = new HTMLInputElement({ 'aria-label': 'Player name' });
    root.append(canvas, score, status, start, pause, resume, restart, left, right, input);
    return { root, canvas, score, status, start, pause, resume, restart, left, right, input };
  };
  const nodes = buildRoot();
  nodes.left.disabled = disabledLeft;
  const sibling = new HTMLElement('section', {}, 'An unrelated tile');
  content.append(nodes.root, sibling);
  const allGames = new Map([['maze', nodes]]);
  for (const id of gameIds || []) if (!allGames.has(id)) { const tile = buildRoot(id); allGames.set(id, tile); content.append(tile.root); }
  document = {
    hidden: false, activeElement: null,
    getElementById: id => rootAvailable && id === content.id ? content : null,
    querySelectorAll: selector => content.querySelectorAll(selector),
    addEventListener: (...args) => add('document', ...args), removeEventListener: (...args) => remove('document', ...args),
    documentElement: { style: { setProperty() {} }, clientHeight: 0, scrollTop: 0, scrollLeft: 0 }, body: { scrollHeight: 100, getBoundingClientRect: () => ({ height: 100 }) },
  };
  const media = { matches: reducedMotion, addEventListener(type, fn) { this.change = fn; }, removeEventListener() { this.change = undefined; } };
  const parent = { postMessage: message => sent.push(JSON.parse(JSON.stringify(message))) };
  const globals = {
    document, parent, Element, HTMLElement, HTMLButtonElement, HTMLInputElement, HTMLCanvasElement, HTMLTextAreaElement, HTMLSelectElement, HTMLFormElement, HTMLAnchorElement,
    HTMLTemplateElement: class extends HTMLElement {}, Event, URL, queueMicrotask,
    getComputedStyle: node => ({ display: node.display, visibility: node.visibility }),
    window: { innerHeight: 0, matchMedia: () => media, addEventListener: (...args) => add('window', ...args), removeEventListener: (...args) => remove('window', ...args) },
    performance: { now: () => now }, requestAnimationFrame: fn => { frames.set(++nextFrame, fn); return nextFrame; }, cancelAnimationFrame: id => frames.delete(id),
    setTimeout: (fn, delay) => { timers.set(++nextTimer, {fn,due:now+delay}); return nextTimer; }, clearTimeout: id => timers.delete(id),
    MutationObserver: class { constructor(fn) { observer = fn; } observe() {} disconnect() { observer = undefined; } },
    ResizeObserver: class { observe() {} },
    Path2D: class { constructor(d) { this.d = d; pathData.push(d); } },
    send: (type, data) => { sent.push(JSON.parse(JSON.stringify({ type, ...data }))); }, isActive: () => active,
  };
  const context = vm.createContext(globals);
  if (bridge) {
    rootAvailable = false;
    vm.runInContext(frameBridgeScript('game-key', 'http://127.0.0.1:5173'), context);
    rootAvailable = true;
    host('render', { version: 1, html: '' }); host('service.configure', { active, capabilities: [] }); host('game.configure', gameIds ? { configs: gameIds.map(id => ({ id })) } : { config: { id: 'maze' } });
  } else vm.runInContext(`${gameValidationCode}\nconst game = (${installFrameGame.toString()})({ isActive, send, validateView: validateGameView }); game.configure({id: 'maze'});`, context);
  function fire(where, type, target = nodes.root, extra = {}) {
    const event = new Event(type, { target, ...extra });
    const handlers = [...listeners[where].get(type) || []].sort((a, b) => Number(b.capture) - Number(a.capture));
    for (const { handler } of handlers) { handler(event); if (event.stopped) break; }
    return event;
  }
  function host(type, data = {}, overrides = {}) {
    const payload = JSON.stringify({ channel: 'living-space-host', bridgeKey: 'game-key', type, ...data });
    context.payload = payload;
    const dataInContext = vm.runInContext('JSON.parse(payload)', context);
    return fire('window', 'message', undefined, { source: parent, origin: 'http://127.0.0.1:5173', data: dataInContext, ...overrides });
  }
  function receive(event, id = 'maze') {
    if (bridge) return host('game.event', { gameId: id, event });
    context.payload = JSON.stringify(event); context.gameId = id;
    return vm.runInContext('game.receive(gameId, JSON.parse(payload))', context);
  }
  function call(method, argument) {
    context.payload = JSON.stringify(argument ?? null);
    return vm.runInContext(`game.${method}(JSON.parse(payload))`, context);
  }
  return {
    ...nodes, content, sibling, sent, pathData, document, media, host, receive, call, buildRoot, allGames,
    fire: (type, target, extra) => fire('document', type, target, extra), windowEvent: (type, extra) => fire('window', type, undefined, extra),
    animate: time => { now = time; const callbacks = [...frames.values()]; frames.clear(); for (const callback of callbacks) callback(time); },
    time: time => { now = time; }, scheduled: () => frames.size, mutate: () => observer?.(),
    advance: milliseconds => { const end = now + milliseconds; for (;;) { const next = [...timers].filter(([,job]) => job.due <= end).sort((a,b) => a[1].due-b[1].due)[0]; if (!next) break; now=next[1].due; timers.delete(next[0]); next[1].fn(); } now=end; },
    timers: () => timers.size,
    setActive: value => { active = value; },
  };
}
const scene = (x = 10, extra = {}) => ({ width: 260, height: 260, background: '#102432', objects: [{ id: 'player', type: 'circle', x, y: 20, radius: 8, fill: '#ffc84c' }], values: { score: 0 }, ...extra });
const playing = f => f.receive({ type: 'status', status: 'running' });
const commands = f => f.sent.filter(item => item.type === 'game.command');

test('games remain idle until an explicit native start, with stateful accessible controls', () => {
  const f = fixture();
  f.score.textContent = '220'; f.call('reapply');
  assert.equal(f.score.textContent, '220', 'saved authored progress remains visible before the lazy runtime starts');
  f.start.type = 'submit'; f.call('reapply');
  assert.equal(f.start.type, 'button', 'a game control never submits a surrounding form, including through voice');
  assert.equal(f.scheduled(), 0); assert.equal(commands(f).length, 0);
  assert.equal(f.start.disabled, false); assert.equal(f.pause.hidden, true); assert.equal(f.resume.hidden, true); assert.equal(f.left.disabled, true);
  assert.equal(f.status.textContent, 'Ready to play.');
  assert.equal(f.fire('click', f.start).defaultPrevented, true);
  assert.deepEqual(commands(f), [{ type: 'game.command', gameId: 'maze', command: 'start' }]);
  assert.equal(f.document.activeElement, f.root);
  f.receive({ type: 'status', status: 'loading' });
  assert.equal(f.start.hidden, true); assert.equal(f.left.disabled, true);
  playing(f); assert.equal(f.pause.hidden, false); assert.equal(f.left.disabled, false); assert.equal(f.restart.hidden, false);
  f.receive({ type: 'status', status: 'paused' });
  assert.equal(f.pause.hidden, true); assert.equal(f.resume.hidden, false);
  f.fire('click', f.resume); assert.equal(commands(f).at(-1).command, 'resume');
  f.receive({ type: 'status', status: 'finished' });
  assert.equal(f.left.disabled, true); assert.equal(f.restart.disabled, false);
  f.fire('click', f.restart); assert.equal(commands(f).at(-1).command, 'restart');
});

test('click, touch activation, arrow keys and WASD share the same bounded semantic action', () => {
  const f = fixture(); playing(f);
  f.fire('click', f.left);
  f.fire('click', f.left, { pointerType: 'touch' });
  assert.equal(f.fire('keydown', f.root, { key: 'ArrowLeft' }).defaultPrevented, true);
  assert.equal(f.fire('keydown', f.root, { key: 'A' }).defaultPrevented, true);
  assert.equal(f.fire('keydown', f.input, { key: 'ArrowLeft' }).defaultPrevented, false);
  assert.equal(f.fire('keydown', f.sibling, { key: 'ArrowLeft' }).defaultPrevented, false);
  assert.equal(f.fire('keydown', f.root, { key: 'ArrowLeft', ctrlKey: true }).defaultPrevented, false);
  assert.equal(f.fire('keydown', f.root, { key: 'ArrowLeft', repeat: true }).defaultPrevented, true);
  assert.equal(f.fire('keydown', f.root, { key: 'PageDown' }).defaultPrevented, false);
  assert.equal(commands(f).length, 5);
  assert.deepEqual(commands(f).map(item => item.action), Array.from({ length: 5 }, () => ({ type: 'direction', direction: 'left' })));
  f.left.disabled = true;
  f.fire('click', f.left); f.fire('keydown', f.root, { key: 'ArrowLeft' });
  assert.equal(commands(f).length, 5);
  const authoredDisabled = fixture({ disabledLeft: true }); playing(authoredDisabled); authoredDisabled.call('reapply');
  assert.equal(authoredDisabled.left.disabled, true, 'authored disabled is preserved across host lifecycle updates');
  authoredDisabled.fire('click', authoredDisabled.left);
  assert.equal(commands(authoredDisabled).length, 0);
});

test('held keyboard input presses once, releases outside the root, and shares physical key sources', () => {
  const f = fixture({heldInputs:true}); playing(f);
  f.fire('keydown', f.root, {key:'ArrowLeft',code:'ArrowLeft'});
  f.fire('keydown', f.root, {key:'ArrowLeft',code:'ArrowLeft',repeat:true});
  f.fire('keydown', f.root, {key:'A',code:'KeyA'});
  assert.equal(commands(f).length, 1);
  f.fire('keyup', f.sibling, {key:'ArrowLeft',code:'ArrowLeft'});
  assert.equal(commands(f).length, 1, 'second physical key keeps the same control held');
  f.fire('keyup', f.sibling, {key:'a',code:'KeyA'});
  assert.deepEqual(commands(f).map(item => item.action.axis), [-1,0]);
  assert.equal(commands(f).at(-1).release, true);
  f.left.setAttribute('data-game-keys','Space');
  assert.equal(f.fire('keydown',f.root,{key:' ',code:'Space'}).defaultPrevented,true);
  f.fire('keyup',f.root,{key:' ',code:'Space'});
  assert.deepEqual(commands(f).map(item => item.action.axis),[-1,0,-1,0]);
});

test('held pointer input releases after capture cancellation without compatibility-click duplication', () => {
  const f = fixture({heldInputs:true}); playing(f);
  assert.equal(f.fire('pointerdown', f.left, {button:0,pointerId:7,pointerType:'touch'}).defaultPrevented, true);
  assert.equal(f.left.capturedPointer, 7);
  f.fire('pointerup', f.sibling, {pointerId:7,pointerType:'touch'});
  f.fire('click', f.left, {detail:1,pointerType:'touch'});
  assert.deepEqual(commands(f).map(item => item.action.axis), [-1,0]);
  f.fire('pointerdown', f.right, {button:0,pointerId:8,pointerType:'touch'});
  f.fire('lostpointercapture', f.sibling, {pointerId:8});
  f.fire('pointercancel', f.sibling, {pointerId:8});
  assert.deepEqual(commands(f).map(item => item.action.axis), [-1,0,1,0]);
});

test('overlapping pointer and keyboard holds do not release early and opposing keys restore the remaining axis', () => {
  const f = fixture({heldInputs:true}); playing(f);
  f.fire('keydown', f.root, {key:'ArrowLeft'});
  f.fire('pointerdown', f.left, {button:0,pointerId:1});
  f.fire('keyup', f.root, {key:'ArrowLeft'});
  assert.deepEqual(commands(f).map(item => item.action.axis), [-1]);
  f.fire('keydown', f.root, {key:'ArrowRight'});
  f.fire('keyup', f.root, {key:'ArrowRight'});
  assert.deepEqual(commands(f).map(item => item.action.axis), [-1,1,0,-1]);
  f.fire('pointerup', f.left, {pointerId:1});
  assert.equal(commands(f).at(-1).action.axis, 0);
});

test('held inputs clear before pause, blur, reconfiguration, DOM replacement and disposal', () => {
  for (const stop of [f => f.fire('click',f.pause), f => f.windowEvent('blur'), f => f.call('configure',null), f => { const replacement=f.buildRoot(); f.content.children=[replacement.root,f.sibling]; f.call('reapply'); }, f => f.call('dispose')]) {
    const f = fixture({heldInputs:true}); playing(f);
    f.fire('keydown', f.root, {key:'ArrowLeft'});
    stop(f);
    assert.equal(commands(f)[1].action.axis, 0, 'neutral input is dispatched before a lifecycle command');
    assert.equal(commands(f)[1].release, true);
    const count = commands(f).length;
    f.fire('keyup', f.root, {key:'ArrowLeft'}); f.advance(1000);
    assert.equal(commands(f).length,count);
  }
});

test('synthetic and spoken clicks pulse held input only after actual worker acknowledgement', async () => {
  const f = fixture({heldInputs:true,bridge:true}); playing(f);
  f.fire('click', f.left, {detail:0});
  const press = commands(f).at(-1);
  assert.equal(press.action.axis,-1);
  f.advance(5000);
  assert.equal(commands(f).length,1, 'queued press has no prematurely queued release');
  f.host('game.result',{requestId:press.requestId,ok:true});
  await Promise.resolve(); await Promise.resolve();
  f.advance(149); assert.equal(commands(f).length,1);
  f.advance(1); assert.equal(commands(f).at(-1).action.axis,0);
  assert.equal(commands(f).at(-1).release,true);
  f.fire('click',f.right,{detail:0});
  const next = commands(f).at(-1);
  f.host('game.result',{requestId:next.requestId,ok:true});
  await Promise.resolve(); await Promise.resolve();
  f.host('service.configure',{active:false,capabilities:[]});
  const count=commands(f).length; f.advance(1000);
  assert.equal(commands(f).length,count,'deactivation cancels pending pulse timers');
});

test('stored release payloads survive attribute edits and malformed releases cannot dispatch', () => {
  const f = fixture({heldInputs:true}); playing(f);
  f.fire('keydown',f.root,{key:'ArrowLeft'});
  f.left.setAttribute('data-game-release','{"type":"move","axis":99}');
  f.fire('keyup',f.root,{key:'ArrowLeft'});
  assert.equal(commands(f).at(-1).action.axis,0);
  for(const raw of ['{"type":"tick"}','broken','{"type":"move","data":"'+'x'.repeat(4096)+'"}']) {
    f.left.setAttribute('data-game-release',raw); f.fire('click',f.left);
  }
  assert.equal(commands(f).length,2);
});

test('canvas interpolation draws matching objects without replacing the DOM or running between frames', () => {
  const f = fixture(); playing(f);
  f.receive({ type: 'frame', view: scene(10, { objects: [{ id: 'player', type: 'circle', x: 10, y: 20, rotation: 350, radius: 8 }] }) }); f.animate(0);
  assert.equal(f.canvas.width, 260); assert.equal(f.canvas.height, 260); assert.equal(f.scheduled(), 0);
  f.time(50); f.receive({ type: 'frame', view: scene(110, { objects: [{ id: 'player', type: 'circle', x: 110, y: 20, rotation: 10, radius: 8 }] }) });
  f.canvas.context.calls.length = 0; f.animate(75);
  assert.deepEqual(f.canvas.context.calls.find(call => call[0] === 'translate'), ['translate', 60, 20]);
  assert.ok(Math.abs(f.canvas.context.calls.find(call => call[0] === 'rotate')[1] - 2 * Math.PI) < 0.00001);
  assert.equal(f.scheduled(), 1); f.animate(100); assert.equal(f.scheduled(), 0);
  assert.equal(f.root.children[0], f.canvas); assert.equal(f.sibling.textWrites, 0); assert.equal(f.content.children.length, 2);
  assert.equal(f.score.textContent, '0'); assert.equal(f.score.textWrites, 1);
});

test('input acknowledgement frames preserve movement pace and update readouts immediately', () => {
  const f = fixture(); playing(f);
  f.receive({ type: 'frame', view: scene(0) }); f.animate(0);
  f.time(50); f.receive({ type: 'frame', view: scene(100) });
  for (const time of [60, 65, 70, 75, 80, 85, 90]) {
    f.time(time); f.receive({ type: 'frame', kind: 'action', view: scene(100, { values: { score: time } }) });
    f.canvas.context.calls.length = 0; f.animate(time);
    assert.equal(f.canvas.context.calls.find(call => call[0] === 'translate')[1], (time - 50) * 2);
    assert.equal(f.score.textContent, String(time));
  }
  f.time(100); f.receive({ type: 'frame', view: scene(200) });
  f.canvas.context.calls.length = 0; f.animate(125);
  assert.equal(f.canvas.context.calls.find(call => call[0] === 'translate')[1], 150);
});

test('decorative movement and rotation cannot restart a character translation', () => {
  const f = fixture(); playing(f);
  const character = (x, rotation = 0, pupilOffset = 0) => scene(x, { objects: [
    { id: 'body', type: 'circle', x, y: 20, radius: 8 },
    { id: 'mouth', type: 'path', x, y: 20, rotation, d: 'M0 0L8 4L8 -4Z' },
    { id: 'pupil', type: 'circle', x: x + pupilOffset, y: 20, radius: 1 },
  ] });
  f.receive({ type: 'frame', view: character(0) }); f.animate(0);
  f.time(50); f.receive({ type: 'frame', view: character(100) });
  f.time(75); f.receive({ type: 'frame', kind: 'action', view: character(100, 90, 2) });
  f.canvas.context.calls.length = 0; f.animate(75);
  assert.deepEqual(f.canvas.context.calls.filter(call => call[0] === 'translate').slice(0, 2), [['translate', 50, 20], ['translate', 50, 20]]);
  f.canvas.context.calls.length = 0; f.animate(90);
  assert.deepEqual(f.canvas.context.calls.filter(call => call[0] === 'translate').slice(0, 2), [['translate', 80, 20], ['translate', 80, 20]]);
  f.time(100); f.receive({ type: 'frame', view: character(200, 90, 2) });
  f.canvas.context.calls.length = 0; f.animate(125);
  assert.deepEqual(f.canvas.context.calls.filter(call => call[0] === 'translate'), [['translate', 150, 20], ['translate', 150, 20], ['translate', 152, 20]]);
  assert.ok(Math.abs(f.canvas.context.calls.find(call => call[0] === 'rotate')[1] - Math.PI / 2) < 0.00001);
});

test('jittered frames continue from the visible pose without a position jump', () => {
  const f = fixture(); playing(f);
  f.receive({ type: 'frame', view: scene(0) }); f.animate(0);
  f.time(50); f.receive({ type: 'frame', view: scene(100) });
  f.canvas.context.calls.length = 0; f.animate(80);
  assert.equal(f.canvas.context.calls.find(call => call[0] === 'translate')[1], 60);
  f.time(80); f.receive({ type: 'frame', view: scene(200) });
  f.canvas.context.calls.length = 0; f.animate(80);
  assert.equal(f.canvas.context.calls.find(call => call[0] === 'translate')[1], 60, 'an early frame cannot snap to the previous unseen endpoint');
  f.canvas.context.calls.length = 0; f.animate(130);
  assert.equal(f.canvas.context.calls.find(call => call[0] === 'translate')[1], 200);
  f.time(140); f.receive({ type: 'frame', view: scene(300) });
  f.canvas.context.calls.length = 0; f.animate(140);
  assert.equal(f.canvas.context.calls.find(call => call[0] === 'translate')[1], 200);
});

test('movement after a stationary interval uses the published cadence independently for each game', () => {
  const f = fixture({ bridge: true, gameIds: ['maze', 'pong'] });
  for (const [id, intervalMs] of [['maze', 20], ['pong', 100]]) {
    f.receive({ type: 'status', status: 'running' }, id);
    f.receive({ type: 'frame', view: scene(0), intervalMs }, id);
  }
  f.animate(0);
  f.time(1000);
  for (const [id, intervalMs] of [['maze', 20], ['pong', 100]]) f.receive({ type: 'frame', view: scene(100), intervalMs }, id);
  for (const tile of f.allGames.values()) tile.canvas.context.calls.length = 0;
  f.animate(1010);
  assert.equal(f.canvas.context.calls.find(call => call[0] === 'translate')[1], 50);
  assert.equal(f.allGames.get('pong').canvas.context.calls.find(call => call[0] === 'translate')[1], 10);
});

test('reset and resume establish an exact pose before normal interpolation continues', () => {
  const f = fixture(); playing(f);
  f.receive({ type: 'frame', view: scene(0) }); f.animate(0);
  f.time(50); f.receive({ type: 'frame', view: scene(100) }); f.animate(75);
  f.time(80); f.receive({ type: 'frame', kind: 'reset', view: scene(10) });
  f.canvas.context.calls.length = 0; f.animate(80);
  assert.equal(f.canvas.context.calls.find(call => call[0] === 'translate')[1], 10);
  f.time(130); f.receive({ type: 'frame', view: scene(110) });
  f.canvas.context.calls.length = 0; f.animate(155);
  assert.equal(f.canvas.context.calls.find(call => call[0] === 'translate')[1], 60);
  f.receive({ type: 'status', status: 'paused' });
  f.time(200); playing(f); f.receive({ type: 'frame', kind: 'reset', view: scene(110) });
  f.time(250); f.receive({ type: 'frame', view: scene(210) });
  f.canvas.context.calls.length = 0; f.animate(275);
  assert.equal(f.canvas.context.calls.find(call => call[0] === 'translate')[1], 160);
});

test('readiness distinguishes authored previews from a retained canvas after an error', () => {
  const f = fixture();
  assert.equal(f.root.dataset.gameReady, 'false');
  playing(f); assert.equal(f.root.dataset.gameReady, 'false', 'running status alone does not hide the authored preview');
  f.receive({ type: 'frame', view: scene() }); f.animate(0);
  assert.equal(f.root.dataset.gameReady, 'true');
  f.receive({ type: 'status', status: 'error', message: 'Please restart the game.' });
  assert.equal(f.root.dataset.gameReady, 'true', 'the last canvas frame remains instead of revealing overlapping preview art');
  f.call('configure', null);
  assert.equal(f.root.dataset.gameReady, 'false', 'removing the game clears readiness on the old root');
  f.call('configure', { id: 'maze' });
  assert.equal(f.root.dataset.gameReady, 'false');
});

test('bounded native shapes, cached paths and text readouts remain plain data', () => {
  const f = fixture({ reducedMotion: true }); playing(f);
  const objects = [
    { id: 'box', type: 'rect', width: 30, height: 20, radius: 3, fill: '#fff' },
    { id: 'dot', type: 'circle', radius: 3, stroke: '#000', fill: 'none' },
    { id: 'line', type: 'path', d: 'M0 0L10 10', stroke: '#fff', fill: 'none' },
    { id: 'label', type: 'text', text: '10 points' },
  ];
  f.receive({ type: 'frame', view: scene(10, { objects, values: { score: '<img src=x onerror=alert(1)>' } }) }); f.animate(0);
  assert.equal(f.score.textContent, '<img src=x onerror=alert(1)>'); assert.equal(f.score.children.length, 0);
  assert.ok(f.canvas.context.calls.some(call => call[0] === 'roundRect'));
  assert.ok(f.canvas.context.calls.some(call => call[0] === 'fillText' && call[1] === '10 points'));
  assert.equal(f.canvas.context.font, '16px system-ui, sans-serif');
  f.time(50); f.receive({ type: 'frame', view: scene(10, { objects }) }); f.animate(50);
  assert.deepEqual(f.pathData, ['M0 0L10 10']); assert.equal(f.scheduled(), 0);
  f.receive({ type: 'frame', view: scene(10, { width: 99999 }) });
  assert.equal(f.root.dataset.gameStatus, 'error'); assert.match(f.status.textContent, /invalid scene/);
  assert.equal(f.left.disabled, true); assert.equal(commands(f).at(-1).command, 'pause');
});

test('reduced motion skips interpolation and status pausing cancels outstanding animation', () => {
  const f = fixture({ reducedMotion: true }); playing(f);
  f.receive({ type: 'frame', view: scene(10) }); f.animate(0);
  f.time(50); f.receive({ type: 'frame', view: scene(110) }); f.canvas.context.calls.length = 0; f.animate(50);
  assert.deepEqual(f.canvas.context.calls.find(call => call[0] === 'translate'), ['translate', 110, 20]); assert.equal(f.scheduled(), 0);
  f.media.matches = false; f.time(100); f.receive({ type: 'frame', view: scene(210) }); f.animate(110); assert.equal(f.scheduled(), 1);
  f.receive({ type: 'status', status: 'paused' }); f.animate(111); assert.equal(f.scheduled(), 0);
});

test('DOM replacement and motion preference changes retain a baseline for the next tick', () => {
  const f = fixture(); playing(f);
  f.receive({ type: 'frame', view: scene(100) }); f.animate(0);
  const replacement = f.buildRoot(); f.content.children = [f.sibling]; f.content.append(replacement.root);
  f.time(50); f.call('reapply'); f.animate(50);
  f.time(100); f.receive({ type: 'frame', view: scene(200) });
  replacement.canvas.context.calls.length = 0; f.animate(125);
  assert.equal(replacement.canvas.context.calls.find(call => call[0] === 'translate')[1], 150);
  f.media.matches = true; f.media.change(); f.animate(130);
  f.media.matches = false; f.media.change(); f.animate(150);
  f.time(200); f.receive({ type: 'frame', view: scene(300) });
  replacement.canvas.context.calls.length = 0; f.animate(225);
  assert.equal(replacement.canvas.context.calls.find(call => call[0] === 'translate')[1], 250);
});

test('same-revision DOM patches restore the current scene and removal pauses without losing it', () => {
  const f = fixture(); playing(f);
  f.receive({ type: 'frame', view: scene(45, { values: { score: 42 } }) }); f.animate(0);
  f.score.textContent = ''; f.call('reapply'); f.animate(1); assert.equal(f.score.textContent, '42');
  f.root.isConnected = false; f.content.children = [f.sibling]; f.call('reapply');
  assert.equal(commands(f).at(-1).command, 'pause'); assert.equal(f.scheduled(), 0);
  const replacement = f.buildRoot(); f.content.append(replacement.root); f.call('reapply'); f.animate(2);
  assert.equal(replacement.root.dataset.gameStatus, 'paused'); assert.equal(replacement.score.textContent, '42');
  assert.ok(replacement.canvas.context.calls.some(call => call[0] === 'translate' && call[1] === 45));
  assert.equal(replacement.resume.hidden, false);
});

test('hidden documents, focus departure and blur pause once and require explicit resume', () => {
  const f = fixture(); playing(f); f.receive({ type: 'frame', view: scene() });
  f.document.hidden = true; f.fire('visibilitychange');
  assert.equal(f.scheduled(), 0); assert.equal(commands(f).length, 1); assert.equal(commands(f)[0].command, 'pause');
  f.windowEvent('blur'); assert.equal(commands(f).length, 1);
  f.document.hidden = false; f.fire('visibilitychange'); assert.equal(commands(f).length, 1); assert.equal(f.root.dataset.gameStatus, 'paused');
  playing(f); f.fire('focusout', f.left, { relatedTarget: f.right }); assert.equal(commands(f).length, 1);
  f.fire('focusout', f.left, { relatedTarget: f.sibling }); assert.equal(commands(f).length, 2);
  playing(f); f.windowEvent('blur'); assert.equal(commands(f).length, 3);
  playing(f); f.call('dispose'); f.fire('click', f.left); f.windowEvent('blur'); f.receive({ type: 'frame', view: scene(100) });
  assert.equal(commands(f).length, 3); assert.equal(f.scheduled(), 0);
});

test('inactive, foreign, malformed and out-of-scope game controls cannot dispatch', () => {
  const f = fixture({ active: false });
  f.fire('click', f.start); f.receive({ type: 'status', status: 'running' }); assert.equal(commands(f).length, 0);
  f.setActive(true); f.call('reapply'); f.receive({ type: 'status', status: 'running' }, 'other'); assert.equal(f.left.disabled, true);
  playing(f);
  for (const raw of ['null', '[]', '{"type":"tick"}', '{"type":"direction","__proto__":{}}', '{"type":"direction","value":1e999}', '{"type":"direction","value":"' + 'x'.repeat(9000) + '"}', '{bad']) {
    f.left.setAttribute('data-game-action', raw); f.fire('click', f.left);
  }
  assert.equal(commands(f).length, 0);
  const nested = f.buildRoot(); nested.root.setAttribute('data-game', 'other'); f.root.append(nested.root); f.fire('click', nested.left);
  assert.equal(commands(f).length, 0);
  f.call('configure', { id: 'constructor' }); f.fire('click', f.start); assert.equal(commands(f).length, 0);
});

test('production serialized bridge authenticates game events and awaits game acceptance for voice', async () => {
  const f = fixture({ bridge: true });
  f.host('game.event', { gameId: 'maze', event: { type: 'status', status: 'running' } }, { source: {} });
  assert.equal(f.root.dataset.gameStatus, 'idle');
  f.host('voice.snapshot', { version: 1, requestId: 101 });
  const snapshot = f.sent.find(item => item.type === 'voice.result' && item.requestId === 101).surface;
  const start = snapshot.controls.find(item => item.label === 'Start game'); assert.ok(start);
  f.host('voice.execute', { version: 1, requestId: 102, action: { type: 'click', id: start.id } });
  await Promise.resolve(); assert.equal(f.sent.some(item => item.type === 'voice.result' && item.requestId === 102), false);
  const command = commands(f).at(-1); assert.equal(command.command, 'start');
  f.receive({ type: 'status', status: 'running' });
  f.host('game.result', { requestId: command.requestId, ok: true });
  await Promise.resolve(); await Promise.resolve();
  const result = f.sent.find(item => item.type === 'voice.result' && item.requestId === 102);
  assert.equal(result.ok, true); assert.match(result.message, /accepted the command/); assert.doesNotMatch(result.message, /saved/);
  f.receive({ type: 'frame', view: scene() }); f.animate(0); assert.ok(f.canvas.context.calls.length);
  f.host('voice.snapshot', { version: 1, requestId: 103 });
  const current = f.sent.find(item => item.type === 'voice.result' && item.requestId === 103).surface;
  const left = current.controls.find(item => item.label === 'Move left');
  f.host('voice.execute', { version: 1, requestId: 104, action: { type: 'click', id: left.id } });
  f.host('game.result', { requestId: commands(f).at(-1).requestId, ok: false });
  await Promise.resolve(); await Promise.resolve();
  assert.equal(f.sent.find(item => item.type === 'voice.result' && item.requestId === 104).ok, false);
  f.host('service.configure', { active: false, capabilities: [] }); f.fire('click', f.left);
  assert.equal(commands(f).length, 2); assert.equal(f.left.disabled, true);
});

test('four games retain independent canvases, scores, controls and lifecycle state', () => {
  const ids = ['maze', 'pong', 'blocks', 'invaders'];
  const f = fixture({ bridge: true, gameIds: ids });
  for (const [index, id] of ids.entries()) {
    const tile = f.allGames.get(id);
    assert.equal(tile.root.dataset.gameStatus, 'idle');
    f.fire('click', tile.start);
    assert.equal(commands(f).at(-1).gameId, id);
    f.receive({ type: 'status', status: 'running' }, id);
    f.receive({ type: 'frame', view: scene(20 + index * 40, { values: { score: 100 + index } }) }, id);
  }
  f.animate(0);
  for (const [index, id] of ids.entries()) {
    const tile = f.allGames.get(id);
    assert.equal(tile.score.textContent, String(100 + index));
    assert.deepEqual(tile.canvas.context.calls.find(call => call[0] === 'translate'), ['translate', 20 + index * 40, 20]);
    assert.equal(tile.root.dataset.gameStatus, 'running');
  }
  f.receive({ type: 'status', status: 'finished' }, 'blocks');
  assert.equal(f.allGames.get('blocks').left.disabled, true);
  for (const id of ['maze', 'pong', 'invaders']) assert.equal(f.allGames.get(id).left.disabled, false);
  const before = commands(f).length;
  f.fire('keydown', f.allGames.get('pong').root, { key: 'ArrowLeft' });
  f.fire('click', f.allGames.get('invaders').right);
  assert.deepEqual(commands(f).slice(before).map(command => [command.gameId, command.action.direction]), [['pong', 'left'], ['invaders', 'right']]);
  f.receive({ type: 'frame', view: scene(150, { values: { score: 999 } }) }, 'unknown');
  assert.deepEqual(ids.map(id => f.allGames.get(id).score.textContent), ['100', '101', '102', '103']);
});

test('held input and focus changes cannot leak between nested or neighboring games', () => {
  const f = fixture({ bridge: true, heldInputs: true, gameIds: ['maze', 'pong'] });
  const pong = f.allGames.get('pong');
  f.content.children = f.content.children.filter(node => node !== pong.root); f.root.append(pong.root);
  for (const id of ['maze', 'pong']) f.receive({ type: 'status', status: 'running' }, id);
  f.fire('keydown', pong.root, { key: 'ArrowLeft', code: 'ArrowLeft' });
  f.fire('keyup', pong.root, { key: 'ArrowLeft', code: 'ArrowLeft' });
  assert.deepEqual(commands(f).map(command => [command.gameId, command.action.axis]), [['pong', -1], ['pong', 0]]);
  f.fire('pointerdown', f.left, { button: 0, pointerId: 1 });
  f.fire('focusout', f.root, { relatedTarget: pong.root });
  const tail = commands(f).slice(2);
  assert.deepEqual(tail.map(command => [command.gameId, command.command, command.action?.axis]), [['maze', 'action', -1], ['maze', 'action', 0], ['maze', 'pause', undefined]]);
  assert.equal(f.root.dataset.gameStatus, 'paused');
  assert.equal(pong.root.dataset.gameStatus, 'running');
  const count = commands(f).length;
  f.fire('pointerup', pong.root, { pointerId: 1 });
  assert.equal(commands(f).length, count, 'the old physical input was released when its game lost focus');
});

test('removing one game settles its pending commands and preserves the others', async () => {
  const f = fixture({ bridge: true, gameIds: ['maze', 'pong'] });
  const pong = f.allGames.get('pong');
  for (const id of ['maze', 'pong']) {
    f.receive({ type: 'status', status: 'running' }, id);
    f.receive({ type: 'frame', view: scene(30, { values: { score: id === 'maze' ? 2 : 7 } }) }, id);
  }
  f.host('voice.snapshot', { version: 1, requestId: 201 });
  const snapshot = f.sent.find(item => item.type === 'voice.result' && item.requestId === 201).surface;
  const mazeLeft = snapshot.controls.find(item => item.label === 'Move left');
  f.host('voice.execute', { version: 1, requestId: 202, action: { type: 'click', id: mazeLeft.id } });
  const pending = commands(f).at(-1);
  assert.equal(pending.gameId, 'maze');
  f.host('game.configure', { configs: [{ id: 'pong' }] });
  await Promise.resolve(); await Promise.resolve();
  assert.equal(f.sent.find(item => item.type === 'voice.result' && item.requestId === 202).ok, false);
  assert.equal(f.root.dataset.gameReady, 'false'); assert.equal(f.left.disabled, true);
  assert.equal(pong.root.dataset.gameStatus, 'running'); assert.equal(pong.score.textContent, '7');
  const count = commands(f).length;
  f.fire('keydown', f.root, { key: 'ArrowLeft' }); assert.equal(commands(f).length, count);
  f.fire('keydown', pong.root, { key: 'ArrowLeft' }); assert.equal(commands(f).at(-1).gameId, 'pong');
  f.host('game.result', { requestId: pending.requestId, ok: true });
  await Promise.resolve();
  assert.equal(f.sent.filter(item => item.type === 'voice.result' && item.requestId === 202).length, 1);
});

test('the frame admits at most four distinct game instances', () => {
  const ids = ['maze', 'pong', 'blocks', 'invaders', 'extra'];
  const f = fixture({ bridge: true, gameIds: ids });
  for (const id of ids) {
    const tile = f.allGames.get(id);
    f.receive({ type: 'status', status: 'running' }, id);
    f.receive({ type: 'frame', view: scene() }, id);
    f.fire('keydown', tile.root, { key: 'ArrowLeft' });
  }
  f.animate(0);
  assert.deepEqual(commands(f).map(command => command.gameId), ids.slice(0, 4));
  assert.equal(f.allGames.get('extra').canvas.context.calls.length, 0);
});

test('returning from a draft restores game controls without overriding authored disabled states', () => {
  const f = fixture({ bridge: true, disabledLeft: true, gameIds: ['maze', 'pong'] });
  const pong = f.allGames.get('pong');
  for (const id of ['maze', 'pong']) f.receive({ type: 'status', status: 'running' }, id);
  f.host('service.configure', { active: false, capabilities: [] });
  f.host('game.configure', { configs: [] });
  assert.equal(f.start.disabled, true); assert.equal(pong.start.disabled, true);
  f.host('service.configure', { active: true, capabilities: [] });
  f.host('game.configure', { configs: [{ id: 'maze' }, { id: 'pong' }] });
  assert.equal(f.start.disabled, false); assert.equal(pong.start.disabled, false);
  f.fire('click', pong.start);
  assert.equal(commands(f).at(-1).gameId, 'pong');
  assert.equal(commands(f).at(-1).command, 'start');
  for (const id of ['maze', 'pong']) f.receive({ type: 'status', status: 'running' }, id);
  assert.equal(f.left.disabled, true, 'authored disabled remains disabled after a new installer');
  assert.equal(f.right.disabled, false);
  assert.equal(pong.left.disabled, false, 'host lifecycle disabling is temporary');
});
