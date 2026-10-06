import { createHash, randomUUID } from 'node:crypto';
import { mkdir, readFile, rename, unlink, writeFile } from 'node:fs/promises';
import { createConnection } from 'node:net';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { createSpaceDirectory, demoUsers } from '../server/identity.mjs';
import { verifyModule } from '../server/runtime.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
export const legacyPaintingSourceHash = '1be66d5a3e887a6569f71c18056e0819aae4c06fc3d12d9a87a03976242a53ef';
export const rasterPaintingSourceHash = '769e1753533500e7b086f36066b7a2d1ac9bda1d5ac3609141d50b6dfa2adc4d';
const hash = value => createHash('sha256').update(value).digest('hex');
const revisionHash = revision => hash(`${revision.source}\n${revision.tests}`);
const currentRevision = saved => saved?.revisions?.find(revision => revision.id === saved.currentRevisionId);
const same = (left, right) => JSON.stringify(left) === JSON.stringify(right);
const terminated = text => text.endsWith('\n') ? text : `${text}\n`;
const defaultProposal = async () => (await import('../server/painting/index.mjs')).paintingProposal();
const addFile = (path, text) => `*** Add File: ${path}\n${text.slice(0, -1).split('\n').map(line => `+${line}`).join('\n')}`;

async function optionalText(filename) {
  try { return await readFile(filename, 'utf8'); }
  catch (error) { if (error.code === 'ENOENT') return null; throw error; }
}

async function atomicJson(filename, value) {
  const temporary = `${filename}.${randomUUID()}.tmp`;
  try {
    await writeFile(temporary, JSON.stringify(value), { mode: 0o600, flag: 'wx' });
    await rename(temporary, filename);
  } finally { await unlink(temporary).catch(() => {}); }
}

export function assertPaintingServerStopped(port = Number(process.env.PORT || 4318)) {
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Use a valid local API port.');
  return new Promise((accept, reject) => {
    const socket = createConnection({ host: '127.0.0.1', port });
    socket.setTimeout(1000);
    socket.once('connect', () => { socket.destroy(); reject(new Error(`Stop the Little Worlds server on port ${port} before upgrading the painting world.`)); });
    socket.once('timeout', () => { socket.destroy(); reject(new Error('Could not confirm that the local API server is stopped.')); });
    socket.once('error', error => { socket.destroy(); error.code === 'ECONNREFUSED' ? accept() : reject(error); });
  });
}

/**
 * Opt-in offline installation into the known prepared Iris world only. The
 * local proposal uses the ordinary owner apply_patch/verify/publish path. It
 * never calls a model, changes live participation, or captures it as a reset
 * baseline. Injection seams support isolated test fixtures, not CLI bypasses.
 */
export async function upgradePainting({
  dataDir = join(root, '.local'), apply = false, updateBaseline = false, port,
  proposalFactory = defaultProposal, allowedSourceHashes = [legacyPaintingSourceHash, rasterPaintingSourceHash],
  probeServer = assertPaintingServerStopped, verify = verifyModule,
  log = message => console.log(message),
} = {}) {
  dataDir = resolve(dataDir);
  const historyDir = `${dataDir}-reset-history`;
  const storeFile = join(dataDir, 'spaces/iris/space.json');
  const baselineFile = join(historyDir, 'baseline.json');
  const markerFile = join(dataDir, 'painting-upgrade.json');
  const lockFile = join(dataDir, '.upgrade-painting.lock');
  const tracked = new Map();
  const read = async filename => {
    const text = await optionalText(filename);
    tracked.set(filename, text);
    return text === null ? null : JSON.parse(text);
  };
  const assertOtherOperationsStopped = async () => {
    for (const filename of [join(historyDir, 'transaction.json'), join(historyDir, '.adopt-devday-baseline.lock'),
      join(dataDir, 'demo-preparation.json.lock'), join(dataDir, 'devday-restyle.json.lock'), join(dataDir, '.prepare-arcade.lock')]) {
      if (await optionalText(filename) !== null) throw new Error('A reset or preparation lock is present. Let that operation finish before upgrading the painting world.');
    }
  };
  const assertUnchanged = async (except = []) => {
    for (const [filename, original] of tracked) {
      if (!except.includes(filename) && await optionalText(filename) !== original) throw new Error('Saved data changed during verification. Retry with the server stopped.');
    }
  };
  await assertOtherOperationsStopped();
  if (await optionalText(lockFile) !== null) throw new Error('Painting upgrade is already locked. Inspect the previous operation before removing its lock.');
  if (apply) await probeServer(port);
  // These files must already exist, so opening the directory cannot seed new
  // people or initialize a new friendship graph as an installation side effect.
  const registry = await read(join(dataDir, 'identities.json'));
  const graph = await read(join(dataDir, 'community.json'));
  if (registry?.version !== 1 || !Array.isArray(registry.users) || !graph ||
    demoUsers.some(person => !registry.users.some(user => same(user, person)))) {
    throw new Error('An existing, fully initialized demo directory is required. No spaces were changed.');
  }
  const saved = await read(storeFile);
  const oldRevision = currentRevision(saved);
  if (saved?.ownerId !== 'iris' || saved.kind !== 'blank' || !oldRevision || !saved.state) throw new Error('The saved Iris world is missing or unsupported.');
  if (saved.session?.status !== 'idle') throw new Error('Iris has an unfinished edit. Let the app recover it before upgrading.');
  const previousMarker = await read(markerFile);
  if (previousMarker && previousMarker.version !== 1) throw new Error('The painting upgrade record has an unsupported format.');
  const requested = await proposalFactory();
  if (!requested || ['source', 'tests', 'summary'].some(key => typeof requested[key] !== 'string' || !requested[key].trim())) {
    throw new Error('The curated painting proposal is incomplete. No spaces were changed.');
  }
  const proposal = { ...requested, source: terminated(requested.source), tests: terminated(requested.tests) };
  const curatedHashes = new Set([hash(requested.source), hash(proposal.source)]);
  const acceptedHashes = new Set([...allowedSourceHashes, ...curatedHashes]);
  const assertEligible = (revision, description) => {
    if (!revision || typeof revision.source !== 'string' || typeof revision.tests !== 'string' || !acceptedHashes.has(hash(revision.source))) {
      throw new Error(`${description} has later or unrecognized owner edits. Refusing to replace it.`);
    }
  };
  assertEligible(oldRevision, 'The current Iris world');
  const verifiesWithoutChangingState = async (state, description) => {
    const result = await verify(proposal.source, proposal.tests, structuredClone(state), {
      owner: { id: 'iris', name: 'Iris' }, visitor: { id: 'painting-upgrade-visitor', name: 'Visitor' }, projectCatalog: true,
    });
    if (!result.ok) throw new Error(`${description} failed painting verification. ${result.checks?.filter(check => !check.ok).map(check => `${check.name}: ${check.message || 'failed'}`).join('; ') || 'No successful checks.'}`);
    if (!same(result.candidateState, state)) throw new Error(`${description} would change saved participation or its project catalog. No spaces were changed.`);
    return result;
  };
  const verified = await verifiesWithoutChangingState(saved.state, 'The current world');
  const needsPublication = revisionHash(oldRevision) !== revisionHash(proposal);
  let nextBaseline, baselineChanged = false, nextInitial, initialChanged = false;
  if (updateBaseline) {
    const baseline = await read(baselineFile);
    if (baseline && (baseline.version !== 1 || !Array.isArray(baseline.users) ||
      !baseline.users.some(person => person.id === 'iris' && person.ownSpaceId === 'iris') ||
      baseline.spaces?.iris?.ownerId !== 'iris' || baseline.spaces.iris.kind !== 'blank')) {
      throw new Error('The original Iris reset baseline is missing or unsupported. Refusing to capture live participation.');
    }
    const replaceInitial = async (initial, description) => {
      assertEligible(initial?.revision, description);
      const checked = await verifiesWithoutChangingState(initial.state, description);
      return { ...initial, revision: { ...initial.revision, source: proposal.source, tests: proposal.tests,
        meta: checked.meta, checks: checked.checks } };
    };
    if (saved.initialBaseline) {
      nextInitial = await replaceInitial(saved.initialBaseline, 'The ORIGINAL initial baseline');
      initialChanged = !same(nextInitial, saved.initialBaseline);
    }
    if (baseline) {
      nextBaseline = structuredClone(baseline);
      const original = baseline.spaces.iris;
      const selected = currentRevision(original);
      const replaced = await replaceInitial({ revision: selected, state: original.state }, 'The ORIGINAL reset baseline');
      const next = { ...original, revisions: original.revisions.map(revision => revision.id === selected.id ? replaced.revision : revision) };
      if (original.initialBaseline) next.initialBaseline = await replaceInitial(original.initialBaseline, 'The ORIGINAL nested baseline');
      nextBaseline.spaces.iris = next;
      const prepared = nextBaseline.prepared?.iris;
      if (prepared?.revisionId === selected.id) prepared.sourceHash = revisionHash(replaced.revision);
      baselineChanged = !same(nextBaseline, baseline);
    } else if (!saved.initialBaseline) {
      throw new Error('No original Iris reset or initial baseline exists. Refusing to capture live participation.');
    }
  }
  await assertUnchanged();
  const plan = { applied: false, publication: needsPublication, baseline: baselineChanged || initialChanged };
  if (!apply || (!needsPublication && !plan.baseline)) {
    log(`${apply ? 'Already upgraded' : 'Dry run'}: painting publication ${needsPublication ? 'required' : 'unchanged'}; reset baseline ${plan.baseline ? 'would update from its original state' : 'unchanged'}.`);
    return plan;
  }
  try { await writeFile(lockFile, JSON.stringify({ pid: process.pid }), { mode: 0o600, flag: 'wx' }); }
  catch (error) { if (error.code === 'EEXIST') throw new Error('Painting upgrade is already locked.'); throw error; }
  let directory;
  const backupDirectory = join(historyDir, 'painting-upgrade-backups', randomUUID());
  try {
    await assertOtherOperationsStopped();
    await probeServer(port);
    await assertUnchanged();
    await mkdir(backupDirectory, { recursive: true, mode: 0o700 });
    const manifest = [];
    for (const filename of [storeFile, markerFile, ...(baselineChanged ? [baselineFile] : [])]) {
      const text = tracked.get(filename);
      if (text === null) { manifest.push({ filename, existed: false }); continue; }
      const backup = `${manifest.length}.json`;
      await writeFile(join(backupDirectory, backup), text, { mode: 0o600, flag: 'wx' });
      manifest.push({ filename, backup, sha256: hash(text) });
    }
    await writeFile(join(backupDirectory, 'manifest.json'), JSON.stringify({ version: 1, files: manifest }), { mode: 0o600, flag: 'wx' });
    await assertUnchanged();
    let published = saved;
    if (needsPublication || initialChanged) {
      let calls = 0;
      const patch = `*** Begin Patch\n${addFile('space.js', proposal.source)}\n${addFile('tests.js', proposal.tests)}\n*** End Patch`;
      directory = await createSpaceDirectory({ dataDir, adapter: {
        keyAvailable: true, model: 'curated-painting', tier: 'local',
        async respond() {
          if (++calls > 1) throw new Error('The fixed painting proposal failed; no model repair will be attempted.');
          return { output: [{ type: 'custom_tool_call', call_id: 'curated-painting-1', name: 'apply_patch', input: patch }] };
        },
      } });
      const iris = await directory.serviceFor('iris');
      if (needsPublication) {
        await iris.submit(proposal.summary);
        await iris.waitForIdle();
        published = iris.store.read();
        if (published.session.lastOutcome !== 'completed' || revisionHash(currentRevision(published)) !== revisionHash(proposal)) {
          throw new Error(`The painting proposal did not publish successfully. Original files are backed up in ${backupDirectory}.`);
        }
        if (!same(published.state, saved.state)) throw new Error(`Painting state unexpectedly changed. Original files are backed up in ${backupDirectory}.`);
      }
      if (initialChanged) await iris.store.transact(data => { data.initialBaseline = nextInitial; });
      published = iris.store.read();
      await directory.close();
      directory = undefined;
    }
    await assertUnchanged([storeFile]);
    if (baselineChanged) await atomicJson(baselineFile, nextBaseline);
    const revision = currentRevision(published);
    await atomicJson(markerFile, { version: 1, sourceHash: hash(revision.source), revisionHash: revisionHash(revision),
      revisionId: revision.id, sessionId: published.session.id, completedAt: new Date().toISOString(),
      baselineUpdated: plan.baseline, backupDirectory });
    log(`Painting upgraded through verified publication. Live artwork preserved. Reset baseline ${plan.baseline ? 'updated without live participation' : 'unchanged'}. Backup: ${backupDirectory}`);
    return { ...plan, applied: true, revisionId: revision.id, backupDirectory, checks: verified.checks.length };
  } finally {
    try { await directory?.close(); }
    finally { await unlink(lockFile); }
  }
}

export function parsePaintingUpgradeArgs(args) {
  const result = {};
  const seen = new Set();
  for (let index = 0; index < args.length; index++) {
    const flag = args[index];
    if (seen.has(flag)) throw new Error(`Repeated option: ${flag}`);
    seen.add(flag);
    if (flag === '--apply') result.apply = true;
    else if (flag === '--update-baseline') result.updateBaseline = true;
    else if (flag === '--data-dir' && args[index + 1] && !args[index + 1].startsWith('--')) result.dataDir = resolve(args[++index]);
    else if (flag === '--port' && /^\d+$/.test(args[index + 1] || '')) {
      result.port = Number(args[++index]);
      if (result.port < 1 || result.port > 65535) throw new Error('Use a valid local API port.');
    } else throw new Error('Usage: node scripts/upgrade-painting.mjs [--data-dir directory] [--port number] [--apply] [--update-baseline]');
  }
  return result;
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try { await upgradePainting(parsePaintingUpgradeArgs(process.argv.slice(2))); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
