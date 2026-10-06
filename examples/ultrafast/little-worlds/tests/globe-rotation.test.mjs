import test from 'node:test';
import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';
import { Quaternion, Vector3 } from 'three';

const compiled = await build({
  entryPoints: [fileURLToPath(new URL('../src/globe-rotation.ts', import.meta.url))],
  bundle: true, write: false, format: 'esm', platform: 'node', target: 'node22', logLevel: 'silent',
});
const { createGlobeRotation } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString('base64')}`);
const identity = new Quaternion();
const terminalSpeed = Math.PI * 2 / 60;
const near = (actual, expected, epsilon = 1e-7) => assert.ok(Math.abs(actual - expected) < epsilon, `${actual} should be near ${expected}`);
const sameOrientation = (actual, expected, epsilon = 1e-7) => near(1 - Math.abs(actual.dot(expected)), 0, epsilon);

function flick(vertical = 0) {
  const rotation = createGlobeRotation();
  rotation.begin(0, 0, 0, identity);
  rotation.drag(0.15, vertical / 2, 25);
  rotation.drag(0.3, vertical, 50);
  rotation.end(50);
  return rotation;
}

function turnOver(rotation, seconds, allowMotion = true) {
  const before = rotation.quaternion.clone();
  rotation.step(seconds, allowMotion);
  return rotation.quaternion.angleTo(before);
}

function assertGentleRestart(rotation) {
  const firstTurn = turnOver(rotation, 0.25);
  assert.ok(firstTurn > 0, 'cruise should restart without another interaction');
  assert.ok(firstTurn < terminalSpeed * 0.25 * 0.2, 'cruise should ease in from rest');
  assert.equal(rotation.moving, false, 'resuming cruise must not revive a flick');
}

test('the grabbed surface follows horizontal and vertical screen motion', () => {
  for (const [x, y] of [[0.4, 0], [-0.4, 0], [0, 0.4], [0, -0.4]]) {
    const rotation = createGlobeRotation();
    rotation.begin(0, 0, 0, identity);
    rotation.drag(x, y, 30);
    const front = new Vector3(0, 0, 1).applyQuaternion(rotation.quaternion);
    near(front.x, x);
    near(front.y, y);
    assert.equal(rotation.dragging, true);
  }
});

test('camera-relative dragging preserves the grabbed direction when the camera is tilted', () => {
  const camera = new Quaternion().setFromAxisAngle(new Vector3(0, 0, 1), Math.PI / 3);
  const frozenCamera = camera.clone();
  const rotation = createGlobeRotation();
  rotation.begin(0, 0, 0, camera);
  camera.identity();
  rotation.drag(0.4, 0.2, 30);
  const front = new Vector3(0, 0, 1).applyQuaternion(rotation.quaternion).applyQuaternion(frozenCamera.invert());
  near(front.x, 0.4);
  near(front.y, 0.2);
});

test('trackball remains finite and normalized across the silhouette and far outside it', () => {
  const rotation = createGlobeRotation();
  rotation.begin(0, 0, 0, identity);
  const points = [[0.7, 0], [0.71, 0], [1, 0], [5, 9], [-20, 3], [1e300, -1e300], [0, 0]];
  for (let index = 0; index < 100; index++) {
    rotation.drag(...points[index % points.length], (index + 1) * 16);
    assert.ok(rotation.quaternion.toArray().every(Number.isFinite));
    near(rotation.quaternion.length(), 1);
  }
  const before = rotation.quaternion.clone();
  rotation.drag(Infinity, NaN, 2000);
  sameOrientation(rotation.quaternion, before);
});

test('an untouched globe cruises slowly and grabbing it immediately suspends all motion', () => {
  const rotation = createGlobeRotation();
  near(turnOver(rotation, 2), terminalSpeed * 2);
  assert.equal(rotation.moving, false);
  rotation.begin(0, 0, 0, identity);
  const held = rotation.quaternion.clone();
  rotation.step(5);
  sameOrientation(rotation.quaternion, held);
  assert.equal(rotation.dragging, true);
});

test('release accelerates smoothly from rest toward terminal cruise without overshooting', () => {
  const rotation = createGlobeRotation();
  rotation.begin(0, 0, 0, identity);
  rotation.end(100);
  let previousSpeed = 0;
  for (let interval = 0; interval < 40; interval++) {
    const speed = turnOver(rotation, 0.25) / 0.25;
    assert.ok(speed > previousSpeed, 'cruise speed should increase monotonically');
    assert.ok(speed < terminalSpeed, 'cruise should approach terminal speed without overshoot');
    if (interval === 0) assert.ok(speed < terminalSpeed * 0.2);
    previousSpeed = speed;
  }
  assert.ok(previousSpeed > terminalSpeed * 0.99, 'cruise should reach its steady pace');
  const front = new Vector3(0, 0, 1).applyQuaternion(rotation.quaternion);
  assert.ok(front.x > 0);
  near(front.y, 0);
});

test('a released flick decays into continued cruise identically at different frame rates', () => {
  const rotations = [30, 60, 120].map(fps => {
    const rotation = flick();
    const before = rotation.quaternion.clone();
    assert.equal(rotation.moving, true);
    rotation.step(1 / fps);
    assert.ok(rotation.quaternion.y > before.y);
    for (let frame = 1; frame < fps * 10; frame++) rotation.step(1 / fps);
    assert.equal(rotation.moving, false);
    const continuingTurn = turnOver(rotation, 1);
    assert.ok(continuingTurn > terminalSpeed * 0.7);
    assert.ok(continuingTurn < terminalSpeed * 1.05);
    rotation.step(20);
    near(turnOver(rotation, 1), terminalSpeed, 1e-6);
    return rotation;
  });
  sameOrientation(rotations[0].quaternion, rotations[1].quaternion);
  sameOrientation(rotations[1].quaternion, rotations[2].quaternion);
});

test('mixed-axis flicks and the returning cruise compose consistently across frame rates', () => {
  const orientations = [30, 60, 120].map(fps => {
    const rotation = flick(0.24);
    for (let frame = 0; frame < fps * 10; frame++) rotation.step(1 / fps);
    assert.equal(rotation.moving, false);
    near(rotation.quaternion.length(), 1);
    return rotation.quaternion;
  });
  sameOrientation(orientations[0], orientations[1]);
  sameOrientation(orientations[1], orientations[2]);
});

test('a deliberate long hold before release does not revive an old flick', () => {
  const rotation = createGlobeRotation();
  rotation.begin(0, 0, 0, identity);
  rotation.drag(0.5, 0, 30);
  rotation.end(800);
  assertGentleRestart(rotation);
});

test('a firm throw carries for several seconds and slows smoothly into the resting spin', () => {
  const rotation = flick();
  let previousSpeed = Infinity;
  for (let interval = 0; interval < 60; interval++) {
    const speed = turnOver(rotation, 0.25) / 0.25;
    assert.ok(speed < previousSpeed, 'the throw should lose speed gradually');
    assert.ok(speed > terminalSpeed, 'a forward throw should approach cruise without stopping or dipping below it');
    if (interval === 3) assert.ok(speed > 2, 'momentum should remain clearly visible after one second');
    if (interval === 11) assert.ok(speed > terminalSpeed * 5, 'the globe should still carry the throw after three seconds');
    previousSpeed = speed;
  }
  near(previousSpeed, terminalSpeed, 0.001);
});

test('a normal release delay does not erase a fresh throw', () => {
  const immediate = flick();
  const delayed = createGlobeRotation();
  delayed.begin(0, 0, 0, identity);
  delayed.drag(0.15, 0, 25);
  delayed.drag(0.3, 0, 50);
  delayed.end(115);
  assert.equal(delayed.moving, true);
  immediate.step(0.25);
  delayed.step(0.25);
  sameOrientation(delayed.quaternion, immediate.quaternion);
});

test('a brief release pause keeps momentum even when stationary moves are delivered', () => {
  const rotation = createGlobeRotation();
  rotation.begin(0, 0, 0, identity);
  rotation.drag(0.15, 0, 25);
  rotation.drag(0.3, 0, 50);
  for (const time of [80, 110, 160, 220, 300]) rotation.drag(0.3, 0, time);
  rotation.end(300);
  assert.equal(rotation.moving, true);
  assert.ok(turnOver(rotation, 0.25) > 0.8, 'a normal pause at release must retain a substantial throw');
});

test('holding before a short drag does not dilute the throw across the whole hold', () => {
  const rotation = createGlobeRotation();
  rotation.begin(0, 0, 0, identity);
  rotation.drag(0.3, 0, 5000);
  rotation.end(5020);
  assert.equal(rotation.moving, true);
  assert.ok(turnOver(rotation, 0.25) > 0.4, 'only recent movement should determine release speed');
});

test('a final movement delivered at release carries momentum after a long grab', () => {
  const rotation = createGlobeRotation();
  rotation.begin(0, 0, 0, identity);
  rotation.drag(0.25, 0.1, 3000);
  rotation.end(3000);
  assert.equal(rotation.moving, true);
  assert.ok(turnOver(rotation, 0.25) > 0.35);
});

test('rounded timestamps and duplicate pointer events preserve the release velocity', () => {
  const reference = flick();
  const rounded = createGlobeRotation();
  rounded.begin(0, 0, 0, identity);
  rounded.drag(0.15, 0, 25);
  rounded.drag(0.2, 0, 50);
  rounded.drag(0.3, 0, 50);
  rounded.drag(0.3, 0, 50);
  rounded.end(50);
  assert.equal(rounded.moving, true);
  reference.step(0.5);
  rounded.step(0.5);
  sameOrientation(rounded.quaternion, reference.quaternion);
});

test('out-of-order pointer events cannot reverse or discard an ongoing throw', () => {
  const reference = flick();
  const rotation = createGlobeRotation();
  rotation.begin(0, 0, 0, identity);
  rotation.drag(0.15, 0, 25);
  rotation.drag(0.3, 0, 50);
  rotation.drag(-0.8, 0.5, 20);
  rotation.end(50);
  reference.step(0.5);
  rotation.step(0.5);
  sameOrientation(rotation.quaternion, reference.quaternion);
});

test('regrabbing a moving globe and cancelling preserve orientation without a jump', () => {
  const rotation = flick();
  rotation.step(0.2);
  const before = rotation.quaternion.clone();
  rotation.begin(-0.7, 0.2, 300, identity);
  sameOrientation(rotation.quaternion, before);
  rotation.step(1);
  sameOrientation(rotation.quaternion, before);
  rotation.drag(-0.7, 0.2, 320);
  sameOrientation(rotation.quaternion, before);
  rotation.cancel();
  assert.equal(rotation.dragging, false);
  assert.equal(rotation.moving, false);
  sameOrientation(rotation.quaternion, before);
  assertGentleRestart(rotation);
});

test('reduced motion freezes autonomous rotation but preserves direct manipulation and gentle reenable', () => {
  const rotation = flick();
  rotation.step(0, false);
  const before = rotation.quaternion.clone();
  rotation.step(5, false);
  sameOrientation(rotation.quaternion, before);
  assert.equal(rotation.moving, false);
  rotation.begin(0, 0, 100, identity);
  rotation.drag(0.5, 0, 130);
  assert.ok(rotation.quaternion.angleTo(before) > 0.1);
  rotation.end(130);
  const afterDrag = rotation.quaternion.clone();
  rotation.step(5, false);
  assert.equal(rotation.moving, false);
  sameOrientation(rotation.quaternion, afterDrag);
  assertGentleRestart(rotation);
});

test('reduced motion also prevents initial cruise before any interaction', () => {
  const rotation = createGlobeRotation();
  rotation.step(20, false);
  sameOrientation(rotation.quaternion, identity);
  assertGentleRestart(rotation);
});

test('keyboard nudges rotate predictably and discard any existing flick', () => {
  const rotation = flick();
  rotation.nudge(0.1, 0.1);
  assertGentleRestart(rotation);
  const direct = createGlobeRotation();
  direct.nudge(0.1, 0.1);
  const front = new Vector3(0, 0, 1).applyQuaternion(direct.quaternion);
  assert.ok(front.x > 0 && front.y > 0);
});
