import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile, mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { createSpaceService } from '../server/harness.mjs';
import { initialState, seedSource, seedTests } from '../server/seed.mjs';

// Recorded source from one real Astra/Ultrafast turn. The regression test reads
// it as data and runs it only through the isolated runtime, never in Node.
const source = await readFile(new URL('./fixtures/wish-garden.js', import.meta.url), 'utf8');
const tests = await readFile(new URL('./fixtures/wish-garden-checks.js', import.meta.url), 'utf8');

test('a real generated non-poll capability saves and updates actor-owned wishes while preserving prior app data', async (t) => {
  const dataDir = await mkdtemp(join(tmpdir(), 'living-garden-regression-'));
  const service = await createSpaceService({ dataDir, seedOverride: { state: initialState, source: seedSource, tests: seedTests }, adapter: {
    model: 'recorded-fixture', tier: 'fixture', keyAvailable: true,
    async respond() { return { output: [{ type: 'function_call', call_id: 'recorded-garden', name: 'apply_change', arguments: JSON.stringify({source,tests,summary:'A tiny wish garden'}) }] }; },
  } });
  t.after(async () => { await service.close(); await rm(dataDir, {recursive:true,force:true}); });
  await service.store.transact(data => {
    data.state.contributions.push({id:'existing-vote',actorId:'leo',projectId:'tidepool',points:1});
    data.state.extras.keptNote={text:'An unrelated note'};
  });
  const before=(await service.snapshot()).state;
  await service.submit('Let visitors leave and update their own short wish.');
  await service.waitForIdle();
  const generated=await service.snapshot();
  assert.equal(generated.revision.id,2);
  assert.equal(generated.revision.meta.budget,undefined,'this feature has no point budget');
  const action=(actor,text,extra={})=>service.action({actor,revisionId:2,action:{type:'saveWish',text,...extra}});
  let state=(await action('mira','  A moonlit library  ')).state;
  assert.equal(state.extras.wishGarden['visitor:mira'].text,'A moonlit library');
  state=(await action('leo','A listening garden')).state;
  const other=structuredClone(state.extras.wishGarden['visitor:leo']);
  state=(await action('mira','A library for slow Sundays')).state;
  assert.equal(Object.keys(state.extras.wishGarden).length,2);
  assert.deepEqual(state.extras.wishGarden['visitor:leo'],other);
  for(const text of ['', '  ', 'x'.repeat(181), 4, null]) await assert.rejects(action('mira',text));
  await assert.rejects(action('mira','Overwrite another person',{actorId:'leo'}));
  assert.deepEqual(state.projects,before.projects);
  assert.deepEqual(state.contributions,before.contributions);
  assert.deepEqual(state.extras.keptNote,before.extras.keptNote);
  await action('mira','<img src=x onerror=alert(1)>');
  const view=await service.snapshot('leo');
  assert.ok(view.html.includes('&lt;img src=x onerror=alert(1)&gt;'));
  assert.ok(!view.html.includes('<img src=x'));
  assert.ok(view.html.includes('A listening garden'));
});
