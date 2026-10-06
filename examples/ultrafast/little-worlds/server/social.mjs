import { randomUUID } from 'node:crypto';
import { mkdir, readFile, rename, unlink, writeFile } from 'node:fs/promises';
import { join } from 'node:path';

const fail = (status, message) => Object.assign(new Error(message), { status });
const clone = (value) => structuredClone(value);
const pair = (left, right) => [left, right].sort();
const edgeFor = (left, right) => {
  const [source, target] = pair(left, right);
  return { id: `friend:${source}:${target}`, source, target };
};
const samePair = (request, left, right) =>
  (request.fromId === left && request.toId === right) || (request.fromId === right && request.toId === left);

// These are sample relationships between fictional demo people. All later
// relationships require a request and the recipient's explicit acceptance.
export const demoConnections = [
  ['mira', 'erica'], ['erica', 'james'], ['erica', 'jake'], ['james', 'jake'],
  ['mira', 'iris'], ['iris', 'luca'], ['erica', 'luca'],
];

export async function createSocialGraph({ dataDir, hasPerson, initialConnections = demoConnections }) {
  await mkdir(dataDir, { recursive: true, mode: 0o700 });
  const filename = join(dataDir, 'community.json');
  const requirePerson = (id, actor = false) => {
    if (typeof id !== 'string' || !hasPerson(id)) throw fail(actor ? 401 : 404, actor ? 'Choose a person to enter Little Worlds.' : 'This person does not exist.');
  };
  const requirePair = (actorId, targetId) => {
    requirePerson(actorId, true); requirePerson(targetId);
    if (actorId === targetId) throw fail(400, 'Choose another person to connect with.');
  };
  let state;
  try {
    state = JSON.parse(await readFile(filename, 'utf8'));
    const invalidConnection = (edge) => !edge || typeof edge.source !== 'string' || typeof edge.target !== 'string' ||
      !hasPerson(edge.source) || !hasPerson(edge.target) || edge.source >= edge.target || edge.id !== edgeFor(edge.source, edge.target).id;
    const invalidRequest = (request) => !request || typeof request.id !== 'string' ||
      !hasPerson(request.fromId) || !hasPerson(request.toId) || request.fromId === request.toId ||
      !['pending', 'accepted', 'declined', 'cancelled'].includes(request.status) || typeof request.createdAt !== 'string';
    if (state.version !== 1 || !Array.isArray(state.connections) || !Array.isArray(state.requests) ||
      state.connections.some(invalidConnection) || state.requests.some(invalidRequest) ||
      new Set(state.connections.map((edge) => edge.id)).size !== state.connections.length ||
      new Set(state.requests.map((request) => request.id)).size !== state.requests.length) {
      throw new Error('The saved community has an unsupported format.');
    }
    const pendingPairs = state.requests.filter((request) => request.status === 'pending').map((request) => edgeFor(request.fromId, request.toId).id);
    if (new Set(pendingPairs).size !== pendingPairs.length || pendingPairs.some((id) => state.connections.some((edge) => edge.id === id))) {
      throw new Error('The saved community has conflicting requests.');
    }
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    const connections = initialConnections.filter(([left, right]) => left !== right && hasPerson(left) && hasPerson(right)).map(([left, right]) => edgeFor(left, right));
    state = { version: 1, connections: [...new Map(connections.map((edge) => [edge.id, edge])).values()], requests: [] };
    await writeFile(filename, JSON.stringify(state), { mode: 0o600 });
  }
  let queue = Promise.resolve();
  let closed = false;
  const transact = (change) => {
    if (closed) return Promise.reject(fail(503, 'The community is closing.'));
    const operation = queue.then(async () => {
      const next = clone(state);
      const result = change(next);
      const temporary = join(dataDir, `.community-${randomUUID()}.tmp`);
      try {
        await writeFile(temporary, JSON.stringify(next), { mode: 0o600 });
        await rename(temporary, filename);
      } catch (error) { await unlink(temporary).catch(() => {}); throw error; }
      state = next;
      return clone(result);
    });
    queue = operation.catch(() => {});
    return operation;
  };
  const snapshot = (actorId) => {
    requirePerson(actorId, true);
    const pending = state.requests.filter((request) => request.status === 'pending');
    return clone({ connections: state.connections, requests: {
      incoming: pending.filter((request) => request.toId === actorId),
      outgoing: pending.filter((request) => request.fromId === actorId),
    } });
  };
  const requestFriend = (actorId, targetId) => {
    requirePair(actorId, targetId);
    return transact((next) => {
      const edge = edgeFor(actorId, targetId);
      if (next.connections.some((connection) => connection.id === edge.id)) return { status: 'connected' };
      const existing = next.requests.find((request) => request.status === 'pending' && samePair(request, actorId, targetId));
      // Crossing requests remain pending. Clicking Connect is never consent to
      // accept an incoming request; that is a separate recipient-only action.
      if (existing) return existing;
      const createdAt = new Date().toISOString();
      const request = { id: randomUUID(), fromId: actorId, toId: targetId, status: 'pending', createdAt, updatedAt: createdAt };
      next.requests.push(request);
      return request;
    });
  };
  const respondFriend = (actorId, requestId, decision) => {
    requirePerson(actorId, true);
    if (!['accept', 'decline', 'cancel'].includes(decision)) throw fail(400, 'Choose accept, decline or cancel.');
    return transact((next) => {
      const request = next.requests.find((candidate) => candidate.id === requestId);
      if (!request || (request.fromId !== actorId && request.toId !== actorId)) throw fail(404, 'This friend request does not exist.');
      const permitted = decision === 'cancel' ? request.fromId === actorId : request.toId === actorId;
      if (!permitted) throw fail(403, decision === 'cancel' ? 'Only the sender can cancel this request.' : 'Only the recipient can respond to this request.');
      const status = { accept: 'accepted', decline: 'declined', cancel: 'cancelled' }[decision];
      if (request.status === status) return request;
      if (request.status !== 'pending') throw fail(409, 'This friend request has already been resolved.');
      request.status = status;
      request.updatedAt = new Date().toISOString();
      if (decision === 'accept') next.connections.push(edgeFor(request.fromId, request.toId));
      return request;
    });
  };
  const removeFriend = (actorId, targetId) => {
    requirePair(actorId, targetId);
    return transact((next) => {
      const edge = edgeFor(actorId, targetId);
      next.connections = next.connections.filter((connection) => connection.id !== edge.id);
      return { status: 'disconnected' };
    });
  };
  return { snapshot, requestFriend, respondFriend, removeFriend, async close() { closed = true; await queue; } };
}
