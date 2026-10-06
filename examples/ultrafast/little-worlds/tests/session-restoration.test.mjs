import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

// Run App's real startup effect and API helper. Other components are inert so
// these tests need neither a browser nor a running server.
const appPath = fileURLToPath(new URL('../src/App.tsx', import.meta.url));
const namedStubs = {
  'lucide-react': ['ArrowDown', 'ArrowLeft', 'ArrowUp', 'ArrowUpRight', 'Check', 'ChevronLeft', 'ChevronRight', 'CircleHelp', 'ExternalLink', 'History', 'ImagePlus', 'LoaderCircle', 'LogOut', 'MessageCircle', 'Orbit', 'RotateCcw', 'Square', 'X'],
  './artworks': ['AfterHours', 'SmallHours', 'Tidepool'],
  './reset-session': ['listenForDemoReset', 'returnToWelcomeAfterReset'],
  './space-services': ['createSpaceServices'],
  './voice-action-registry': ['registerVoiceForm'],
  './snapshot-sync': ['canvasEvent', 'createSnapshotRefresher', 'mergeCanvasEvents', 'selectCanvasUpdate', 'snapshotEventId'],
};
const compiled = await build({
  entryPoints: [appPath], bundle: true, write: false, format: 'iife', globalName: 'AppModule',
  jsx: 'transform', jsxFactory: 'h.jsx', jsxFragment: 'h.Fragment',
  plugins: [{ name: 'app-startup-fixtures', setup(builder) {
    builder.onResolve({ filter: /.*/ }, ({ path, importer }) => {
      if (importer === appPath && path !== './api' && path !== '../shared/game-schema.mjs') return { path, namespace: 'fixture' };
    });
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => {
      if (path.endsWith('.css')) return { contents: '' };
      if (path === 'react') return { contents: 'export const {useCallback,useEffect,useMemo,useRef,useState}=h;' };
      if (path === 'react/jsx-runtime') return { contents: 'export const jsx=h.jsx,jsxs=h.jsx,Fragment=h.Fragment;' };
      if (path === './navigation') return { contents: 'export const useAppNavigation=()=>h.navigation;' };
      if (path === './DevDayBrand') return { contents: 'export const WorldBrackets=()=>null; export default "DevDayBrand";' };
      if (path === './ThemeToggle') return { contents: 'export const readAppTheme=()=>"dark"; export default "ThemeToggle";' };
      if (path === './useBuildComparison') return { contents: 'export const useBuildComparison=()=>({comparison:null,connected:true,refreshComparison:async()=>null}); export const watchPendingComparison=()=>()=>{};' };
      if (namedStubs[path]) return { contents: namedStubs[path].map(name => `export const ${name}=()=>{};`).join('\n') };
      return { contents: `export default ${JSON.stringify(path)};` };
    });
  } }],
});

const reply = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
const session = { user: { id: 'mira', name: 'Mira' }, ownSpaceId: 'mira', simulated: true };
const settle = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(done => { resolve = done; }); return { promise, resolve }; }
function findNode(tree, predicate) {
  if (Array.isArray(tree)) return tree.map(child => findNode(child, predicate)).find(Boolean);
  if (!tree || typeof tree !== 'object') return undefined;
  return predicate(tree) ? tree : findNode(tree.props?.children, predicate);
}

function mount(t, fetchSession) {
  const values = new Map([['living-spaces:demo-session', 'saved-token']]);
  const requests = [], hooks = [], effects = [];
  const scrolls = [];
  let index = 0;
  const window = new EventTarget();
  window.scrollTo = options => scrolls.push(options);
  const h = {
    navigation: { route: { screen: 'space', spaceId: 'mira' }, navigate() {}, navigation: {} },
    Fragment: 'fragment', jsx: (type, props) => ({ type, props }),
    useState(initial) {
      const slot = index++;
      if (!(slot in hooks)) hooks[slot] = { value: typeof initial === 'function' ? initial() : initial };
      return [hooks[slot].value, value => { hooks[slot].value = typeof value === 'function' ? value(hooks[slot].value) : value; }];
    },
    useRef(initial) { const slot = index++; return (hooks[slot] ||= { current: initial }); },
    useCallback: callback => callback, useMemo: callback => callback(),
    useEffect(callback, deps) {
      const slot = index++, old = hooks[slot];
      if (!old || deps.some((value, i) => value !== old.deps[i])) {
        hooks[slot] = { deps, cleanup: old?.cleanup };
        effects.push(() => { hooks[slot].cleanup?.(); hooks[slot].cleanup = callback(); });
      }
    },
  };
  const context = vm.createContext({ h, window, document: {}, setTimeout, clearTimeout,
    sessionStorage: { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) },
    fetch: async (path, init) => {
      requests.push({ path, init });
      if (path === '/api/auth/people') return reply({ users: [{ id: 'mira', name: 'Mira', ownSpaceId: 'mira' }] });
      return fetchSession(path, init);
    },
  });
  vm.runInContext(compiled.outputFiles[0].text, context);
  function render() {
    index = 0;
    const tree = context.AppModule.default();
    effects.splice(0).forEach(effect => effect());
    return tree;
  }
  function unmount() { hooks.forEach(hook => hook.cleanup?.()); }
  t.after(unmount);
  render();
  return { render, unmount, window, values, requests, scrolls,
    gate: () => findNode(render(), child => child.type === './AccountGate')?.props,
    voice: () => findNode(render(), child => child.type === './VoiceLayer')?.props,
    workspace: () => findNode(render(), child => typeof child.type === 'function' && child.type.name === 'Workspace')?.props };
}

test('live restoration waits until the saved account has finished restoring', async t => {
  const pending = deferred();
  const app = mount(t, async () => pending.promise);
  assert.equal(app.voice().ready, false);
  assert.equal(app.voice().identity, null);
  await settle();
  assert.equal(app.voice().ready, false, 'a pending saved session is not an anonymous voice session');
  pending.resolve(reply(session));
  await settle();
  assert.equal(app.voice().ready, true);
  assert.equal(app.voice().identity, 'mira');
  assert.equal(app.scrolls.length, 0, 'restoring a session leaves browser scroll restoration intact');
});

test('a temporary connection failure keeps the saved token and focus restores the session', async t => {
  let available = false;
  const app = mount(t, async () => {
    if (!available) throw new TypeError('Failed to fetch');
    return reply(session);
  });
  await settle();
  assert.equal(app.values.get('little-worlds:demo-session'), 'saved-token');
  assert.match(app.gate().error, /Cannot reach the local server/);
  assert.equal(app.gate().busy, false);
  assert.equal(app.voice().ready, false, 'voice cannot resume until the saved identity is known');
  available = true;
  app.window.dispatchEvent(new Event('focus'));
  await settle();
  assert.equal(app.workspace().auth.user.id, 'mira');
  assert.equal(app.voice().ready, true);
  assert.equal(app.requests.filter(request => request.path === '/api/auth/session').length, 2);
  assert.equal(app.requests.at(-1).init.headers.Authorization, 'Bearer saved-token');
});

test('a server error preserves auth and an online event retries without duplicate requests', async t => {
  const pending = deferred();
  let calls = 0;
  const app = mount(t, async () => ++calls === 1 ? reply({ error: 'Unavailable' }, 503) : pending.promise);
  await settle();
  assert.equal(app.values.get('little-worlds:demo-session'), 'saved-token');
  assert.match(app.gate().error, /Cannot reach the local server/);
  app.window.dispatchEvent(new Event('online'));
  app.window.dispatchEvent(new Event('focus'));
  assert.equal(calls, 2);
  pending.resolve(reply(session));
  await settle();
  assert.equal(app.workspace().auth.user.id, 'mira');
  app.window.dispatchEvent(new Event('focus'));
  assert.equal(calls, 2, 'successful startup no longer retries');
});

test('an expired or restarted server session returns to welcome without a notice', async t => {
  const app = mount(t, async () => reply({ error: 'Session ended' }, 401));
  await settle();
  assert.equal(app.values.has('little-worlds:demo-session'), false);
  assert.equal(app.gate().error, null);
  assert.equal(app.gate().people.length, 1);
  app.window.dispatchEvent(new Event('focus'));
  assert.equal(app.requests.filter(request => request.path === '/api/auth/session').length, 1);
});

test('a disposed startup check cannot remove a newer token', async t => {
  const pending = deferred();
  const app = mount(t, async () => pending.promise);
  app.unmount();
  app.values.set('little-worlds:demo-session', 'newer-token');
  pending.resolve(reply({ error: 'Old session expired' }, 401));
  await settle();
  assert.equal(app.values.get('little-worlds:demo-session'), 'newer-token');
});

test('choosing an account stops startup retries and ignores an older pending response', async t => {
  const pending = deferred();
  let reads = 0;
  const app = mount(t, async path => {
    if (path === '/api/auth/sign-in') return reply({ ...session, token: 'new-token', user: { id: 'james', name: 'James' }, ownSpaceId: 'james' });
    if (++reads === 1) throw new TypeError('Failed to fetch');
    return pending.promise;
  });
  await settle();
  const gate = app.gate();
  app.window.dispatchEvent(new Event('focus'));
  gate.onChoose('james');
  await settle();
  pending.resolve(reply({ error: 'Old session expired' }, 401));
  await settle();
  assert.equal(app.values.get('little-worlds:demo-session'), 'new-token');
  assert.equal(app.workspace().auth.user.id, 'james');
  assert.equal(app.scrolls.length, 1, 'choosing an account opens its destination at the header');
  assert.equal(app.scrolls[0].top, 0);
  assert.equal(app.scrolls[0].behavior, 'instant');
  app.window.dispatchEvent(new Event('online'));
  assert.equal(reads, 2);
});
