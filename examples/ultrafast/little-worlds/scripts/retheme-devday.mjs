import { createHash, randomUUID } from 'node:crypto';
import { mkdir, open, readFile, rename, unlink, writeFile } from 'node:fs/promises';
import { dirname, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { parse } from '@babel/parser';
import traverseModule from '@babel/traverse';
import { appSetting } from '../server/environment.mjs';
import { blankSeedSource } from '../server/seed.mjs';
import { verifyModule } from '../server/runtime.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const traverse = traverseModule.default || traverseModule;
const hash = value => createHash('sha256').update(typeof value === 'string' ? value : stable(value)).digest('hex');
const wait = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));
const safeError = error => String(error?.message || error).replace(/sk-[A-Za-z0-9_-]+/g, '[redacted]').slice(0, 700);
const stable = value => JSON.stringify(order(value));
function order(value) {
  if (Array.isArray(value)) return value.map(order);
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.keys(value).sort().map(key => [key, order(value[key])]));
}
const sourceHash = revision => hash(`${revision.source}\n${revision.tests}`);

export const devdayRestyleVersion = 'devday-2026-visual-only-v1';
export const devdayRestylePrompt = `Restyle this CURRENT existing world for OpenAI DevDay 2026. This is a VISUAL-ONLY migration, not a new world or feature rewrite. First inspect and read the complete current space.js and tests.js. Preserve every tile, title, description, label, artwork subject, interaction, form, service and playable game, including all user-created additions. Keep exact stable IDs, catalog order, meta.title/subtitle/budget/layout, capabilities, agent instructions/action definitions, game configuration, and suggestions. Keep the existing reduce function and each game's init/step implementation unchanged. Preserve existing tests and add design checks only if useful. Do not simplify or replace functionality. Preserve the entire saved state, contributions, extras, game progress, paintings and participant ownership. Only project color fields may change; never seed/reset data.
Use the app's DevDay design language deliberately throughout this world's own rendering and artwork: black #000000 canvas, charcoal #111111 / #191919 surfaces, hairline #303030 separators, white #ffffff main text, neutral #a0a0a0 secondary text, DevDay green #04b84c and purple #924ff7; use readable lighter #57dc8c / #b58cff for small accent text. Blue #006aff and orange #ff8549 are sparing subject-specific accents. Use clean sans-serif typography, clear large headings, precise grids and square or subtly rounded geometry. Carry this palette into inline SVG illustrations and game view colors while retaining each world's subject and every mechanic. Maintain distinguishable color-coding and useful contrast, especially canvas palettes and game pieces. A white drawing canvas may stay white when needed for painting, and never recolor saved artwork. Include a restrained DevDay [2026] identifier where it fits, without renaming the world or crowding its content. Use subtle opacity/transform entrances and hover/focus transitions only, with prefers-reduced-motion support; no flashing or distracting continuous motion. Preserve responsive layouts, touch and keyboard controls, labels, all data-action/data-game/data-service/data-paint hooks, empty/error/loading states and meaningful accessibility. Check the complete preserved behavior with the existing tests before publishing. Do not change anything outside this world.`;

function normalizeAst(value) {
  if (Array.isArray(value)) return value.map(normalizeAst);
  if (!value || typeof value !== 'object') return value;
  return Object.fromEntries(Object.entries(value).filter(([key]) => !['start', 'end', 'loc', 'extra', 'leadingComments', 'trailingComments', 'innerComments'].includes(key)).map(([key, item]) => [key, normalizeAst(item)]));
}

function normalizeLogicDependency(node) {
  const normalized = normalizeAst(node);
  function visit(value) {
    if (Array.isArray(value)) return value.map(visit);
    if (!value || typeof value !== 'object') return value;
    // Catalog-like data can supply colors as well as IDs used by validators
    // (for example Nora's topics). Preserve every field except the value of a
    // literal hex `color`, the same visual field allowed in project metadata.
    if (value.type === 'ObjectProperty' && !value.computed && (value.key?.name ?? value.key?.value) === 'color' &&
      value.value?.type === 'StringLiteral' && /^#(?:[a-f\d]{3,4}|[a-f\d]{6}|[a-f\d]{8})$/i.test(value.value.value)) {
      return { ...value, value: { ...value.value, value: '[theme color]' } };
    }
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, visit(item)]));
  }
  return visit(normalized);
}

function moduleFunctions(source, meta) {
  const body = parse(source, { sourceType: 'module' }).program.body;
  const bindings = new Map();
  for (const statement of body) {
    const declaration = statement.type === 'ExportNamedDeclaration' ? statement.declaration : statement;
    if (declaration?.type === 'FunctionDeclaration') bindings.set(declaration.id.name, declaration);
    if (declaration?.type === 'VariableDeclaration') {
      for (const item of declaration.declarations) if (item.id.type === 'Identifier') bindings.set(item.id.name, item.init);
    }
  }
  const resolveNode = node => node?.type === 'Identifier' ? bindings.get(node.name) : node;
  const reduce = resolveNode(bindings.get('reduce'));
  if (!reduce) throw new Error('Cannot fingerprint the current reducer. No restyle was submitted.');
  const gameLogic = {};
  for (const configuration of meta.games || (meta.game ? [{ ...meta.game, exportName: meta.game.exportName || 'game' }] : [])) {
    const game = resolveNode(bindings.get(configuration.exportName));
    if (game?.type !== 'ObjectExpression') throw new Error('Cannot fingerprint the current game implementation. No restyle was submitted.');
    gameLogic[configuration.id] = {};
    for (const name of ['init', 'step']) {
      const property = game.properties.find(item => (item.key?.name || item.key?.value) === name);
      const implementation = property?.type === 'ObjectMethod' ? property : resolveNode(property?.value);
      if (!implementation) throw new Error('Cannot fingerprint all game mechanics. No restyle was submitted.');
      gameLogic[configuration.id][name] = normalizeAst(implementation);
    }
  }
  return { reducer: normalizeAst(reduce), gameLogic };
}

// Follow lexical bindings, not identifier text: a local variable shadowing a
// module constant must not pull an unrelated presentation helper into this
// contract. Static object-member references select just that member, allowing
// a shared helper object to contain independent drawing and logic functions.
export function logicDependencyFingerprint(source, meta = {}) {
  const ast = parse(source, { sourceType: 'module' });
  let program;
  traverse(ast, { Program(path) { program = path; path.stop(); } });
  const selected = new Map();
  const pending = [];
  const gameNames = new Set((meta.games || (meta.game ? [{ ...meta.game, exportName: meta.game.exportName || 'game' }] : [])).map(game => game.exportName));
  const declaration = binding => binding.path.isVariableDeclarator() ? binding.path.get('init') : binding.path;
  const memberName = path => !path.node.computed && path.get('property').isIdentifier()
    ? path.node.property.name : path.get('property').isStringLiteral() ? path.node.property.value : undefined;
  const objectMember = (path, name) => path.isObjectExpression() && !path.node.properties.some(property => property.type === 'SpreadElement')
    ? path.get('properties').find(property => !property.node.computed && (property.node.key?.name ?? property.node.key?.value) === name) : undefined;

  function follow(reference) {
    const binding = reference.scope.getBinding(reference.node.name);
    if (!binding || binding.scope !== program.scope) return;
    const path = declaration(binding);
    if (!path?.node) throw new Error('Cannot fingerprint an uninitialized module dependency.');
    const parent = reference.parentPath;
    const name = parent?.isMemberExpression() && parent.get('object') === reference ? memberName(parent) : undefined;
    const property = name === undefined ? undefined : objectMember(path, name);
    // These interfaces are explicitly allowed to change for visual restyles.
    // Some reducers call render for an HTML size budget, or game.view to
    // validate a checkpoint; that does not make their CSS/palettes mechanics.
    if (binding.identifier.name === 'render' || (gameNames.has(binding.identifier.name) && name === 'view')) {
      selected.set(`${binding.identifier.name}${name ? `.${name}` : ''}`, { presentation: true });
      return;
    }
    if (gameNames.has(binding.identifier.name) && name === undefined && path.isObjectExpression()) {
      const key = binding.identifier.name;
      if (selected.has(key)) return;
      const mechanics = path.get('properties').filter(property => (property.node.key?.name ?? property.node.key?.value) !== 'view');
      selected.set(key, { kind: binding.kind, declaration: mechanics.map(property => normalizeLogicDependency(property.node)) });
      pending.push(...mechanics);
      return;
    }
    // Fixed literal length is the only information read from such a constant.
    // Its palette values may be used independently by render/game.view.
    const lengthOnly = name === 'length' && ((path.isArrayExpression() && path.node.elements.every(element => !element || ['StringLiteral', 'NumericLiteral', 'BooleanLiteral', 'NullLiteral', 'BigIntLiteral'].includes(element.type))) || path.isStringLiteral());
    const key = `${binding.identifier.name}${property || lengthOnly ? `.${name}` : ''}`;
    if (selected.has(key)) return;
    selected.set(key, lengthOnly ? { length: path.isArrayExpression() ? path.node.elements.length : path.node.value.length }
      : { kind: binding.kind, declaration: normalizeLogicDependency((property || path).node) });
    if (!lengthOnly) pending.push(property || path);
    // Module initialization can reassign a let binding after its declaration.
    // Changes in a reachable function are already included by its own AST.
    for (const violation of binding.constantViolations) {
      if (violation.getFunctionParent()) continue;
      const violationKey = `${binding.identifier.name}:initialization:${binding.constantViolations.indexOf(violation)}`;
      if (!selected.has(violationKey)) { selected.set(violationKey, normalizeAst(violation.node)); pending.push(violation); }
    }
  }
  function resolved(path, seen = new Set()) {
    if (!path?.node) throw new Error('Cannot fingerprint a missing logic implementation.');
    if (!path.isIdentifier()) return path;
    const binding = path.scope.getBinding(path.node.name);
    if (!binding || binding.scope !== program.scope || seen.has(binding)) throw new Error('Cannot resolve a module logic binding.');
    seen.add(binding);
    return resolved(declaration(binding), seen);
  }
  const reducer = program.scope.getBinding('reduce');
  if (!reducer) throw new Error('Cannot fingerprint the current reducer.');
  pending.push(resolved(declaration(reducer)));
  for (const configuration of meta.games || (meta.game ? [{ ...meta.game, exportName: meta.game.exportName || 'game' }] : [])) {
    const binding = program.scope.getBinding(configuration.exportName);
    if (!binding) throw new Error('Cannot fingerprint the current game implementation.');
    const game = resolved(declaration(binding));
    for (const name of ['init', 'step']) {
      const property = objectMember(game, name);
      if (!property) throw new Error('Cannot fingerprint all game mechanics.');
      pending.push(resolved(property.isObjectMethod() ? property : property.get('value')));
    }
  }
  while (pending.length) {
    const path = pending.pop();
    if (path.isReferencedIdentifier()) follow(path);
    path.traverse({ ReferencedIdentifier: follow });
  }
  return hash(Object.fromEntries([...selected].sort(([left], [right]) => left.localeCompare(right))));
}

// Digests contain no public contributions, builder source or conversation text.
// Project colors may change; all other persistent content must remain identical.
export function preservationFingerprints(snapshot) {
  const state = structuredClone(snapshot.state);
  if (!state || !Array.isArray(state.projects)) throw new Error('The owner snapshot does not contain valid persistent state.');
  state.projects = state.projects.map(({ color: _color, ...project }) => project);
  const meta = structuredClone(snapshot.revision.meta || {});
  delete meta.accent;
  if (meta.projects) meta.projects = meta.projects.map(({ color: _color, ...project }) => project);
  const { reducer, gameLogic } = moduleFunctions(snapshot.revision.source, meta);
  return { state: hash(state), metadata: hash(meta), reducer: hash(reducer), gameLogic: hash(gameLogic),
    logicDependencies: logicDependencyFingerprint(snapshot.revision.source, meta) };
}

function localApi(value) {
  const url = new URL(value);
  if (!['http:', 'https:'].includes(url.protocol) || !['127.0.0.1', 'localhost', '[::1]'].includes(url.hostname) || url.username || url.password || url.pathname !== '/' || url.search || url.hash) throw new Error('Use a loopback API origin, such as http://127.0.0.1:4318.');
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
      try { pid = JSON.parse(await readFile(filename, 'utf8')).pid; } catch { /* fail closed */ }
      if (!Number.isInteger(pid) || pid < 1) throw new Error('The restyle lock is unreadable. Inspect it before retrying.');
      try { process.kill(pid, 0); } catch (probe) {
        if (probe.code === 'ESRCH') { await unlink(filename).catch(() => {}); continue; }
      }
      throw new Error('Another restyle process is active. Let it finish before retrying.');
    }
  }
  throw new Error('Could not acquire the restyle lock.');
}

export async function rethemeDevday({
  baseUrl = appSetting('API_URL', 'http://127.0.0.1:4318'),
  markerFile = resolve(root, '.local/devday-restyle.json'),
  only, icons = false, verifyRepair = false, concurrency = 2, pollMs = 1000, timeoutMs = 900_000,
  fetchImpl = fetch, verify = verifyModule, log = message => console.log(message),
} = {}) {
  const origin = localApi(baseUrl);
  if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 2) throw new Error('Restyling supports one or two concurrent worlds.');
  await mkdir(dirname(markerFile), { recursive: true, mode: 0o700 });
  const release = await acquireLock(`${markerFile}.lock`);
  let writes = Promise.resolve();
  try {
    let ledger = { version: 1, theme: devdayRestyleVersion, worlds: {} };
    try {
      ledger = JSON.parse(await readFile(markerFile, 'utf8'));
      if (ledger.version !== 1 || ledger.theme !== devdayRestyleVersion || !ledger.worlds || typeof ledger.worlds !== 'object' || Array.isArray(ledger.worlds)) throw new Error('The restyle record has an unsupported format.');
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    const remember = (id, entry) => {
      const operation = writes.then(async () => {
        const next = { ...ledger, worlds: { ...ledger.worlds, [id]: entry } };
        const temporary = `${markerFile}.${randomUUID()}.tmp`;
        try { await writeFile(temporary, JSON.stringify(next, null, 2), { mode: 0o600 }); await rename(temporary, markerFile); }
        catch (error) { await unlink(temporary).catch(() => {}); throw error; }
        ledger = next;
      });
      writes = operation.catch(() => {});
      return operation;
    };
    const request = async (path, token, body) => {
      const response = await fetchImpl(`${origin}${path}`, {
        method: body === undefined ? 'GET' : 'POST',
        headers: { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...(body === undefined ? {} : { 'Content-Type': 'application/json' }) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }), signal: AbortSignal.timeout(30_000),
      });
      if (!response.ok) throw new Error(`Restyle request failed (HTTP ${response.status}) at ${path.replace(/\/spaces\/[^/]+/, '/spaces/[world]')}.`);
      return response.json();
    };
    const { users } = await request('/api/auth/people');
    if (!Array.isArray(users) || !users.length) throw new Error('The API returned no registered worlds.');
    const people = only ? users.filter(person => only.includes(person.id) || only.includes(person.ownSpaceId)) : users;
    if (only?.some(id => !people.some(person => person.id === id || person.ownSpaceId === id))) throw new Error('One or more --only IDs do not match a registered person or world.');
    const results = new Array(people.length);
    let cursor = 0;
    async function restylePerson(person) {
      const started = Date.now();
      const signedIn = await request('/api/auth/sign-in', null, { userId: person.id });
      const token = signedIn.token;
      const base = `/api/spaces/${encodeURIComponent(signedIn.ownSpaceId)}`;
      if (signedIn.ownSpaceId !== person.ownSpaceId) throw new Error('The selected identity does not own the expected world.');
      let entry;
      try {
        let snapshot = await request(base, token);
        if (snapshot.revision.source.trim() === blankSeedSource.trim()) {
          log(`${person.name}: blank world preserved.`);
          return { id: person.id, status: 'blank' };
        }
        const previous = ledger.worlds[person.id];
        if (previous && previous.sessionId !== snapshot.session.id) throw new Error('The world was reset since restyling began. Review its new contents before starting a new migration record.');
        entry = previous;
        if (!entry) {
          if (snapshot.session.status === 'running') throw new Error('An unrelated edit is running. Leave the editor idle and retry when it finishes.');
          entry = { sessionId: snapshot.session.id, baselineRevisionId: snapshot.revision.id, baselineSourceHash: sourceHash(snapshot.revision), fingerprints: preservationFingerprints(snapshot), startedAt: new Date().toISOString(), status: 'prepared' };
          // Persist the baseline before any model request. A crash after POST can
          // recover the exact tagged turn without submitting another edit.
          await remember(person.id, entry);
        }
        let revisions;
        let original;
        const loadOriginal = async () => {
          revisions ||= await request(`${base}/revisions`, token);
          original ||= revisions.find(item => item.id === entry.baselineRevisionId);
          if (!original || sourceHash(original) !== entry.baselineSourceHash) throw new Error('The original revision is missing or changed. Cannot verify preservation.');
          return original;
        };
        // Earlier in-flight runs recorded the direct function hashes. Derive
        // the new dependency contract from their immutable original revision,
        // never the current result, without regenerating or rewriting markers.
        let baselineFingerprints = entry.fingerprints;
        if (!Object.hasOwn(baselineFingerprints, 'logicDependencies')) {
          const baseline = await loadOriginal();
          baselineFingerprints = { ...baselineFingerprints, logicDependencies: logicDependencyFingerprint(baseline.source, baseline.meta) };
        }
        const message = `${devdayRestylePrompt}\n\nMigration: ${devdayRestyleVersion}; original revision ${entry.baselineRevisionId}.`;
        let turn = entry.turnId ? snapshot.session.turns.find(item => item.id === entry.turnId) : [...snapshot.session.turns].reverse().find(item => item.message === message);
        if (entry.status !== 'complete') {
          if (verifyRepair && snapshot.session.status !== 'running' && snapshot.revision.id !== entry.baselineRevisionId) {
            const repair = [...snapshot.session.turns].reverse().find(item => item.status === 'completed' &&
              (item.revisionId === snapshot.revision.id || snapshot.events?.some(event => event.type === 'turn.completed' && event.turnId === item.id && event.data?.revisionId === snapshot.revision.id)));
            if (!repair) throw new Error('The current repair is not linked to a completed owner turn. Cannot confirm it.');
            entry = { ...entry, originalTurnId: entry.originalTurnId || entry.turnId, turnId: repair.id };
            turn = repair;
          }
          if (!turn) {
            if (entry.turnId) throw new Error('The recorded restyle turn is missing. Inspect the saved thread before retrying.');
            if (snapshot.session.status === 'running' || snapshot.revision.id !== entry.baselineRevisionId || sourceHash(snapshot.revision) !== entry.baselineSourceHash || stable(preservationFingerprints(snapshot)) !== stable(baselineFingerprints)) throw new Error('The world changed after its baseline was recorded. Review it before submitting a restyle.');
            log(`${person.name}: restyling the existing world through its owner builder.`);
            const submitted = await request(`${base}/turn`, token, { message });
            if (submitted.steering) throw new Error('Another edit started during submission. Inspect that turn before retrying.');
            turn = { id: submitted.turnId, status: 'running' };
          } else log(`${person.name}: resuming the recorded restyle check.`);
          entry = { ...entry, turnId: turn.id, status: 'running' };
          await remember(person.id, entry);
          while (turn.status === 'running') {
            if (Date.now() - started > timeoutMs) throw new Error('Restyling timed out; the server may still be building. Rerun to resume checking the same turn.');
            await wait(pollMs);
            snapshot = await request(base, token);
            if (snapshot.session.id !== entry.sessionId) throw new Error('The world was reset during restyling. Stop and review it.');
            turn = snapshot.session.turns.find(item => item.id === entry.turnId);
            if (!turn) throw new Error('The recorded restyle turn is no longer present.');
          }
          if (turn.status !== 'completed') throw new Error(`The restyle turn ended as ${turn.status}. Review and repair through the owner builder; no successful restyle was recorded.`);
          snapshot = await request(base, token);
          const revisionId = turn.revisionId || snapshot.events?.findLast(event => event.turnId === turn.id && event.type === 'turn.completed')?.data?.revisionId;
          if (snapshot.revision.id !== revisionId) throw new Error('Another revision followed the restyle. Review it before confirming preservation.');
          const revision = snapshot.revision;
          if (sourceHash(revision) === entry.baselineSourceHash) throw new Error('The completed turn did not change the world. No restyle was accepted.');
          if (!snapshot.html?.trim() || !revision.checks?.length || revision.checks.some(check => !check.ok) || revision.source.trim() === blankSeedSource.trim()) throw new Error('The restyle did not publish a verified, nonempty world.');
          const differences = Object.entries(preservationFingerprints(snapshot)).filter(([key, value]) => baselineFingerprints[key] !== value).map(([key]) => key);
          if (differences.length) throw new Error(`Preservation check failed: ${differences.join(', ')} changed. The revision was published but is NOT accepted; repair it through the owner builder using the original revision before retrying.`);
          const original = await loadOriginal();
          const originalChecks = await verify(revision.source, original.tests, snapshot.state, { owner: { id: person.id, name: person.name }, visitor: { id: 'devday-preservation-visitor', name: 'Visitor' }, projectCatalog: true });
          if (!originalChecks.ok) throw new Error('The restyled world failed its ORIGINAL feature tests. Repair it before confirming preservation.');
          entry = { ...entry, fingerprints: baselineFingerprints, status: 'complete', revisionId, sourceHash: sourceHash(revision), verifiedAt: new Date().toISOString(), originalChecks: originalChecks.checks.length };
          await remember(person.id, entry);
          log(`${person.name}: visual restyle verified; state, mechanics and original feature tests preserved.`);
        } else {
          revisions ||= await request(`${base}/revisions`, token);
          const accepted = revisions.find(item => item.id === entry.revisionId && sourceHash(item) === entry.sourceHash);
          if (!accepted) throw new Error('The accepted restyle revision is missing or changed.');
          if (logicDependencyFingerprint(accepted.source, accepted.meta) !== baselineFingerprints.logicDependencies) throw new Error('Preservation check failed: logicDependencies changed in the accepted restyle. Review and repair the world before accepting it.');
          log(`${person.name}: already restyled; current owner edits preserved.`);
        }
        if (icons && entry.iconStatus !== 'complete') {
          let { icon } = await request(`${base}/icon`, token);
          if (!entry.iconStatus) {
            entry = { ...entry, iconStatus: 'prepared', originalIconVersion: icon.version || null };
            await remember(person.id, entry);
            ({ icon } = await request(`${base}/icon/generate`, token, {}));
            entry = { ...entry, iconStatus: 'running' };
            await remember(person.id, entry);
          } else if (icon.status === 'empty' || (icon.status === 'ready' && (icon.version || null) === entry.originalIconVersion)) {
            // The manager reports generating whenever an active job exists.
            // Ready with the old version means a crash/restart abandoned the
            // request (or occurred before POST); resubmit once on this resume.
            log(`${person.name}: resuming an interrupted icon request.`);
            ({ icon } = await request(`${base}/icon/generate`, token, {}));
            entry = { ...entry, iconStatus: 'running' };
            await remember(person.id, entry);
          }
          const iconStart = Date.now();
          while (icon.status === 'generating' || (icon.status === 'ready' && (icon.version || null) === entry.originalIconVersion)) {
            if (Date.now() - iconStart > timeoutMs) throw new Error('The icon is still pending. Rerun to resume checking it without submitting another request.');
            await wait(pollMs);
            ({ icon } = await request(`${base}/icon`, token));
          }
          if (icon.status !== 'ready' || !icon.dataUrl) throw new Error('The world is preserved, but its icon regeneration failed. Regenerate the icon through its normal owner control.');
          entry = { ...entry, iconStatus: 'complete', iconVersion: icon.version, iconVerifiedAt: new Date().toISOString() };
          await remember(person.id, entry);
          log(`${person.name}: themed icon ready.`);
        }
        return { id: person.id, status: previous?.status === 'complete' ? 'skipped' : 'restyled', revisionId: entry.revisionId, ...(icons ? { iconStatus: entry.iconStatus } : {}) };
      } finally { await request('/api/auth/sign-out', token, {}).catch(() => {}); }
    }
    async function worker() {
      while (cursor < people.length) {
        const index = cursor++;
        try { results[index] = await restylePerson(people[index]); }
        catch (error) { results[index] = { id: people[index].id, status: 'failed', error: safeError(error) }; log(`${people[index].name}: ${safeError(error)}`); }
      }
    }
    await Promise.all(Array.from({ length: Math.min(concurrency, people.length) }, worker));
    await writes;
    return results;
  } finally { await writes; await release(); }
}

export function parseRethemeArgs(args) {
  const options = {};
  const usage = 'Usage: node scripts/retheme-devday.mjs [--only person-id,space-id] [--icons] [--verify-repair] [--api-url http://127.0.0.1:4318] [--data-dir .local]';
  for (let index = 0; index < args.length; index++) {
    const flag = args[index];
    if (flag === '--icons' && options.icons === undefined) options.icons = true;
    else if (flag === '--verify-repair' && options.verifyRepair === undefined) options.verifyRepair = true;
    else if (flag === '--only' && options.only === undefined) {
      options.only = args[++index]?.split(',');
      if (!options.only?.length || options.only.some(id => !/^[A-Za-z0-9_-]+$/.test(id)) || new Set(options.only).size !== options.only.length) throw new Error(usage);
    } else if (flag === '--api-url' && options.baseUrl === undefined) { options.baseUrl = args[++index]; if (!options.baseUrl) throw new Error(usage); localApi(options.baseUrl); }
    else if (flag === '--data-dir' && options.markerFile === undefined) { const dir = args[++index]; if (!dir || dir.startsWith('--')) throw new Error(usage); options.markerFile = resolve(dir, 'devday-restyle.json'); }
    else throw new Error(usage);
  }
  return options;
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  try { const results = await rethemeDevday(parseRethemeArgs(process.argv.slice(2))); if (results.some(result => result.status === 'failed')) process.exitCode = 1; }
  catch (error) { console.error(safeError(error)); process.exitCode = 1; }
}
