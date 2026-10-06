import test from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

const compiled = await build({ entryPoints: [new URL('../src/frame-viewport.ts', import.meta.url).pathname], bundle: true, write: false, format: 'esm' });
const { frameVoiceViewport } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);

function fixture(width = 1200, height = 900) {
  const document = { defaultView: { innerWidth: width, innerHeight: height, getComputedStyle: element => element.style } };
  return (left, top, logicalWidth, logicalHeight, options = {}) => {
    const { scale = 1, borderLeft = 0, borderTop = 0, clientWidth = logicalWidth, clientHeight = logicalHeight,
      overflowX = 'visible', overflowY = 'visible', parent = null } = options;
    return { ownerDocument: document, parentElement: parent, offsetWidth: logicalWidth, offsetHeight: logicalHeight,
      clientLeft: borderLeft, clientTop: borderTop, clientWidth, clientHeight, style: { overflowX, overflowY },
      getBoundingClientRect: () => ({ left, top, width: logicalWidth * scale, height: logicalHeight * scale }) };
  };
}

test('ordinary full-width frames retain their window-relative visible slice', () => {
  const node = fixture(900, 700);
  assert.deepEqual(frameVoiceViewport(node(-40, -100, 1000, 1600)), { left: 40, top: 100, width: 900, height: 700 });
});

test('a scaled desktop preview maps its visible slice back to logical coordinates', () => {
  const node = fixture(1000, 700);
  assert.deepEqual(frameVoiceViewport(node(100, -50, 1600, 2000, { scale: .4 })), { left: 0, top: 125, width: 1600, height: 1750 });
});

test('comparison scrollport clips below-fold controls and excludes borders and scrollbar gutters', () => {
  const node = fixture();
  const preview = node(100, 100, 400, 250, { borderLeft: 1, borderTop: 1, clientWidth: 383, clientHeight: 248, overflowX: 'auto', overflowY: 'auto' });
  const frame = node(100, 100, 800, 1000, { scale: .5, parent: preview });
  assert.deepEqual(frameVoiceViewport(frame), { left: 2, top: 2, width: 766, height: 496 });
});

test('scrolling the comparison pane changes the logical area even while the window stays still', () => {
  const node = fixture();
  const preview = node(100, 100, 400, 250, { overflowY: 'auto' });
  const before = frameVoiceViewport(node(100, 100, 800, 2000, { scale: .5, parent: preview }));
  const after = frameVoiceViewport(node(100, -200, 800, 2000, { scale: .5, parent: preview }));
  assert.deepEqual(before, { left: 0, top: 0, width: 800, height: 500 });
  assert.deepEqual(after, { left: 0, top: 600, width: 800, height: 500 });
});

test('nested clips intersect independently on each axis and visible overflow does not clip', () => {
  const node = fixture();
  const outer = node(0, 100, 500, 300, { overflowY: 'hidden' });
  const inner = node(200, 0, 250, 800, { overflowX: 'clip', parent: outer });
  const decoration = node(0, 0, 20, 20, { parent: inner });
  const frame = node(100, -100, 1000, 2000, { scale: .5, parent: decoration });
  assert.deepEqual(frameVoiceViewport(frame), { left: 200, top: 400, width: 500, height: 600 });
});

test('transformed scrollports and left-hand scrollbar gutters use rendered client geometry', () => {
  const node = fixture();
  const preview = node(100, 100, 1000, 600, { scale: .5, borderLeft: 18, borderTop: 2, clientWidth: 980, clientHeight: 596, overflowX: 'scroll', overflowY: 'scroll' });
  const frame = node(100, 0, 1600, 2000, { scale: .5, parent: preview });
  assert.deepEqual(frameVoiceViewport(frame), { left: 18, top: 202, width: 980, height: 596 });
});

test('iframe borders are excluded before converting to its content coordinates', () => {
  const node = fixture();
  const frame = node(100, -50, 804, 1004, { scale: .5, borderLeft: 2, borderTop: 2, clientWidth: 800, clientHeight: 1000 });
  assert.deepEqual(frameVoiceViewport(frame), { left: 0, top: 98, width: 800, height: 902 });
});

test('fully clipped and zero-scale frames return finite empty visible regions', () => {
  const node = fixture();
  const preview = node(100, 100, 400, 250, { overflowY: 'hidden' });
  assert.deepEqual(frameVoiceViewport(node(100, -500, 800, 1000, { scale: .5, parent: preview })), { left: 0, top: 1000, width: 800, height: 0 });
  assert.deepEqual(frameVoiceViewport(node(0, 0, 800, 1000, { scale: 0 })), { left: 0, top: 0, width: 0, height: 0 });
});
