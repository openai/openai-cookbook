import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { build } from 'esbuild';
import * as THREE from 'three';

// Run the component's real listeners and rotation model. Only React mounting,
// browser plumbing, and GPU drawing are replaced; rendered quaternions remain real.
const compiled = await build({
  entryPoints: [new URL('../src/LivingWorld.tsx', import.meta.url).pathname],
  bundle: true, write: false, format: 'iife', globalName: 'LivingWorldModule',
  jsx: 'transform', jsxFactory: 'h.jsx', define: { 'import.meta.env.DEV': 'false' },
  plugins: [{ name: 'browser-fixtures', setup(builder) {
    builder.onResolve({ filter: /^(react(?:\/jsx-runtime)?|gsap|three)$|living-world-scene$|\.css$/ }, ({ path }) => ({ path, namespace: 'fixture' }));
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => {
      if (path.endsWith('.css')) return { contents: '' };
      if (path === 'react/jsx-runtime') return { contents: 'export const jsx=h.jsx, jsxs=h.jsx;' };
      if (path === 'react') return { contents: 'export const useRef=h.useRef, useEffect=h.useEffect, useState=h.useState;' };
      if (path === 'gsap') return { contents: 'export default { ticker: h.ticker };' };
      if (path.endsWith('living-world-scene')) return { contents: 'export function createLivingWorldScene(){ return {world:new h.THREE.Group(),dispose(){}}; }' };
      return { contents: `export const WebGLRenderer=h.Renderer;
        export const {Quaternion,Vector3,Scene,OrthographicCamera,HemisphereLight,DirectionalLight,
          SRGBColorSpace,ACESFilmicToneMapping,PCFShadowMap}=h.THREE;` };
    });
  } }],
});

async function mountWorld(t) {
  let now = 0;
  class Surface extends EventTarget {
    style = {}; dataset = {}; captures = new Set();
    clientWidth = 246; clientHeight = 246;
    getBoundingClientRect() {
      return { left: parseFloat(this.style.left) || 0, top: parseFloat(this.style.top) || 0,
        width: parseFloat(this.style.width) || this.clientWidth, height: parseFloat(this.style.height) || this.clientHeight };
    }
    appendChild() {} remove() {} focus() {} closest() { return this; }
    setPointerCapture(id) { this.captures.add(id); }
    hasPointerCapture(id) { return this.captures.has(id); }
    releasePointerCapture(id) {
      this.captures.delete(id);
      dispatch('lostpointercapture', 0, now, { pointerId: id });
    }
  }
  const host = new Surface(), surface = new Surface();
  const refs = [host, surface], effects = [], cleanups = [], frames = [], listeners = new Set();
  const ticker = { time: 0, add: fn => listeners.add(fn), remove: fn => listeners.delete(fn) };
  class Renderer {
    domElement = new Surface(); shadowMap = {};
    setPixelRatio() {} setClearColor() {} setSize() {} dispose() {} forceContextLoss() {}
    render(scene, camera) { camera.updateMatrixWorld(); frames.push(scene.children[0].quaternion.clone()); }
  }
  const media = Object.assign(new EventTarget(), { matches: false });
  const browser = Object.assign(new EventTarget(), { devicePixelRatio: 1, matchMedia: () => media });
  const document = Object.assign(new EventTarget(), { hidden: false });
  const h = { THREE, Renderer, ticker, jsx: () => null, useRef: () => ({ current: refs.shift() }),
    useEffect: fn => effects.push(fn), useState: () => [false, () => {}] };
  const context = vm.createContext({ h, window: browser, document, performance: { now: () => now },
    ResizeObserver: class { observe() {} disconnect() {} },
    IntersectionObserver: class { observe() {} disconnect() {} } });
  vm.runInContext(compiled.outputFiles[0].text, context);
  context.LivingWorldModule.default();
  for (const effect of effects) cleanups.push(effect());
  await new Promise(resolve => setImmediate(resolve));
  assert.ok(frames.length && listeners.size, 'the component must mount and start rendering');
  t.after(() => { for (const cleanup of cleanups) cleanup(); });

  function dispatch(type, x, time, extra = {}) {
    now = time;
    const bounds = surface.getBoundingClientRect();
    const event = new Event(type, { cancelable: true });
    Object.defineProperties(event, Object.fromEntries(Object.entries({
      pointerId: 1, pointerType: 'mouse', isPrimary: true, button: 0, buttons: 1,
      clientX: bounds.left + bounds.width * (x + 1) / 2,
      clientY: bounds.top + bounds.height / 2, timeStamp: time, ...extra,
    }).map(([key, value]) => [key, { value }])));
    surface.dispatchEvent(event);
  }
  function drag() {
    dispatch('pointerdown', 0, 0);
    dispatch('pointermove', 0.15, 25);
    dispatch('pointermove', 0.3, 50);
  }
  function coast() {
    const before = frames.at(-1);
    for (let frame = 0; frame < 15; frame++) {
      ticker.time += 1 / 60;
      for (const listener of listeners) listener(ticker.time);
    }
    return before.angleTo(frames.at(-1));
  }
  return { surface, dispatch, drag, coast };
}

for (const latePointerUp of [false, true]) {
  test(`capture loss preserves a throw ${latePointerUp ? 'before a delayed pointerup' : 'when pointerup is omitted'}`, async t => {
    const world = await mountWorld(t);
    world.drag();
    world.surface.captures.delete(1);
    world.dispatch('lostpointercapture', 0.3, 60);
    if (latePointerUp) world.dispatch('pointerup', 0.3, 70, { buttons: 0 });
    assert.equal(world.surface.dataset.dragging, undefined);
    assert.ok(world.coast() > 0.8, 'rendered globe must retain visible momentum after capture loss');
  });
}

test('normal pointerup followed by capture loss does not cancel the throw', async t => {
  const world = await mountWorld(t);
  world.drag();
  world.dispatch('pointerup', 0.3, 60, { buttons: 0 });
  assert.equal(world.surface.hasPointerCapture(1), false);
  assert.ok(world.coast() > 0.8);
});

test('pointercancel followed by capture loss discards the throw', async t => {
  const world = await mountWorld(t);
  world.drag();
  world.dispatch('pointercancel', 0.3, 60, { buttons: 0 });
  assert.equal(world.surface.dataset.dragging, undefined);
  assert.ok(world.coast() < 0.01, 'a real abort may gently restart idle spin, but must not coast');
});
