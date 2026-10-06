import { appSetting } from '../server/environment.mjs';
import { createHash, randomUUID } from 'node:crypto';
import { mkdir, open, readFile, rename, unlink, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { demoPreparationVersion, demoPrompts } from '../server/demo-prompts.mjs';
import { blankSeedSource } from '../server/seed.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const hash = value => createHash('sha256').update(value).digest('hex');
const sourceHash = revision => hash(`${revision.source}\n${revision.tests}`);
const safeMessage = error => String(error?.message || error).replace(/sk-[A-Za-z0-9_-]+/g, '[redacted]').slice(0, 700);
const wait = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

function localApi(value) {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) ||
    url.username || url.password || url.search || url.hash || url.pathname !== '/') {
    throw new Error('Use a loopback API origin, such as http://127.0.0.1:4318.');
  }
  return url.origin;
}

async function acquireLock(filename) {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      const file = await open(filename, 'wx', 0o600);
      await file.writeFile(JSON.stringify({ pid: process.pid, createdAt: new Date().toISOString() }));
      await file.close();
      return () => unlink(filename).catch(() => {});
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      let pid;
      try { pid = JSON.parse(await readFile(filename, 'utf8')).pid; } catch { /* fail closed below */ }
      if (!Number.isInteger(pid) || pid < 1) throw new Error('The preparation lock is unreadable. Inspect it before trying again.');
      try { process.kill(pid, 0); }
      catch (probe) {
        if (probe.code === 'ESRCH') { await unlink(filename).catch(() => {}); continue; }
      }
      throw new Error('Another preparation process is active. Let it finish before trying again.');
    }
  }
  throw new Error('Could not acquire the preparation lock. Try again.');
}

// No direct store edits, seed substitutions, authored modules or automatic
// resets. This uses the same authenticated turn endpoint as the app composer.
export async function prepareDemo({
  baseUrl = appSetting('API_URL', 'http://127.0.0.1:4318'),
  markerFile = resolve(root, '.local/demo-preparation.json'),
  prompts = demoPrompts,
  version = demoPreparationVersion,
  rebuild = false,
  concurrency = 2,
  pollMs = 750,
  timeoutMs = 600_000,
  fetchImpl = fetch,
  log = message => console.log(message),
} = {}) {
  const origin = localApi(baseUrl);
  if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 2) throw new Error('Preparation supports one or two concurrent builds.');
  if (prompts.some(item => !item?.id || typeof item.prompt !== 'string' || !item.prompt.trim() || item.prompt.length > 4000) || new Set(prompts.map(item => item.id)).size !== prompts.length) {
    throw new Error('Preparation requires unique people and prompts of at most 4,000 characters.');
  }
  await mkdir(dirname(markerFile), { recursive: true, mode: 0o700 });
  const release = await acquireLock(`${markerFile}.lock`);
  let writes = Promise.resolve();
  try {
    let ledger = { version: 1, prepared: {} };
    try {
      ledger = JSON.parse(await readFile(markerFile, 'utf8'));
      if (ledger.version !== 1 || !ledger.prepared || typeof ledger.prepared !== 'object' || Array.isArray(ledger.prepared)) throw new Error('The preparation record has an unsupported format.');
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    const request = async (path, token, body) => {
      const response = await fetchImpl(`${origin}${path}`, {
        method: body === undefined ? 'GET' : 'POST',
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(30_000),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(`Preparation request failed (${response.status}): ${safeMessage(data.error || 'Please try again.')}`);
      return data;
    };
    const remember = (id, entry) => {
      const operation = writes.then(async () => {
        const next = { ...ledger, prepared: { ...ledger.prepared, [id]: entry } };
        const temporary = `${markerFile}.${randomUUID()}.tmp`;
        try {
          await writeFile(temporary, JSON.stringify(next, null, 2), { mode: 0o600 });
          await rename(temporary, markerFile);
        } catch (error) { await unlink(temporary).catch(() => {}); throw error; }
        ledger = next;
      });
      writes = operation.catch(() => {});
      return operation;
    };
    const results = new Array(prompts.length);
    let cursor = 0;
    async function preparePerson(person) {
      const started = Date.now();
      const signedIn = await request('/api/auth/sign-in', null, { userId: person.id });
      const token = signedIn.token;
      const base = `/api/spaces/${encodeURIComponent(signedIn.ownSpaceId)}`;
      const promptHash = hash(`${version}\n${person.prompt}`);
      try {
        let snapshot = await request(base, token);
        const sessionId = snapshot.session.id;
        const previous = ledger.prepared[person.id];
        let revisions;
        const loadRevisions = async () => revisions ||= await request(`${base}/revisions`, token);
        if (!rebuild && previous?.promptHash === promptHash && previous.sessionId === sessionId) {
          const saved = (await loadRevisions()).find(revision => revision.id === previous.revisionId);
          if (saved && sourceHash(saved) === previous.sourceHash) {
            log(`${person.name || person.id}: already generated; preserved the current page.`);
            return { id: person.id, status: 'skipped', revisionId: previous.revisionId };
          }
        }
        let turn = !rebuild && [...(snapshot.session.turns || [])].reverse().find(item => item.message === person.prompt && ['running', 'completed'].includes(item.status));
        if (!turn) {
          if (snapshot.session.status === 'running') throw new Error('This person already has an active edit. Let it finish before preparation.');
          log(`${person.name || person.id}: submitting the creative brief through the normal builder.`);
          const submitted = await request(`${base}/turn`, token, { message: person.prompt });
          if (submitted.steering) throw new Error('Another edit started during preparation. Wait for the existing turn before trying again.');
          turn = { id: submitted.turnId, status: 'running' };
        } else log(`${person.name || person.id}: resuming the recorded preparation turn.`);
        while (turn.status === 'running') {
          if (Date.now() - started > timeoutMs) throw new Error('Preparation timed out; the server may still be building. Rerun to resume checking the same turn.');
          await wait(pollMs);
          snapshot = await request(base, token);
          if (snapshot.session.id !== sessionId) throw new Error('The space was reset during preparation. Retry after the reset finishes.');
          const found = snapshot.session.turns?.find(item => item.id === turn.id);
          if (!found) throw new Error('The preparation turn is no longer present in the saved thread.');
          turn = found;
        }
        if (turn.status !== 'completed') {
          const detail = snapshot.events?.findLast(event => event.turnId === turn.id && ['turn.failed', 'turn.cancelled'].includes(event.type))?.detail;
          throw new Error(detail || `The builder turn ended as ${turn.status}; no successful preparation was recorded.`);
        }
        const revisionId = turn.revisionId || snapshot.events?.findLast(event => event.turnId === turn.id && event.type === 'turn.completed')?.data?.revisionId;
        revisions = undefined;
        const revision = (await loadRevisions()).find(item => item.id === revisionId);
        if (!revision || revision.source.trim() === blankSeedSource.trim() || revision.meta?.layout !== 'canvas' ||
          !Array.isArray(revision.checks) || !revision.checks.length || revision.checks.some(check => check.ok !== true)) {
          throw new Error('The turn did not produce a verified generated canvas. No successful preparation was recorded.');
        }
        if ((person.requiredCapabilities || []).some(capability => !revision.meta?.capabilities?.includes(capability))) {
          throw new Error('The generated page omitted a required service capability. Review it and use --rebuild to generate again.');
        }
        if ((person.requiredAgentActions || []).some(name => !revision.meta?.agent?.actions?.some(action => action.name === name))) {
          throw new Error('The generated page omitted a required agent action. Review it and use --rebuild to generate again.');
        }
        if ((person.requiredGames || []).some(id => !revision.meta?.games?.some(game => game.id === id))) {
          throw new Error('The generated page omitted a required playable game. Review it and use --rebuild to generate again.');
        }
        if (snapshot.revision.id === revisionId && !snapshot.html?.trim()) throw new Error('The generated canvas is empty. No successful preparation was recorded.');
        const entry = { preparationVersion: version, promptHash, sessionId, turnId: turn.id, revisionId,
          sourceHash: sourceHash(revision), completedAt: new Date().toISOString() };
        await remember(person.id, entry);
        log(`${person.name || person.id}: generated revision ${revisionId}; ${revision.checks.length} checks passed.`);
        return { id: person.id, status: 'generated', revisionId };
      } finally {
        await request('/api/auth/sign-out', token, {}).catch(() => {});
      }
    }
    async function worker() {
      while (cursor < prompts.length) {
        const index = cursor++;
        try { results[index] = await preparePerson(prompts[index]); }
        catch (error) {
          results[index] = { id: prompts[index].id, status: 'failed', error: safeMessage(error) };
          log(`${prompts[index].name || prompts[index].id}: ${results[index].error}`);
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(concurrency, prompts.length) }, worker));
    await writes;
    return results;
  } finally { await writes; await release(); }
}

export function parsePreparationArgs(args) {
  let rebuild = false;
  let selected;
  const usage = 'Usage: node scripts/prepare-demo.mjs [--rebuild] [--only iris,luca]';
  for (let index = 0; index < args.length; index++) {
    if (args[index] === '--rebuild' && !rebuild) rebuild = true;
    else if (args[index] === '--only' && selected === undefined) {
      selected = args[++index]?.split(',');
      if (!selected?.length || selected.some(id => !demoPrompts.some(person => person.id === id)) || new Set(selected).size !== selected.length) {
        throw new Error(`${usage}. Choose unique IDs from: ${demoPrompts.map(person => person.id).join(', ')}.`);
      }
    } else throw new Error(usage);
  }
  return { rebuild, prompts: selected ? demoPrompts.filter(person => selected.includes(person.id)) : demoPrompts };
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try {
    const results = await prepareDemo(parsePreparationArgs(process.argv.slice(2)));
    if (results.some(result => result.status === 'failed')) process.exitCode = 1;
  } catch (error) { console.error(safeMessage(error)); process.exitCode = 1; }
}
