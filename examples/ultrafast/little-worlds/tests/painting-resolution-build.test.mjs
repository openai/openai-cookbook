import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createSpaceService } from '../server/harness.mjs';
import { paintingProposal } from './fixtures/painting/index.mjs';

const owner = { id: 'iris', name: 'Iris' };
const visitor = { id: 'leo', name: 'Leo' };
const pixelData = html => html.match(/data-paint-pixels="([^"]*)"/)[1];
const paint = (columns, rows, cell, color) => ({ type: 'paint_pixels', columns, rows, cells: [{ cell, color }] });
const dimensionsPatch = (fromColumns, fromRows, columns, rows) => [
  '*** Begin Patch',
  '*** Update File: space.js',
  '@@',
  `-const COLUMNS = ${fromColumns};`,
  `+const COLUMNS = ${columns};`,
  `-const ROWS = ${fromRows};`,
  `+const ROWS = ${rows};`,
  '*** End Patch',
].join('\n');

function assertSurface(snapshot, columns, rows) {
  assert.equal(snapshot.session.lastOutcome, 'completed');
  assert.equal((snapshot.html.match(/<canvas\b/g) || []).length, 1);
  assert.equal(snapshot.html.includes('data-paint-cell='), false);
  assert.match(snapshot.html, new RegExp(`width="${columns}" height="${rows}"`));
  assert.ok(snapshot.html.includes('aspect-ratio:3/2'), 'Increasing pixel density preserves the authored physical aspect ratio');
  assert.equal(pixelData(snapshot.html).length, columns * rows);
  assert.ok(snapshot.html.length < 180000, 'The complete higher-resolution world stays within the unchanged HTML limit');
  const properties = snapshot.revision.meta.agent.actions[0].parameters.properties;
  assert.deepEqual(properties.columns, { type: 'integer', minimum: columns, maximum: columns });
  assert.deepEqual(properties.rows, { type: 'integer', minimum: rows, maximum: rows });
  assert.equal(properties.cells.items.properties.cell.maximum, columns * rows - 1);
  assert.ok(snapshot.revision.checks.length >= 4 && snapshot.revision.checks.every(check => check.ok), 'Real host and generated feature checks pass before publication');
}

test('successive owner builder patches double the painting resolution, preserve all records, and keep visitor drawing correct', { timeout: 60000 }, async t => {
  const dataDir = await mkdtemp(join(tmpdir(), 'little-worlds-resolution-build-'));
  let service;
  t.after(async () => { await service?.close(); await rm(dataDir, { recursive: true, force: true }); });
  const proposal = await paintingProposal();
  const legacyState = {
    projects: [], contributions: [],
    extras: {
      canvas: {
        iris: { actorId: 'iris', color: 1, marks: { 0: [1, 1], 49: [4, 2], 1535: [2, 3] } },
        leo: { actorId: 'leo', color: 0, marks: { 49: [0, 4] } },
      },
      notes: { keep: { actorId: 'somebody-else', text: 'This unrelated record must survive every build and stroke.' } },
    },
  };
  const requests = [];
  const steps = [
    { fromColumns: 48, fromRows: 32, columns: 96, rows: 64, request: 'Double the resolution of this canvas, keeping the same physical size. Make every pixel smaller.' },
    { fromColumns: 96, fromRows: 64, columns: 192, rows: 128, request: 'Double the resolution again. Keep the canvas the same size and preserve everyone’s painting.' },
  ];
  service = await createSpaceService({
    dataDir, owner, actors: [owner, visitor],
    seedOverride: { source: proposal.source, tests: proposal.tests, state: legacyState },
    adapter: {
      model: 'local-resolution-fixture', tier: 'ultrafast', keyAvailable: true,
      async respond(request) {
        const step = steps[requests.length];
        assert.ok(step, 'A successful dimensions-only patch needs no repair model calls');
        requests.push(request);
        const input = JSON.stringify(request.input);
        assert.ok(input.includes(step.request), 'The ordinary owner request reaches the builder');
        assert.ok(input.includes(`const COLUMNS = ${step.fromColumns};`), 'The builder receives the current published source');
        return { output: [{ type: 'custom_tool_call', id: `ctc-resolution-${step.columns}`, call_id: `resolution-${step.columns}`, name: 'apply_patch', input: dimensionsPatch(step.fromColumns, step.fromRows, step.columns, step.rows) }] };
      },
    },
  });
  const original = await service.snapshot();
  assert.equal(original.revision.id, 1);
  assert.equal(pixelData(original.html).length, 48 * 32);
  assert.deepEqual(original.state, legacyState);
  const originalStateJson = JSON.stringify(original.state);

  await service.submit(steps[0].request);
  await service.waitForIdle();
  const first = await service.snapshot();
  assertSurface(first, 96, 64);
  assert.equal(first.revision.id, 2);
  assert.equal(first.revision.source, proposal.source.replace('const COLUMNS = 48;', 'const COLUMNS = 96;').replace('const ROWS = 32;', 'const ROWS = 64;'));
  assert.equal(first.revision.tests, proposal.tests, 'Dimensions derive from metadata, so the original feature tests remain valid');
  assert.equal(JSON.stringify(first.state), originalStateJson, 'Code publication preserves every legacy record exactly');
  for (const cell of [0, 1, 96, 97]) assert.equal(pixelData(first.html)[cell], '1', 'The original upper-left pixel retains its footprint');
  for (const cell of [194, 195, 290, 291]) assert.equal(pixelData(first.html)[cell], '0', 'The newer visitor mark still wins at the original relative location');

  await service.action({ actor: visitor.id, revisionId: 2, action: paint(96, 64, 6143, 6) });
  const painted = await service.snapshot(visitor.id);
  assert.equal(pixelData(painted.html)[6143], '6', 'A visitor can paint the exact new bottom-right edge');
  assert.deepEqual(painted.state.extras.canvas.iris, legacyState.extras.canvas.iris);
  assert.deepEqual(painted.state.extras.notes, legacyState.extras.notes);
  assert.deepEqual(painted.state.extras.canvas.leo.planes.map(plane => [plane.columns, plane.rows]), [[48, 32], [96, 64]], 'The acting visitor keeps both coordinate systems');
  const stateBeforeSecondBuild = JSON.stringify(painted.state);

  await service.submit(steps[1].request);
  await service.waitForIdle();
  const second = await service.snapshot(visitor.id);
  assertSurface(second, 192, 128);
  assert.equal(second.revision.id, 3);
  assert.equal(second.revision.source, proposal.source.replace('const COLUMNS = 48;', 'const COLUMNS = 192;').replace('const ROWS = 32;', 'const ROWS = 128;'));
  assert.equal(second.revision.tests, proposal.tests);
  assert.equal(JSON.stringify(second.state), stateBeforeSecondBuild, 'A second real publication also leaves saved artwork byte-identical');
  const secondPixels = pixelData(second.html);
  for (const row of [0, 1, 2, 3]) for (const column of [0, 1, 2, 3]) assert.equal(secondPixels[row * 192 + column], '1');
  for (const row of [126, 127]) for (const column of [190, 191]) assert.equal(secondPixels[row * 192 + column], '6', 'The new 96×64 edge mark becomes the corresponding 2×2 block');

  await assert.rejects(service.action({ actor: visitor.id, revisionId: 2, action: paint(96, 64, 6143, 3) }), /space just changed/);
  await assert.rejects(service.action({ actor: visitor.id, revisionId: 3, action: paint(96, 64, 6143, 3) }), /resolution changed/);
  assert.equal(JSON.stringify((await service.snapshot()).state), stateBeforeSecondBuild, 'Both stale revision and stale dimensions are rejected without changing data');
  await service.action({ actor: owner.id, revisionId: 3, action: paint(192, 128, 24575, 5) });
  const final = await service.snapshot();
  assert.equal(pixelData(final.html)[24575], '5');
  assert.equal(pixelData(final.html)[24574], '6', 'Only one fine-resolution pixel changes');
  assert.deepEqual(final.state.extras.canvas.leo, painted.state.extras.canvas.leo, 'The owner stroke preserves the visitor layer exactly');
  assert.deepEqual(final.state.extras.notes, legacyState.extras.notes);
  assert.equal(requests.length, 2);
  assert.equal(final.events.filter(event => event.type === 'revision.published').length, 2);
  assert.equal(final.events.filter(event => event.type === 'tool.completed' && event.data?.tool === 'verify_workspace').length, 2);
  const history = service.store.read();
  assert.equal(history.session.turns.length, 2);
  assert.ok(history.session.turns.every(turn => turn.status === 'completed'));
  for (const step of steps) {
    const output = history.session.items.find(item => item.type === 'custom_tool_call_output' && item.call_id === `resolution-${step.columns}`);
    assert.ok(output, 'The successful publication is recorded as a tool result');
    assert.equal(JSON.parse(output.output).ok, true);
  }
  const lastWorkspace = join(dataDir, 'workspaces', history.session.turns.at(-1).id);
  assert.equal(await readFile(join(lastWorkspace, 'tests.js'), 'utf8'), proposal.tests);
  assert.equal(await readFile(join(lastWorkspace, 'space.js'), 'utf8'), second.revision.source);
});
