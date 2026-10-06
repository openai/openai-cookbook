import express from 'express';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { resolve, join } from 'node:path';
import { existsSync } from 'node:fs';
import { createSpaceDirectory, demoUsers, httpError, publicEvent, scopedSnapshot } from './identity.mjs';
import { beginDemoReset, recoverDemoReset } from './demo-reset.mjs';
import { publicError } from './responses.mjs';
import { createPersonaServices, validateHealthMessages } from './persona-services.mjs';
import { createSpaceIconGenerator, normalizeSpaceIcon, SPACE_ICON_MAX_BYTES } from './space-icon-image.mjs';
import { createSpaceAgent } from './space-agent.mjs';
import { validateAgentConfig, validateAgentMessages } from './space-agent-schema.mjs';
import { createVoiceService } from './voice.mjs';
import { createEventStreamLifecycle } from './event-stream.mjs';

const root = fileURLToPath(new URL('../', import.meta.url));
const localHosts = new Set(['localhost', '127.0.0.1', '[::1]', '::1']);
const isLoopback = (host) => localHosts.has(host);

export async function createApp(options = {}) {
  const { generateIcons = false, iconGenerator, ...otherOptions } = options;
  const directoryOptions = { dataDir: join(root, '.local'), ...otherOptions,
    iconGenerator: iconGenerator || (generateIcons ? createSpaceIconGenerator() : undefined) };
  await recoverDemoReset(directoryOptions.dataDir);
  let directory = await createSpaceDirectory(directoryOptions);
  let service = await directory.serviceFor('mira');
  if (directoryOptions.iconGenerator) await directory.list();
  let resetInProgress = null;
  async function resetDemo() {
    voice.reset();
    for (const controller of activeSpaceAgents.values()) controller.abort(new Error('The demo is resetting.'));
    // Open every built-in canvas before closing the directory. Fresh installs
    // may not yet have materialized all default stores on disk.
    await Promise.all(demoUsers.map(person => directory.serviceFor(person.ownSpaceId)));
    let transaction;
    let replacement;
    try {
      await directory.close();
      transaction = await beginDemoReset(directoryOptions.dataDir);
      replacement = await createSpaceDirectory(directoryOptions);
      const replacementService = await replacement.serviceFor('mira');
      await transaction.commit();
      directory = replacement;
      service = replacementService;
      return { ok: true, users: directory.people() };
    } catch (error) {
      await replacement?.close();
      await transaction?.rollback();
      if (!transaction) await recoverDemoReset(directoryOptions.dataDir);
      // Baseline validation or a disk failure must not leave the app pointing
      // at closed stores. The intact original is reopened after rollback.
      directory = await createSpaceDirectory(directoryOptions);
      service = await directory.serviceFor('mira');
      throw error;
    }
  }
  const personas = createPersonaServices({ adapter: options.healthAdapter, fetchImpl: options.newsFetchImpl, newsMode: options.newsMode });
  const activeHealthChats = new Set();
  const spaceAgent = createSpaceAgent({ adapter: options.spaceAgentAdapter, apiKey: options.apiKey, model: options.model, tier: options.tier });
  const activeSpaceAgents = new Map();
  const voice = createVoiceService({ apiKey: options.apiKey, model: options.model, tier: options.tier, fetchImpl: options.voiceFetchImpl, adapter: options.voiceAdapter, responsesFetchImpl: options.voiceResponsesFetchImpl });
  const app = express();
  app.disable('x-powered-by');
  app.use((request, response, next) => {
    let host;
    try { host = new URL(`http://${request.headers.host || ''}`).hostname; } catch { /* rejected below */ }
    if (!isLoopback(host)) return response.status(403).json({ error: 'Little Worlds only accepts local requests.' });
    const origin = request.get('origin');
    if (origin) {
      try {
        const url = new URL(origin);
        if (!isLoopback(url.hostname) || !['http:', 'https:'].includes(url.protocol)) throw new Error();
      } catch { return response.status(403).json({ error: 'This origin is not allowed.' }); }
    }
    if (request.get('sec-fetch-site') === 'cross-site') return response.status(403).json({ error: 'Cross-site requests are not allowed.' });
    response.set('X-Content-Type-Options', 'nosniff');
    response.set('Referrer-Policy', 'no-referrer');
    next();
  });
  const parseJson = express.json({ limit: '48kb', type: 'application/json' });
  app.use((request, response, next) => {
    // Image uploads and bounded voice snapshots have route-specific parsers.
    if (request.method === 'POST' && /^\/api\/spaces\/[^/]+\/icon\/?$/.test(request.path)) return next();
    if (request.path.startsWith('/api/voice/')) return next();
    return parseJson(request, response, next);
  });
  app.use('/api', (_request, response, next) => { response.set('Cache-Control', 'no-store'); next(); });
  app.use('/api', (request, response, next) => {
    if (resetInProgress) return response.status(request.path === '/demo/reset' ? 409 : 503).json({ error: 'The demo is resetting. Please try again in a moment.' });
    if (request.method === 'POST' && !request.is('application/json')) return response.status(415).json({ error: 'Send application/json.' });
    next();
  });
  app.post('/api/demo/reset', async (request, response) => {
    // The local demo intentionally permits reset from its signed-out welcome
    // screen, but another local website cannot silently trigger it.
    let origin;
    try { origin = new URL(request.get('origin') || request.get('referer') || ''); } catch { /* rejected below */ }
    if (!origin || origin.host !== request.get('host') || !isLoopback(origin.hostname)) throw httpError(403, 'Reset the demo from its own browser window.');
    if (!request.body || Array.isArray(request.body) || request.body.confirmation !== 'reset-demo' || Object.keys(request.body).length !== 1) {
      throw httpError(400, 'Confirm that you want to reset this demo.');
    }
    resetInProgress = resetDemo();
    try { response.json(await resetInProgress); }
    finally { resetInProgress = null; }
  });
  // Voice can operate the welcome/sign-in screen. Its same-origin session
  // capability authorizes planning only; normal UI actions retain their auth.
  app.use('/api/voice', voice.router);
  app.get('/api/auth/people', async (_request, response) => {
    // The simulated sign-in chooser shares only each space's display icon,
    // using the same projection as the community and space header.
    const users = await Promise.all(directory.people().map(async person => ({
      ...person, icon: await directory.iconFor(person.ownSpaceId),
    })));
    response.json({ users, simulated: true });
  });
  app.post('/api/auth/sign-in', async (request, response) => response.json(await directory.signIn(request.body)));
  app.use('/api', (request, _response, next) => {
    try { request.principal = directory.authenticate(request.get('authorization')); next(); } catch (error) { next(error); }
  });
  app.get('/api/auth/session', (request, response) => response.json({ user: request.principal.user, ownSpaceId: request.principal.ownSpaceId, simulated: true }));
  app.post('/api/auth/sign-out', (request, response) => { request.principal.revoke(); response.json({ ok: true }); });
  app.get('/api/spaces', async (_request, response) => response.json({ spaces: await directory.list() }));
  app.get('/api/community', async (request, response) => response.json(await directory.community(request.principal.user.id)));
  app.post('/api/friends/request', async (request, response) => response.json(await directory.requestFriend(request.principal.user.id, request.body?.targetId)));
  app.post('/api/friends/respond', async (request, response) => response.json(await directory.respondFriend(request.principal.user.id, request.body?.requestId, request.body?.decision)));
  app.post('/api/friends/remove', async (request, response) => response.json(await directory.removeFriend(request.principal.user.id, request.body?.targetId)));

  async function scope(request, _response, next) {
    try {
      // Legacy URLs remain authenticated aliases for the caller's own space.
      // Query/body IDs never select either the actor or an owner capability.
      const id = request.params.spaceId || request.principal.ownSpaceId;
      const owner = directory.ownerForSpace(id);
      if (!owner) throw httpError(404, 'This space does not exist.');
      request.spaceId = id;
      request.spaceService = await directory.serviceFor(id);
      request.canEdit = owner.id === request.principal.user.id;
      next();
    } catch (error) { next(error); }
  }
  function ownerOnly(request, _response, next) {
    next(request.canEdit ? undefined : httpError(403, 'Only the owner can change this space.'));
  }
  app.get('/api/spaces/:spaceId/icon', scope, async (request, response) => {
    response.json({ icon: await directory.iconFor(request.spaceId) });
  });
  app.post('/api/spaces/:spaceId/icon', scope, ownerOnly, express.json({ limit: '7mb', type: 'application/json' }), async (request, response) => {
    const payload = request.body;
    if (!payload || Array.isArray(payload) || typeof payload !== 'object' || Object.keys(payload).length !== 1 || typeof payload.dataUrl !== 'string') {
      throw httpError(400, 'Choose an image to upload.');
    }
    const maximumEncodedLength = Math.ceil(SPACE_ICON_MAX_BYTES / 3) * 4;
    if (payload.dataUrl.length > maximumEncodedLength + 64) throw httpError(413, 'Choose an image under 5 MB.');
    const match = /^data:image\/(png|jpeg|webp);base64,([A-Za-z0-9+/]+={0,2})$/.exec(payload.dataUrl);
    if (!match || match[2].length % 4 !== 0) throw httpError(400, 'Choose a PNG, JPEG, or WebP image.');
    const image = Buffer.from(match[2], 'base64');
    if (image.length > SPACE_ICON_MAX_BYTES) throw httpError(413, 'Choose an image under 5 MB.');
    const normalized = await normalizeSpaceIcon(image);
    // Normalization drops metadata and saves only a small, decoded raster.
    response.json({ icon: await directory.uploadIcon(request.spaceId, normalized) });
  });
  app.post('/api/spaces/:spaceId/icon/generate', scope, ownerOnly, async (request, response) => {
    if (!request.body || Array.isArray(request.body) || typeof request.body !== 'object' || Object.keys(request.body).length) {
      throw httpError(400, 'This icon request contains unsupported fields.');
    }
    response.status(202).json({ icon: await directory.regenerateIcon(request.spaceId) });
  });
  app.post('/api/spaces/:spaceId/services/:capability', scope, async (request, response) => {
    const capability = request.params.capability;
    if (!['health-chat', 'finance-news', 'space-agent'].includes(capability)) throw httpError(404, 'This service does not exist.');
    const payload = request.body;
    const allowedFields = capability === 'finance-news' ? ['revisionId'] : ['revisionId', 'messages'];
    if (!payload || typeof payload !== 'object' || Array.isArray(payload) || Object.keys(payload).some(key => !allowedFields.includes(key))) {
      throw httpError(400, 'This service request contains unsupported fields.');
    }
    if (!Number.isInteger(payload.revisionId)) throw httpError(400, 'A published space revision is required.');
    const data = request.spaceService.store.read();
    if (data.currentRevisionId !== payload.revisionId) throw httpError(409, 'This space just changed. Try this service again.');
    const published = data.revisions.find(revision => revision.id === data.currentRevisionId);
    // Authority comes only from the checked, published module for this space.
    // A frame request or client-supplied list cannot add a capability.
    if (!Array.isArray(published?.meta?.capabilities) || !published.meta.capabilities.includes(capability)) throw httpError(403, 'This space has not enabled that service.');
    if (capability === 'finance-news') return response.json(await personas.financeNews());

    // Both conversational services accept only a bounded alternating history.
    const messages = capability === 'space-agent' ? validateAgentMessages(payload.messages) : validateHealthMessages(payload.messages);
    if (capability === 'space-agent') {
      validateAgentConfig(published.meta);
      const key = `${request.principal.user.id}:${request.spaceId}`;
      if (activeSpaceAgents.has(key)) throw httpError(409, 'Finish or stop your current request in this space first.');
      if (activeSpaceAgents.size >= 8) throw httpError(429, 'The shared agents are busy. Please try again shortly.');
      const controller = new AbortController();
      activeSpaceAgents.set(key, controller);
      const signal = AbortSignal.any([controller.signal, request.principal.signal, AbortSignal.timeout(120_000)]);
      const stop = () => controller.abort();
      const unsubscribe = request.spaceService.store.subscribe(event => {
        if (event.type === 'revision.published' || event.type === 'space.reset' || event.type === 'space.updated' && event.data?.reset) {
          controller.abort(new Error('This space just changed. Please send your request again.'));
        }
      });
      response.on('close', stop);
      response.status(200).set({ 'Content-Type': 'text/event-stream', Connection: 'keep-alive', 'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no' });
      response.flushHeaders();
      const emit = event => {
        signal.throwIfAborted();
        if (request.principal.active() && !response.destroyed) response.write(`data: ${JSON.stringify(event)}\n\n`);
      };
      try {
        await spaceAgent.run({ service: request.spaceService, actorId: request.principal.user.id, revisionId: payload.revisionId, messages, signal, onEvent: emit });
      } catch (error) {
        if (!response.destroyed && request.principal.active()) {
          response.write(`data: ${JSON.stringify({ type: 'error', message: signal.aborted ? 'This request stopped. Any completed changes remain saved.' : publicError(error) })}\n\n`);
        }
      } finally {
        if (activeSpaceAgents.get(key) === controller) activeSpaceAgents.delete(key);
        unsubscribe(); response.off('close', stop); response.end();
      }
      return;
    }
    const personId = request.principal.user.id;
    if (activeHealthChats.has(personId)) throw httpError(409, 'Finish or stop your current answer first.');
    activeHealthChats.add(personId);
    const controller = new AbortController();
    const signal = AbortSignal.any([controller.signal, request.principal.signal, AbortSignal.timeout(90_000)]);
    const stop = () => controller.abort();
    response.on('close', stop);
    response.status(200).set({ 'Content-Type': 'text/event-stream', Connection: 'keep-alive', 'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no' });
    response.flushHeaders();
    const emit = event => {
      signal.throwIfAborted();
      if (request.principal.active() && !response.destroyed) response.write(`data: ${JSON.stringify(event)}\n\n`);
    };
    // Health messages remain transient request data, never space state, builder
    // history, or persisted events. A service call is not a generated reducer.
    try { await personas.healthChat({ messages, signal, onEvent: emit }); }
    catch (error) { if (!response.destroyed && request.principal.active()) response.write(`data: ${JSON.stringify({ type: 'error', message: signal.aborted ? 'This answer was stopped. You can ask again.' : publicError(error) })}\n\n`); }
    finally { activeHealthChats.delete(personId); response.off('close', stop); response.end(); }
  });
  const snapshot = async (request, response) => {
    const data = await request.spaceService.snapshot(request.principal.user.id);
    const space = await directory.metadata(request.spaceId, data.revision.source);
    response.json(scopedSnapshot(data, space, request.canEdit));
  };
  const events = (request, response) => {
    response.status(200).set({ 'Content-Type': 'text/event-stream', Connection: 'keep-alive', 'Cache-Control': 'no-cache, no-transform', 'X-Accel-Buffering': 'no' });
    response.flushHeaders();
    const stream = createEventStreamLifecycle(response, request.principal);
    // An immediate comment makes proxy/browser connection state observable even
    // when a brand-new space has no events to replay.
    if (stream.writable()) response.write(': connected\n\n');
    const after = Number(request.get('last-event-id') || request.query.since || 0);
    let delivered = Number.isFinite(after) ? after : 0;
    const send = (rawEvent) => {
      if (!stream.writable()) return;
      const event = request.canEdit ? rawEvent : publicEvent(rawEvent);
      if (!event) return;
      if (Number(event.id) <= delivered) return;
      delivered = Number(event.id);
      response.write(`id: ${event.id}\ndata: ${JSON.stringify(event)}\n\n`);
    };
    // Subscribe synchronously before reading the ledger: no event can fall into a replay gap.
    const unsubscribe = request.spaceService.store.subscribe(send);
    stream.onCleanup(unsubscribe);
    request.spaceService.store.read().events.forEach(send);
    stream.startHeartbeat(() => response.write(': keepalive\n\n'));
  };
  const activity = (request, response) => {
    if (!request.principal.active()) throw httpError(401, 'Your session has ended. Sign in again.');
    const feed = request.params.comparisonId
      ? request.spaceService.getComparisonActivity(request.params.comparisonId)
      : request.spaceService.activity;
    response.status(200).set({ 'Content-Type': 'text/event-stream', Connection: 'keep-alive', 'Cache-Control': 'no-store, no-transform', 'X-Accel-Buffering': 'no' });
    response.flushHeaders();
    const stream = createEventStreamLifecycle(response, request.principal);
    const end = stream.end;
    const queued = new Map();
    let queuedBytes = 0;
    let waitingForDrain = false;
    const drain = () => {
      waitingForDrain = false;
      if (!stream.writable()) return;
      while (queued.size && stream.writable()) {
        const [key, block] = queued.entries().next().value;
        queued.delete(key); queuedBytes -= Buffer.byteLength(block);
        if (!response.write(block)) { waitingForDrain = true; return; }
      }
    };
    response.on('drain', drain);
    stream.onCleanup(() => { queued.clear(); queuedBytes = 0; response.off('drain', drain); });
    const send = event => {
      if (!stream.writable()) return;
      if (event.type === 'activity.reset') { queued.clear(); queuedBytes = 0; }
      const key = event.data?.entryId || 'reset';
      const block = `id: ${event.id}\ndata: ${JSON.stringify(event)}\n\n`;
      queuedBytes += Buffer.byteLength(block) - Buffer.byteLength(queued.get(key) || '');
      queued.set(key, block);
      // Coalesce updates while a socket drains. A stalled observer cannot slow
      // generation or retain unbounded output; reconnect gets a fresh snapshot.
      if (queued.size > 121 || queuedBytes > 5 * 1024 * 1024) { response.destroy(); return; }
      if (!waitingForDrain) drain();
    };
    // This is a cumulative snapshot, not a durable event ledger. A reconnect
    // intentionally ignores Last-Event-ID and replaces any stale/pruned rows.
    // Flush before subscribing: otherwise pending updates can reach this viewer
    // ahead of their earlier request rows. This synchronous pair has no gap.
    const replay = feed.read();
    send({ id: '0', type: 'activity.reset', time: new Date().toISOString(), title: 'Current build activity', data: { reason: 'replay' } });
    const unsubscribe = feed.subscribe(send, end);
    stream.onCleanup(unsubscribe);
    replay.forEach(send);
    stream.startHeartbeat(() => { if (!waitingForDrain) waitingForDrain = !response.write(': keepalive\n\n'); });
  };
  const comparisonEvents = (request, response) => {
    const feed = request.spaceService.comparison;
    if (!request.principal.active()) throw httpError(401, 'Your session has ended. Sign in again.');
    response.status(200).set({ 'Content-Type': 'text/event-stream', Connection: 'keep-alive', 'Cache-Control': 'no-store, no-transform', 'X-Accel-Buffering': 'no' });
    response.flushHeaders();
    const stream = createEventStreamLifecycle(response, request.principal);
    const end = stream.end;
    let pending;
    let waitingForDrain = false;
    const drain = () => {
      waitingForDrain = false;
      if (!stream.writable() || !pending) return;
      const block = pending; pending = undefined;
      waitingForDrain = !response.write(block);
    };
    const send = event => {
      if (!stream.writable()) return;
      // Full bounded replacement state, including at most two inert previews.
      // A stalled client retains one latest state and never slows either build.
      // During normal streaming, unchanged HTML is omitted. Under backpressure
      // use a full snapshot so a compact update cannot replace an undelivered
      // preview that this client would otherwise never receive.
      const next = waitingForDrain ? feed.snapshot() : event;
      pending = `id: ${next.id}\ndata: ${JSON.stringify(next)}\n\n`;
      if (!waitingForDrain) drain();
    };
    response.on('drain', drain);
    stream.onCleanup(() => { pending = undefined; response.off('drain', drain); });
    const replay = feed.snapshot();
    const unsubscribe = feed.subscribe(send, end);
    stream.onCleanup(unsubscribe);
    send(replay);
    stream.startHeartbeat(() => { if (!waitingForDrain) waitingForDrain = !response.write(': keepalive\n\n'); });
  };
  const registerSpaceRoutes = (base) => {
    const path = (suffix) => base ? `${base}${suffix}` : (suffix || '/api/space');
    app.get(path(''), scope, snapshot);
    app.get(base ? path('/game') : '/api/game', scope, async (request, response) => response.json(await request.spaceService.game(request.principal.user.id, request.query.gameId)));
    app.get(base ? path('/events') : '/api/events', scope, events);
    app.get(base ? path('/activity') : '/api/activity', scope, ownerOnly, activity);
    app.get(base ? path('/comparison') : '/api/comparison', scope, ownerOnly, (request, response) => response.json({ comparison: request.spaceService.comparison.read() }));
    app.get(base ? path('/comparison/events') : '/api/comparison/events', scope, ownerOnly, comparisonEvents);
    app.get(base ? path('/comparison/:comparisonId/activity') : '/api/comparison/:comparisonId/activity', scope, ownerOnly, activity);
    app.post(base ? path('/comparison/:comparisonId/finish') : '/api/comparison/:comparisonId/finish', scope, ownerOnly, async (request, response) => response.json(await request.spaceService.finishComparison(request.params.comparisonId)));
    app.get(base ? path('/revisions') : '/api/revisions', scope, ownerOnly, async (request, response) => response.json(await request.spaceService.revisions()));
    app.post(base ? path('/turn') : '/api/turn', scope, ownerOnly, async (request, response) => {
      if (request.body?.compare !== undefined && typeof request.body.compare !== 'boolean') throw httpError(400, 'compare must be true or false.');
      response.status(202).json(await request.spaceService.submit(request.body?.message, { compare: request.body?.compare === true, appTheme: request.body?.appTheme }));
    });
    app.post(base ? path('/cancel') : '/api/cancel', scope, ownerOnly, async (request, response) => response.json(await request.spaceService.cancel()));
    app.post(base ? path('/action') : '/api/action', scope, async (request, response) => response.json(await request.spaceService.action({
      action: request.body?.action, revisionId: request.body?.revisionId, actor: request.principal.user.id,
    })));
    app.post(base ? path('/restore') : '/api/restore', scope, ownerOnly, async (request, response) => response.json(await request.spaceService.restore(request.body?.revisionId)));
    app.post(base ? path('/reset') : '/api/reset', scope, ownerOnly, async (request, response) => response.json(await request.spaceService.reset()));
  };
  registerSpaceRoutes('/api/spaces/:spaceId');
  registerSpaceRoutes('');
  app.use('/api', (_request, response) => response.status(404).json({ error: 'This API route does not exist.' }));
  const dist = join(root, 'dist');
  if (existsSync(dist)) {
    app.use(express.static(dist));
    app.get('/{*splat}', (_request, response) => response.sendFile(join(dist, 'index.html')));
  }
  app.use((error, _request, response, _next) => {
    const status = error.status || (error.type === 'entity.too.large' ? 413 : 400);
    response.status(status).json({ error: publicError(error) });
  });
  return { app, get service() { return service; }, get directory() { return directory; }, async close() {
    for (const controller of activeSpaceAgents.values()) controller.abort();
    await voice.close();
    await spaceAgent.close();
    await resetInProgress?.catch(() => {});
    await directory.close();
  } };
}

if (process.argv[1] && pathToFileURL(resolve(process.argv[1])).href === import.meta.url) {
  const port = Number(process.env.PORT || 4318);
  const { app, close } = await createApp({ generateIcons: true });
  const server = app.listen(port, '127.0.0.1', () => console.log(`Little Worlds API: http://127.0.0.1:${port}`));
  let stopping = false;
  const stop = async () => {
    if (stopping) return; stopping = true;
    server.close(); server.closeAllConnections();
    await close(); process.exit(0);
  };
  process.on('SIGINT', stop); process.on('SIGTERM', stop);
}
