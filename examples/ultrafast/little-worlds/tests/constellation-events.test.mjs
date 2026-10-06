import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { build } from 'esbuild';

// Exercise the component's real gesture handlers and projection. The fixture
// replaces React mounting, browser plumbing, and decorative drawing only.
const compiled = await build({
  entryPoints: [new URL('../src/Constellation.tsx', import.meta.url).pathname],
  bundle: true, write: false, format: 'iife', globalName: 'ConstellationModule',
  jsx: 'transform', jsxFactory: 'h.jsx',
  plugins: [{ name: 'browser-fixtures', setup(builder) {
    builder.onResolve({ filter: /^(react(?:\/jsx-runtime)?|gsap|lucide-react)$|SpaceIcon$|\.css$/ }, ({ path }) => ({ path, namespace: 'fixture' }));
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => {
      if (path.endsWith('.css')) return { contents: '' };
      if (path === 'react/jsx-runtime') return { contents: 'export const jsx=(tag,props,key)=>h.jsx(tag,{...props,key}), jsxs=jsx;' };
      if (path === 'react') return { contents: 'export const {useRef,useState,useEffect,useLayoutEffect,useMemo,useId}=h;' };
      if (path === 'gsap') return { contents: 'export const gsap=h.gsap;' };
      if (path === 'lucide-react') return { contents: 'export const Hand=()=>null,Maximize=Hand,Minus=Hand,Orbit=Hand,Pause=Hand,Play=Hand,Plus=Hand;' };
      return { contents: 'export default function SpaceIcon(){return null;}' };
    });
  } }],
});

const close = (actual, expected, message) => assert.ok(Math.abs(actual - expected) < 1e-7, `${message}: ${actual} ≈ ${expected}`);
const pointClose = (actual, expected, message) => {
  close(actual.x, expected.x, `${message} x`);
  close(actual.y, expected.y, `${message} y`);
};

function mountGalaxy(t, { storage = new Map(), people: initialPeople } = {}) {
  const people = initialPeople || ['mira', 'james', 'erica'].map(id => ({ id, name: id, role: 'A space', color: '#cadcb0' }));
  const selections = [], writes = [], elements = new Map(), hooks = [], ticks = new Set();
  let hookIndex = 0, layoutQueue = [], effectQueue = [], tree;
  let props = { people, connections: [], currentUserId: 'mira', selectedId: null, onSelect: id => selections.push(id) };
  const media = Object.assign(new EventTarget(), { matches: false });
  const browser = Object.assign(new EventTarget(), { devicePixelRatio: 1, matchMedia: () => media });
  const document = Object.assign(new EventTarget(), { hidden: false, documentElement: { dataset: {} } });
  const mutations = new Set(), strokes = [], fills = [];
  const context2d = { setTransform() {}, clearRect() {}, beginPath() {}, moveTo() {}, lineTo() {}, arc() {},
    stroke() { strokes.push(this.strokeStyle); }, fill() { fills.push(this.fillStyle); } };
  const localStorage = {
    getItem: key => storage.get(key) ?? null,
    removeItem: key => storage.delete(key),
    setItem: (key, value) => { storage.set(key, value); writes.push({ key, value }); },
  };
  class Surface extends EventTarget {
    constructor(tag) {
      super(); this.tag = tag; this.props = {}; this.children = []; this.parent = null;
      this.dataset = {}; this.captures = new Set(); this.x = 0; this.y = 0;
      this.style = { setProperty(name, value) { this[name] = value; } };
    }
    getBoundingClientRect() { return { left: 50, top: 80, width: 800, height: 600 }; }
    getContext() { return context2d; }
    focus() { document.activeElement = this; }
    closest(selector) {
      for (let current = this; current; current = current.parent) {
        if (selector === '[data-person-id]' && current.dataset.personId) return current;
      }
      return null;
    }
    querySelectorAll(selector) {
      const result = [];
      const visit = element => {
        if (selector.startsWith('.') ? (element.props.className || '').split(' ').includes(selector.slice(1)) : element.tag === selector) result.push(element);
        element.children.forEach(visit);
      };
      this.children.forEach(visit); return result;
    }
    querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
    contains(target) { return target === this || this.children.some(child => child.contains(target)); }
    setAttribute(name, value) { this.props[name] = value; }
    setPointerCapture(id) { this.captures.add(id); }
    hasPointerCapture(id) { return this.captures.has(id); }
    releasePointerCapture(id) {
      if (!this.captures.delete(id)) return;
      this.props.onLostPointerCapture?.(event('lostpointercapture', { pointerId: id, target: this, currentTarget: this, buttons: 0 }));
    }
  }
  const sameDeps = (a, b) => a && b && a.length === b.length && a.every((value, index) => Object.is(value, b[index]));
  function effect(callback, deps, queue) {
    const index = hookIndex++, previous = hooks[index];
    if (!previous || !sameDeps(previous.deps, deps)) {
      const slot = hooks[index] = { deps, cleanup: previous?.cleanup };
      queue.push(() => { slot.cleanup?.(); slot.cleanup = callback(); });
    }
  }
  const h = {
    jsx: (tag, attributes, ...children) => ({ tag, props: { ...attributes, children: children.length ? children : attributes?.children } }),
    useRef(value) { const index = hookIndex++; return hooks[index] ||= { current: value }; },
    useState(value) {
      const index = hookIndex++, slot = hooks[index] ||= { value: typeof value === 'function' ? value() : value };
      return [slot.value, next => { slot.value = typeof next === 'function' ? next(slot.value) : next; }];
    },
    useEffect: (callback, deps) => effect(callback, deps, effectQueue),
    useLayoutEffect: (callback, deps) => effect(callback, deps, layoutQueue),
    useMemo(callback, deps) {
      const index = hookIndex++;
      if (!hooks[index] || !sameDeps(hooks[index].deps, deps)) hooks[index] = { deps, value: callback() };
      return hooks[index].value;
    },
    useId() { hookIndex++; return 'galaxy-help'; },
    gsap: {
      quickSetter: (element, axis) => value => { element[axis] = value; },
      ticker: { add: callback => ticks.add(callback), remove: callback => ticks.delete(callback) },
      matchMedia: () => ({ add() {}, revert() {} }),
      fromTo: () => ({ kill() {} }),
      to(target, values) {
        for (const [key, value] of Object.entries(values)) if (!['duration', 'ease'].includes(key) && typeof value === 'number') target[key] = value;
        values.onUpdate?.(); values.onComplete?.(); return { kill() {} };
      },
    },
  };
  const context = vm.createContext({ h, window: browser, document, localStorage,
    MutationObserver: class {
      constructor(callback) { this.callback = callback; }
      observe() { mutations.add(this.callback); }
      disconnect() { mutations.delete(this.callback); }
    },
    ResizeObserver: class {
      constructor(callback) { this.callback = callback; }
      observe() { this.callback([{ contentRect: { width: 800, height: 600 } }]); }
      disconnect() {}
    },
  });
  vm.runInContext(compiled.outputFiles[0].text, context);

  function mount(vnode, path, parent) {
    if (!vnode || typeof vnode !== 'object' || typeof vnode.tag !== 'string') return null;
    let element = elements.get(path);
    if (!element) { element = new Surface(vnode.tag); elements.set(path, element); }
    if (element.props.ref && element.props.ref !== vnode.props.ref && typeof element.props.ref === 'function') element.props.ref(null);
    element.props = vnode.props; element.parent = parent;
    element.dataset = Object.fromEntries(Object.entries(vnode.props).filter(([key]) => key.startsWith('data-')).map(([key, value]) => [key.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase()), value]));
    const children = [vnode.props.children].flat(Infinity).filter(child => child && typeof child === 'object');
    element.children = children.map((child, index) => mount(child, `${path}/${child.props?.key ?? index}`, element)).filter(Boolean);
    if (typeof vnode.props.ref === 'function') vnode.props.ref(element);
    else if (vnode.props.ref) vnode.props.ref.current = element;
    return element;
  }
  function render(next = {}) {
    props = { ...props, ...next }; hookIndex = 0; layoutQueue = []; effectQueue = [];
    tree = mount(context.ConstellationModule.default(props), 'root', null);
    for (const callback of layoutQueue) callback();
    for (const callback of effectQueue) callback();
    tick();
  }
  function tick() { for (const callback of ticks) callback(0, 16); }
  function event(type, extra = {}) {
    const value = { type, pointerId: 1, pointerType: 'mouse', isPrimary: true, button: 0, buttons: 1, clientX: 0, clientY: 0, shiftKey: false,
      defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, stopPropagation() {}, ...extra };
    value.nativeEvent = value; return value;
  }
  function scene() { return tree.querySelector('.constellation-scene'); }
  function person(id = 'mira') { return [...elements.values()].find(element => element.dataset.personId === id); }
  function point(id = 'mira') { const node = person(id).parent; return { x: node.x, y: node.y }; }
  function pointer(type, location = point(), extra = {}) {
    const handlers = { pointerdown: 'onPointerDown', pointermove: 'onPointerMove', pointerup: 'onPointerUp', pointercancel: 'onPointerCancel', lostpointercapture: 'onLostPointerCapture' };
    const surface = scene();
    const value = event(type, { clientX: location.x + 50, clientY: location.y + 80, currentTarget: surface, target: type === 'pointerdown' ? person() : surface, ...extra });
    surface.props[handlers[type]]?.(value);
    return value;
  }
  function windowEvent(type, location = point(), extra = {}) {
    const value = new Event(type, { cancelable: true });
    const values = { pointerId: 1, pointerType: 'mouse', isPrimary: true, button: 0, buttons: 0, clientX: location.x + 50, clientY: location.y + 80, ...extra };
    for (const [key, data] of Object.entries(values)) Object.defineProperty(value, key, { value: data });
    browser.dispatchEvent(value); return value;
  }
  function drag(offset = { x: 140, y: 90 }) {
    const start = point(), finish = { x: start.x + offset.x, y: start.y + offset.y };
    pointer('pointerdown', start); pointer('pointermove', finish);
    pointClose(point(), finish, 'held person follows pointer');
    return { start, finish };
  }
  function saved() { return new Map(JSON.parse(storage.get('little-worlds.galaxy-layout.v1:mira') || '[]')); }
  render();
  t.after(() => { for (const hook of hooks) hook?.cleanup?.(); });
  const setTheme = theme => { document.documentElement.dataset.theme = theme; for (const callback of mutations) callback(); };
  return { scene, person, point, pointer, windowEvent, drag, tick, render, storage, saved, selections, writes, people, strokes, fills, setTheme };
}

test('community field repaints with contrasting neutral lines and stars when appearance changes', t => {
  const galaxy = mountGalaxy(t);
  assert.ok(galaxy.strokes.includes('rgba(245,245,245,.045)'));
  galaxy.strokes.length = 0; galaxy.fills.length = 0;
  galaxy.setTheme('light');
  assert.ok(galaxy.strokes.includes('rgba(73,85,105,.085)'));
  assert.ok(galaxy.fills.some(color => color.startsWith('rgba(73,85,105,')));
  assert.ok(!galaxy.fills.some(color => color.startsWith('rgba(245,245,245,')));
  galaxy.strokes.length = 0;
  galaxy.setTheme('dark');
  assert.ok(galaxy.strokes.includes('rgba(245,245,245,.045)'));
});

test('a saved galaxy layout from before the rename keeps every placement', t => {
  const galaxy = mountGalaxy(t);
  const { finish } = galaxy.drag();
  galaxy.pointer('pointerup', finish, { buttons: 0 });
  const saved = galaxy.storage.get('little-worlds.galaxy-layout.v1:mira');
  const storage = new Map([['living-spaces.galaxy-layout.v1:mira', saved]]);
  const reopened = mountGalaxy(t, { storage });
  pointClose(reopened.point(), finish, 'legacy world position restores on mount');
  assert.equal(storage.get('little-worlds.galaxy-layout.v1:mira'), saved);
  assert.equal(storage.has('living-spaces.galaxy-layout.v1:mira'), false);
});

for (const lateUp of [false, true]) {
  test(`node capture loss keeps its new position ${lateUp ? 'before a delayed pointerup' : 'when pointerup is missing'}`, t => {
    const galaxy = mountGalaxy(t);
    const { finish } = galaxy.drag();
    galaxy.scene().captures.delete(1);
    galaxy.pointer('lostpointercapture', { x: 0, y: 0 });
    const writes = galaxy.writes.length;
    if (lateUp) galaxy.pointer('pointerup', { x: finish.x + 100, y: finish.y + 50 }, { buttons: 0 });
    for (let index = 0; index < 5; index++) galaxy.tick();
    pointClose(galaxy.point(), finish, 'released person stays placed');
    assert.ok(galaxy.saved().has('mira'), 'the placement survives a new visit');
    assert.equal(galaxy.writes.length, writes, 'late pointerup must not recommit or move the person');
    assert.deepEqual(galaxy.selections, [], 'a drag never opens the person');
    const reopened = mountGalaxy(t, { storage: galaxy.storage });
    pointClose(reopened.point(), finish, 'saved world position restores on mount');
  });
}

test('pointercancel preserves the last valid placement and ends the gesture', t => {
  const galaxy = mountGalaxy(t);
  const { finish } = galaxy.drag();
  galaxy.pointer('pointercancel', { x: 0, y: 0 }, { buttons: 0 });
  galaxy.pointer('pointermove', { x: 600, y: 400 }, { buttons: 0 });
  pointClose(galaxy.point(), finish, 'cancel must not undo the placement or apply cancellation coordinates');
  assert.ok(galaxy.saved().has('mira'));
  assert.equal(galaxy.scene().hasPointerCapture(1), false);
  assert.deepEqual(galaxy.selections, []);
});

test('capture transfer from a descendant and stale capture loss do not interrupt an active drag', t => {
  const galaxy = mountGalaxy(t);
  const { finish } = galaxy.drag();
  galaxy.pointer('lostpointercapture', finish, { target: galaxy.person() });
  galaxy.pointer('lostpointercapture', finish);
  const next = { x: finish.x + 35, y: finish.y + 20 };
  galaxy.pointer('pointermove', next);
  pointClose(galaxy.point(), next, 'scene still holds and moves the person');
  galaxy.pointer('pointerup', next, { buttons: 0 });
  pointClose(galaxy.point(), next, 'normal release preserves the placement');
  assert.ok(galaxy.saved().has('mira'));
  assert.deepEqual(galaxy.selections, []);
});

test('pointerup includes the final movement even when move events were sparse', t => {
  const galaxy = mountGalaxy(t), start = galaxy.point();
  const finish = { x: start.x + 150, y: start.y + 110 };
  galaxy.pointer('pointerdown', start);
  galaxy.pointer('pointerup', finish, { buttons: 0 });
  pointClose(galaxy.point(), finish, 'last release coordinates are committed');
  assert.ok(galaxy.saved().has('mira'));
  assert.deepEqual(galaxy.selections, [], 'a fast drag without a sampled move is not a click');
});

test('a hover after a missed release ends the drag without moving to the hover position', t => {
  const galaxy = mountGalaxy(t), { finish } = galaxy.drag();
  galaxy.pointer('pointermove', { x: 680, y: 400 }, { buttons: 0 });
  pointClose(galaxy.point(), finish, 'hover is not an extra drag movement');
  assert.ok(galaxy.saved().has('mira'));
  assert.equal(galaxy.scene().hasPointerCapture(1), false);
});

for (const ending of ['pointerup', 'pointercancel', 'blur']) {
  test(`window ${ending} preserves placement when the scene misses the event`, t => {
    const galaxy = mountGalaxy(t), { finish } = galaxy.drag();
    galaxy.windowEvent(ending, finish);
    galaxy.pointer('pointermove', { x: 680, y: 400 });
    pointClose(galaxy.point(), finish, 'window ending finishes the active drag');
    assert.ok(galaxy.saved().has('mira'));
    assert.equal(galaxy.scene().hasPointerCapture(1), false);
    assert.deepEqual(galaxy.selections, []);
  });
}

test('pointer motion outside the scene continues a held drag and window release finishes it', t => {
  const galaxy = mountGalaxy(t), { finish } = galaxy.drag();
  const next = { x: finish.x + 65, y: finish.y + 20 };
  galaxy.windowEvent('pointermove', next, { buttons: 1 });
  pointClose(galaxy.point(), next, 'outside motion continues the captured gesture');
  galaxy.windowEvent('pointerup', next);
  galaxy.windowEvent('pointermove', { x: 700, y: 500 });
  pointClose(galaxy.point(), next, 'post-release outside movement does not move the person');
  assert.ok(galaxy.saved().has('mira'));
  assert.equal(galaxy.scene().hasPointerCapture(1), false);
});

test('a directory refresh preserves a held person and a completed placement', t => {
  const galaxy = mountGalaxy(t), { finish } = galaxy.drag();
  galaxy.render({ people: [...galaxy.people].reverse().map(person => ({ ...person })) });
  pointClose(galaxy.point(), finish, 'refresh while held keeps world placement');
  const next = { x: finish.x + 20, y: finish.y + 20 };
  galaxy.pointer('pointerup', next, { buttons: 0 });
  galaxy.render({ people: [...galaxy.people, { id: 'luca', name: 'Luca', role: 'Teacher', color: '#cadcb0' }] });
  pointClose(galaxy.point(), next, 'adding someone after release keeps existing placement');
  assert.ok(galaxy.saved().has('mira'));
});

test('ordinary clicks and keyboard activation still select a person exactly once', t => {
  const galaxy = mountGalaxy(t), start = galaxy.point();
  galaxy.pointer('pointerdown', start);
  galaxy.pointer('pointerup', start, { buttons: 0 });
  galaxy.person().props.onClick({ detail: 1 });
  assert.deepEqual(galaxy.selections, ['mira']);
  assert.equal(galaxy.saved().size, 0, 'clicking must not pin a drifting person');
  galaxy.person().props.onClick({ detail: 0 });
  assert.deepEqual(galaxy.selections, ['mira', 'mira']);
});

test('background rotation and shift-drag panning still move the galaxy without pinning people', t => {
  const galaxy = mountGalaxy(t), start = galaxy.point();
  const origin = { x: 400, y: 300 }, finish = { x: 460, y: 330 };
  galaxy.pointer('pointerdown', origin, { target: galaxy.scene() });
  galaxy.pointer('pointermove', finish);
  galaxy.pointer('pointerup', finish, { buttons: 0 });
  const rotated = galaxy.point();
  assert.ok(Math.hypot(rotated.x - start.x, rotated.y - start.y) > 10);
  galaxy.pointer('pointerdown', origin, { target: galaxy.scene() });
  galaxy.pointer('pointermove', finish, { shiftKey: true });
  galaxy.pointer('pointerup', finish, { buttons: 0, shiftKey: true });
  pointClose(galaxy.point(), { x: rotated.x + 60, y: rotated.y + 30 }, 'shift drag pans the whole view');
  assert.equal(galaxy.saved().size, 0);
  assert.deepEqual(galaxy.selections, []);
});

test('native dragstart is suppressed inside the interactive galaxy', t => {
  const galaxy = mountGalaxy(t);
  let prevented = false;
  galaxy.scene().props.onDragStart?.({ preventDefault() { prevented = true; } });
  assert.equal(prevented, true, 'native dragging must not take over a pointer gesture');
});
