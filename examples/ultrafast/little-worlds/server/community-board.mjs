import { readFile } from 'node:fs/promises';

// This bundled example is ordinary editable space code. Only a never-created
// Nora store receives it; reopening a store never replaces a saved revision.
export const communityBoardSource = await readFile(new URL('./community-board/space.js', import.meta.url), 'utf8');
export const communityBoardTests = await readFile(new URL('./community-board/tests.js', import.meta.url), 'utf8');
export const communityBoardSeed = {
  source: communityBoardSource,
  tests: communityBoardTests,
  state: { projects: [], contributions: [], extras: {} },
  icon: {
    mimeType: 'image/webp',
    data: (await readFile(new URL('../public/space-icons/nora-town-square.webp', import.meta.url))).toString('base64'),
    status: 'ready', source: 'upload', version: 'nora-town-square-devday-2026-v1',
  },
};
