import { readFileSync } from 'node:fs';
import { parse } from 'dotenv';

// Treat old and current names as aliases so an inherited process setting still
// wins over .env after the rename. Within either source, Little Worlds wins.
const inherited = { ...process.env };
try {
  const settings = parse(readFileSync(new URL('../.env', import.meta.url)));
  for (const [name, value] of Object.entries(settings)) {
    if (!Object.hasOwn(process.env, name)) process.env[name] = value;
  }
} catch (error) {
  if (error.code !== 'ENOENT') throw error;
}
for (const name of Object.keys(inherited).filter(name => name.startsWith('LIVING_SPACES_'))) {
  const currentName = name.replace('LIVING_SPACES_', 'LITTLE_WORLDS_');
  if (!Object.hasOwn(inherited, currentName)) process.env[currentName] = inherited[name];
}

export function appSetting(name, fallback) {
  return (process.env[`LITTLE_WORLDS_${name}`] ?? process.env[`LIVING_SPACES_${name}`]) || fallback;
}
