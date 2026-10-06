import test from 'node:test';
import assert from 'node:assert/strict';
import { arcadeProposal } from '../server/arcade/index.mjs';
import { verifyModule } from '../server/runtime.mjs';

test('Karen’s complete four-game canvas passes ordinary owner and visitor publication', async () => {
  const proposal = await arcadeProposal();
  assert.ok(Buffer.byteLength(proposal.source) < 80_000);
  const state = { projects: [], contributions: [], extras: { notes: { other: { actorId: 'other', text: 'Keep me' } } } };
  const before = structuredClone(state);
  const verified = await verifyModule(proposal.source, proposal.tests, state, {
    owner: { id: 'karen', name: 'Karen' }, visitor: { id: 'visitor', name: 'Visitor' },
  });
  assert.equal(verified.ok, true, JSON.stringify(verified.checks.filter(check => !check.ok)));
  assert.deepEqual(state, before);
  assert.deepEqual(verified.meta.games.map(game => game.id), ['pacman', 'space-invaders', 'snake', 'tetris']);
});
