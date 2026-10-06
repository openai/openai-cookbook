import { createHash, randomUUID } from 'node:crypto';
import { mkdir, readFile, rename, unlink, writeFile } from 'node:fs/promises';
import { createConnection } from 'node:net';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { demoUsers } from '../server/identity.mjs';
import { verifyModule } from '../server/runtime.mjs';
import { DEV_DAY_THEME_VERSION } from '../server/devday-theme.mjs';
import { devdayRestyleVersion } from './retheme-devday.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const targets = demoUsers.filter(person => person.id !== 'leo');
const hash = value => createHash('sha256').update(value).digest('hex');
const sourceHash = revision => hash(`${revision.source}\n${revision.tests}`);
const currentRevision = saved => saved.revisions?.find(revision => revision.id === saved.currentRevisionId);
const storePath = (dataDir, person) => person.id === 'mira' ? join(dataDir, 'space.json') : join(dataDir, 'spaces', person.ownSpaceId, 'space.json');
const clone = value => structuredClone(value);
const same = (left, right) => JSON.stringify(left) === JSON.stringify(right);

async function optionalText(filename) {
  try { return await readFile(filename, 'utf8'); }
  catch (error) { if (error.code === 'ENOENT') return null; throw error; }
}

export function assertBaselineServerStopped(port = Number(process.env.PORT || 4318)) {
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Use a valid local API port.');
  return new Promise((accept, reject) => {
    const socket = createConnection({ host: '127.0.0.1', port });
    socket.setTimeout(1000);
    socket.once('connect', () => { socket.destroy(); reject(new Error(`Stop the Little Worlds server on port ${port} before adopting reset baselines.`)); });
    socket.once('timeout', () => { socket.destroy(); reject(new Error('Could not confirm that the local API server is stopped.')); });
    socket.once('error', error => { socket.destroy(); error.code === 'ECONNREFUSED' ? accept() : reject(error); });
  });
}

function validateBaseline(baseline) {
  const historicalIds = [
    ['mira', 'james', 'jake', 'erica', 'leo'],
    ['mira', 'james', 'jake', 'erica', 'leo', 'iris', 'luca'],
    ['mira', 'james', 'jake', 'erica', 'leo', 'iris', 'luca', 'karen'],
    demoUsers.map(person => person.id),
  ];
  if (baseline?.version !== 1 || !historicalIds.some(ids => same(baseline.users, ids.map(id => demoUsers.find(person => person.id === id)))) ||
    !baseline.spaces || Object.keys(baseline.spaces).length !== baseline.users.length ||
    baseline.users.some(person => baseline.spaces[person.id]?.ownerId !== person.id || baseline.spaces[person.id]?.kind !== person.kind)) {
    throw new Error('The saved reset baseline has an unsupported format. Nothing was changed.');
  }
}

/** Only presentation colors may change in baseline data; never copy live records. */
function themedState(state, meta) {
  if (!state || !Array.isArray(state.projects)) throw new Error('The original baseline state is missing.');
  const next = clone(state);
  const colors = new Map((meta.projects || []).map(project => [project.id, project.color]));
  next.projects = next.projects.map(project => colors.has(project.id) ? { ...project, color: colors.get(project.id) } : project);
  return next;
}

/**
 * Explicit, offline adoption after the owner-builder migration has completed.
 * Dry-run is the default. The live design, participation, accounts, friendship
 * graph, builder histories and earlier revision records are never replaced.
 * Nora can remain absent from an older reset baseline: normal reset upgrades
 * append her from the updated initialBaseline without recapturing old people.
 */
export async function adoptDevdayBaseline({
  dataDir = join(root, '.local'), apply = false, port,
  probeServer = assertBaselineServerStopped, verify = verifyModule,
  log = message => console.log(message),
} = {}) {
  dataDir = resolve(dataDir);
  const historyDir = `${dataDir}-reset-history`;
  const baselineFile = join(historyDir, 'baseline.json');
  const markerFile = join(dataDir, 'devday-restyle.json');
  const tracked = new Map();
  const read = async filename => { const text = await optionalText(filename); tracked.set(filename, text); return text === null ? null : JSON.parse(text); };
  const noOperationInProgress = async () => {
    for (const filename of [join(historyDir, 'transaction.json'), `${markerFile}.lock`, join(dataDir, '.prepare-arcade.lock')]) {
      if (await optionalText(filename) !== null) throw new Error('A reset or preparation lock is present. Let that operation finish before adopting baselines.');
    }
  };
  await noOperationInProgress();
  if (apply) await probeServer(port);
  const ledger = await read(markerFile);
  if (ledger?.version !== 1 || ledger.theme !== devdayRestyleVersion || !ledger.worlds) throw new Error('A completed DevDay restyle record is required. Nothing was changed.');
  const baseline = await read(baselineFile);
  if (baseline) validateBaseline(baseline);
  const nextBaseline = clone(baseline);
  const updates = new Map();
  const results = [];

  for (const person of targets) {
    const filename = storePath(dataDir, person);
    const saved = await read(filename);
    const entry = ledger.worlds[person.id];
    const revision = currentRevision(saved || {});
    if (!saved || saved.ownerId !== person.id || saved.kind !== person.kind || saved.session?.status !== 'idle' ||
      entry?.status !== 'complete' || entry.sessionId !== saved.session.id || entry.revisionId !== revision?.id || entry.sourceHash !== sourceHash(revision) ||
      !revision.checks?.length || revision.checks.some(check => !check.ok)) {
      throw new Error(`${person.name}: the current published world must match its completed, verified restyle record.`);
    }
    const icon = saved.icon;
    if (entry.iconStatus !== 'complete' || icon?.status !== 'ready' || icon.source !== 'generated' || !icon.data || icon.mimeType !== 'image/webp' ||
      icon.version !== entry.iconVersion || icon.themeVersion !== DEV_DAY_THEME_VERSION || icon.fingerprint !== hash(`${DEV_DAY_THEME_VERSION}\0${revision.source}`)) {
      throw new Error(`${person.name}: a completed DevDay icon for this exact published world is required.`);
    }
    const replace = async initial => {
      if (!initial?.revision || typeof initial.revision.source !== 'string' || typeof initial.revision.tests !== 'string') throw new Error(`${person.name}: the original baseline revision is missing.`);
      const state = themedState(initial.state, revision.meta);
      const verified = await verify(revision.source, revision.tests, state, {
        owner: { id: person.id, name: person.name }, visitor: { id: 'devday-baseline-visitor', name: 'Visitor' }, projectCatalog: false,
      });
      if (!verified.ok) {
        const failures = verified.checks.filter(check => !check.ok).map(check => `${check.name}: ${check.message || 'failed'}`).join('; ');
        throw new Error(`${person.name}: the themed world does not pass verification with the ORIGINAL reset baseline state. Nothing was changed. ${failures}`);
      }
      return { ...initial, state, icon: clone(icon), revision: {
        ...initial.revision, source: revision.source, tests: revision.tests, meta: clone(revision.meta), checks: verified.checks,
      } };
    };
    let initialChanged = false;
    if (saved.initialBaseline) {
      const initialBaseline = await replace(saved.initialBaseline);
      initialChanged = !same(initialBaseline, saved.initialBaseline);
      if (initialChanged) updates.set(filename, { ...saved, initialBaseline });
    }
    const original = baseline?.spaces[person.id];
    let resetChanged = false;
    if (original) {
      const selected = currentRevision(original);
      const adopted = await replace({ revision: selected, state: original.state });
      const next = { ...original, state: adopted.state, icon: adopted.icon,
        revisions: original.revisions.map(item => item.id === selected.id ? adopted.revision : item),
        ...(original.initialBaseline ? { initialBaseline: await replace(original.initialBaseline) } : {}),
      };
      resetChanged = !same(original, next);
      nextBaseline.spaces[person.id] = next;
      // This marker still refers to the same prepared revision and historical
      // turn. Keep its content fingerprint in sync with the adopted design.
      const prepared = nextBaseline.prepared?.[person.id];
      if (prepared?.revisionId === selected.id) prepared.sourceHash = sourceHash(adopted.revision);
    } else if (!saved.initialBaseline) {
      throw new Error(`${person.name}: no original reset or initial baseline exists; refusing to capture current participant data.`);
    }
    results.push({ id: person.id, initialChanged, resetChanged });
  }
  if (baseline && !same(nextBaseline, baseline)) updates.set(baselineFile, nextBaseline);
  const assertUnchanged = async () => {
    for (const [filename, original] of tracked) if (await optionalText(filename) !== original) throw new Error('Saved data changed during verification. Nothing was changed; retry with the server stopped.');
  };
  await assertUnchanged();
  if (!apply || !updates.size) {
    log(`${apply ? 'Already adopted' : 'Dry run'}: ${results.length} verified worlds; ${updates.size} baseline files ${apply ? 'need updates' : 'would change'}. Live worlds and participation are preserved.`);
    return { applied: false, files: updates.size, worlds: results };
  }

  await mkdir(historyDir, { recursive: true, mode: 0o700 });
  const lockFile = join(historyDir, '.adopt-devday-baseline.lock');
  try { await writeFile(lockFile, JSON.stringify({ pid: process.pid }), { flag: 'wx', mode: 0o600 }); }
  catch (error) { if (error.code === 'EEXIST') throw new Error('Baseline adoption is already locked. Inspect the previous operation before removing its lock.'); throw error; }
  const id = randomUUID();
  const backupDirectory = join(historyDir, 'devday-baseline-backups', id);
  const written = [];
  const atomicText = async (filename, text) => {
    const temporary = `${filename}.${id}.tmp`;
    try { await writeFile(temporary, text, { flag: 'wx', mode: 0o600 }); await rename(temporary, filename); }
    finally { await unlink(temporary).catch(() => {}); }
  };
  try {
    await noOperationInProgress();
    await probeServer(port);
    await assertUnchanged();
    await mkdir(backupDirectory, { recursive: true, mode: 0o700 });
    const manifest = [];
    for (const [filename] of updates) {
      const backup = `${manifest.length}.json`;
      await writeFile(join(backupDirectory, backup), tracked.get(filename), { flag: 'wx', mode: 0o600 });
      manifest.push({ filename, backup, sha256: hash(tracked.get(filename)) });
    }
    await writeFile(join(backupDirectory, 'manifest.json'), JSON.stringify({ version: 1, theme: DEV_DAY_THEME_VERSION, files: manifest }, null, 2), { flag: 'wx', mode: 0o600 });
    for (const [filename, value] of updates) {
      if (await optionalText(filename) !== tracked.get(filename)) throw new Error('A baseline file changed before adoption. Original files will be restored.');
      await atomicText(filename, JSON.stringify(value));
      written.push(filename);
    }
  } catch (error) {
    for (const filename of written.reverse()) await atomicText(filename, tracked.get(filename));
    throw error;
  } finally { await unlink(lockFile); }
  log(`Adopted ${results.length} verified DevDay worlds into ${updates.size} baseline files. Originals backed up in ${backupDirectory}.`);
  return { applied: true, files: updates.size, worlds: results, backupDirectory };
}

export function parseBaselineArgs(args) {
  const result = {};
  const seen = new Set();
  for (let index = 0; index < args.length; index++) {
    const flag = args[index];
    if (seen.has(flag)) throw new Error(`Repeated option: ${flag}`);
    seen.add(flag);
    if (flag === '--apply') result.apply = true;
    else if (flag === '--data-dir' && args[index + 1] && !args[index + 1].startsWith('--')) result.dataDir = resolve(args[++index]);
    else if (flag === '--port' && /^\d+$/.test(args[index + 1] || '')) {
      result.port = Number(args[++index]);
      if (result.port < 1 || result.port > 65535) throw new Error('Use a valid local API port.');
    } else throw new Error('Usage: node scripts/adopt-devday-baseline.mjs [--data-dir directory] [--port number] [--apply]');
  }
  return result;
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try { await adoptDevdayBaseline(parseBaselineArgs(process.argv.slice(2))); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
