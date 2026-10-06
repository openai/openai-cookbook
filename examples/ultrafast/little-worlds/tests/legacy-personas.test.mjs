import test from 'node:test';
import assert from 'node:assert/strict';
import { seedForPersona } from './fixtures/legacy-personas.mjs';
import { compileModule, renderModule, reduceModule, verifyModule } from '../server/runtime.mjs';

for (const id of ['mira', 'james', 'jake', 'erica']) {
  test(`legacy ${id} fixture remains compatible with host and behavioral checks`, async () => {
    const seed = seedForPersona(id);
    const result = await verifyModule(seed.source, seed.tests, seed.state, {
      owner: { id, name: id }, visitor: { id: 'leo', name: 'Leo' },
    });
    assert.equal(result.ok, true, JSON.stringify(result.checks.filter(check => !check.ok)));
    assert.equal(result.meta.layout, 'canvas');
  });
}

test('Mira preserves legacy votes and arbitrary feature records', async () => {
  const seed = seedForPersona('mira');
  const state = {
    ...seed.state,
    contributions: [{ id: 'old-leo-1', actorId: 'leo', projectId: 'tidepool', points: 3 }],
    extras: { legacy: { shape: 'not an actor collection' }, guestbook: { greeting: { actorId: 'leo', text: 'Keep growing.' } } },
  };
  const result = await verifyModule(seed.source, seed.tests, state);
  assert.equal(result.ok, true, JSON.stringify(result.checks.filter(check => !check.ok)));
  const actor = { id: 'mira', name: 'Mira' };
  const next = await reduceModule(result.bundle, state, { type: 'support', projectId: 'afterhours' }, actor);
  assert.deepEqual(next.extras, state.extras);
  assert.deepEqual(next.contributions[0], state.contributions[0]);
  await assert.rejects(() => reduceModule(result.bundle, state, { type: 'support', projectId: 'tidepool' }, { id: 'leo', name: 'Leo' }), /three votes/);
});

test('Persona controls store each visitor’s preferences separately', async () => {
  const seed = seedForPersona('erica');
  const { bundle } = await compileModule(seed.source);
  const a = { id: 'visitor-a', name: 'A' };
  const b = { id: 'visitor-b', name: 'B' };
  const first = await reduceModule(bundle, seed.state, { type: 'explore', region: 'movement' }, a);
  const second = await reduceModule(bundle, first, { type: 'explore', region: 'attention' }, b);
  assert.equal(second.extras.neuralExplorer[a.id].region, 'movement');
  assert.equal(second.extras.neuralExplorer[b.id].region, 'attention');
  assert.match(await renderModule(bundle, second, a), /cerebellum/);
  assert.match(await renderModule(bundle, second, b), /frontal lobes/);
});

test('Persona lookup excludes inherited names and returns independent seed state', () => {
  assert.equal(seedForPersona('constructor'), undefined);
  assert.equal(seedForPersona('unknown'), undefined);
  const one = seedForPersona('mira');
  one.state.projects[0].title = 'Changed locally';
  assert.equal(seedForPersona('mira').state.projects[0].title, 'Fern studies');
});

test('Finance renders safe defaults for an incompatible saved scenario', async () => {
  const seed = seedForPersona('james');
  const { bundle } = await compileModule(seed.source);
  const actor = { id: 'visitor', name: 'Visitor' };
  const state = { ...seed.state, extras: { financeScenario: { visitor: { actorId: 'visitor', principal: '<img>', monthly: null, rate: 999999, years: 0 } } } };
  const html = await renderModule(bundle, state, actor);
  assert.doesNotMatch(html, /<img>|NaN|Infinity/);
  assert.match(html, /after 20 years/);
});
