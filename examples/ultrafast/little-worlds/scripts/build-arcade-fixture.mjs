import { mkdir, readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { arcadeProposal } from '../server/arcade/index.mjs';
import { compileModule, gameInit, renderModule } from '../server/runtime.mjs';
import { gameConfigs } from '../shared/game-schema.mjs';

// Build only an ignored browser artifact. The optional prepared mode reads
// only the current source, never carries visitor data into the fixture, and
// never writes the application store or calls a model.
const actor = { id: 'arcade-browser-fixture', name: 'Arcade browser fixture' };
const prepared = process.argv.includes('--prepared');
let source;
if (prepared) {
  const space = JSON.parse(await readFile(new URL('../.local/spaces/karen/space.json', import.meta.url), 'utf8'));
  source = space.revisions?.find(revision => revision.id === space.currentRevisionId)?.source;
  if (typeof source !== 'string') throw new Error('No current prepared Karen source was found.');
} else source = (await arcadeProposal()).source;
const compiled = await compileModule(source);
const state = { projects: [], contributions: [], extras: {} };
const names = { pacman: 'PacMan', 'space-invaders': 'Space Invaders', snake: 'Snake', tetris: 'Tetris' };
const games = await Promise.all(gameConfigs(compiled.meta).map(async config => {
  const bundle = compiled.gameBundles[config.id];
  const saved = await gameInit(bundle, null, actor);
  state.extras[config.id] = { [actor.id]: saved };
  return { name: names[config.id] || config.id, config, bundle, saved };
}));
const html = await renderModule(compiled.bundle, state, actor);
const directory = new URL('../tests/browser/.generated/', import.meta.url);
const output = new URL('karen.json', directory);
await mkdir(directory, { recursive: true });
await writeFile(output, JSON.stringify({ revisionId: 1, sourceKind: prepared ? 'prepared' : 'proposal', actor, html, games }, null, 2));
console.log(`Built ${games.length} arcade games: ${fileURLToPath(output)}`);
