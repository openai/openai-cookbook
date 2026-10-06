import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { build } from 'esbuild';

const compiled = await build({
  entryPoints: [new URL('../src/BuildProgress.tsx', import.meta.url).pathname],
  bundle: true, write: false, platform: 'node', format: 'cjs', packages: 'external',
  jsx: 'automatic', loader: { '.css': 'empty' },
});
const require = createRequire(import.meta.url);
function load(react) {
  const module = { exports: {} };
  new Function('module', 'exports', 'require', compiled.outputFiles[0].text)(module, module.exports,
    name => name === 'react' && react ? react : require(name));
  return module.exports;
}
const { default: BuildProgress, deriveBuildProgress } = load();
const base = { status: 'ready', expectedOutputTokens: 1000, outputTokens: 0, laneStatus: 'running', tier: 'ultrafast' };
const derive = props => deriveBuildProgress({ ...base, ...props });
const render = props => renderToStaticMarkup(createElement(BuildProgress, { ...base, ...props }));

function find(node, predicate) {
  if (!node || typeof node !== 'object') return undefined;
  if (predicate(node)) return node;
  for (const child of [node.props?.children].flat()) {
    const found = find(child, predicate);
    if (found) return found;
  }
}

function fixture() {
  const slots = [];
  let cursor = 0, dirty = false;
  const Component = load({ useState(initial) {
    const index = cursor++;
    slots[index] ??= typeof initial === 'function' ? initial() : initial;
    return [slots[index], value => { slots[index] = value; dirty = true; }];
  } }).default;
  return props => {
    let element, attempts = 0;
    do {
      assert.ok(attempts++ < 10, 'state updates settle');
      dirty = false; cursor = 0;
      element = Component({ ...base, ...props });
    } while (dirty);
    return {
      state: element.props['data-progress-state'],
      estimate: element.props['data-expected-output-tokens'],
      basis: element.props['data-progress-basis'],
      track: find(element, node => node.props?.role === 'progressbar').props,
      fill: find(element, node => node.props?.className === 'build-progress-fill').props.style.transform,
      highlight: !!find(element, node => node.props?.className === 'build-progress-highlight'),
    };
  };
}

test('estimated output reserves the last part of the bar for successful completion', () => {
  assert.equal(derive({ outputTokens: 0 }).value, 0);
  assert.equal(derive({ outputTokens: 500 }).value, .45);
  assert.equal(derive({ outputTokens: 1000 }).value, .9);
  const over = derive({ outputTokens: 2000 });
  assert.ok(over.value > .9 && over.value < .95);
  assert.ok(derive({ outputTokens: Number.MAX_VALUE }).value < 1);
  assert.equal(derive({ outputTokens: 0, laneStatus: 'completed' }).value, 1);
});

test('ready and fallback estimates follow the same measured output', () => {
  assert.deepEqual(derive({ status: 'fallback', outputTokens: 800 }), derive({ outputTokens: 800 }));
  const current = derive({ status: 'pending', outputTokens: 800, expectedOutputTokens: undefined });
  assert.equal(current.value, 0);
  assert.equal(current.indeterminate, true);
  assert.equal(current.state, 'pending');
});

test('pending snapshots cannot introduce a budget until the estimator resolves', () => {
  assert.equal(derive({ status: 'pending', expectedOutputTokens: 1000 }).indeterminate, true);
  const update = fixture();
  const pending = update({ status: 'pending', expectedOutputTokens: 500, outputTokens: 300 });
  assert.equal(pending.state, 'pending');
  assert.equal(pending.estimate, undefined);
  assert.equal(pending.track['aria-valuenow'], undefined);
  const ready = update({ status: 'fallback', expectedOutputTokens: 1000, outputTokens: 300 });
  assert.equal(ready.estimate, 1000);
  assert.equal(ready.track['aria-valuenow'], 27);
  const replay = update({ status: 'pending', expectedOutputTokens: 500, outputTokens: 400 });
  assert.equal(replay.state, 'active');
  assert.equal(replay.estimate, 1000);
  assert.equal(replay.track['aria-valuenow'], 36);
});

test('invalid or missing estimates remain indeterminate only while the lane is active', () => {
  for (const expectedOutputTokens of [undefined, 0, -100, NaN, Infinity, -Infinity]) {
    for (const laneStatus of ['preparing', 'running']) {
      assert.equal(derive({ expectedOutputTokens, laneStatus }).indeterminate, true);
    }
    for (const laneStatus of ['completed', 'failed', 'cancelled']) {
      const result = derive({ expectedOutputTokens, laneStatus });
      assert.equal(result.indeterminate, false);
      assert.equal(result.state, laneStatus);
      assert.equal(result.value, laneStatus === 'completed' ? 1 : 0);
    }
  }
});

test('invalid output never produces invalid fill or accessibility values', () => {
  for (const outputTokens of [NaN, Infinity, -Infinity, -20]) {
    assert.equal(derive({ outputTokens }).value, 0);
    const html = render({ outputTokens });
    assert.match(html, /aria-valuenow="0"/);
    assert.doesNotMatch(html, /NaN|Infinity/);
  }
});

test('failed and cancelled lanes keep partial progress without completion or shimmer', () => {
  for (const laneStatus of ['failed', 'cancelled']) {
    const result = derive({ outputTokens: 600, laneStatus });
    assert.equal(result.value, .54);
    assert.equal(result.indeterminate, false);
    const html = render({ outputTokens: 600, laneStatus });
    assert.match(html, new RegExp(`data-progress-state="${laneStatus}"`));
    assert.match(html, /scaleX\(0\.54\)/);
    assert.doesNotMatch(html, /build-progress-highlight|Build complete|data-progress-state="completed"/);
  }
});

test('accessible progress identifies each lane without displaying numeric percentages', () => {
  for (const [tier, label] of [['ultrafast', 'Ultrafast'], ['standard', 'Standard']]) {
    const html = render({ tier, outputTokens: 500 });
    assert.match(html, new RegExp(`aria-label="${label} build progress"`));
    assert.match(html, /aria-valuenow="45"/);
    assert.equal(html.replace(/<[^>]*>/g, ''), 'Build progress');
  }
  const pending = render({ status: 'pending', expectedOutputTokens: undefined });
  assert.doesNotMatch(pending, /aria-valuenow=/);
  assert.match(pending, /build-progress-highlight/);
});

test('replayed output and revised or missing estimates cannot move an accepted bar backward', () => {
  const update = fixture();
  assert.equal(update({ status: 'pending', expectedOutputTokens: undefined, outputTokens: 100 }).highlight, true);
  assert.equal(update({ outputTokens: 100 }).track['aria-valuenow'], 9);
  const progressed = update({ outputTokens: 300 });
  assert.equal(progressed.fill, 'scaleX(0.27)');
  assert.equal(update({ expectedOutputTokens: 2000, outputTokens: 100 }).fill, progressed.fill);
  assert.equal(update({ expectedOutputTokens: 100, outputTokens: NaN }).fill, progressed.fill);
  assert.equal(update({ status: 'fallback', expectedOutputTokens: undefined, outputTokens: 400 }).track['aria-valuenow'], 36);
  assert.equal(update({ outputTokens: Infinity, laneStatus: 'failed' }).track['aria-valuenow'], 36);
});

test('a fresh mounted comparison resets completion and the accepted estimate', () => {
  const previous = fixture();
  assert.equal(previous({ laneStatus: 'completed' }).track['aria-valuenow'], 100);
  const next = fixture();
  const pending = next({ status: 'pending', expectedOutputTokens: undefined });
  assert.equal(pending.state, 'pending');
  assert.equal(pending.track['aria-valuenow'], undefined);
  assert.equal(next({ expectedOutputTokens: 2000, outputTokens: 1000 }).track['aria-valuenow'], 45);
});

test('successful completion survives stale active props without marking failed lanes successful', () => {
  const update = fixture();
  assert.equal(update({ outputTokens: 400 }).track['aria-valuenow'], 36);
  assert.equal(update({ laneStatus: 'completed', outputTokens: 600 }).state, 'completed');
  for (const laneStatus of ['running', 'preparing']) {
    const replay = update({ status: 'pending', expectedOutputTokens: undefined, laneStatus, outputTokens: 100 });
    assert.equal(replay.state, 'completed');
    assert.equal(replay.track['aria-valuenow'], 100);
    assert.equal(replay.highlight, false);
  }
  for (const laneStatus of ['failed', 'cancelled']) {
    const failed = fixture();
    assert.equal(failed({ laneStatus, outputTokens: 400 }).state, laneStatus);
    const finalTelemetry = failed({ laneStatus, outputTokens: 600 });
    assert.equal(finalTelemetry.state, laneStatus);
    assert.equal(finalTelemetry.track['aria-valuenow'], 54);
    assert.equal(finalTelemetry.highlight, false);
  }
});

test('the completed Ultrafast output calibrates an overestimated Standard build', () => {
  const update = fixture();
  const props = { tier: 'standard', expectedOutputTokens: 2000, outputTokens: 600 };
  assert.equal(update(props).track['aria-valuenow'], 27);
  const calibrated = update({ ...props, completedReferenceTokens: 1000 });
  assert.equal(calibrated.estimate, 1000);
  assert.equal(calibrated.basis, 'ultrafast');
  assert.equal(calibrated.track['aria-valuenow'], 54);
  assert.equal(update({ ...props, completedReferenceTokens: 1000, outputTokens: 1000 }).track['aria-valuenow'], 90);
  assert.equal(update({ ...props, laneStatus: 'completed' }).track['aria-valuenow'], 100);
});

test('calibrating an underestimated Standard build never moves its bar backward', () => {
  const update = fixture();
  const props = { tier: 'standard', expectedOutputTokens: 1000, outputTokens: 600 };
  assert.equal(update(props).track['aria-valuenow'], 54);
  const calibrated = update({ ...props, completedReferenceTokens: 2000 });
  assert.equal(calibrated.estimate, 2000, 'the real completed reference replaces the smaller estimate');
  assert.equal(calibrated.track['aria-valuenow'], 54, 'previously displayed progress is retained');
  assert.equal(update({ ...props, completedReferenceTokens: 2000, outputTokens: 1600 }).track['aria-valuenow'], 72);
});

test('a completed peer supplies progress while the initial estimator is still pending', () => {
  const update = fixture();
  const props = { tier: 'standard', status: 'pending', expectedOutputTokens: undefined, outputTokens: 400 };
  assert.equal(update(props).highlight, true);
  const calibrated = update({ ...props, completedReferenceTokens: 1000 });
  assert.equal(calibrated.state, 'active');
  assert.equal(calibrated.track['aria-valuenow'], 36);
  assert.equal(calibrated.highlight, false);
  const lateEstimate = update({ ...props, status: 'ready', expectedOutputTokens: 5000, outputTokens: 500 });
  assert.equal(lateEstimate.estimate, 1000, 'a late estimator result cannot undo the observed reference');
  assert.equal(lateEstimate.track['aria-valuenow'], 45);
});

test('invalid, stale, and missing reference snapshots cannot corrupt a Standard calibration', () => {
  const update = fixture();
  const props = { tier: 'standard', expectedOutputTokens: 3000, outputTokens: 500 };
  for (const completedReferenceTokens of [undefined, 0, -1, NaN, Infinity, -Infinity]) {
    const result = update({ ...props, completedReferenceTokens });
    assert.equal(result.estimate, 3000);
    assert.equal(result.track['aria-valuenow'], 15);
  }
  assert.equal(update({ ...props, completedReferenceTokens: 1000 }).track['aria-valuenow'], 45);
  const finalTelemetry = update({ ...props, completedReferenceTokens: 1200 });
  assert.equal(finalTelemetry.estimate, 1200, 'late final telemetry can increase the observed peer output');
  assert.equal(finalTelemetry.track['aria-valuenow'], 45);
  for (const completedReferenceTokens of [undefined, 0, NaN, Infinity, 900]) {
    const replay = update({ ...props, status: 'pending', expectedOutputTokens: undefined, completedReferenceTokens });
    assert.equal(replay.estimate, 1200);
    assert.equal(replay.basis, 'ultrafast');
    assert.equal(replay.track['aria-valuenow'], 45);
  }
  assert.equal(update({ ...props, outputTokens: 1000 }).track['aria-valuenow'], 75);
});

test('the Ultrafast lane never calibrates itself from peer output', () => {
  const update = fixture();
  const props = { expectedOutputTokens: 2000, outputTokens: 600 };
  const baseline = update(props);
  const ignored = update({ ...props, completedReferenceTokens: 500 });
  assert.equal(ignored.estimate, baseline.estimate);
  assert.equal(ignored.fill, baseline.fill);
  assert.equal(ignored.basis, 'estimate');
  const pending = fixture()({ ...props, status: 'pending', completedReferenceTokens: 500 });
  assert.equal(pending.highlight, true);
  assert.equal(pending.estimate, undefined);
});

test('actual verification and publication advance short builds without claiming completion', () => {
  for (const tier of ['ultrafast', 'standard']) {
    const update = fixture();
    const props = { tier, expectedOutputTokens: 2000, outputTokens: 100 };
    assert.equal(update(props).track['aria-valuenow'], 5);
    assert.equal(update({ ...props, phase: 'verify' }).track['aria-valuenow'], 90);
    assert.equal(update({ ...props, phase: 'build', outputTokens: 150 }).track['aria-valuenow'], 90,
      'a repair pass cannot erase already displayed verification progress');
    const publishing = update({ ...props, phase: 'publish' });
    assert.equal(publishing.state, 'active');
    assert.equal(publishing.track['aria-valuenow'], 97);
    assert.equal(update({ ...props, phase: 'build' }).track['aria-valuenow'], 97);
    assert.equal(update({ ...props, laneStatus: 'completed' }).track['aria-valuenow'], 100);
  }
  for (const [phase, expected] of [['verify', .9], ['publish', .97]]) {
    const result = derive({ status: 'pending', expectedOutputTokens: undefined, phase });
    assert.equal(result.indeterminate, false);
    assert.equal(result.state, 'active');
    assert.equal(result.value, expected);
  }
});

test('a new comparison starts without the previous peer calibration or milestone floor', () => {
  const old = fixture();
  const props = { tier: 'standard', completedReferenceTokens: 1000, phase: 'publish' };
  assert.equal(old(props).track['aria-valuenow'], 97);
  assert.equal(old({ ...props, laneStatus: 'completed' }).track['aria-valuenow'], 100);
  const next = fixture();
  assert.equal(next({ tier: 'standard', status: 'pending', expectedOutputTokens: undefined }).highlight, true);
  const estimated = next({ tier: 'standard', expectedOutputTokens: 2000, outputTokens: 500 });
  assert.equal(estimated.basis, 'estimate');
  assert.equal(estimated.estimate, 2000);
  assert.equal(estimated.track['aria-valuenow'], 23);
});

test('failed and cancelled Standard runs reject new calibration but retain late output telemetry', () => {
  for (const laneStatus of ['failed', 'cancelled']) {
    const update = fixture();
    const props = { tier: 'standard', expectedOutputTokens: 1000, outputTokens: 400 };
    assert.equal(update(props).track['aria-valuenow'], 36);
    const stopped = update({ ...props, laneStatus, completedReferenceTokens: 500 });
    assert.equal(stopped.state, laneStatus);
    assert.equal(stopped.estimate, 1000);
    assert.equal(stopped.track['aria-valuenow'], 36);
    const lateTelemetry = update({ ...props, laneStatus, outputTokens: 600, completedReferenceTokens: 300 });
    assert.equal(lateTelemetry.track['aria-valuenow'], 54);
    assert.equal(lateTelemetry.basis, 'estimate');
    assert.equal(lateTelemetry.highlight, false);
    const calibrated = fixture();
    assert.equal(calibrated({ ...props, completedReferenceTokens: 500 }).track['aria-valuenow'], 72);
    const preserved = calibrated({ ...props, laneStatus, completedReferenceTokens: 2000 });
    assert.equal(preserved.estimate, 500);
    assert.equal(preserved.track['aria-valuenow'], 72);
    assert.equal(preserved.state, laneStatus);
  }
});

test('calibration and milestone details do not introduce additional visible copy', () => {
  for (const phase of ['build', 'verify', 'publish']) {
    const html = render({ tier: 'standard', completedReferenceTokens: 600, outputTokens: 200, phase });
    assert.equal(html.replace(/<[^>]*>/g, ''), 'Build progress');
    assert.match(html, /aria-label="Standard build progress"/);
    assert.doesNotMatch(html, /NaN|Infinity/);
  }
});
