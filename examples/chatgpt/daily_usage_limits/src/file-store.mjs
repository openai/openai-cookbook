import { mkdir, open, readFile, rename, rm, stat } from 'node:fs/promises';
import { createHash, randomUUID } from 'node:crypto';
import { join, resolve, dirname } from 'node:path';
import { digest as stateDigest } from './policy.mjs';

const digest = value => createHash('sha256').update(value).digest('hex').slice(0, 24);
const failure = code => Object.assign(new Error(code), { code });
function requireLocalFilesystem() {
  // Windows needs ACL validation and its own durable metadata-write strategy.
  if (process.platform === 'win32') throw failure('LOCAL_STORAGE_REQUIRES_MACOS_OR_LINUX');
}
async function syncDirectory(path) {
  const handle = await open(path, 'r');
  try { await handle.sync(); } finally { await handle.close(); }
}
export async function atomicJson(path, value) {
  requireLocalFilesystem();
  const temporary = `${path}.${randomUUID()}.tmp`;
  const handle = await open(temporary, 'wx', 0o600);
  try {
    await handle.writeFile(`${JSON.stringify(value, null, 2)}\n`);
    await handle.sync();
  } finally { await handle.close(); }
  await rename(temporary, path);
  await syncDirectory(dirname(path));
}

/** Single-host store for a cold standby. Never place the directory on a network filesystem.
 * Atomic mkdir excludes concurrent processes. Locks survive process crashes deliberately:
 * an operator must stop the writer and reconcile pending work before removing a stale lock.
 * The fsynced append-only journal is authoritative; state.json is a convenience snapshot.
 */
export class FileStore {
  constructor(directory) {
    this.directory = resolve(directory);
    this.active = new Map();
  }
  async init() {
    requireLocalFilesystem();
    await mkdir(this.directory, { recursive: true, mode: 0o700 });
    if ((await stat(this.directory)).mode & 0o077) throw failure('STATE_DIRECTORY_NOT_PRIVATE');
    return this;
  }
  paths(key) {
    const prefix = join(this.directory, digest(key));
    return { lock: `${prefix}.lock`, journal: `${prefix}.journal.jsonl`, state: `${prefix}.state.json` };
  }
  async withLock(key, callback) {
    await this.init();
    const { lock } = this.paths(key);
    const token = randomUUID();
    try { await mkdir(lock, { mode: 0o700 }); } catch (error) {
      if (error.code === 'EEXIST') throw failure('LOCAL_LOCK_HELD_RECONCILE_BEFORE_REMOVAL');
      throw error;
    }
    // If the process dies after mkdir, the empty directory still safely blocks another writer.
    await atomicJson(join(lock, 'owner.json'), { token, pid: process.pid, startedAt: new Date().toISOString() });
    await syncDirectory(this.directory);
    this.active.set(key, token);
    try { return await callback(); } finally {
      try {
        await this.assertLock(key);
        await rm(lock, { recursive: true });
        await syncDirectory(this.directory);
      } finally { this.active.delete(key); }
    }
  }
  async assertLock(key) {
    const token = this.active.get(key);
    if (!token) throw failure('LOCAL_WRITE_REQUIRES_LOCK');
    let owner;
    try { owner = JSON.parse(await readFile(join(this.paths(key).lock, 'owner.json'), 'utf8')); }
    catch { throw failure('LOCAL_LOCK_LOST'); }
    if (owner.token !== token || owner.pid !== process.pid) throw failure('LOCAL_LOCK_LOST');
  }
  async entries(key) {
    let data;
    try { data = await readFile(this.paths(key).journal, 'utf8'); } catch (error) {
      if (error.code === 'ENOENT') return [];
      throw error;
    }
    if (data && !data.endsWith('\n')) throw failure('LOCAL_JOURNAL_INCOMPLETE_REVIEW_REQUIRED');
    try {
      return data.trim() ? data.trimEnd().split('\n').map(line => {
        const entry = JSON.parse(line);
        if (entry.schemaVersion !== 1 || entry.controllerKey !== digest(key) || !['state', 'receipt'].includes(entry.kind)) throw new Error();
        return entry;
      }) : [];
    } catch { throw failure('LOCAL_JOURNAL_CORRUPT_REVIEW_REQUIRED'); }
  }
  async getState(key) {
    const entries = await this.entries(key);
    return entries.findLast(entry => entry.kind === 'state')?.value ?? null;
  }
  async append(key, kind, value) {
    await this.assertLock(key);
    // Validate the previous journal before appending; never hide truncated crash evidence.
    await this.entries(key);
    const handle = await open(this.paths(key).journal, 'a', 0o600);
    try {
      await handle.writeFile(`${JSON.stringify({ schemaVersion: 1, kind, controllerKey: digest(key), persistedAt: new Date().toISOString(), value })}\n`);
      await handle.sync();
    } finally { await handle.close(); }
    await syncDirectory(this.directory);
  }
  async putState(key, state) {
    await this.append(key, 'state', state);
    await this.assertLock(key);
    await atomicJson(this.paths(key).state, state);
  }
  async transitionState(key, { previous, next }) {
    await this.assertLock(key);
    if (stateDigest(await this.getState(key)) !== stateDigest(previous)) throw failure('RENEWAL_PRIOR_STATE_CHANGED');
    // The fsynced append-only journal already retains every prior period. One
    // state entry commits the transition; the convenience snapshot is rebuilt.
    await this.putState(key, next);
  }
  async putReceipt(receipt) {
    const key = [...this.active.keys()].find(key => digest(key) === receipt.controllerKey);
    if (!key) throw failure('LOCAL_RECEIPT_REQUIRES_LOCK');
    await this.append(key, 'receipt', receipt);
    await this.assertLock(key);
    await atomicJson(join(this.directory, `${receipt.controllerKey}.latest-receipt.json`), receipt);
  }
}
