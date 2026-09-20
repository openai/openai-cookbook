import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';

const aws = dirname(fileURLToPath(import.meta.url));
const root = resolve(aws, '..');
const dist = resolve(aws, 'dist');
const staging = resolve(dist, 'package');
mkdirSync(dist, { recursive: true, mode: 0o700 });
rmSync(staging, { recursive: true, force: true });
mkdirSync(staging, { mode: 0o700 });

// Follow literal relative imports from these entry points. Never copy a source directory,
// configuration, enrollment, fixtures, receipts, .env, or credentials wholesale.
const included = new Set();
function include(relative) {
  if (included.has(relative)) return;
  if (!/^(aws|src)\/[a-z0-9_-]+\.mjs$/.test(relative)) throw new Error(`Disallowed package path: ${relative}`);
  const source = resolve(root, relative);
  if (!existsSync(source)) throw new Error(`Missing source file: ${relative}`);
  included.add(relative);
  const target = resolve(staging, relative);
  mkdirSync(dirname(target), { recursive: true });
  cpSync(source, target);
  const text = readFileSync(source, 'utf8');
  for (const match of text.matchAll(/(?:from\s*|import\s*\()(['"])(\.{1,2}\/[^'"]+)\1/g)) {
    const dependency = resolve(dirname(source), match[2]).slice(root.length + 1);
    include(dependency);
  }
}
try {
  include('aws/lambda.mjs');
  // npm installs at the ZIP root, where both aws/ and src/ imports can find it.
  cpSync(resolve(aws, 'package.json'), resolve(staging, 'package.json'));
  cpSync(resolve(aws, 'package-lock.json'), resolve(staging, 'package-lock.json'));
  execFileSync('npm', ['ci', '--omit=dev', '--ignore-scripts', '--no-audit', '--no-fund'],
    { cwd: staging, stdio: 'inherit' });
  const zip = resolve(dist, 'controller.zip');
  rmSync(zip, { force: true });
  execFileSync('zip', ['-q', '-r', zip, '.'], { cwd: staging, stdio: 'inherit' });
  const digest = createHash('sha256').update(readFileSync(zip)).digest('hex');
  writeFileSync(resolve(dist, 'controller.sha256'), `${digest}  controller.zip\n`);
  writeFileSync(resolve(dist, 'source-manifest.json'), `${JSON.stringify([...included].sort(), null, 2)}\n`);
  console.log(`Built aws/dist/controller.zip; SHA-256 ${digest}. No upload or cloud change performed.`);
} finally { rmSync(staging, { recursive: true, force: true }); }
