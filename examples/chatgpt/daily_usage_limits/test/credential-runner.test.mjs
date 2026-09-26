import test from 'node:test';
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { constants as fsConstants } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseCredentialArgs, runWithCredentials } from '../src/credential-runner.mjs';

const SECRET = 'synthetic-secret-for-launcher-tests';
const FIXTURE_DIR = resolve('credential-runner-fixtures');
const CONFIG_PATH = join(FIXTURE_DIR, 'config.json');
const ENROLLMENT_PATH = join(FIXTURE_DIR, 'enrollment.json');
const STATE_PATH = join(FIXTURE_DIR, 'state');
const CREDENTIALS_DIRECTORY = join(FIXTURE_DIR, 'credentials', 'example.service');
const CLI_PATH = fileURLToPath(new URL('../src/cli.mjs', import.meta.url));
const base = ['run', '--provider', 'keychain', '--service', 'usage-limit-example', '--account', 'automation',
  '--config', CONFIG_PATH, '--enrollment', ENROLLMENT_PATH, '--state', STATE_PATH];
const systemd = ['run', '--provider', 'systemd', '--config', CONFIG_PATH,
  '--enrollment', ENROLLMENT_PATH, '--state', STATE_PATH];
const rejectsCode = (promise, code) => assert.rejects(promise, error => error.code === code && error.message === code);

function harness({ code = 0, signal = null, onSpawn, onExec, onOpen, platform = 'darwin', env,
  fileMode = 0o100400, owner = 1000, isFile = true, secret = SECRET + '\n' } = {}) {
  const signalSource = new EventEmitter();
  const calls = { exec: [], spawn: [], open: [], killed: [], closed: 0, stdout: '', stderr: '' };
  const child = new EventEmitter();
  child.stdout = new EventEmitter();
  child.stderr = new EventEmitter();
  child.kill = received => { calls.killed.push(received); return true; };
  const buffer = Buffer.from(secret);
  const dependencies = {
    platform, uid: 1000, env: env ?? { PATH: '/usr/bin', NODE_OPTIONS: '--import=untrusted.mjs',
      NODE_PATH: '/untrusted', CREDENTIALS_DIRECTORY },
    signalSource,
    stdout: { write: value => { calls.stdout += value; } },
    stderr: { write: value => { calls.stderr += value; } },
    execFileImpl: (path, args, options, callback) => {
      calls.exec.push({ path, args, options });
      if (onExec) return onExec({ path, args, options, callback });
      callback(null, secret, '');
    },
    openImpl: async (path, flags) => {
      calls.open.push({ path, flags });
      if (onOpen) return onOpen({ path, flags });
      return { stat: async () => ({ isFile: () => isFile, mode: fileMode, uid: owner, size: buffer.length }),
        readFile: async () => buffer, close: async () => { calls.closed += 1; } };
    },
    spawnImpl: (path, args, options) => {
      calls.spawn.push({ path, args, options: { ...options, env: { ...options.env } } });
      queueMicrotask(() => {
        if (onSpawn) onSpawn({ child, calls, signalSource });
        else child.stdout.emit('data', Buffer.from('{"ok":true}\n'));
        child.emit('close', code, signal);
      });
      return child;
    },
  };
  return { calls, dependencies, signalSource, buffer };
}

test('Keychain retrieval uses fixed executable and argument vector; child environment is transient', async () => {
  const h = harness();
  assert.deepEqual(await runWithCredentials(base, h.dependencies), { code: 0, signal: null });
  assert.deepEqual(h.calls.exec[0].args,
    ['find-generic-password', '-s', 'usage-limit-example', '-a', 'automation', '-w']);
  assert.equal(h.calls.exec[0].path, '/usr/bin/security');
  assert.equal(h.calls.exec[0].options.shell, false);
  assert.equal(h.calls.spawn[0].path, process.execPath);
  assert.equal(h.calls.spawn[0].args[0], CLI_PATH);
  assert.deepEqual(h.calls.spawn[0].args.slice(1), ['run', '--config', CONFIG_PATH,
    '--enrollment', ENROLLMENT_PATH, '--state', STATE_PATH]);
  assert.equal(h.calls.spawn[0].options.env.CHATGPT_ADMIN_API_KEY, SECRET);
  assert.equal(h.calls.spawn[0].options.env.NODE_OPTIONS, undefined);
  assert.equal(h.calls.spawn[0].options.env.NODE_PATH, undefined);
  assert.equal(h.dependencies.env.CHATGPT_ADMIN_API_KEY, undefined);
  assert.equal(h.calls.stdout, '{"ok":true}\n');
  assert.equal(h.calls.stderr, '');
  assert.equal(h.calls.open.length, 0);
});

test('service and account shell characters remain literal arguments', async () => {
  const args = [...base];
  args[4] = 'literal $(command) ; `value`';
  const h = harness();
  await runWithCredentials(args, h.dependencies);
  assert.equal(h.calls.exec[0].args[2], 'literal $(command) ; `value`');
  assert.equal(h.calls.exec[0].options.shell, false);
});

test('snapshot and restore are allowlisted; --apply is explicit for writes', () => {
  const snapshot = parseCredentialArgs(['snapshot', '--provider', 'keychain', '--service', 'example',
    '--account', 'operator', '--config', CONFIG_PATH, '--out', ENROLLMENT_PATH]);
  assert.deepEqual(snapshot.cliArgs, ['snapshot', '--config', CONFIG_PATH, '--out', ENROLLMENT_PATH]);
  const restore = parseCredentialArgs(['restore', ...base.slice(1), '--apply']);
  assert.equal(restore.cliArgs[0], 'restore');
  assert.equal(restore.cliArgs.at(-1), '--apply');
  const resume = parseCredentialArgs(['resume-auth', ...base.slice(1)]);
  assert.equal(resume.cliArgs[0], 'resume-auth');
  assert.throws(() => parseCredentialArgs(['resume-auth', ...base.slice(1), '--apply']), /CREDENTIAL_RUNNER_ARGUMENTS_INVALID/);
  const cancel = parseCredentialArgs(['cancel-initial', ...base.slice(1)]);
  assert.equal(cancel.cliArgs[0], 'cancel-initial');
  assert.throws(() => parseCredentialArgs(['cancel-initial', ...base.slice(1), '--apply']), /CREDENTIAL_RUNNER_ARGUMENTS_INVALID/);
});

test('unknown flags, synthetic mode, unexpected commands and incompatible provider flags are rejected before retrieval', async () => {
  for (const args of [
    [...base, '--synthetic'], [...base, '--command', 'sh'], ['inspect', ...base.slice(1)],
    [...base, 'restore'], [...systemd, '--service', 'example'],
    ['snapshot', '--provider', 'systemd', '--config', CONFIG_PATH, '--out', ENROLLMENT_PATH, '--apply'],
    ['snapshot', '--provider', 'systemd', '--config', CONFIG_PATH],
  ]) {
    const h = harness();
    await assert.rejects(runWithCredentials(args, h.dependencies));
    assert.equal(h.calls.exec.length, 0);
    assert.equal(h.calls.open.length, 0);
    assert.equal(h.calls.spawn.length, 0);
  }
});

test('provider platform mismatch and missing identities stop before retrieval', async () => {
  await rejectsCode(runWithCredentials(base, harness({ platform: 'linux' }).dependencies), 'KEYCHAIN_REQUIRES_MACOS');
  await rejectsCode(runWithCredentials(systemd, harness().dependencies), 'SYSTEMD_REQUIRES_LINUX');
  assert.throws(() => parseCredentialArgs(['run', '--provider', 'keychain', '--config', CONFIG_PATH,
    '--enrollment', ENROLLMENT_PATH, '--state', STATE_PATH]), /KEYCHAIN_IDENTITY_REQUIRED/);
});

test('Keychain errors and invalid secret values never become logs or child arguments', async () => {
  for (const onExec of [({ callback }) => callback(new Error(SECRET)), () => { throw new Error(SECRET); }]) {
    const h = harness({ onExec });
    await rejectsCode(runWithCredentials(base, h.dependencies), 'CREDENTIAL_READ_FAILED');
    assert.equal(h.calls.stdout + h.calls.stderr, '');
    assert.equal(h.calls.spawn.length, 0);
  }
  for (const secret of ['', '\n', 'two lines\nsecret', 'secret with spaces', 'x'.repeat(16385)]) {
    const h = harness({ secret });
    await rejectsCode(runWithCredentials(base, h.dependencies), 'CREDENTIAL_INVALID');
    assert.equal(h.calls.spawn.length, 0);
  }
});

test('systemd opens only the fixed credential name with no-follow and checks descriptor permissions', async () => {
  const h = harness({ platform: 'linux' });
  await runWithCredentials(systemd, h.dependencies);
  assert.deepEqual(h.calls.open, [{ path: join(CREDENTIALS_DIRECTORY, 'chatgpt-admin-key'),
    flags: fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW | fsConstants.O_NONBLOCK }]);
  assert.equal(h.calls.exec.length, 0);
  assert.equal(h.calls.closed, 1);
  assert.ok(h.buffer.every(byte => byte === 0));
  assert.equal(h.calls.spawn[0].options.env.CHATGPT_ADMIN_API_KEY, SECRET);
});

test('systemd rejects missing directory, non-private files, wrong owner, symlink/open failure', async () => {
  for (const env of [{}, { CREDENTIALS_DIRECTORY: 'relative' }]) {
    const h = harness({ platform: 'linux', env });
    await rejectsCode(runWithCredentials(systemd, h.dependencies), 'SYSTEMD_CREDENTIAL_DIRECTORY_REQUIRED');
    assert.equal(h.calls.open.length, 0);
  }
  for (const options of [{ fileMode: 0o100644 }, { owner: 2000 }, { isFile: false }]) {
    const h = harness({ platform: 'linux', ...options });
    await rejectsCode(runWithCredentials(systemd, h.dependencies), 'CREDENTIAL_FILE_NOT_PRIVATE');
    assert.equal(h.calls.closed, 1);
    assert.equal(h.calls.spawn.length, 0);
  }
  const denied = harness({ platform: 'linux', onOpen: async () => { throw new Error(SECRET); } });
  await rejectsCode(runWithCredentials(systemd, denied.dependencies), 'CREDENTIAL_READ_FAILED');
  assert.equal(denied.calls.stdout + denied.calls.stderr, '');
});

test('child output redacts a secret even across chunk boundaries and forwards its exit status', async () => {
  const h = harness({ code: 2, onSpawn: ({ child }) => {
    child.stdout.emit('data', Buffer.from('before ' + SECRET.slice(0, 12)));
    child.stdout.emit('data', Buffer.from(SECRET.slice(12) + ' after'));
    child.stderr.emit('data', Buffer.from(SECRET));
  } });
  assert.deepEqual(await runWithCredentials(base, h.dependencies), { code: 2, signal: null });
  assert.equal(h.calls.stdout, 'before [REDACTED] after');
  assert.equal(h.calls.stderr, '[REDACTED]');
});

test('redaction also covers JSON-escaped and URI-encoded credential values', async () => {
  const secret = 'synthetic-"quoted"-secret';
  const h = harness({ secret, onSpawn: ({ child }) => {
    child.stdout.emit('data', Buffer.from(JSON.stringify({ value: secret })));
    child.stderr.emit('data', Buffer.from(encodeURIComponent(secret)));
  } });
  await runWithCredentials(base, h.dependencies);
  assert.equal(h.calls.stdout, '{"value":"[REDACTED]"}');
  assert.equal(h.calls.stderr, '[REDACTED]');
});

test('SIGTERM forwards to the controller and listeners are cleaned up', async () => {
  const h = harness({ signal: 'SIGTERM', code: null, onSpawn: ({ signalSource }) => signalSource.emit('SIGTERM') });
  assert.deepEqual(await runWithCredentials(base, h.dependencies), { code: null, signal: 'SIGTERM' });
  assert.deepEqual(h.calls.killed, ['SIGTERM']);
  for (const signal of ['SIGINT', 'SIGTERM', 'SIGHUP']) assert.equal(h.signalSource.listenerCount(signal), 0);
});

test('spawn errors are redacted and do not leave signal handlers', async () => {
  const h = harness({ onSpawn: ({ child }) => child.emit('error', new Error(SECRET)) });
  await rejectsCode(runWithCredentials(base, h.dependencies), 'CONTROLLER_START_FAILED');
  assert.equal(h.calls.stdout + h.calls.stderr, '');
  assert.equal(h.signalSource.listenerCount('SIGTERM'), 0);
});

test('oversized controller output stops the child and emits only a bounded error', async () => {
  const h = harness({ onSpawn: ({ child }) => child.stdout.emit('data', Buffer.alloc(4 * 1024 * 1024 + 1, 'x')) });
  await rejectsCode(runWithCredentials(base, h.dependencies), 'CONTROLLER_OUTPUT_LIMIT');
  assert.deepEqual(h.calls.killed, ['SIGTERM']);
  assert.equal(h.calls.stdout + h.calls.stderr, '');
});
