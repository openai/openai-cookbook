import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { build } from 'esbuild';

const compiled = await build({
  entryPoints: [new URL('../src/theme-transition.ts', import.meta.url).pathname],
  bundle: true, write: false, platform: 'node', format: 'cjs', packages: 'external',
});
const module = { exports: {} };
new Function('module', 'exports', 'require', compiled.outputFiles[0].text)(module, module.exports, createRequire(import.meta.url));
const { runThemeTransition, finishThemeTransition, BEFORE_THEME_CHANGE } = module.exports;

function deferred() {
  let resolve, reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function fixture(options = {}) {
  const attributes = new Map([['data-theme', 'dark']]);
  const events = [], transitions = [];
  const attributeName = key => `data-${key.replace(/[A-Z]/g, letter => `-${letter.toLowerCase()}`)}`;
  const root = {
    style: {},
    dataset: new Proxy({}, {
      get: (_, key) => attributes.get(attributeName(key)),
      set: (_, key, value) => { attributes.set(attributeName(key), String(value)); return true; },
      deleteProperty: (_, key) => attributes.delete(attributeName(key)),
    }),
    hasAttribute: key => attributes.has(key),
    getAttribute: key => attributes.get(key) ?? null,
    setAttribute: (key, value) => attributes.set(key, String(value)),
    removeAttribute: key => attributes.delete(key),
  };
  if (options.worldTransition) root.setAttribute('data-world-transition', '');
  const snapshot = type => ({
    type,
    theme: root.dataset.theme,
    suppressed: root.hasAttribute('data-theme-commit'),
    transitioning: root.hasAttribute('data-theme-transition'),
  });
  const document = {
    documentElement: root,
    hidden: Boolean(options.hidden),
    visibilityState: options.hidden ? 'hidden' : 'visible',
    defaultView: {
      matchMedia(query) {
        assert.equal(query, '(prefers-reduced-motion: reduce)');
        return { matches: Boolean(options.reducedMotion) };
      },
      getComputedStyle(element) {
        assert.equal(element, root);
        return { get backgroundColor() { events.push(snapshot('flush')); return root.dataset.theme === 'dark' ? 'rgb(0, 0, 0)' : 'rgb(255, 255, 255)'; } };
      },
    },
    querySelector(selector) {
      assert.equal(selector, '.build-comparison[data-morphing]');
      return options.comparisonMorph ? {} : null;
    },
  };
  if (!options.noNativeTransition) {
    document.startViewTransition = function (update) {
      assert.equal(this, document);
      events.push(snapshot('start'));
      if (options.startThrows === 'before-update') throw new Error('Capture unavailable');
      const ready = deferred(), finished = deferred();
      const transition = {
        update, ready, finished, skips: 0,
        handle: {
          ready: ready.promise,
          finished: finished.promise,
          skipTransition() { transition.skips++; events.push(snapshot('skip')); },
        },
      };
      transitions.push(transition);
      if (options.synchronousUpdate || options.startThrows === 'after-update') update();
      if (options.startThrows === 'after-update') throw new Error('Capture failed after update');
      return transition.handle;
    };
  }
  return {
    document, root, events, transitions,
    change(theme) { return () => { events.push(snapshot('commit')); root.dataset.theme = theme; }; },
    commits() { return events.filter(event => event.type === 'commit'); },
  };
}

function assertClean(app) {
  assert.equal(app.root.hasAttribute('data-theme-commit'), false, 'CSS transition suppression is temporary');
  assert.equal(app.root.hasAttribute('data-theme-transition'), false, 'root snapshot animation has ended');
}

function assertFlushedCommit(app, before, after) {
  const commits = app.events.flatMap((event, index) => event.type === 'commit' ? [index] : []);
  const index = commits.at(-1);
  assert.notEqual(index, undefined, 'the theme update ran');
  assert.equal(app.events[index].suppressed, true, 'the palette changes while CSS transitions are suppressed');
  const beforeCommit = app.events[index - 1], afterCommit = app.events[index + 1];
  assert.equal(beforeCommit.type, 'flush', 'resolve the old palette before changing it');
  assert.equal(beforeCommit.theme, before);
  assert.equal(beforeCommit.suppressed, true);
  assert.equal(afterCommit.type, 'flush', 'resolve the new palette before restoring CSS transitions');
  assert.equal(afterCommit.theme, after);
  assert.equal(afterCommit.suppressed, true);
}

const settle = () => new Promise(resolve => setImmediate(resolve));

test('native transitions commit only inside the capture callback and clean up when finished', async t => {
  const app = fixture();
  t.after(() => finishThemeTransition(app.document));
  runThemeTransition(app.change('light'), app.document);
  assert.equal(app.commits().length, 0);
  assert.equal(app.root.dataset.theme, 'dark');
  assert.equal(app.root.hasAttribute('data-theme-transition'), true);
  assert.equal(app.root.hasAttribute('data-theme-commit'), false);
  assert.deepEqual(app.events, [{ type: 'start', theme: 'dark', suppressed: false, transitioning: true }]);

  const transition = app.transitions[0];
  transition.update();
  transition.update();
  assert.equal(app.commits().length, 1, 'a duplicate capture callback cannot apply the theme twice');
  assertFlushedCommit(app, 'dark', 'light');
  assert.equal(app.root.hasAttribute('data-theme-commit'), false);
  assert.equal(app.root.hasAttribute('data-theme-transition'), true);
  transition.ready.resolve();
  await settle();
  assert.equal(app.root.hasAttribute('data-theme-transition'), true, 'ready does not end the snapshot animation');
  transition.finished.resolve();
  await settle();
  assertClean(app);
  assert.equal(app.commits().length, 1);
  assert.equal(transition.skips, 0);
});

test('finishing a pending transition commits before skipping and makes late callbacks harmless', async () => {
  const app = fixture();
  runThemeTransition(app.change('light'), app.document);
  const transition = app.transitions[0];
  finishThemeTransition(app.document);
  assertFlushedCommit(app, 'dark', 'light');
  assert.equal(app.commits().length, 1);
  assert.equal(transition.skips, 1);
  assert.equal(app.events.find(event => event.type === 'skip').theme, 'light');
  assertClean(app);
  const eventCount = app.events.length;
  finishThemeTransition(app.document);
  transition.update();
  transition.ready.reject(new Error('Transition was skipped'));
  transition.finished.reject(new Error('Transition was interrupted'));
  await settle();
  assert.equal(app.events.length, eventCount, 'completed transitions cannot commit, flush, or skip again');
  assertClean(app);
});

test('finishing an already committed transition skips its animation without another theme update', async () => {
  const app = fixture();
  runThemeTransition(app.change('light'), app.document);
  const transition = app.transitions[0];
  transition.update();
  finishThemeTransition(app.document);
  transition.finished.resolve();
  await settle();
  assert.equal(app.commits().length, 1);
  assert.equal(transition.skips, 1);
  assertClean(app);
});

test('rapid requests commit the previous choice before capturing the next and ignore stale work', async t => {
  const app = fixture();
  t.after(() => finishThemeTransition(app.document));
  runThemeTransition(app.change('light'), app.document);
  const first = app.transitions[0];
  runThemeTransition(app.change('dark'), app.document);
  const second = app.transitions[1];
  assert.equal(first.skips, 1);
  assert.equal(app.commits().length, 1);
  assert.equal(app.root.dataset.theme, 'light');
  assert.equal(app.events.filter(event => event.type === 'start')[1].theme, 'light');

  first.update();
  first.ready.reject(new Error('Old capture skipped'));
  first.finished.resolve();
  await settle();
  assert.equal(app.commits().length, 1);
  assert.equal(app.root.hasAttribute('data-theme-transition'), true, 'old completion must not clear the new animation');
  second.update();
  assert.equal(app.commits().length, 2);
  assertFlushedCommit(app, 'light', 'dark');
  first.update();
  assert.equal(app.root.dataset.theme, 'dark');
  second.finished.resolve();
  await settle();
  assertClean(app);
});

test('the before-theme-change event settles pending layout work before native theme capture', t => {
  const app = fixture({ worldTransition: true });
  t.after(() => finishThemeTransition(app.document));
  assert.equal(typeof BEFORE_THEME_CHANGE, 'string');
  app.document.dispatchEvent = event => {
    assert.equal(event.type, BEFORE_THEME_CHANGE);
    assert.equal(app.transitions.length, 0, 'layout work finishes before native capture starts');
    assert.equal(app.root.hasAttribute('data-theme-transition'), false);
    assert.equal(app.root.hasAttribute('data-world-transition'), true);
    app.root.removeAttribute('data-world-transition');
    app.events.push({ type: 'layout-finished' });
    return true;
  };

  runThemeTransition(app.change('light'), app.document);
  assert.equal(app.root.hasAttribute('data-world-transition'), false);
  assert.equal(app.transitions.length, 1, 'a settled layout allows the native theme transition');
  assert.deepEqual(app.events.map(event => event.type), ['layout-finished', 'start']);
  assert.equal(app.commits().length, 0, 'the theme still waits for its capture callback');
  app.transitions[0].update();
  assertFlushedCommit(app, 'dark', 'light');
  finishThemeTransition(app.document);
  assertClean(app);
});

for (const [name, options] of [
  ['without native view transitions', { noNativeTransition: true }],
  ['with reduced motion', { reducedMotion: true }],
  ['while the document is hidden', { hidden: true }],
  ['during a world transition', { worldTransition: true }],
  ['during a build comparison morph', { comparisonMorph: true }],
]) {
  test(`theme changes apply immediately ${name}`, () => {
    const app = fixture(options);
    runThemeTransition(app.change('light'), app.document);
    assert.equal(app.transitions.length, 0);
    assert.equal(app.commits().length, 1);
    assertFlushedCommit(app, 'dark', 'light');
    assertClean(app);
    finishThemeTransition(app.document);
    assert.equal(app.commits().length, 1);
    if (options.worldTransition) assert.equal(app.root.hasAttribute('data-world-transition'), true);
  });
}

for (const when of ['before-update', 'after-update']) {
  test(`a native start failure ${when} leaves one complete palette change`, () => {
    const app = fixture({ startThrows: when });
    assert.doesNotThrow(() => runThemeTransition(app.change('light'), app.document));
    assert.equal(app.commits().length, 1);
    assertFlushedCommit(app, 'dark', 'light');
    assertClean(app);
    app.transitions[0]?.update();
    finishThemeTransition(app.document);
    assert.equal(app.commits().length, 1);
  });
}

test('a synchronous native callback still commits only once and retains the animation until finished', async () => {
  const app = fixture({ synchronousUpdate: true });
  runThemeTransition(app.change('light'), app.document);
  assert.equal(app.commits().length, 1);
  assertFlushedCommit(app, 'dark', 'light');
  assert.equal(app.root.hasAttribute('data-theme-transition'), true);
  app.transitions[0].finished.resolve();
  await settle();
  assert.equal(app.commits().length, 1);
  assertClean(app);
});

test('rejected native promises are handled and a failed capture still applies the requested theme', async () => {
  const app = fixture();
  runThemeTransition(app.change('light'), app.document);
  const transition = app.transitions[0];
  transition.ready.reject(new Error('Snapshot capture failed'));
  transition.finished.reject(new Error('Animation failed before callback'));
  await settle();
  assert.equal(app.commits().length, 1);
  assertFlushedCommit(app, 'dark', 'light');
  assertClean(app);
  transition.update();
  finishThemeTransition(app.document);
  assert.equal(app.commits().length, 1);
});

test('an old rejected completion cannot remove a newer transition marker', async () => {
  const app = fixture();
  runThemeTransition(app.change('light'), app.document);
  const first = app.transitions[0];
  first.update();
  runThemeTransition(app.change('dark'), app.document);
  first.ready.reject(new Error('Old capture was cancelled'));
  first.finished.reject(new Error('Old animation was cancelled'));
  await settle();
  assert.equal(app.root.dataset.theme, 'light');
  assert.equal(app.root.hasAttribute('data-theme-transition'), true);
  assert.equal(app.commits().length, 1);
  finishThemeTransition(app.document);
  assert.equal(app.root.dataset.theme, 'dark');
  assert.equal(app.commits().length, 2);
  assertClean(app);
});

test('finishing one document leaves another document’s pending theme transition intact', () => {
  const first = fixture(), second = fixture();
  runThemeTransition(first.change('light'), first.document);
  runThemeTransition(second.change('light'), second.document);
  finishThemeTransition(first.document);
  assertClean(first);
  assert.equal(second.commits().length, 0);
  assert.equal(second.root.hasAttribute('data-theme-transition'), true);
  assert.equal(second.transitions[0].skips, 0);
  finishThemeTransition(second.document);
  assert.equal(second.commits().length, 1);
  assertClean(second);
});
