import { createHash, randomBytes, randomUUID } from 'node:crypto';
import { mkdir, readFile, rename, unlink, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { createSpaceService, spacePreviewVersion } from './harness.mjs';
import { blankSeedSource } from './seed.mjs';
import { createSocialGraph } from './social.mjs';
import { createSpaceIconManager } from './space-icons.mjs';
import { communityBoardSeed } from './community-board.mjs';
import { demoAppearanceFor, withDemoIconAppearance } from './demo-appearance.mjs';

const clone = (value) => structuredClone(value);
const tokenKey = (token) => createHash('sha256').update(token).digest('hex');
const generatedPersonId = /^person_[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const generatedSpaceId = /^space_[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/;
const sessionDurationMs = 12 * 60 * 60 * 1000;
export const httpError = (status, message) => Object.assign(new Error(message), { status });
export const demoUsers = [
  { id: 'mira', name: 'Mira', ownSpaceId: 'mira', kind: 'studio' },
  { id: 'james', name: 'James', ownSpaceId: 'james', kind: 'blank' },
  { id: 'jake', name: 'Jake', ownSpaceId: 'jake', kind: 'blank' },
  { id: 'erica', name: 'Erica', ownSpaceId: 'erica', kind: 'blank' },
  { id: 'leo', name: 'Leo', ownSpaceId: 'leo', kind: 'blank' },
  { id: 'iris', name: 'Iris', ownSpaceId: 'iris', kind: 'blank' },
  { id: 'luca', name: 'Luca', ownSpaceId: 'luca', kind: 'blank' },
  { id: 'karen', name: 'Karen', ownSpaceId: 'karen', kind: 'blank' },
  { id: 'nora', name: 'Nora', ownSpaceId: 'nora', kind: 'blank' },
];
export const personaProfiles = {
  mira: { role: 'Botany enthusiast', tagline: 'Growing a little wonder.', theme: 'botany', avatar: '/portraits/mira.jpg' },
  james: { role: 'Finance professional', tagline: 'A clearer view of what comes next.', theme: 'finance', avatar: '/portraits/james.jpg' },
  jake: { role: 'Nurse', tagline: 'A little knowledge. A little care.', theme: 'care', avatar: '/portraits/jake.jpg' },
  erica: { role: 'Neuroscientist', tagline: 'Curious minds, connected.', theme: 'neuroscience', avatar: '/portraits/erica.jpg' },
  iris: { role: 'Painter', tagline: 'One canvas. Everyone’s mark.', theme: 'painting' },
  luca: { role: 'Language teacher', tagline: 'A little Spanish, a new adventure.', theme: 'language-learning' },
  karen: { role: 'Arcade enthusiast', tagline: 'One more game. Four little adventures.', theme: 'retro-arcade' },
  nora: { role: 'Community host', tagline: 'Good company. Little discoveries.', theme: 'town-square' },
};

// This is deliberately a demo identity selector. The bearer token enforces a
// selected identity's permissions, but selecting that identity is not proof of
// who the person is. Replace signIn with verified OIDC in a hosted deployment.
export async function createSpaceDirectory({ dataDir, sessionTtlMs = sessionDurationMs, iconGenerator, ...serviceOptions }) {
  await mkdir(dataDir, { recursive: true, mode: 0o700 });
  const filename = join(dataDir, 'identities.json');
  let registry;
  try {
    registry = JSON.parse(await readFile(filename, 'utf8'));
    if (registry.version !== 1 || !Array.isArray(registry.users) || registry.users.some((user) => {
      if (!user || typeof user.name !== 'string' || !user.name.trim() || user.name.length > 48) return true;
      const demo = demoUsers.find((candidate) => candidate.id === user.id);
      if (demo) return user.ownSpaceId !== demo.ownSpaceId || user.kind !== demo.kind;
      return !generatedPersonId.test(user.id) || !generatedSpaceId.test(user.ownSpaceId) || user.kind !== 'blank';
    }) || new Set(registry.users.map((user) => user.id)).size !== registry.users.length ||
      new Set(registry.users.map((user) => user.ownSpaceId)).size !== registry.users.length ||
      !registry.users.some((user) => user.id === 'mira') || !registry.users.some((user) => user.id === 'leo')) {
      throw new Error('The saved demo identity directory has an unsupported format.');
    }
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    registry = { version: 1, users: clone(demoUsers) };
    await writeFile(filename, JSON.stringify(registry), { mode: 0o600 });
  }
  // Append missing demo people without rewriting any existing account or
  // workspace. Old registries still contain Mira, Leo and user-created people.
  const missingPeople = demoUsers.filter((demo) => !registry.users.some((user) => user.id === demo.id));
  if (missingPeople.length) {
    const next = { ...registry, users: [...registry.users, ...clone(missingPeople)] };
    const temporary = join(dataDir, `.identities-${randomUUID()}.tmp`);
    try {
      await writeFile(temporary, JSON.stringify(next), { mode: 0o600 });
      await rename(temporary, filename);
    } catch (error) { await unlink(temporary).catch(() => {}); throw error; }
    registry = next;
  }
  const sessions = new Map();
  const services = new Map();
  const iconControllers = new Map();
  const icons = createSpaceIconManager({ generate: iconGenerator });
  let writeQueue = Promise.resolve();
  let closed = false;
  const profileFor = (id) => personaProfiles[id] ? { ...personaProfiles[id] } : undefined;
  const displayOrder = new Map(demoUsers.map((person, index) => [person.id, index]));
  const people = () => [...registry.users].sort((left, right) => (displayOrder.get(left.id) ?? demoUsers.length) - (displayOrder.get(right.id) ?? demoUsers.length))
    .map(({ id, name, ownSpaceId }) => ({ id, name, ownSpaceId, ...(profileFor(id) ? { profile: profileFor(id) } : {}) }));
  const actors = () => registry.users.map(({ id, name }) => ({ id, name }));
  const social = await createSocialGraph({ dataDir, hasPerson: (id) => registry.users.some((user) => user.id === id) });
  const ownerForSpace = (id) => registry.users.find((user) => user.ownSpaceId === id);
  const serviceFor = async (id) => {
    const owner = ownerForSpace(id);
    if (!owner) throw httpError(404, 'This space does not exist.');
    if (closed) throw httpError(503, 'The space directory is closing.');
    if (!services.has(id)) {
      // Mira's existing data stays exactly where it was. Every additional
      // registered space receives its own store, workspace and agent thread.
      const directory = owner.id === 'mira' ? dataDir : join(dataDir, 'spaces', id);
      const opening = createSpaceService({ ...serviceOptions, dataDir: directory,
        ...(owner.id === 'nora' && serviceOptions.seedOverride === undefined ? { initialSeedOverride: communityBoardSeed } : {}),
        owner: { id: owner.id, name: owner.name }, kind: owner.kind === 'studio' ? 'studio' : 'blank', getActors: actors }).then(service => {
          const icon = icons.attach(service, { profile: profileFor(owner.id) });
          iconControllers.set(id, icon);
          void icon.ensure();
          return service;
        });
      services.set(id, opening);
      opening.catch(() => { if (services.get(id) === opening) services.delete(id); });
    }
    return services.get(id);
  };
  const metadata = async (id, renderedSource) => {
    const owner = ownerForSpace(id);
    const service = await serviceFor(id);
    const saved = service.store.read();
    const revision = saved.revisions.find((candidate) => candidate.id === saved.currentRevisionId);
    const appearance = demoAppearanceFor(owner.id, renderedSource ?? revision?.source);
    return { id, owner: { id: owner.id, name: owner.name }, kind: owner.kind === 'studio' ? 'studio' : 'blank',
      revisionId: saved.currentRevisionId, hasBuilt: Boolean(revision && revision.source.trim() !== blankSeedSource.trim()),
      previewVersion: spacePreviewVersion(saved),
      icon: withDemoIconAppearance(owner.id, iconControllers.get(id).metadata()),
      ...(appearance ? { appearance } : {}),
      ...(profileFor(owner.id) ? { profile: profileFor(owner.id) } : {}) };
  };
  const register = (rawName) => {
    const name = typeof rawName === 'string' ? rawName.trim().replace(/\s+/g, ' ') : '';
    if (!name || name.length > 48 || /[\x00-\x1f\x7f<>]/.test(name)) throw httpError(400, 'Choose a name between 1 and 48 characters.');
    const operation = writeQueue.then(async () => {
      if (closed) throw httpError(503, 'The space directory is closing.');
      if (registry.users.length >= 100) throw httpError(400, 'This local demo has reached its account limit.');
      const user = { id: `person_${randomUUID()}`, name, ownSpaceId: `space_${randomUUID()}`, kind: 'blank' };
      const next = { ...registry, users: [...registry.users, user] };
      const temporary = join(dataDir, `.identities-${randomUUID()}.tmp`);
      try {
        await writeFile(temporary, JSON.stringify(next), { mode: 0o600 });
        await rename(temporary, filename);
      } catch (error) { await unlink(temporary).catch(() => {}); throw error; }
      registry = next;
      return user;
    });
    writeQueue = operation.catch(() => {});
    return operation;
  };
  const endSession = (key) => {
    const session = sessions.get(key);
    if (!session) return;
    sessions.delete(key);
    clearTimeout(session.timeout);
    session.controller.abort();
  };
  const signIn = async (input = {}) => {
    if (closed) throw httpError(503, 'The space directory is closing.');
    const user = typeof input.userId === 'string'
      ? registry.users.find((candidate) => candidate.id === input.userId)
      : await register(input.name);
    if (!user) throw httpError(404, 'Choose a person from this local demo.');
    await serviceFor(user.ownSpaceId);
    if (closed) throw httpError(503, 'The space directory is closing.');
    const token = randomBytes(32).toString('base64url');
    const key = tokenKey(token);
    const session = { userId: user.id, expiresAt: Date.now() + sessionTtlMs, controller: new AbortController() };
    session.timeout = setTimeout(() => endSession(key), sessionTtlMs);
    session.timeout.unref();
    sessions.set(key, session);
    return { token, user: { id: user.id, name: user.name }, ownSpaceId: user.ownSpaceId, simulated: true };
  };
  const authenticate = (authorization) => {
    if (closed) throw httpError(503, 'The space directory is closing.');
    const match = /^Bearer ([A-Za-z0-9_-]{43})$/.exec(authorization || '');
    if (!match) throw httpError(401, 'Choose a person to enter Little Worlds.');
    const key = tokenKey(match[1]);
    const session = sessions.get(key);
    if (!session || session.expiresAt <= Date.now()) {
      endSession(key);
      throw httpError(401, 'Your demo session ended. Please sign in again.');
    }
    const user = registry.users.find((candidate) => candidate.id === session.userId);
    if (!user) { endSession(key); throw httpError(401, 'Your demo session ended.'); }
    return { user: { id: user.id, name: user.name }, ownSpaceId: user.ownSpaceId,
      signal: session.controller.signal, active: () => sessions.has(key) && session.expiresAt > Date.now(), revoke: () => endSession(key) };
  };
  const list = async () => Promise.all(registry.users.map((user) => metadata(user.ownSpaceId)));
  const community = async (actorId) => {
    // Validate the principal before opening any other person's public space.
    const graph = social.snapshot(actorId);
    return { spaces: await list(), ...graph };
  };
  const iconFor = async (id) => { await serviceFor(id); return withDemoIconAppearance(ownerForSpace(id).id, iconControllers.get(id).metadata()); };
  const uploadIcon = async (id, normalized) => {
    await serviceFor(id);
    return withDemoIconAppearance(ownerForSpace(id).id, await iconControllers.get(id).upload(normalized));
  };
  const regenerateIcon = async (id) => {
    await serviceFor(id);
    if (!iconGenerator) throw httpError(503, 'Image generation is not configured.');
    const controller = iconControllers.get(id);
    // Image generation is independent of page edits and HTTP request lifetime.
    // The controller persists failures and exposes them through its metadata.
    void controller.regenerate().catch(() => {});
    return withDemoIconAppearance(ownerForSpace(id).id, controller.metadata());
  };
  return { people, actors, ownerForSpace, serviceFor, metadata, signIn, authenticate, list, community,
    iconFor, uploadIcon, regenerateIcon,
    async requestFriend(actorId, targetId) { if (closed) throw httpError(503, 'The space directory is closing.'); await social.requestFriend(actorId, targetId); return community(actorId); },
    async respondFriend(actorId, requestId, decision) { if (closed) throw httpError(503, 'The space directory is closing.'); await social.respondFriend(actorId, requestId, decision); return community(actorId); },
    async removeFriend(actorId, targetId) { if (closed) throw httpError(503, 'The space directory is closing.'); await social.removeFriend(actorId, targetId); return community(actorId); },
    async close() {
      closed = true;
      for (const key of [...sessions.keys()]) endSession(key);
      await writeQueue;
      await social.close();
      await Promise.allSettled([...services.values()]);
      await icons.close();
      const outcomes = await Promise.allSettled([...services.values()].map(async (opening) => (await opening).close()));
      const failed = outcomes.find(outcome => outcome.status === 'rejected');
      if (failed) throw failed.reason;
    },
  };
}

// Only these public changes can reach a visitor. Do not pass through arbitrary
// event data: tool output can contain source, tests, prompts or session details.
export function publicEvent(event) {
  const titles = { 'space.updated': 'Someone joined in', 'revision.published': 'This space evolved',
    'revision.restored': 'This space evolved', 'space.reset': 'A fresh beginning', 'icon.updated': 'This space has a new icon' };
  if (!Object.hasOwn(titles, event.type)) return null;
  const revisionId = event.data?.revisionId;
  return { id: event.id, time: event.time, type: event.type, title: titles[event.type],
    data: Number.isInteger(revisionId) ? { revisionId } : {} };
}

export function scopedSnapshot(snapshot, space, canEdit) {
  const permissions = { canEdit, canViewRuntime: canEdit };
  if (canEdit) return { ...snapshot, space, permissions };
  const { id, title, createdAt, meta } = snapshot.revision;
  return { state: clone(snapshot.state), html: snapshot.html, actor: snapshot.actor, space, permissions,
    revision: { id, title, createdAt, meta }, session: { status: snapshot.session.status },
    config: { adapter: 'local' }, events: snapshot.events.map(publicEvent).filter(Boolean) };
}
