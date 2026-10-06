import { readFile } from 'node:fs/promises';

/** Offline, reviewed source. Dimensions are substituted once; every contract derives from them. */
export async function paintingProposal({ columns = 48, rows = 32 } = {}) {
  if (!Number.isInteger(columns) || !Number.isInteger(rows) || columns < 1 || rows < 1 || columns > 256 || rows > 256) {
    throw new Error('Painting dimensions must be integers from 1 to 256.');
  }
  const source = (await readFile(new URL('./space.js', import.meta.url), 'utf8'))
    .replace('const COLUMNS = 48;', `const COLUMNS = ${columns};`)
    .replace('const ROWS = 32;', `const ROWS = ${rows};`);
  return {
    source,
    tests: await readFile(new URL('./tests.js', import.meta.url), 'utf8'),
    summary: 'Upgrade the shared painting surface while preserving its artwork and layout',
  };
}
