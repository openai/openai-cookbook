import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, utimesSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { inflateRawSync } from 'node:zlib';
import { buildPackage, dependencyPath, resolveNpmCli } from '../aws/package.mjs';
import { createZip } from '../aws/zip.mjs';

function temporary(t) {
  const root = mkdtempSync(join(tmpdir(), 'cookbook package '));
  t.after(() => rmSync(root, { recursive: true, force: true }));
  return root;
}

function put(root, name, value = '') {
  const path = join(root, ...name.split('/'));
  mkdirSync(dirname(path), { recursive: true });
  writeFileSync(path, value);
  return path;
}

function fixture(t) {
  const root = temporary(t);
  put(root, 'aws/lambda.mjs', "import './store.mjs';\nexport { run } from '../src/controller.mjs';\n");
  put(root, 'aws/store.mjs', 'export const store = {};\n');
  put(root, 'src/controller.mjs', "export async function run() { return import('./policy.mjs'); }\n");
  put(root, 'src/policy.mjs', 'export const policy = {};\n');
  put(root, 'aws/package.json', '{"private":true,"type":"module"}\n');
  put(root, 'aws/package-lock.json', '{"lockfileVersion":3}\n');
  const npmCli = put(root, 'npm cli/npm-cli.js');
  return { root, npmCli };
}

function link(t, target, path, type = 'file') {
  try { symlinkSync(target, path, type); return true; }
  catch (error) {
    if (process.platform === 'win32' && ['EPERM', 'EACCES'].includes(error.code)) {
      t.skip('This Windows account cannot create symbolic links');
      return false;
    }
    throw error;
  }
}

// Read the standard central directory and recover file contents independently of the writer.
function readZip(buffer) {
  const end = buffer.length - 22;
  assert.equal(buffer.readUInt32LE(end), 0x06054b50);
  assert.equal(buffer.readUInt16LE(end + 20), 0);
  const count = buffer.readUInt16LE(end + 10);
  let cursor = buffer.readUInt32LE(end + 16);
  assert.equal(cursor + buffer.readUInt32LE(end + 12), end);
  const files = new Map();
  for (let index = 0; index < count; index++) {
    assert.equal(buffer.readUInt32LE(cursor), 0x02014b50);
    const nameLength = buffer.readUInt16LE(cursor + 28);
    const name = buffer.subarray(cursor + 46, cursor + 46 + nameLength).toString('utf8');
    assert.equal(buffer.readUInt16LE(cursor + 8), 0x0800);
    assert.equal(buffer.readUInt16LE(cursor + 10), 8);
    assert.equal(buffer.readUInt16LE(cursor + 12), 0);
    assert.equal(buffer.readUInt16LE(cursor + 14), 0x2821);
    assert.equal(buffer.readUInt32LE(cursor + 38) >>> 16, 0o100644);
    const local = buffer.readUInt32LE(cursor + 42);
    assert.equal(buffer.readUInt32LE(local), 0x04034b50);
    assert.equal(buffer.readUInt16LE(local + 26), nameLength);
    assert.equal(buffer.subarray(local + 30, local + 30 + nameLength).toString('utf8'), name);
    const size = buffer.readUInt32LE(cursor + 20);
    const data = inflateRawSync(buffer.subarray(local + 30 + nameLength, local + 30 + nameLength + size));
    assert.equal(data.length, buffer.readUInt32LE(cursor + 24));
    assert.equal(buffer.readUInt32LE(local + 14), buffer.readUInt32LE(cursor + 16));
    files.set(name, { data, crc: buffer.readUInt32LE(cursor + 16) });
    cursor += 46 + nameLength + buffer.readUInt16LE(cursor + 30) + buffer.readUInt16LE(cursor + 32);
  }
  assert.equal(cursor, end);
  return files;
}

test('relative imports use portable archive paths and stay inside the source allowlist', () => {
  assert.equal(dependencyPath('aws/lambda.mjs', '../src/controller.mjs'), 'src/controller.mjs');
  assert.equal(dependencyPath('src/controller.mjs', './policy.mjs'), 'src/policy.mjs');
  for (const invalid of ['../../private.mjs', '../.private/config.mjs', '../src/config.json', './sub/file.mjs', '.\\store.mjs']) {
    assert.throws(() => dependencyPath('aws/lambda.mjs', invalid));
  }
});

test('npm resolution accepts the lifecycle CLI or explicit JavaScript path, never npm.cmd', t => {
  const { npmCli } = fixture(t);
  assert.equal(resolveNpmCli(undefined, { npm_execpath: npmCli }), realpathSync(npmCli));
  assert.equal(resolveNpmCli(npmCli, { npm_execpath: 'npm.cmd' }), realpathSync(npmCli));
  for (const value of [undefined, 'npm', 'npm.cmd', 'npm-cli.js']) {
    assert.throws(() => resolveNpmCli(value, {}), /npm run package/);
  }
});

test('ZIP entries round-trip binary and UTF-8 content with deterministic bytes and known CRC', t => {
  const root = temporary(t);
  const source = put(root, 'z/credit-€含.mjs', '123456789');
  put(root, 'a.bin', Buffer.from([0, 1, 127, 128, 255]));
  put(root, 'empty', '');
  const first = createZip(root);
  utimesSync(source, new Date('2030-01-01'), new Date('2030-01-01'));
  assert.deepEqual(createZip(root), first);
  const entries = readZip(first);
  assert.deepEqual([...entries.keys()], ['a.bin', 'empty', 'z/credit-€含.mjs']);
  assert.deepEqual(entries.get('a.bin').data, Buffer.from([0, 1, 127, 128, 255]));
  assert.equal(entries.get('empty').data.length, 0);
  assert.equal(entries.get('z/credit-€含.mjs').data.toString(), '123456789');
  assert.equal(entries.get('z/credit-€含.mjs').crc, 0xcbf43926);
});

test('package follows runtime imports, excludes private and unused files, and invokes npm with Node', t => {
  const options = fixture(t);
  for (const file of ['.env', '.private/enrollment.json', 'aws/credentials.json', 'src/unused.mjs', 'test/fixture.json']) {
    put(options.root, file, 'private fixture');
  }
  const calls = [];
  options.run = (command, args, settings) => {
    calls.push({ command, args, settings });
    put(settings.cwd, 'node_modules/example/index.js', 'export default 1;\n');
  };
  const first = buildPackage(options);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].command, process.execPath);
  assert.deepEqual(calls[0].args, [realpathSync(options.npmCli), 'ci', '--omit=dev', '--ignore-scripts', '--no-bin-links', '--no-audit', '--no-fund']);
  assert.equal(calls[0].settings.shell, undefined);
  assert.deepEqual(first.manifest, ['aws/lambda.mjs', 'aws/store.mjs', 'src/controller.mjs', 'src/policy.mjs']);
  const entries = readZip(readFileSync(first.zip));
  assert.deepEqual([...entries.keys()], [...first.manifest, 'node_modules/example/index.js', 'package-lock.json', 'package.json'].sort());
  assert.doesNotMatch(readFileSync(first.zip).toString(), /private fixture/);
  assert.equal(existsSync(join(options.root, 'aws/dist/package')), false);
  assert.equal(buildPackage(options).digest, first.digest);
});

test('failed npm install cleans staging and leaves no new archive', t => {
  const options = fixture(t);
  assert.throws(() => buildPackage({ ...options, run() { throw new Error('install failed'); } }), /install failed/);
  assert.equal(existsSync(join(options.root, 'aws/dist/package')), false);
  assert.equal(existsSync(join(options.root, 'aws/dist/controller.zip')), false);
});

test('source files cannot be symbolic links', t => {
  const options = fixture(t);
  const source = join(options.root, 'aws/store.mjs');
  rmSync(source);
  if (!link(t, put(options.root, '.private/secret.mjs', 'secret'), source)) return;
  assert.throws(() => buildPackage({ ...options, run() { assert.fail('npm must not run'); } }), /Symbolic links/);
});

test('source directories cannot be symbolic links', t => {
  const options = fixture(t);
  rmSync(join(options.root, 'src'), { recursive: true });
  const other = temporary(t);
  put(other, 'controller.mjs', '');
  if (!link(t, other, join(options.root, 'src'), 'dir')) return;
  assert.throws(() => buildPackage({ ...options, run() { assert.fail('npm must not run'); } }), /Symbolic links/);
});

test('ZIP refuses dependency symlinks and directory symlinks', t => {
  for (const type of ['file', 'dir']) {
    const root = temporary(t);
    const outside = temporary(t);
    const file = put(outside, 'secret', 'secret');
    if (!link(t, type === 'file' ? file : outside, join(root, 'linked'), type)) return;
    assert.throws(() => createZip(root), /Symbolic links/);
  }
});

test('preexisting output symlinks cannot redirect package writes', t => {
  const options = fixture(t);
  const outside = put(options.root, 'outside.txt', 'keep');
  mkdirSync(join(options.root, 'aws/dist'), { recursive: true });
  if (!link(t, outside, join(options.root, 'aws/dist/controller.zip'))) return;
  assert.throws(() => buildPackage({ ...options, run() {} }), /Symbolic links/);
  assert.equal(readFileSync(outside, 'utf8'), 'keep');
});
