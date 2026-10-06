import { createHash, randomUUID } from 'node:crypto';
import { mkdir, readFile, rename, unlink, writeFile } from 'node:fs/promises';
import { createConnection } from 'node:net';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { demoPreparationVersion, demoPrompts } from '../server/demo-prompts.mjs';
import { createSpaceDirectory } from '../server/identity.mjs';
import { blankSeedSource } from '../server/seed.mjs';
import { normalizeSpaceIcon } from '../server/space-icon-image.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const hash = value => createHash('sha256').update(value).digest('hex');
const sourceHash = revision => hash(`${revision.source}\n${revision.tests}`);
const currentRevision = saved => saved.revisions.find(revision => revision.id === saved.currentRevisionId);
const sameImage = (left, right) => left?.mimeType === right.mimeType && left?.data === right.data;
const defaultProposal = async () => (await import('../server/arcade/index.mjs')).arcadeProposal();
const brief = demoPrompts.find(person => person.id === 'karen');
const terminated = text => text.endsWith('\n') ? text : `${text}\n`;
const addFile = (path, text) => `*** Add File: ${path}\n${text.slice(0, -1).split('\n').map(line => `+${line}`).join('\n')}`;

async function optionalText(filename) {
  try { return await readFile(filename, 'utf8'); }
  catch (error) { if (error.code === 'ENOENT') return null; throw error; }
}

async function atomicJson(filename, value) {
  const temporary = `${filename}.${randomUUID()}.tmp`;
  try {
    await writeFile(temporary, JSON.stringify(value, null, 2), { mode: 0o600, flag: 'wx' });
    await rename(temporary, filename);
  } catch (error) { await unlink(temporary).catch(() => {}); throw error; }
}

/** Refuse offline writes while any process listens on the app's API port. */
export function assertServerStopped(port = Number(process.env.PORT || 4318)) {
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('PORT must be a valid local API port.');
  return new Promise((accept, reject) => {
    const socket = createConnection({ host: '127.0.0.1', port });
    socket.setTimeout(1000);
    socket.once('connect', () => {
      socket.destroy();
      reject(new Error(`Stop the Little Worlds server on port ${port} before preparing the arcade.`));
    });
    socket.once('timeout', () => {
      socket.destroy();
      reject(new Error(`Could not confirm that the server on port ${port} is stopped.`));
    });
    socket.once('error', error => {
      socket.destroy();
      if (error.code === 'ECONNREFUSED') accept();
      else reject(new Error(`Could not check the local API port: ${error.message}`));
    });
  });
}

/**
 * Explicit offline preparation only. The fixed proposal enters through the
 * ordinary owner builder, including verification and atomic publication.
 * Existing nonblank pages are never replaced and no model API is configured.
 */
export async function prepareArcade({
  dataDir = join(root, '.local'),
  iconFile = join(root, 'public/space-icons/james-finance.webp'),
  proposalFactory = defaultProposal,
  probeServer = assertServerStopped,
  log = message => console.log(message),
} = {}) {
  dataDir = resolve(dataDir);
  await probeServer();
  const portrait = await normalizeSpaceIcon(await readFile(iconFile));
  const requestedProposal = await proposalFactory();
  if (!requestedProposal || ['source', 'tests', 'summary'].some(key => typeof requestedProposal[key] !== 'string' || !requestedProposal[key].trim())) {
    throw new Error('The curated arcade proposal is incomplete. No spaces were changed.');
  }
  // Codex Add File writes end in a newline. Use those exact bytes for both the
  // patch and the preparation ledger's repeatable source fingerprint.
  const proposal = { ...requestedProposal, source: terminated(requestedProposal.source), tests: terminated(requestedProposal.tests) };
  const patch = `*** Begin Patch\n${addFile('space.js', proposal.source)}\n${addFile('tests.js', proposal.tests)}\n*** End Patch`;
  const markerFile = join(dataDir, 'demo-preparation.json');
  const ledgerText = await optionalText(markerFile);
  const ledger = ledgerText === null ? { version: 1, prepared: {} } : JSON.parse(ledgerText);
  if (ledger.version !== 1 || !ledger.prepared || typeof ledger.prepared !== 'object' || Array.isArray(ledger.prepared)) {
    throw new Error('The preparation record has an unsupported format. No spaces were changed.');
  }
  const baselineFile = join(`${dataDir}-reset-history`, 'baseline.json');
  const baselineText = await optionalText(baselineFile);
  const baseline = baselineText === null ? null : JSON.parse(baselineText);
  if (baseline && (baseline.version !== 1 || !Array.isArray(baseline.users) ||
    !baseline.users.some(person => person.id === 'james' && person.ownSpaceId === 'james') ||
    baseline.spaces?.james?.ownerId !== 'james' || baseline.spaces.james.kind !== 'blank')) {
    throw new Error('The saved demo baseline is unsupported. No spaces were changed.');
  }
  // Do not let opening a target silently recover and alter an unfinished turn.
  for (const id of ['karen', 'james']) {
    const text = await optionalText(join(dataDir, 'spaces', id, 'space.json'));
    if (text && JSON.parse(text).session?.status === 'running') {
      throw new Error(`${id === 'karen' ? 'Karen' : 'James'} has an unfinished edit. Let the app recover it before preparing the arcade.`);
    }
  }
  await mkdir(dataDir, { recursive: true, mode: 0o700 });
  const lockFile = join(dataDir, '.prepare-arcade.lock');
  try { await writeFile(lockFile, JSON.stringify({ pid: process.pid }), { mode: 0o600, flag: 'wx' }); }
  catch (error) {
    if (error.code === 'EEXIST') throw new Error('Arcade preparation is already locked. Check the previous preparation process before removing its lock.');
    throw error;
  }
  let directory;
  try {
    let calls = 0;
    directory = await createSpaceDirectory({ dataDir, adapter: {
      keyAvailable: true, model: 'curated-arcade', tier: 'local',
      async respond() {
        return { output: [{ type: 'custom_tool_call', call_id: `curated-arcade-${++calls}`, name: 'apply_patch', input: patch }] };
      },
    } });
    const karen = await directory.serviceFor('karen');
    let saved = karen.store.read();
    let arcadeStatus = 'preserved';
    if (currentRevision(saved)?.source.trim() === blankSeedSource.trim()) {
      await karen.submit(brief.prompt);
      await karen.waitForIdle();
      saved = karen.store.read();
      if (saved.session.lastOutcome !== 'completed') {
        const failure = saved.events.findLast(event => event.type === 'tool.failed' && event.stage === 'verify') ||
          saved.events.findLast(event => event.type === 'turn.failed');
        throw new Error(`The arcade did not pass verification. ${failure?.detail || 'The existing canvas was preserved.'}`);
      }
      arcadeStatus = 'prepared';
    }
    // Recover an interrupted marker write without rebuilding a published page,
    // and retain the original prepared revision even after later owner edits.
    const proposalHashes = new Set([sourceHash(proposal), sourceHash(requestedProposal)]);
    const preparedRevision = saved.revisions.find(revision => proposalHashes.has(sourceHash(revision)));
    const preparedTurn = preparedRevision && saved.session.turns.find(turn =>
      turn.status === 'completed' && turn.message === brief.prompt && turn.revisionId === preparedRevision.id);
    if (preparedTurn) {
      if (brief.requiredGames.some(id => !preparedRevision.meta?.games?.some(game => game.id === id))) {
        throw new Error('The curated arcade is missing a required playable game. No successful preparation was recorded.');
      }
      const entry = { preparationVersion: demoPreparationVersion,
        promptHash: hash(`${demoPreparationVersion}\n${brief.prompt}`), sessionId: saved.session.id,
        turnId: preparedTurn.id, revisionId: preparedRevision.id, sourceHash: sourceHash(preparedRevision) };
      const previous = ledger.prepared.karen;
      if (!previous || Object.entries(entry).some(([key, value]) => previous[key] !== value)) {
        if (await optionalText(markerFile) !== ledgerText) throw new Error('The preparation record changed during the import. Rerun after other preparation finishes.');
        await atomicJson(markerFile, { ...ledger, prepared: { ...ledger.prepared, karen: { ...entry, completedAt: new Date().toISOString() } } });
      }
    }
    const james = await directory.serviceFor('james');
    let jamesStatus = 'unchanged';
    if (!sameImage(james.store.read().icon, portrait)) {
      await directory.uploadIcon('james', portrait);
      jamesStatus = 'updated';
    }
    const icon = james.store.read().icon;
    let baselineBackup;
    if (baseline && !sameImage(baseline.spaces.james.icon, portrait)) {
      if (await optionalText(baselineFile) !== baselineText) throw new Error('The reset baseline changed during the import. Its original contents were preserved.');
      baselineBackup = join(dirname(baselineFile), `baseline-before-arcade-${randomUUID()}.json`);
      await writeFile(baselineBackup, baselineText, { mode: 0o600, flag: 'wx' });
      await atomicJson(baselineFile, { ...baseline, spaces: { ...baseline.spaces, james: { ...baseline.spaces.james, icon } } });
    }
    log(`Karen: ${arcadeStatus}. James portrait: ${jamesStatus}.${baselineBackup ? ' Previous reset baseline backed up.' : ''}`);
    return { arcade: arcadeStatus, jamesPortrait: jamesStatus, ...(baselineBackup ? { baselineBackup } : {}) };
  } finally {
    try { await directory?.close(); }
    finally { await unlink(lockFile); }
  }
}

export function parseArcadeArgs(args) {
  if (!args.length) return {};
  if (args.length === 2 && args[0] === '--data-dir' && args[1] && !args[1].startsWith('--')) return { dataDir: resolve(args[1]) };
  throw new Error('Usage: node scripts/prepare-arcade.mjs [--data-dir directory]');
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try { await prepareArcade(parseArcadeArgs(process.argv.slice(2))); }
  catch (error) { console.error(error.message); process.exitCode = 1; }
}
