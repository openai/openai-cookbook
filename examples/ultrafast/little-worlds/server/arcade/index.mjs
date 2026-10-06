import { readFile } from 'node:fs/promises';

export async function arcadeProposal() {
  const parts = await Promise.all(['pacman', 'invaders', 'snake', 'tetris', 'page'].map(name => readFile(new URL(`./${name}.mjs`, import.meta.url), 'utf8')));
  const tests = await readFile(new URL('./published-tests.js.txt', import.meta.url), 'utf8');
  return { source: parts.join('\n\n'), tests, summary: 'Created Karen’s retro arcade with four independently playable games: PacMan, Space Invaders, Snake and Tetris. Each has keyboard, touch and Live controls, plus personal saved progress.' };
}
