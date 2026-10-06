import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

// Exercise the real Workspace submit handler and real suggestion buttons.
// The model/network and unrelated components are inert; no paid calls occur.
const appPath = fileURLToPath(new URL('../src/App.tsx', import.meta.url));
const exportsByModule = {
  'lucide-react': ['ArrowDown', 'ArrowLeft', 'ArrowUp', 'ArrowUpRight', 'Check', 'ChevronLeft', 'ChevronRight', 'CircleHelp', 'ExternalLink', 'Gamepad2', 'History', 'ImagePlus', 'LoaderCircle', 'LogOut', 'MessageCircle', 'MessageSquare', 'Orbit', 'RotateCcw', 'Square', 'X'],
  './artworks': ['AfterHours', 'SmallHours', 'Tidepool'],
  './reset-session': ['listenForDemoReset', 'returnToWelcomeAfterReset'],
  './space-services': ['createSpaceServices'],
  './voice-action-registry': ['registerVoiceForm'],
  './navigation': ['useAppNavigation'],
};
const compiled = await build({
  entryPoints: [appPath], bundle: true, write: false, format: 'iife', globalName: 'WorkspaceModule',
  jsx: 'transform', jsxFactory: 'h.jsx', jsxFragment: 'h.Fragment',
  plugins: [{ name: 'workspace-inspiration-fixture', setup(builder) {
    builder.onLoad({ filter: /\/src\/App\.tsx$/ }, async () => ({
      contents: `${await readFile(appPath, 'utf8')}\nexport { Workspace };`, loader: 'tsx',
    }));
    builder.onResolve({ filter: /.*/ }, ({ path, importer }) => {
      if (path === 'react' || path === 'react/jsx-runtime' || path === 'lucide-react' || path.endsWith('.css')
        || importer === appPath && !['./InspirationPrompts', './snapshot-sync', '../shared/game-schema.mjs'].includes(path)) {
        return { path, namespace: 'fixture' };
      }
    });
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => {
      if (path.endsWith('.css')) return { contents: '' };
      if (path === 'react') return { contents: 'export const {useCallback,useEffect,useMemo,useRef,useState}=h;' };
      if (path === 'react/jsx-runtime') return { contents: 'export const jsx=h.jsx,jsxs=h.jsx,Fragment=h.Fragment;' };
      if (path === './api') return { contents: 'export const api=(...args)=>h.api(...args); export class ApiError extends Error {} export const captureSessionApi=()=>h.captureSessionApi(), hasSessionToken=()=>true, setSessionToken=()=>{}, watchEvents=()=>()=>{};' };
      if (path === './DevDayBrand') return { contents: 'export const WorldBrackets=()=>null; export default "DevDayBrand";' };
      if (path === './ThemeToggle') return { contents: 'export const readAppTheme=()=>h.appTheme; export default "ThemeToggle";' };
      if (path === './voice-action-registry') return { contents: 'export const registerVoiceForm=(...args)=>h.registerVoiceForm(...args);' };
      if (path === './useBuildComparison') return { contents: 'export const useBuildComparison=()=>({comparison:h.comparison || null,connected:true,refreshComparison:async()=>null}); export const watchPendingComparison=()=>()=>{};' };
      if (exportsByModule[path]) return { contents: exportsByModule[path].map(name => `export const ${name}=()=>null;`).join('\n') };
      return { contents: `export default ${JSON.stringify(path)};` };
    });
  } }],
});

function findNode(tree, predicate) {
  if (Array.isArray(tree)) return tree.map(child => findNode(child, predicate)).find(Boolean);
  if (!tree || typeof tree !== 'object') return undefined;
  return predicate(tree) ? tree : findNode(tree.props?.children, predicate);
}
function collectNodes(tree, predicate, results = []) {
  if (Array.isArray(tree)) tree.forEach(child => collectNodes(child, predicate, results));
  else if (tree && typeof tree === 'object') {
    if (predicate(tree)) results.push(tree);
    collectNodes(tree.props?.children, predicate, results);
  }
  return results;
}
function deferred() {
  let resolve, reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
const settle = () => new Promise(resolve => setImmediate(resolve));
const signedIn = { user: { id: 'mira', name: 'Mira' }, ownSpaceId: 'mira' };
function workspace({ canEdit = true, keyAvailable = true, status = 'idle', hasBuilt = false, community = false, available = true, comparison, turns = [] } = {}) {
  const snapshot = available ? {
    permissions: { canEdit, canViewRuntime: true },
    config: { keyAvailable }, session: { status, turns },
    revision: { id: 1, meta: { layout: 'canvas' } },
    space: { id: 'mira', owner: signedIn.user, kind: 'blank', hasBuilt },
    state: { projects: [], contributions: [], extras: {} }, events: [], html: '',
  } : null;
  const requests = [], slots = [], effects = [];
  let cursor = 0, effectCursor = 0, updates = 0, layoutActive = false, automaticLayout = true, voiceHandler;
  let currentRoute = { screen: community ? 'community' : 'space', spaceId: 'mira', place: 'map' };
  const h = {
    comparison,
    appTheme: 'dark',
    sessionToken: 'initial-session',
    Fragment: 'fragment', jsx: (type, props) => ({ type, props }),
    useState(initial) {
      const index = cursor++;
      slots[index] ??= { value: index === 0 ? snapshot : typeof initial === 'function' ? initial() : initial };
      return [slots[index].value, update => { updates++; slots[index].value = typeof update === 'function' ? update(slots[index].value) : update; }];
    },
    useRef(value) { const index = cursor++; return slots[index] ??= { current: value }; },
    useMemo: create => create(), useCallback: callback => callback,
    useEffect(create, deps) {
      const index = effectCursor++;
      const previous = effects[index];
      if (!previous || !deps || !previous.deps || deps.some((value, i) => !Object.is(value, previous.deps[i]))) {
        effects[index] = { create, deps, pending: true, cleanup: previous?.cleanup };
      }
    },
    captureSessionApi() { const token = h.sessionToken; return (path, body) => h.api(path, body, token); },
    registerVoiceForm(_form, handler) {
      voiceHandler = handler;
      return () => { if (voiceHandler === handler) voiceHandler = undefined; };
    },
    api(path, body, sessionToken = h.sessionToken) {
      const pending = deferred();
      requests.push({ path, body, sessionToken, ...pending });
      return pending.promise;
    },
  };
  const context = vm.createContext({ h, Error, setTimeout, clearTimeout,
    document: { title: '' }, window: { scrollTo() {}, matchMedia: () => ({ matches: true }) } });
  vm.runInContext(compiled.outputFiles[0].text, context);
  const callbacks = { onArrived() {}, onRoute() {}, onSignOut() {}, onExpired() {} };
  function render() {
    cursor = 0; effectCursor = 0;
    const tree = context.WorkspaceModule.Workspace({
      auth: signedIn, route: currentRoute,
      navigation: {}, arrivalRequested: false, ...callbacks,
    });
    const comparison = findNode(tree, node => node.type === './BuildComparison');
    if (automaticLayout && comparison?.props.onLayoutChange && comparison.props.active !== layoutActive) {
      layoutActive = comparison.props.active;
      comparison.props.onLayoutChange(layoutActive);
      return render();
    }
    return tree;
  }
  function suggestions() {
    const element = findNode(render(), node => node.type?.name === 'InspirationPrompts');
    return element ? collectNodes(element.type(element.props), node => node.type === 'button') : [];
  }
  const textarea = () => findNode(render(), node => node.type === 'textarea');
  return {
    render, requests, suggestions, textarea,
    get snapshot() { return slots[0]?.value ?? snapshot; },
    get stateUpdates() { return updates; },
    holdComparisonLayout() { automaticLayout = false; },
    notifyComparisonLayout(value) {
      const comparison = findNode(render(), node => node.type === './BuildComparison');
      layoutActive = value;
      comparison.props.onLayoutChange(value);
    },
    notifyComparisonTransition(value) {
      findNode(render(), node => node.type === './BuildComparison').props.onTransitionChange(value);
    },
    commitEffects() { for (const effect of effects) if (effect.pending) { effect.pending = false; effect.cleanup?.(); effect.cleanup = effect.create(); } },
    unmount() { for (const effect of effects) effect.cleanup?.(); },
    navigate: screen => { currentRoute = { ...currentRoute, screen }; render(); },
    updateComparison: value => { h.comparison = value; render(); },
    changeSession: value => { h.sessionToken = value; },
    changeTheme: value => { h.appTheme = value; },
    submitByVoice() {
      const form = findNode(render(), node => node.type === 'form' && node.props.className.startsWith('composer'));
      form.props.ref.current = {};
      this.commitEffects();
      assert.equal(typeof voiceHandler, 'function', 'the real composer registers its voice submit handler');
      return voiceHandler();
    },
    updateSnapshot: update => { render(); slots[0].value = { ...slots[0].value, ...update }; },
    type: value => textarea().props.onChange({ target: { value } }),
    submit: () => findNode(render(), node => node.type === 'form' && node.props.className.startsWith('composer')).props.onSubmit({ preventDefault() {} }),
  };
}

test('three short inspiration tiles appear below the owner composer on new and built spaces', () => {
  for (const hasBuilt of [false, true]) {
    const app = workspace({ hasBuilt });
    const buttons = app.suggestions();
    assert.equal(buttons.length, 3);
    assert.deepEqual(buttons.map(button => button.props['aria-label']), [
      'Build a tiny arcade', 'Build a shared guestbook', 'Build an orbiting solar system',
    ]);
    for (const button of buttons) {
      assert.equal(button.props.type, 'button');
      assert.equal(button.props.disabled, false);
      assert.ok(button.props['aria-description'].startsWith('Add '), 'voice receives the actual build request');
    }
    const order = collectNodes(app.render(), node => node.type === 'form' || node.type?.name === 'InspirationPrompts');
    assert.equal(order[0].type, 'form');
    assert.equal(order[1].type.name, 'InspirationPrompts');
  }
});

test('visitors, unloaded spaces, and Community do not expose build suggestions', () => {
  for (const options of [{ canEdit: false }, { available: false }, { community: true }]) {
    assert.equal(workspace(options).suggestions().length, 0);
  }
});

test('each tile submits its request through the owner turn endpoint without replacing the draft', async () => {
  for (let index = 0; index < 3; index++) {
    const app = workspace();
    app.type('A thought I am still writing');
    const button = app.suggestions()[index];
    button.props.onClick();
    assert.equal(app.requests.length, 1);
    assert.equal(app.requests[0].path, '/api/spaces/mira/turn');
    assert.equal(app.requests[0].body.message, button.props['aria-description']);
    assert.equal(app.requests[0].body.compare, true, 'inspiration uses the same parallel builder as chat');
    assert.equal(app.textarea().props.value, 'A thought I am still writing');
    app.type('A thought I kept writing while the request started');
    app.requests[0].resolve({ turnId: 'new-turn' });
    await settle();
    assert.equal(app.textarea().props.value, 'A thought I kept writing while the request started');
    assert.ok(app.suggestions().every(next => next.props.disabled), 'accepted turn disables suggestions while awaiting its stream');
  }
});

test('rapid repeated tile and form activation starts only one request', async () => {
  const app = workspace();
  app.type('A typed request');
  const [first, second] = app.suggestions();
  first.props.onClick();
  first.props.onClick();
  second.props.onClick();
  app.submit();
  assert.equal(app.requests.length, 1);
  assert.ok(app.suggestions().every(button => button.props.disabled));
  app.requests[0].resolve({ turnId: 'new-turn' });
  await settle();
});

test('suggestions cannot interrupt an active build or submit without an API key', () => {
  for (const options of [{ status: 'running' }, { keyAvailable: false }]) {
    const app = workspace(options);
    for (const button of app.suggestions()) {
      assert.equal(button.props.disabled, true);
      button.props.onClick();
    }
    assert.equal(app.requests.length, 0, 'the submit guard also protects direct or stale handler calls');
  }
});

test('failed suggestion requests preserve the draft and can be retried', async () => {
  const app = workspace();
  app.type('Keep my draft');
  app.suggestions()[0].props.onClick();
  app.requests[0].reject(new Error('The connection was interrupted'));
  await settle();
  assert.equal(app.textarea().props.value, 'Keep my draft');
  assert.ok(app.suggestions().every(button => !button.props.disabled));
  const toast = findNode(app.render(), node => node.props?.className === 'toast');
  assert.ok(JSON.stringify(toast).includes('The connection was interrupted'));
  app.suggestions()[0].props.onClick();
  assert.equal(app.requests.length, 2);
  app.requests[1].resolve({ turnId: 'retry-turn' });
  await settle();
});

test('ordinary chat submission still clears only the submitted draft', async () => {
  const app = workspace();
  app.type('  Make a garden  ');
  app.submit();
  assert.equal(app.requests[0].body.message, 'Make a garden');
  assert.equal(app.requests[0].body.compare, true);
  app.requests[0].resolve({ turnId: 'first-turn' });
  await settle();
  assert.equal(app.textarea().props.value, '');

  app.type('My follow-up');
  app.submit();
  app.type('The next thought');
  app.requests[1].resolve({ turnId: 'second-turn' });
  await settle();
  assert.equal(app.textarea().props.value, 'The next thought');
});

test('typed, suggested, and voice requests capture the current app theme for both build lanes', async () => {
  for (const appTheme of ['light', 'dark']) {
    for (const trigger of ['typed', 'suggested', 'voice']) {
      const app = workspace();
      app.type('Build a garden');
      // Read at submission time, not from a stale render or the world's palette.
      app.changeTheme(appTheme);
      if (trigger === 'suggested') app.suggestions()[0].props.onClick();
      else if (trigger === 'voice') void app.submitByVoice();
      else app.submit();
      const turns = app.requests.filter(request => request.path.endsWith('/turn'));
      assert.equal(turns.length, 1, `${trigger} submits exactly one turn`);
      assert.equal(turns[0].body.appTheme, appTheme, `${trigger} passes the current app theme`);
      assert.equal(turns[0].body.compare, true, 'both lanes share the same captured preference');
      app.changeTheme(appTheme === 'light' ? 'dark' : 'light');
      assert.equal(turns[0].body.appTheme, appTheme, 'later theme changes do not mutate an accepted request');
      turns[0].resolve({ turnId: `${trigger}-${appTheme}` });
      await settle();
      app.unmount();
    }
  }
});

const runningComparison = () => ({
  id: 'parallel-build', primaryTurnId: 'ultrafast-turn', finished: false,
  ultrafast: { status: 'completed' }, standard: { status: 'running', html: '<p>Standard preview</p>' },
});
const completedTurn = overrides => ({ id: 'ultrafast-turn', status: 'completed', revisionId: 1, ...overrides });
const comparisonNode = app => findNode(app.render(), node => node.type === './BuildComparison');
const primaryFrame = app => findNode(comparisonNode(app).props.children, node => node.type === './GeneratedFrame');

test('only successful Ultrafast output calibrates Standard within the current comparison', () => {
  const initial = { ...runningComparison(), progress: { status: 'ready', expectedOutputTokens: 6000 },
    ultrafast: { status: 'running', outputTokens: 1400 } };
  const app = workspace({ hasBuilt: true, comparison: initial });
  const progress = lane => comparisonNode(app).props[`${lane}Activity`].props.comparisonProgress;
  for (const status of ['preparing', 'running', 'failed', 'cancelled']) {
    app.updateComparison({ ...initial, ultrafast: { status, outputTokens: 2500 } });
    assert.equal(progress('standard').completedReferenceTokens, undefined);
  }
  app.updateComparison({ ...initial, ultrafast: { status: 'completed', outputTokens: 2500 } });
  assert.equal(progress('standard').completedReferenceTokens, 2500);
  assert.equal(progress('standard').expectedOutputTokens, 6000, 'the original estimate remains available as fallback');
  assert.equal(progress('ultrafast').completedReferenceTokens, undefined);
  app.updateComparison({ ...initial, id: 'next-comparison', ultrafast: { status: 'running', outputTokens: 100 } });
  assert.equal(progress('standard').id, 'next-comparison');
  assert.equal(progress('standard').completedReferenceTokens, undefined, 'previous builds cannot calibrate a new request');
});

test('Ultrafast interaction waits for its matching published revision while Standard is still building', () => {
  const app = workspace({ hasBuilt: true, comparison: runningComparison() });
  assert.equal(comparisonNode(app).props.primaryInteractive, false, 'completed telemetry cannot unlock an old snapshot');
  assert.equal(primaryFrame(app).props.pending, true);

  app.updateSnapshot({ session: { status: 'idle', turns: [completedTurn({ revisionId: 2 })] } });
  assert.equal(comparisonNode(app).props.primaryInteractive, false, 'the turn and rendered revision must match');
  assert.equal(primaryFrame(app).props.pending, true);

  app.updateSnapshot({ revision: { id: 2, meta: { layout: 'canvas' } } });
  assert.equal(comparisonNode(app).props.primaryInteractive, true, 'the committed world becomes usable without leaving the split');
  assert.equal(primaryFrame(app).props.pending, false);
  const standard = comparisonNode(app).props.standardPreview;
  assert.equal(standard.props.pending, true, 'Standard cannot access host actions, services, games, or voice');
  assert.equal(standard.props.dimmed, false, 'read-only Standard still renders at full brightness');
  assert.equal(standard.props.services, undefined);
  assert.equal(standard.props.games, undefined);
  assert.equal(standard.props.capabilities, undefined);
  assert.equal(comparisonNode(app).props.active, true, 'interaction does not leave the comparison');
});

test('only the completed primary turn can unlock the comparison world', () => {
  for (const turns of [[], [completedTurn({ id: 'other-turn' })], [completedTurn({ status: 'running' })], [completedTurn({ status: 'failed' })]]) {
    const app = workspace({ hasBuilt: true, comparison: runningComparison(), turns });
    assert.equal(comparisonNode(app).props.primaryInteractive, false);
    assert.equal(primaryFrame(app).props.pending, true);
  }
  const app = workspace({ hasBuilt: true, comparison: runningComparison(), turns: [completedTurn()], status: 'running' });
  assert.equal(comparisonNode(app).props.primaryInteractive, false, 'a newer active build must remain protected');
});

test('the exit is named Enter your world and retains its old spoken alias', () => {
  const app = workspace({ hasBuilt: true, comparison: runningComparison(), turns: [completedTurn()] });
  const exit = findNode(app.render(), node => node.props?.className === 'finish-build-button');
  assert.match(JSON.stringify(exit.props.children), /Enter your world/);
  assert.doesNotMatch(JSON.stringify(exit.props.children), /Finish build/);
  assert.match(exit.props['aria-description'], /Finish build/);
});

test('Enter your world cannot dismiss the comparison with a stale published snapshot', async () => {
  const app = workspace({ hasBuilt: true, comparison: runningComparison() });
  findNode(app.render(), node => node.props?.className === 'finish-build-button').props.onClick();
  assert.equal(app.requests.length, 1);
  app.requests[0].resolve({ ...app.snapshot, session: { turns: [completedTurn({ revisionId: 2 })] }, revision: { id: 1 } });
  await settle();
  assert.equal(app.requests.length, 1, 'the finish endpoint must not run before the rendered revision matches');
  assert.equal(comparisonNode(app).props.active, true);
  assert.match(JSON.stringify(findNode(app.render(), node => node.props?.className === 'toast')), /still syncing/);
});

const enterWorld = app => findNode(app.render(), node => node.props?.className === 'finish-build-button').props.onClick();
const completedWorkspace = () => workspace({ hasBuilt: true, comparison: runningComparison(), turns: [completedTurn()] });
const savedEvent = id => ({ id: String(id), type: 'space.updated', time: '2026-09-25T00:00:00Z' });

test('entering preserves newer interaction snapshots and keeps its captured session without focusing the composer', async () => {
  const app = completedWorkspace();
  const oldSnapshot = { ...app.snapshot, events: [savedEvent(10)], html: '<p>Before the interaction</p>' };
  let focused = 0;
  app.textarea().props.ref.current = { focus() { focused++; } };
  enterWorld(app);
  app.updateSnapshot({ events: [savedEvent(20)], html: '<p>The newly saved interaction</p>' });
  app.render();
  app.changeSession('replacement-session');
  app.requests[0].resolve(oldSnapshot);
  await settle();
  assert.equal(app.requests.length, 2);
  assert.match(app.requests[1].path, /\/comparison\/parallel-build\/finish$/);
  assert.equal(app.requests[1].sessionToken, 'initial-session');
  assert.equal(primaryFrame(app).props.html, '<p>The newly saved interaction</p>');
  app.requests[1].resolve({});
  await settle();
  assert.equal(comparisonNode(app).props.active, false);
  assert.equal(focused, 0, 'a pointer-driven exit must not open the mobile keyboard');
});

test('both Activity children remain mounted from the first close render until layout and transition finish', async () => {
  for (const firstToFinish of ['layout', 'transition']) {
    const app = completedWorkspace();
    const initial = comparisonNode(app);
    const activitySlots = ['ultrafastActivity', 'standardActivity'];
    const identity = child => child && {
      type: child.type, key: child.props.key, path: child.props.path, turnId: child.props.turnId,
    };
    const initialIdentities = activitySlots.map(slot => identity(initial.props[slot]));
    assert.ok(initialIdentities.every(Boolean), 'both Activity streams start mounted');
    const assertRetained = phase => {
      const node = comparisonNode(app);
      for (const [index, slot] of activitySlots.entries()) {
        assert.ok(node.props[slot], `${slot} must not unmount during ${phase}`);
        assert.deepEqual(identity(node.props[slot]), initialIdentities[index], `${slot} retains its stream identity during ${phase}`);
      }
    };

    // BuildComparison retains its split layout while the exit animation captures
    // the old DOM. Its transition notification may arrive after the close render.
    app.holdComparisonLayout();
    enterWorld(app);
    app.requests[0].resolve(app.snapshot);
    await settle();
    app.requests[1].resolve({});
    await settle();
    assert.equal(comparisonNode(app).props.active, false, 'the real finish flow requested the close');
    assertRetained('the first close render, before transition-start notification');

    app.notifyComparisonTransition(true);
    assertRetained('the running exit transition');
    if (firstToFinish === 'layout') app.notifyComparisonLayout(false);
    else app.notifyComparisonTransition(false);
    assertRetained(`${firstToFinish} completion while the other phase is retained`);

    if (firstToFinish === 'layout') app.notifyComparisonTransition(false);
    else app.notifyComparisonLayout(false);
    const finished = comparisonNode(app);
    for (const slot of activitySlots) assert.equal(finished.props[slot], null, `${slot} releases only after both phases finish`);
  }
});

test('failed finish reads and writes leave the comparison open and release the retry lock', async () => {
  for (const stage of ['read', 'write']) {
    const app = completedWorkspace();
    enterWorld(app);
    if (stage === 'write') {
      app.requests[0].resolve(app.snapshot);
      await settle();
    }
    app.requests.at(-1).reject(new Error(`${stage} failed`));
    await settle();
    assert.equal(comparisonNode(app).props.active, true);
    assert.match(JSON.stringify(findNode(app.render(), node => node.props?.className === 'toast')), new RegExp(`${stage} failed`));
    const count = app.requests.length;
    enterWorld(app);
    assert.equal(app.requests.length, count + 1, `${stage} failure permits a new read`);
    app.requests.at(-1).reject(new Error('End fixture request'));
    await settle();
  }
});

test('rapid repeated exit activation starts only one request before a React commit', async () => {
  const app = completedWorkspace();
  const click = findNode(app.render(), node => node.props?.className === 'finish-build-button').props.onClick;
  click(); click();
  assert.equal(app.requests.length, 1);
  app.requests[0].reject(new Error('End fixture request'));
  await settle();
});

async function mountedCompletedWorkspace() {
  const app = completedWorkspace();
  app.render(); app.commitEffects();
  await settle();
  for (const request of app.requests) request.resolve(app.snapshot);
  await settle();
  app.render(); app.commitEffects();
  app.requests.length = 0;
  return app;
}

test('navigation away and back invalidates a pending exit instead of resuming its finish write', async () => {
  const app = await mountedCompletedWorkspace();
  enterWorld(app);
  const oldRead = app.requests[0];
  app.navigate('community'); app.commitEffects();
  app.navigate('space'); app.commitEffects();
  const count = app.requests.length;
  oldRead.resolve(app.snapshot);
  await settle();
  assert.equal(app.requests.length, count);
  assert.equal(comparisonNode(app).props.active, true);
  enterWorld(app);
  assert.equal(app.requests.length, count + 1, 'returning to the space can explicitly retry');
  app.requests.at(-1).reject(new Error('End fixture request'));
  await settle();
  app.unmount();
});

test('unmount ignores a delayed finish read or write and emits no further state updates', async () => {
  for (const stage of ['read', 'write']) {
    const app = await mountedCompletedWorkspace();
    enterWorld(app);
    if (stage === 'write') {
      app.requests[0].resolve(app.snapshot);
      await settle();
    }
    const pending = app.requests.at(-1);
    app.unmount();
    const count = app.requests.length, updates = app.stateUpdates;
    pending.resolve(stage === 'read' ? app.snapshot : {});
    await settle();
    assert.equal(app.requests.length, count);
    assert.equal(app.stateUpdates, updates);
  }
});

test('a replacement comparison or lost permission invalidates a delayed exit before effects commit', async () => {
  for (const change of ['comparison', 'permission']) {
    const app = completedWorkspace();
    enterWorld(app);
    if (change === 'comparison') app.updateComparison({ ...runningComparison(), id: 'replacement-build' });
    else { app.updateSnapshot({ permissions: { canEdit: false, canViewRuntime: false } }); app.render(); }
    app.requests[0].resolve(app.snapshot);
    await settle();
    assert.equal(app.requests.length, 1, `${change} prevents the old finish write`);
  }
});
