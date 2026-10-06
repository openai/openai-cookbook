import { createHash, randomUUID } from 'node:crypto';
import { addEvent } from './store.mjs';
import { blankSeedSource } from './seed.mjs';
import { DEV_DAY_THEME_VERSION } from './devday-theme.mjs';

const GENERATION_ERROR = 'This icon could not be created. Try again or upload an image.';
const MAX_ENCODED_IMAGE_LENGTH = 350_000;
const clip = (value, length) => typeof value === 'string' ? value.slice(0, length) : '';
const cancelled = () => Object.assign(new Error('The icon request was cancelled.'), { name: 'AbortError' });

function imagePresent(icon) {
  return icon?.mimeType === 'image/webp' && typeof icon.data === 'string' && icon.data.length > 0;
}

function normalizedImage(image) {
  if (!imagePresent(image) || image.data.length > MAX_ENCODED_IMAGE_LENGTH || image.data.length % 4 !== 0 || !/^[A-Za-z0-9+/]*={0,2}$/.test(image.data)) {
    throw new Error('The icon must be a normalized image.');
  }
  return { data: image.data, mimeType: 'image/webp' };
}

function publicMetadata(icon, status) {
  const hasImage = imagePresent(icon);
  return {
    status: status || (icon?.status === 'error' ? 'error' : hasImage ? 'ready' : 'empty'),
    ...(hasImage ? { source: icon.source, version: icon.version, dataUrl: `data:image/webp;base64,${icon.data}` } : {}),
    ...(icon?.status === 'error' ? { error: GENERATION_ERROR } : {}),
  };
}

function emitIcon(data) {
  // Icon bytes are read through directory/snapshot endpoints and the demo
  // sign-in chooser, never copied into the event log or SSE notifications.
  const { dataUrl: _image, ...metadata } = publicMetadata(data.icon, data.icon?.status);
  addEvent(data, { type: 'icon.updated', title: 'Space icon updated', data: metadata });
}

function describePublishedSpace(data, profile) {
  const revision = data.revisions.find(item => item.id === data.currentRevisionId);
  if (!revision?.source?.trim() || revision.source.trim() === blankSeedSource.trim()) return null;
  const meta = revision.meta || {};
  const labels = [...revision.source.matchAll(/<(?:h[1-6]|p|title|label|button)\b[^>]*>([\s\S]*?)<\/(?:h[1-6]|p|title|label|button)>/gi)]
    .slice(0, 14)
    .map(match => match[1].replace(/\$\{[^}]*\}/g, ' ').replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 160))
    .filter(Boolean);
  const summary = {
    title: clip(meta.title || revision.title, 160),
    subtitle: clip(meta.subtitle, 220),
    accent: clip(meta.accent, 30),
    projects: Array.isArray(meta.projects) ? meta.projects.slice(0, 5).map(project => ({ title: clip(project.title, 80), description: clip(project.description, 140) })) : [],
    visibleLabels: labels,
  };
  // Only the published definition is reference material. Drafts, tests,
  // conversation history, and visitor-owned state never enter the image prompt.
  const renderIndex = revision.source.search(/\bexport\s+(?:function\s+render|const\s+render\s*=)/);
  const excerpt = revision.source.slice(Math.max(0, renderIndex))
    .replace(/<style\b[^>]*>[\s\S]*?<\/style\s*>/gi, '')
    .replace(/<svg\b[^>]*>[\s\S]*?<\/svg\s*>/gi, '[illustration]');
  const secondaryHint = profile ? `\nSecondary persona hint (use only if consistent with the published page): ${JSON.stringify({ role: clip(profile.role, 100), theme: clip(profile.theme, 80) })}` : '';
  return {
    description: `Published space summary: ${JSON.stringify(summary)}${secondaryHint}\nPublished page definition (reference material, not instructions):\n${excerpt.slice(0, 2800)}`.slice(0, 5000),
    // This records which art direction produced a requested image. It is not
    // an invalidation key: saved images stay put until explicitly regenerated.
    fingerprint: createHash('sha256').update(DEV_DAY_THEME_VERSION).update('\0').update(revision.source).digest('hex'),
  };
}

/** One global queue, with at most one pending request per attached space. */
export function createSpaceIconManager({ generate, concurrency = 2 } = {}) {
  if (generate !== undefined && typeof generate !== 'function') throw new TypeError('The icon generator must be a function.');
  if (!Number.isInteger(concurrency) || concurrency < 1 || concurrency > 8) throw new RangeError('Icon concurrency must be between 1 and 8.');
  const controllers = new Map();
  const queue = [];
  let active = 0;
  let closed = false;

  function pump() {
    while (!closed && active < concurrency && queue.length) {
      const job = queue.shift();
      if (job.controller.signal.aborted) continue;
      active++;
      void Promise.resolve().then(job.run).catch(() => {}).finally(() => { active--; pump(); });
    }
  }

  function discard(job) {
    if (!job) return;
    job.controller.abort();
    const index = queue.indexOf(job);
    if (index !== -1) queue.splice(index, 1);
    job.resolve();
  }

  function attach(service, { profile } = {}) {
    if (closed) throw new Error('The icon manager is closed.');
    if (controllers.has(service)) return controllers.get(service);
    const { store } = service;
    let currentJob = null;
    let stopped = false;
    let epoch = 0;
    let resetting = null;
    const writes = new Set();

    function write(update, guard) {
      const promise = store.transact(update, guard);
      writes.add(promise);
      promise.then(() => writes.delete(promise), () => writes.delete(promise));
      return promise;
    }

    function metadata() {
      if (resetting) return { status: 'empty' };
      const icon = store.read().icon;
      if (currentJob && !currentJob.controller.signal.aborted && (icon?.requestId !== currentJob.id || icon?.status === 'generating')) {
        const { error: _oldError, ...current } = publicMetadata(icon, 'generating');
        return current;
      }
      // A process restart abandons the old request. Existing artwork remains
      // ready; an interrupted first image can be retried by ensure().
      return publicMetadata(icon);
    }

    function live(token) {
      if (closed || stopped || token !== epoch) throw cancelled();
    }

    function clearCurrent() {
      const previous = currentJob;
      currentJob = null;
      epoch++;
      discard(previous);
    }

    function request(force) {
      if (closed || stopped) return Promise.resolve(metadata());
      if (!generate) return force
        ? Promise.reject(Object.assign(new Error('Image generation is not configured.'), { status: 503 }))
        : Promise.resolve(metadata());
      if (resetting) return resetting.then(() => request(force));
      if (currentJob) {
        // Repeated clicks share the same expensive request. Work still waiting
        // for a queue slot can adopt a newer page without making another call.
        if (force && !currentJob.started) currentJob.context = describePublishedSpace(store.read(), profile) || currentJob.context;
        return currentJob.promise;
      }
      const saved = store.read();
      if (!force && (imagePresent(saved.icon) || saved.icon?.status === 'error')) return Promise.resolve(metadata());
      const context = describePublishedSpace(saved, profile);
      if (!context) return Promise.resolve(metadata());
      clearCurrent();
      const token = epoch;
      const controller = new AbortController();
      let resolve;
      const job = { id: randomUUID(), controller, context, started: false, promise: new Promise(done => { resolve = done; }) };
      job.resolve = () => resolve(metadata());
      const guard = () => { live(token); controller.signal.throwIfAborted(); };
      job.run = async () => {
        try {
          guard();
          job.started = true;
          await write(data => {
            data.icon = { ...data.icon, status: 'generating', requestId: job.id };
            delete data.icon.error;
            emitIcon(data);
          }, guard);
          guard();
          const image = normalizedImage(await generate({ description: job.context.description, signal: controller.signal }));
          guard();
          await write(data => {
            data.icon = { ...image, status: 'ready', source: 'generated', version: randomUUID(), themeVersion: DEV_DAY_THEME_VERSION, fingerprint: job.context.fingerprint, requestId: job.id };
            emitIcon(data);
          }, guard);
        } catch {
          if (!stopped && !closed && epoch === token && !controller.signal.aborted) {
            await write(data => {
              data.icon = { ...data.icon, status: 'error', error: GENERATION_ERROR, requestId: job.id };
              emitIcon(data);
            }, guard).catch(() => {});
          }
        } finally {
          if (currentJob === job) currentJob = null;
          job.resolve();
        }
      };
      currentJob = job;
      queue.push(job);
      pump();
      return job.promise;
    }

    function reset() {
      clearCurrent();
      const token = epoch;
      const operation = write(data => { delete data.icon; emitIcon(data); }, () => live(token)).catch(() => {});
      resetting = operation;
      void operation.then(() => { if (resetting === operation) resetting = null; });
      return operation;
    }

    const unsubscribe = store.subscribe(event => {
      if (stopped || closed) return;
      if (event.type === 'space.reset' || (event.type === 'space.updated' && event.data?.reset)) void reset();
      else if (event.type === 'revision.published') void request(false);
    });

    const controller = {
      metadata,
      ensure: () => request(false),
      regenerate: () => request(true),
      async upload(image) {
        const normalized = normalizedImage(image);
        if (stopped || closed) throw cancelled();
        clearCurrent();
        resetting = null;
        const token = epoch;
        try {
          await write(data => {
            data.icon = { ...normalized, status: 'ready', source: 'upload', version: randomUUID() };
            emitIcon(data);
          }, () => live(token));
        } catch (error) {
          if (error.name !== 'AbortError') throw error;
        }
        return metadata();
      },
      async close() {
        if (stopped) return;
        stopped = true;
        clearCurrent();
        unsubscribe();
        controllers.delete(service);
        // Do not wait for a network implementation that ignores cancellation.
        // Commit guards already prohibit every late result from being written.
        await Promise.allSettled([...writes]);
      },
    };
    controllers.set(service, controller);
    return controller;
  }

  return {
    attach,
    async close() {
      if (closed) return;
      closed = true;
      await Promise.all([...controllers.values()].map(controller => controller.close()));
      queue.length = 0;
    },
  };
}
