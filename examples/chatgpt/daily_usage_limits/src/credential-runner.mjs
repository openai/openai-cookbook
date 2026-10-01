// Retrieve an existing local credential and pass it only to the fixed controller.
// This launcher never creates a credential, writes a secret file, or runs a shell.
import { execFile, spawn } from 'node:child_process';
import { open } from 'node:fs/promises';
import { constants as fsConstants } from 'node:fs';
import { constants as osConstants } from 'node:os';
import { isAbsolute, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { parseArgs } from 'node:util';

const CLI_PATH = fileURLToPath(new URL('./cli.mjs', import.meta.url));
const MAX_SECRET_BYTES = 16384;
const MAX_OUTPUT_BYTES = 4 * 1024 * 1024;
const SIGNALS = ['SIGINT', 'SIGTERM', 'SIGHUP'];
const fail = code => Object.assign(new Error(code), { code });
const validText = value => typeof value === 'string' && value.length > 0 &&
  value.length <= 4096 && !/[\u0000-\u001f\u007f]/.test(value);

export function parseCredentialArgs(args) {
  let parsed;
  try {
    parsed = parseArgs({ args, allowPositionals: true, strict: true, options: {
      provider: { type: 'string' }, service: { type: 'string' }, account: { type: 'string' },
      config: { type: 'string' }, enrollment: { type: 'string' }, state: { type: 'string' },
      out: { type: 'string' }, apply: { type: 'boolean', default: false },
    } });
  } catch { throw fail('CREDENTIAL_RUNNER_ARGUMENTS_INVALID'); }
  const { values, positionals } = parsed;
  const command = positionals[0];
  if (positionals.length !== 1 || !['snapshot', 'run', 'restore', 'resume-auth', 'cancel-initial'].includes(command) ||
      !['keychain', 'systemd'].includes(values.provider) || !validText(values.config)) {
    throw fail('CREDENTIAL_RUNNER_ARGUMENTS_INVALID');
  }
  if (values.provider === 'keychain') {
    if (!validText(values.service) || !validText(values.account)) throw fail('KEYCHAIN_IDENTITY_REQUIRED');
  } else if (values.service !== undefined || values.account !== undefined) {
    throw fail('CREDENTIAL_RUNNER_ARGUMENTS_INVALID');
  }
  if (command === 'snapshot') {
    if (!validText(values.out) || values.enrollment !== undefined || values.state !== undefined || values.apply) {
      throw fail('CREDENTIAL_RUNNER_ARGUMENTS_INVALID');
    }
  } else if (!validText(values.enrollment) || !validText(values.state) || values.out !== undefined) {
    throw fail('CREDENTIAL_RUNNER_ARGUMENTS_INVALID');
  }
  if (['resume-auth', 'cancel-initial'].includes(command) && values.apply) throw fail('CREDENTIAL_RUNNER_ARGUMENTS_INVALID');
  const cliArgs = [command, '--config', resolve(values.config)];
  if (command === 'snapshot') cliArgs.push('--out', resolve(values.out));
  else cliArgs.push('--enrollment', resolve(values.enrollment), '--state', resolve(values.state));
  if (values.apply) cliArgs.push('--apply');
  return { ...values, command, cliArgs };
}

function normalizeSecret(value) {
  const secret = Buffer.isBuffer(value) ? value.toString('utf8') : value;
  if (typeof secret !== 'string' || Buffer.byteLength(secret) > MAX_SECRET_BYTES) throw fail('CREDENTIAL_INVALID');
  const trimmed = secret.replace(/\r?\n$/, '');
  if (!trimmed || /\s|[\u0000-\u001f\u007f]/.test(trimmed)) throw fail('CREDENTIAL_INVALID');
  return trimmed;
}

async function loadCredential(parsed, { env, platform, uid, execFileImpl, openImpl }) {
  if (parsed.provider === 'keychain') {
    if (platform !== 'darwin') throw fail('KEYCHAIN_REQUIRES_MACOS');
    let value;
    try {
      value = await new Promise((resolvePromise, rejectPromise) => {
        execFileImpl('/usr/bin/security', ['find-generic-password', '-s', parsed.service, '-a', parsed.account, '-w'],
          { encoding: 'utf8', timeout: 10000, maxBuffer: MAX_SECRET_BYTES, shell: false, windowsHide: true },
          (error, stdout) => error ? rejectPromise(fail('CREDENTIAL_READ_FAILED')) : resolvePromise(stdout));
      });
    } catch { throw fail('CREDENTIAL_READ_FAILED'); }
    return normalizeSecret(value);
  }
  if (platform !== 'linux') throw fail('SYSTEMD_REQUIRES_LINUX');
  const directory = env.CREDENTIALS_DIRECTORY;
  if (!validText(directory) || !isAbsolute(directory) || !Number.isSafeInteger(uid)) {
    throw fail('SYSTEMD_CREDENTIAL_DIRECTORY_REQUIRED');
  }
  let handle;
  let bytes;
  try {
    handle = await openImpl(join(directory, 'chatgpt-admin-key'),
      fsConstants.O_RDONLY | fsConstants.O_NOFOLLOW | fsConstants.O_NONBLOCK);
    const metadata = await handle.stat();
    if (!metadata.isFile() || (metadata.mode & 0o077) !== 0 ||
        ![uid, 0].includes(metadata.uid) || metadata.size < 1 || metadata.size > MAX_SECRET_BYTES) {
      throw fail('CREDENTIAL_FILE_NOT_PRIVATE');
    }
    // Read through the descriptor we checked, preventing a path-swap after stat.
    bytes = await handle.readFile();
    return normalizeSecret(bytes);
  } catch (error) {
    if (['CREDENTIAL_FILE_NOT_PRIVATE', 'CREDENTIAL_INVALID'].includes(error.code)) throw error;
    throw fail('CREDENTIAL_READ_FAILED');
  } finally {
    if (Buffer.isBuffer(bytes)) bytes.fill(0);
    if (handle) await handle.close().catch(() => {});
  }
}

export async function runWithCredentials(args, {
  env = process.env, platform = process.platform, uid = process.getuid?.(),
  execFileImpl = execFile, openImpl = open, spawnImpl = spawn,
  signalSource = process, stdout = process.stdout, stderr = process.stderr,
} = {}) {
  const parsed = parseCredentialArgs(args);
  const secret = await loadCredential(parsed, { env, platform, uid, execFileImpl, openImpl });
  const childEnv = { ...env, CHATGPT_ADMIN_API_KEY: secret };
  // Do not allow inherited Node hooks to run arbitrary code with the retrieved key.
  delete childEnv.NODE_OPTIONS;
  delete childEnv.NODE_PATH;
  let child;
  try {
    child = spawnImpl(process.execPath, [CLI_PATH, ...parsed.cliArgs],
      { env: childEnv, shell: false, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true });
  } catch { throw fail('CONTROLLER_START_FAILED'); }
  finally { delete childEnv.CHATGPT_ADMIN_API_KEY; }

  return await new Promise((resolvePromise, rejectPromise) => {
    const output = { stdout: [], stderr: [] };
    let totalBytes = 0;
    let failed;
    let settled = false;
    let forwardedSignal;
    const forward = signal => {
      forwardedSignal = signal;
      try { child.kill(signal); } catch { failed = 'CONTROLLER_SIGNAL_FAILED'; }
    };
    const handlers = Object.fromEntries(SIGNALS.map(signal => [signal, () => forward(signal)]));
    for (const [signal, handler] of Object.entries(handlers)) signalSource.on(signal, handler);
    const cleanup = () => {
      for (const [signal, handler] of Object.entries(handlers)) signalSource.removeListener(signal, handler);
    };
    const collect = stream => chunk => {
      const bytes = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
      totalBytes += bytes.length;
      if (totalBytes > MAX_OUTPUT_BYTES) {
        failed = 'CONTROLLER_OUTPUT_LIMIT';
        try { child.kill('SIGTERM'); } catch { /* Report the bounded error below. */ }
        return;
      }
      output[stream].push(bytes);
    };
    child.stdout.on('data', collect('stdout'));
    child.stderr.on('data', collect('stderr'));
    child.once('error', () => {
      if (settled) return;
      settled = true;
      cleanup();
      rejectPromise(fail('CONTROLLER_START_FAILED'));
    });
    child.once('close', (code, signal) => {
      if (settled) return;
      settled = true;
      cleanup();
      if (failed) { rejectPromise(fail(failed)); return; }
      // Join chunks before redaction: a secret split across chunks must not leak.
      const secretForms = [...new Set([secret, JSON.stringify(secret).slice(1, -1), encodeURIComponent(secret)])]
        .sort((left, right) => right.length - left.length);
      const redact = chunks => secretForms.reduce((text, value) => text.split(value).join('[REDACTED]'),
        Buffer.concat(chunks).toString('utf8'));
      stdout.write(redact(output.stdout));
      stderr.write(redact(output.stderr));
      if (code !== null && (!Number.isInteger(code) || code < 0 || code > 255)) {
        rejectPromise(fail('CONTROLLER_EXIT_INVALID')); return;
      }
      resolvePromise({ code, signal: signal ?? forwardedSignal ?? null });
    });
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  runWithCredentials(process.argv.slice(2)).then(result => {
    if (result.signal && SIGNALS.includes(result.signal)) {
      // Restore normal signal exit semantics after our forwarding handlers are removed.
      process.kill(process.pid, result.signal);
      process.exitCode = 128 + osConstants.signals[result.signal];
    } else process.exitCode = result.code ?? 2;
  }).catch(error => {
    const safe = /^[A-Z][A-Z0-9_]+$/.test(error.code ?? '') ? error.code : 'CREDENTIAL_RUNNER_FAILED';
    console.error(JSON.stringify({ ok: false, code: safe,
      action: 'Check the approved local credential setup and controller receipt. No secret values are printed.' }));
    process.exitCode = 2;
  });
}
