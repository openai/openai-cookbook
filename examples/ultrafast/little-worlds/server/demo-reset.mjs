import { createHash, randomUUID } from 'node:crypto';
import { access, mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises';
import { join, resolve } from 'node:path';
import { demoUsers } from './identity.mjs';
import { demoConnections } from './social.mjs';
import { verifyModule } from './runtime.mjs';

const clone = value => structuredClone(value);
const hash = revision => createHash('sha256').update(`${revision.source}\n${revision.tests}`).digest('hex');
const readJson = async filename => JSON.parse(await readFile(filename, 'utf8'));
const exists = async filename => { try { await access(filename); return true; } catch (error) { if (error.code === 'ENOENT') return false; throw error; } };
const storePath = (root, person) => person.id === 'mira' ? join(root, 'space.json') : join(root, 'spaces', person.ownSpaceId, 'space.json');
const historyPath = dataDir => `${resolve(dataDir)}-reset-history`;
const originalDefaultIds = ['mira', 'james', 'jake', 'erica', 'leo'];
const sevenDefaultIds = [...originalDefaultIds, 'iris', 'luca'];
const eightDefaultIds = [...sevenDefaultIds, 'karen'];

async function writeJson(filename, value) {
  const temporary = `${filename}.${randomUUID()}.tmp`;
  try { await writeFile(temporary, JSON.stringify(value), { mode: 0o600 }); await rename(temporary, filename); }
  catch (error) { await rm(temporary, { force: true }); throw error; }
}

// Generated feature records belong to their actor. Keep authored project data
// and default-person records, but never resurrect removed accounts' records.
function withoutRemovedActors(value, removed, defaults) {
  if (Array.isArray(value)) return value.map(item => withoutRemovedActors(item, removed, defaults)).filter(item => item !== undefined);
  if (!value || typeof value !== 'object') return value;
  if (typeof value.actorId === 'string' && !defaults.has(value.actorId)) return undefined;
  return Object.fromEntries(Object.entries(value)
    .filter(([key]) => !removed.has(key) && !/^person_[a-f0-9-]{36}$/.test(key))
    .map(([key, item]) => [key, withoutRemovedActors(item, removed, defaults)])
    .filter(([, item]) => item !== undefined));
}

function historyThrough(data, selectedTurn) {
  if (!selectedTurn) return { turns: [], items: [] };
  const turnIndex = data.session.turns.findIndex(turn => turn.id === selectedTurn.id);
  const turns = data.session.turns.slice(0, turnIndex + 1);
  // Match ordinary turn starts, not steering messages. If older storage cannot
  // be matched unambiguously, retain the readable thread and rebuild context.
  let position = 0;
  for (const turn of turns) {
    const prefix = `Owner's request: ${turn.message}\n\n`;
    const found = data.session.items.findIndex((item, index) => index >= position && item.role === 'user' && typeof item.content === 'string' && item.content.startsWith(prefix));
    if (found < 0) return { turns, items: [] };
    position = found + 1;
  }
  const next = data.session.items.findIndex((item, index) => index >= position && item.role === 'user' && typeof item.content === 'string' && item.content.startsWith("Owner's request: "));
  return { turns, items: data.session.items.slice(0, next < 0 ? undefined : next) };
}

function cleanContext(items, removed, defaults) {
  const delimiter = '\n\nCurrent workspace and live state (authoritative for this turn):\n';
  return items.map(item => {
    if (item.role !== 'user' || typeof item.content !== 'string' || !item.content.includes(delimiter)) return item;
    const split = item.content.indexOf(delimiter) + delimiter.length;
    try {
      const workspace = JSON.parse(item.content.slice(split));
      workspace.state = withoutRemovedActors(workspace.state, removed, defaults);
      return { ...item, content: item.content.slice(0, split) + JSON.stringify(workspace) };
    } catch { return { ...item, content: item.content.slice(0, split - delimiter.length) }; }
  });
}

async function captureBaseline(dataDir, people = demoUsers) {
  const registry = await readJson(join(dataDir, 'identities.json'));
  let preparation = { version: 1, prepared: {} };
  try { preparation = await readJson(join(dataDir, 'demo-preparation.json')); }
  catch (error) { if (error.code !== 'ENOENT') throw error; }
  const defaults = new Set(demoUsers.map(person => person.id));
  const removed = new Set(registry.users.filter(person => !defaults.has(person.id)).map(person => person.id));
  const baseline = { version: 1, createdAt: new Date().toISOString(), users: clone(people), spaces: {}, prepared: {} };
  for (const person of people) {
    const data = await readJson(storePath(dataDir, person));
    const initial = data.initialBaseline;
    if (initial && (!initial.revision || typeof initial.revision.source !== 'string' || typeof initial.revision.tests !== 'string' || !initial.state)) {
      throw new Error(`The original ${person.name} canvas is invalid. The demo was not reset.`);
    }
    const marker = preparation.prepared?.[person.id];
    const preparedRevision = data.revisions.find(revision => revision.id === marker?.revisionId);
    const preparedTurn = data.session.turns.find(turn => turn.id === marker?.turnId && turn.status === 'completed');
    const verifiedMarker = !initial && preparedRevision && preparedTurn && marker.sessionId === data.session.id && marker.sourceHash === hash(preparedRevision);
    const selected = initial?.revision || (verifiedMarker ? preparedRevision : data.revisions.find(revision => revision.id === data.currentRevisionId));
    if (!selected) throw new Error(`The saved ${person.name} canvas is missing. The demo was not reset.`);
    const selectedTurn = initial ? undefined : (verifiedMarker ? preparedTurn : data.session.turns.findLast(turn => turn.status === 'completed' && turn.revisionId === selected.id));
    const history = historyThrough(data, selectedTurn);
    const state = withoutRemovedActors(initial?.state || data.state, removed, defaults);
    const verified = await verifyModule(selected.source, selected.tests, state, {
      owner: { id: person.id, name: person.name }, visitor: { id: 'reset-verification-visitor', name: 'Visitor' }, projectCatalog: true,
    });
    if (!verified.ok) throw new Error(`The original ${person.name} canvas did not pass its checks. The demo was not reset.`);
    baseline.spaces[person.id] = {
      ...data, ...(initial ? { icon: clone(initial.icon) } : {}), ownerId: person.id, kind: person.kind, state: clone(verified.candidateState), currentRevisionId: selected.id,
      revisions: (initial ? [selected] : data.revisions.filter(revision => revision.id <= selected.id)).map(revision => revision.id === selected.id ? { ...revision, checks: verified.checks } : revision),
      session: { id: data.session.id, status: 'idle', turns: history.turns, items: cleanContext(history.items, removed, defaults), lastOutcome: history.turns.length ? 'completed' : undefined },
      events: [], sequence: 0,
    };
    if (verifiedMarker) baseline.prepared[person.id] = clone(marker);
  }
  return baseline;
}

function validateBaseline(baseline) {
  // Accept the exact five-, seven- and eight-person historical layouts for append-only
  // upgrades. Never accept arbitrary missing, renamed, or unknown identities.
  const legacyUsers = [originalDefaultIds, sevenDefaultIds, eightDefaultIds].map(ids => ids.map(id => demoUsers.find(person => person.id === id)));
  const supportedUsers = [demoUsers, ...legacyUsers].some(users => JSON.stringify(baseline?.users) === JSON.stringify(users));
  if (baseline?.version !== 1 || !supportedUsers ||
    !baseline.spaces || Object.keys(baseline.spaces).length !== baseline.users.length ||
    baseline.users.some(person => baseline.spaces[person.id]?.ownerId !== person.id || baseline.spaces[person.id]?.kind !== person.kind)) {
    throw new Error('The saved demo baseline is invalid. The current spaces were kept.');
  }
}

function transactionPaths(dataDir, transaction) {
  if (transaction?.version !== 1 || !/^[a-f0-9-]{36}$/.test(transaction.id)) throw new Error('The saved reset transaction is invalid.');
  const history = historyPath(dataDir);
  return { history, journal: join(history, 'transaction.json'), staging: join(history, `staging-${transaction.id}`), backup: join(history, 'backups', transaction.id) };
}

// Recovery runs before any store opens. A crash between the two renames either
// completes the prepared replacement or leaves the intact original in place.
export async function recoverDemoReset(dataDir) {
  const journal = join(historyPath(dataDir), 'transaction.json');
  let transaction;
  try { transaction = await readJson(journal); } catch (error) { if (error.code === 'ENOENT') return; throw error; }
  const paths = transactionPaths(dataDir, transaction);
  const [hasLive, hasBackup, hasStaging] = await Promise.all([exists(dataDir), exists(paths.backup), exists(paths.staging)]);
  if (!hasLive && hasBackup) await rename(hasStaging ? paths.staging : paths.backup, dataDir);
  else if (!hasLive) throw new Error('The demo reset could not recover its saved spaces.');
  if (hasLive && hasStaging) await rm(paths.staging, { recursive: true, force: true });
  await rm(paths.journal, { force: true });
}

// Call only after every old service has closed. No live files are mutated until
// the complete replacement is ready; the whole old directory becomes a backup.
export async function beginDemoReset(dataDir) {
  const history = historyPath(dataDir);
  await mkdir(join(history, 'backups'), { recursive: true, mode: 0o700 });
  const baselineFile = join(history, 'baseline.json');
  let baseline;
  try { baseline = await readJson(baselineFile); }
  catch (error) {
    if (error.code !== 'ENOENT') throw error;
    baseline = await captureBaseline(dataDir);
    await writeJson(baselineFile, baseline);
  }
  validateBaseline(baseline);
  const missingPeople = demoUsers.filter(person => !baseline.users.some(user => user.id === person.id));
  if (missingPeople.length) {
    // Never recapture established defaults from later edits. Verify only the
    // newly introduced canvases, then atomically extend the saved baseline.
    const additions = await captureBaseline(dataDir, missingPeople);
    baseline = { ...baseline, users: clone(demoUsers),
      spaces: { ...baseline.spaces, ...additions.spaces },
      prepared: { ...baseline.prepared, ...additions.prepared } };
    validateBaseline(baseline);
    await writeJson(baselineFile, baseline);
  }
  const transaction = { version: 1, id: randomUUID() };
  const paths = transactionPaths(dataDir, transaction);
  await mkdir(paths.staging, { recursive: true, mode: 0o700 });
  let originalMoved = false;
  try {
    await writeJson(join(paths.staging, 'identities.json'), { version: 1, users: baseline.users });
    const connections = demoConnections.map(([left, right]) => {
      const [source, target] = [left, right].sort(); return { id: `friend:${source}:${target}`, source, target };
    });
    await writeJson(join(paths.staging, 'community.json'), { version: 1, connections, requests: [] });
    const prepared = clone(baseline.prepared || {});
    for (const person of demoUsers) {
      const data = clone(baseline.spaces[person.id]);
      data.session.id = randomUUID();
      const filename = storePath(paths.staging, person);
      if (person.id !== 'mira') await mkdir(join(paths.staging, 'spaces', person.ownSpaceId), { recursive: true, mode: 0o700 });
      await writeJson(filename, data);
      if (prepared[person.id]) prepared[person.id].sessionId = data.session.id;
    }
    await writeJson(join(paths.staging, 'demo-preparation.json'), { version: 1, prepared });
    await writeJson(paths.journal, transaction);
    await rename(dataDir, paths.backup);
    originalMoved = true;
    await rename(paths.staging, dataDir);
  } catch (error) {
    if (originalMoved) {
      // If rollback itself fails, preserve the journal and both directories so
      // startup recovery can complete it. Never orphan the only original copy.
      try { await rename(paths.backup, dataDir); }
      catch { throw new Error('The reset could not finish restoring its backup. Restart the local app to recover it.', { cause: error }); }
    }
    await rm(paths.staging, { recursive: true, force: true });
    await rm(paths.journal, { force: true });
    throw error;
  }
  return {
    backupDirectory: paths.backup,
    async commit() { await rm(paths.journal, { force: true }); },
    async rollback() {
      // Preserve even the failed replacement until the original is back.
      const failed = join(history, `failed-${transaction.id}`);
      await rename(dataDir, failed);
      await rename(paths.backup, dataDir);
      await rm(paths.journal, { force: true });
      await rm(failed, { recursive: true, force: true });
    },
  };
}
