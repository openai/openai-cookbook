import { copyFileSync, lstatSync, mkdirSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs';
import { dirname, isAbsolute, join, posix, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import { parseArgs } from 'node:util';
import { createZip } from './zip.mjs';

const defaultRoot = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const sourcePattern = /^(aws|src)\/[a-z0-9_-]+\.mjs$/;

// Import specifiers and archive names always use '/', including on Windows.
export function dependencyPath(importer, specifier) {
  if (!sourcePattern.test(importer) || !/^\.{1,2}\//.test(specifier) || specifier.includes('\\')) {
    throw new Error('Invalid relative source import');
  }
  const dependency = posix.normalize(posix.join(posix.dirname(importer), specifier));
  if (!sourcePattern.test(dependency)) throw new Error(`Disallowed package path: ${dependency}`);
  return dependency;
}

function checkPath(root, relative, { optional = false } = {}) {
  let current = root;
  for (const part of ['', ...relative.split('/')]) {
    current = join(current, part);
    const entry = lstatSync(current, { throwIfNoEntry: false });
    if (!entry) {
      if (optional) return;
      throw new Error(`Missing package input: ${relative}`);
    }
    if (entry.isSymbolicLink()) throw new Error(`Symbolic links are not allowed: ${relative}`);
  }
}

export function resolveNpmCli(explicit, environment = process.env) {
  const candidate = explicit ?? environment.npm_execpath;
  if (!candidate || !isAbsolute(candidate) || !/\.[cm]?js$/i.test(candidate)) {
    throw new Error('Run npm run package --prefix aws, or node aws/package.mjs --npm-cli "<absolute path to npm-cli.js>". A Node.js installation with npm is required.');
  }
  const npmCli = realpathSync(candidate);
  if (!lstatSync(npmCli).isFile()) throw new Error('The npm CLI must be a JavaScript file');
  return npmCli;
}

export function buildPackage({ root = defaultRoot, npmCli, run = execFileSync } = {}) {
  root = resolve(root);
  npmCli = resolveNpmCli(npmCli);
  const dist = resolve(root, 'aws/dist');
  const staging = resolve(dist, 'package');
  checkPath(root, 'aws/dist', { optional: true });
  mkdirSync(dist, { recursive: true, mode: 0o700 });
  checkPath(root, 'aws/dist/package', { optional: true });
  rmSync(staging, { recursive: true, force: true });
  mkdirSync(staging, { mode: 0o700 });

  // Follow only the runtime's literal relative imports; never copy a source directory.
  const included = new Set();
  function include(relative) {
    if (included.has(relative)) return;
    if (!sourcePattern.test(relative)) throw new Error(`Disallowed package path: ${relative}`);
    checkPath(root, relative);
    const source = resolve(root, relative);
    if (!lstatSync(source).isFile()) throw new Error(`Not a source file: ${relative}`);
    included.add(relative);
    const target = resolve(staging, relative);
    mkdirSync(dirname(target), { recursive: true });
    copyFileSync(source, target);
    const text = readFileSync(source, 'utf8');
    for (const match of text.matchAll(/(?:from\s*|import\s*(?:\(\s*)?)(['"])(\.{1,2}\/[^'"]+)\1/g)) {
      include(dependencyPath(relative, match[2]));
    }
  }
  try {
    include('aws/lambda.mjs');
    for (const name of ['package.json', 'package-lock.json']) {
      checkPath(root, `aws/${name}`);
      if (!lstatSync(resolve(root, 'aws', name)).isFile()) throw new Error(`Not a file: ${name}`);
      copyFileSync(resolve(root, 'aws', name), resolve(staging, name));
    }
    // Use the same Node executable on every platform; never execute npm.cmd or a shell.
    // Runtime dependencies do not need command shims, which can be symbolic links.
    run(process.execPath, [npmCli, 'ci', '--omit=dev', '--ignore-scripts', '--no-bin-links', '--no-audit', '--no-fund'],
      { cwd: staging, stdio: 'inherit' });
    const archive = createZip(staging);
    const digest = createHash('sha256').update(archive).digest('hex');
    const manifest = [...included].sort();
    for (const [name, content] of [
      ['controller.zip', archive], ['controller.sha256', `${digest}  controller.zip\n`],
      ['source-manifest.json', `${JSON.stringify(manifest, null, 2)}\n`],
    ]) {
      checkPath(root, `aws/dist/${name}`, { optional: true });
      writeFileSync(resolve(dist, name), content, { mode: 0o600 });
    }
    return { zip: resolve(dist, 'controller.zip'), digest, manifest };
  } finally { rmSync(staging, { recursive: true, force: true }); }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { values } = parseArgs({ options: { 'npm-cli': { type: 'string' }, help: { type: 'boolean' } } });
  if (values.help) {
    console.log('Run npm run package --prefix aws. Direct invocation: node aws/package.mjs --npm-cli "<absolute path to npm-cli.js>". Requires Node.js with npm; no ZIP utility is needed.');
  } else {
    const { digest } = buildPackage({ npmCli: values['npm-cli'] });
    console.log(`Built aws/dist/controller.zip; SHA-256 ${digest}. No upload or cloud change performed.`);
  }
}
