import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { transform } from 'esbuild';

const { code } = await transform(await readFile(new URL('../src/constellation-layout.ts', import.meta.url), 'utf8'), { loader: 'ts', format: 'esm' });
const { initialCamera, projectConstellation, positionForPerson, galaxyDrift, projectGalaxyPoint, unprojectGalaxyPoint } = await import(`data:text/javascript;base64,${Buffer.from(code).toString('base64')}`);
const irisId = 'person_8d44ad87-657a-4df8-8739-c9251f897834';
const people = ['mira', 'james', 'jake', 'erica', 'leo', irisId, 'luca', 'karen'].map(id => ({ id }));
const close = (a, b, message) => assert.ok(Math.abs(a - b) < 1e-9, `${message}: ${a} ≈ ${b}`);

// Portraits may naturally pass in front of one another while the galaxy turns.
// The opening composition still needs to be legible on the smallest canvas.
test('all demo portraits have distinct, visible hit areas on the smallest supported canvas', () => {
  const size = { width: 290, height: 420 };
  const nodes = projectConstellation(people, initialCamera, 0, size);
  for (const node of nodes) {
    assert.ok(node.x > 30 && node.x < size.width - 30, `${node.id} fits horizontally`);
    assert.ok(node.y > 65 && node.y < size.height - 90, `${node.id} clears the toolbar`);
    for (const other of nodes) if (other.id !== node.id) assert.ok(Math.hypot(node.x - other.x, node.y - other.y) > 78, `${node.id} and ${other.id} have separate hit areas`);
  }
  assert.deepEqual(positionForPerson(irisId), positionForPerson('iris'));
});

test('refreshing, adding, or reordering people preserves the existing world positions', () => {
  const all = [...people, { id: 'new-visitor-1' }, { id: 'new-visitor-2' }];
  const size = { width: 850, height: 600 };
  const a = projectConstellation(all, initialCamera, 17, size);
  const b = projectConstellation([...all].reverse(), initialCamera, 17, size);
  assert.deepEqual(a, b);
  const original = projectConstellation(people, initialCamera, 17, size);
  assert.deepEqual(original, a.filter(node => people.some(person => person.id === node.id)));
  assert.equal(new Set(a.map(node => node.id)).size, all.length);
  assert.ok(a.every(node => [node.x, node.y, node.depth].every(Number.isFinite)));
});

test('rotation changes depth, panning translates every person, and zoom remains finite', () => {
  const size = { width: 850, height: 600 };
  const base = projectConstellation(people, initialCamera, 0, size);
  const translated = projectConstellation(people, { ...initialCamera, x: 120, y: -65 }, 0, size);
  base.forEach((node, index) => { close(translated[index].x - node.x, 120, 'pan x'); close(translated[index].y - node.y, -65, 'pan y'); });
  const rotated = projectConstellation(people, { ...initialCamera, yaw: 1.4, pitch: .4 }, 0, size);
  assert.ok(rotated.every((node, index) => node.depth !== base[index].depth));
  for (const zoom of [.65, 1, 2.5]) {
    const nodes = projectConstellation(people, { ...initialCamera, yaw: 100, pitch: 1.15, zoom }, 100, size);
    assert.ok(nodes.every(node => [node.x, node.y, node.depth, node.scale].every(Number.isFinite)));
    assert.ok(nodes.every(node => node.scale >= .7 && node.scale <= 1.25));
  }
});

test('world-to-screen projection round trips at arbitrary rotation, zoom, and pan', () => {
  const sizes = [{ width: 290, height: 420 }, { width: 850, height: 600 }];
  for (const size of sizes) for (const yaw of [-7, -Math.PI / 2, 0, .9, Math.PI / 2, 5]) for (const pitch of [-1.15, 0, .7, 1.15]) for (const zoom of [.65, 1, 2.5]) {
    const camera = { ...initialCamera, yaw, pitch, zoom, x: -71, y: 133 };
    for (const person of people) {
      const world = positionForPerson(person.id);
      const projected = projectGalaxyPoint(world, camera, size);
      const restored = unprojectGalaxyPoint(projected, projected.depth, camera, size);
      for (const axis of ['x', 'y', 'z']) close(restored[axis], world[axis], `${person.id} ${axis}`);
      const pointer = { x: projected.x + 93, y: projected.y - 57 };
      const dragged = unprojectGalaxyPoint(pointer, projected.depth, camera, size);
      const after = projectGalaxyPoint(dragged, camera, size);
      close(after.x, pointer.x, 'drag follows pointer x');
      close(after.y, pointer.y, 'drag follows pointer y');
      close(after.depth, projected.depth, 'drag preserves camera depth');
    }
  }
});

test('depth crossings are continuous and never kick neighboring portraits apart', () => {
  const size = { width: 850, height: 600 };
  const pair = [{ id: 'left' }, { id: 'right' }];
  const positions = new Map([['left', { x: 0, y: 0, z: -.8 }], ['right', { x: 0, y: 0, z: .8 }]]);
  const a = projectConstellation(pair, { ...initialCamera, pitch: -1e-6 }, 0, size, positions);
  const b = projectConstellation(pair, { ...initialCamera, pitch: 1e-6 }, 0, size, positions);
  assert.ok(a[0].y < a[1].y && b[0].y > b[1].y, 'people cross naturally in depth');
  a.forEach((node, index) => assert.ok(Math.hypot(node.x - b[index].x, node.y - b[index].y) < .001));
  const exactlyAligned = projectConstellation(pair, initialCamera, 0, size, positions);
  close(exactlyAligned[0].x, exactlyAligned[1].x, 'no horizontal collision displacement');
  close(exactlyAligned[0].y, exactlyAligned[1].y, 'no vertical collision displacement');
});

test('a complete horizontal rotation preserves portrait separation instead of collapsing the disk edge-on', () => {
  const size = { width: 290, height: 420 };
  for (let step = 0; step <= 120; step++) {
    const yaw = step / 120 * Math.PI * 2;
    const nodes = projectConstellation(people, { ...initialCamera, yaw }, 0, size);
    for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
      assert.ok(Math.hypot(nodes[i].x - nodes[j].x, nodes[i].y - nodes[j].y) > 78, `${nodes[i].id} and ${nodes[j].id} remain separated at yaw ${yaw}`);
    }
    for (const pitch of [-.85, .85]) {
      const before = projectConstellation(people, { ...initialCamera, yaw, pitch }, 0, size);
      const after = projectConstellation(people, { ...initialCamera, yaw: yaw + .000001, pitch }, 0, size);
      before.forEach((node, index) => assert.ok(Math.hypot(node.x - after[index].x, node.y - after[index].y) < .001, 'tilted rotation stays continuous'));
    }
  }
});

test('ambient movement is deterministic, bounded, and does not disturb pinned people', () => {
  const size = { width: 850, height: 600 };
  for (const person of people) for (const time of [0, 1, 20, 300, 5000]) {
    const drift = galaxyDrift(person.id, time);
    assert.deepEqual(drift, galaxyDrift(person.id, time));
    assert.ok(Math.abs(drift.x) <= .036 && Math.abs(drift.y) <= .028 && Math.abs(drift.z) <= .016);
  }
  const saved = new Map([['mira', { x: .1, y: -.4, z: .6 }]]);
  const base = projectConstellation(people, initialCamera, 0, size, saved);
  const later = projectConstellation(people, initialCamera, 400, size, saved);
  assert.deepEqual(base.find(node => node.id === 'mira'), later.find(node => node.id === 'mira'));
  assert.notDeepEqual(base.find(node => node.id === 'james'), later.find(node => node.id === 'james'));
  assert.deepEqual(saved.get('mira'), { x: .1, y: -.4, z: .6 }, 'projection does not mutate saved positions');
});

test('new people occupy a shallow galactic disk instead of a spherical shell', () => {
  const points = Array.from({ length: 100 }, (_, index) => positionForPerson(`visitor-${index}`));
  assert.ok(points.every(point => Math.abs(point.z) <= .15));
  const radii = points.map(point => Math.hypot(point.x, point.y / .9));
  assert.ok(Math.max(...radii) - Math.min(...radii) > .25, 'people span multiple distances from the center');
});
