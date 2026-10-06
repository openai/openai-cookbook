import { installFrameRenderer } from './frame-renderer';
import { installPaintGestures } from './frame-paint-gestures';
import { installFrameVoice } from './frame-voice';
import { installFrameGame } from './frame-game';
import { gameValidationCode } from '../shared/game-schema.mjs';
import type { validateGameView } from '../shared/game-schema.mjs';
import { paintValidationCode } from '../shared/paint-schema.mjs';
import type { validatePaintConfig, validatePaintPixels } from '../shared/paint-schema.mjs';

export type FrameServiceName = 'health-chat' | 'finance-news' | 'space-agent';
export type FrameServiceOperation = 'submit' | 'load' | 'refresh' | 'clear' | 'cancel';
export type FrameServiceRequest = { service: FrameServiceName; operation?: FrameServiceOperation; input?: Record<string, string> };
export type FrameServiceState = {
  status: 'loading' | 'ready' | 'error';
  text?: string; error?: string; note?: string; urgent?: boolean; stopped?: boolean;
  messages?: { role: 'user' | 'assistant'; content: string }[];
  items?: { id?: string; title: string; summary?: string; date?: string; publishedAt?: string; url?: string; source?: string }[];
  sources?: { id?: string; title: string; url?: string; checkedAt?: string }[];
};
export type FrameServiceController = {
  request(request: FrameServiceRequest, emit: (state: FrameServiceState) => void): void | Promise<void>;
  cancel?(service?: FrameServiceName): void;
};

const names: FrameServiceName[] = ['health-chat', 'finance-news', 'space-agent'];
const officialOrigins: Record<FrameServiceName, string[]> = {
  'health-chat': ['https://www.nhlbi.nih.gov', 'https://www.cdc.gov', 'https://medlineplus.gov', 'https://www.nimh.nih.gov', 'https://www.ninds.nih.gov', 'https://www.nhs.uk'],
  'finance-news': ['https://www.federalreserve.gov'],
  'space-agent': [],
};
export function frameCapabilities(values: readonly string[] = []): FrameServiceName[] {
  return names.filter(name => values.includes(name));
}
/** Private, per-viewer message draft. This is never a public space action. */
export function frameServiceDraft(value: unknown, service: FrameServiceName): string | undefined {
  if (service !== 'health-chat' && service !== 'space-agent') return;
  return typeof value === 'string' && value.length <= 4000 && !value.includes('\0') ? value : undefined;
}
export function approvedServiceUrl(value: unknown, service: FrameServiceName): string | undefined {
  if (typeof value !== 'string' || value.length > 2000) return;
  try {
    const url = new URL(value);
    if (url.username || url.password || !officialOrigins[service]?.includes(url.origin)) return;
    return url.href;
  } catch { return; }
}
export function frameServiceRequest(value: unknown, allowed: readonly FrameServiceName[]): FrameServiceRequest | undefined {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return;
  const request = value as Record<string, unknown>;
  const service = request.service as FrameServiceName;
  if (!allowed.includes(service)) return;
  const chat = service !== 'finance-news';
  const operation = request.operation ?? (chat ? 'submit' : 'load');
  const permitted = chat ? ['submit', 'clear', 'cancel'] : ['load', 'refresh', 'cancel'];
  if (typeof operation !== 'string' || !permitted.includes(operation)) return;
  const input = request.input ?? {};
  if (!input || typeof input !== 'object' || Array.isArray(input) || Object.keys(input).length > 20) return;
  const entries = Object.entries(input);
  if (entries.some(([key, item]) => !/^[a-zA-Z][a-zA-Z0-9_-]{0,63}$/.test(key) || ['constructor', 'prototype', '__proto__'].includes(key) || typeof item !== 'string' || item.length > 4000)) return;
  if (JSON.stringify(input).length > 8000) return;
  return { service, operation: operation as FrameServiceOperation, input: Object.fromEntries(entries) as Record<string, string> };
}
export function frameServiceState(value: FrameServiceState, service: FrameServiceName): FrameServiceState | undefined {
  if (!value || !['loading', 'ready', 'error'].includes(value.status)) return;
  const string = (item: unknown, limit = 6000) => typeof item === 'string' ? item.slice(0, limit) : undefined;
  return {
    status: value.status, text: string(value.text), error: string(value.error, 1000), note: string(value.note, 1000),
    urgent: value.urgent === true, stopped: value.stopped === true,
    messages: Array.isArray(value.messages) ? value.messages.slice(-12).filter(item => item && ['user', 'assistant'].includes(item.role) && typeof item.content === 'string').map(item => ({ role: item.role, content: item.content.slice(0, 6000) })) : undefined,
    items: Array.isArray(value.items) ? value.items.slice(0, 20).filter(item => item && typeof item.title === 'string').map(item => ({ id: string(item.id, 2000), title: item.title.slice(0, 400), summary: string(item.summary, 2000), date: string(item.date || item.publishedAt, 100), publishedAt: string(item.publishedAt, 100), source: string(item.source, 200), url: approvedServiceUrl(item.url, service) })) : undefined,
    sources: Array.isArray(value.sources) ? value.sources.slice(0, 12).filter(item => item && typeof item.title === 'string').map(item => ({ id: string(item.id, 200), title: item.title.slice(0, 400), checkedAt: string(item.checkedAt, 100), url: approvedServiceUrl(item.url, service) })) : undefined,
  };
}
export function serviceStateUrls(state: FrameServiceState | undefined): string[] {
  return [...(state?.items || []), ...(state?.sources || [])].flatMap(item => item.url ? [item.url] : []);
}

export const MAX_FRAME_HEIGHT = 8000;

// Serialized into the nonce-protected frame. Every runtime dependency must be
// inside this function; all layout, wording and styling come from space.js.
function installFrameBridge(config: { key: string; parentOrigin: string; origins: Record<string, string[]>; maxHeight: number }, renderer: typeof installFrameRenderer, installPainting: typeof installPaintGestures, installVoice: typeof installFrameVoice, installGame: typeof installFrameGame, validateView: typeof validateGameView, validatePainting: typeof validatePaintConfig, validatePixels: typeof validatePaintPixels) {
  let active = false;
  let allowed: string[] = [];
  const states = new Map<string, FrameServiceState>();
  const locallyEdited = new Set<string>();
  const autoStarted = new Set<string>();
  const disabledInitially = new WeakMap<HTMLButtonElement | HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement, boolean>();
  const collections = new WeakMap<Element, { template: HTMLTemplateElement; rows: { key: string; nodes: Node[] }[] }>();
  const send = (type: string, data: Record<string, unknown> = {}) => parent.postMessage({ channel: 'living-space', bridgeKey: config.key, type, ...data }, config.parentOrigin);
  const updateHtml = renderer();
  let renderedVersion = -1;
  let lastHtmlChangeVersion = -1;
  let renderedHtml: string | undefined;
  let nextAction = 0;
  const actions = new Map<number, (ok: boolean) => void>();
  const gameActions = new Map<number, { gameId: string; resolve: (ok: boolean) => void }>();
  const serviceActions = new Map<number, { service: string; resolve: (ok: boolean) => void }>();
  let voiceActions: Promise<boolean>[] | null = null;
  let voiceGameAction = false;
  let voiceServiceAction = false;
  const dispatch = (action: Record<string, unknown>): Promise<boolean> => {
    if (!active || actions.size >= 64) return Promise.resolve(false);
    const requestId = ++nextAction;
    const result = new Promise<boolean>(resolve => { actions.set(requestId, resolve); send('action', { action, requestId }); });
    voiceActions?.push(result);
    return result;
  };
  const painting = installPainting({ isActive: () => active, dispatch }, validatePainting, validatePixels);
  const voice = installVoice();
  const games = new Map<string, ReturnType<typeof installGame>>();
  // A draft can dispose and reinstall games while keeping their DOM nodes.
  // Preserve authored states so temporary host disabling never becomes sticky.
  const gameDisabled = new WeakMap<HTMLButtonElement | HTMLInputElement, boolean>();
  const createGame = (gameId: string) => installGame({ isActive: () => active, validateView, authoredDisabled: gameDisabled, send: (type, data) => {
    if (!active || type !== 'game.command' || gameActions.size >= 64) { const rejected = Promise.resolve(false); voiceActions?.push(rejected); return rejected; }
    const requestId = ++nextAction;
    const result = new Promise<boolean>(resolve => { gameActions.set(requestId, { gameId, resolve }); send(type, { ...data, gameId, requestId }); });
    if (voiceActions) voiceGameAction = true;
    voiceActions?.push(result);
    return result;
  } });
  function configureGames(configs: unknown[]) {
    const ids = new Set<string>();
    for (const config of configs.slice(0, 4)) {
      const id = config && typeof config === 'object' ? (config as { id?: unknown }).id : undefined;
      if (typeof id === 'string' && /^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(id) && !['constructor', 'prototype', '__proto__'].includes(id)) ids.add(id);
    }
    for (const [id, game] of games) if (!ids.has(id)) {
      game.configure(undefined); game.dispose(); games.delete(id);
      for (const [requestId, pending] of gameActions) if (pending.gameId === id) { pending.resolve(false); gameActions.delete(requestId); }
    }
    for (const id of ids) {
      if (!games.has(id)) games.set(id, createGame(id));
      games.get(id)!.configure({ id });
    }
  }
  const roots = () => [...document.querySelectorAll<HTMLElement>('[data-service]')];
  const owned = (root: HTMLElement, selector: string) => [...root.querySelectorAll<HTMLElement>(selector)].filter(node => node.closest('[data-service]') === root);
  const messageInputs = (root: HTMLElement) => owned(root, 'input[name="message"],textarea[name="message"]').filter((node): node is HTMLInputElement | HTMLTextAreaElement => node instanceof HTMLTextAreaElement || node instanceof HTMLInputElement && ['text', 'search'].includes(node.type));
  const draftService = (service: string) => service === 'health-chat' || service === 'space-agent';
  function rememberDraft(root: HTMLElement, value: string) {
    const service = root.dataset.service || '';
    if (!active || !allowed.includes(service) || !draftService(service)) return;
    locallyEdited.add(service);
    // Longer invalid input must not retain and later restore an older draft.
    send('service.draft', { service, value: value.slice(0, 4000).replaceAll('\0', '') });
  }
  const object = (value: string | undefined) => { try { const parsed = JSON.parse(value || '{}'); return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {}; } catch { return {}; } };
  const safeUrl = (value: unknown, service: string) => {
    if (typeof value !== 'string') return undefined;
    try { const url = new URL(value); return !url.username && !url.password && config.origins[service]?.includes(url.origin) ? url.href : undefined; } catch { return undefined; }
  };
  const fieldNodes = (nodes: Node[]) => nodes.flatMap(node => node instanceof Element ? [...(node.matches('[data-field]') ? [node] : []), ...node.querySelectorAll('[data-field]')] : []);
  function fill(nodes: Node[], record: Record<string, unknown>, service: string) {
    for (const node of fieldNodes(nodes)) {
      // Service results are display data, never form values that could be
      // accidentally submitted to the public persistent-state action path.
      if (node.matches('input,textarea,select,option,button')) continue;
      const field = node.getAttribute('data-field') || '';
      const value = record[field];
      if (field === 'url') {
        const url = safeUrl(value, service);
        if (node instanceof HTMLAnchorElement) {
          if (url) { node.href = url; node.dataset.serviceLink = service; node.removeAttribute('aria-disabled'); }
          else { node.removeAttribute('href'); node.removeAttribute('data-service-link'); node.setAttribute('aria-disabled', 'true'); }
          node.rel = 'noopener noreferrer';
        }
      } else {
        node.textContent = field === 'role' && typeof value === 'string' ? node.getAttribute(`data-role-${value}`) || value : typeof value === 'string' || typeof value === 'number' ? String(value) : '';
      }
    }
    for (const node of nodes) if (node instanceof HTMLElement && typeof record.role === 'string') node.dataset.serviceRole = record.role;
  }
  function list(root: HTMLElement, kind: 'messages' | 'items' | 'sources', templateName: string, records: Record<string, unknown>[]) {
    const template = owned(root, `template[data-service-${templateName}]`)[0];
    if (!(template instanceof HTMLTemplateElement)) return;
    for (const container of owned(root, `[data-service-${kind}]`)) {
      if (container.closest('input,textarea,select,option,button')) continue;
      const previous = collections.get(container);
      const oldRows = previous?.template === template ? previous.rows : [];
      const atBottom = container.scrollHeight - container.clientHeight - container.scrollTop < 40;
      const rows = records.map((record, index) => {
        const key = `${record.id || record.role || kind}:${index}`;
        const row = oldRows.find(item => item.key === key) || { key, nodes: [...template.content.cloneNode(true).childNodes] };
        fill(row.nodes, record, root.dataset.service || '');
        return row;
      });
      if (oldRows.length !== rows.length || rows.some((row, index) => row !== oldRows[index])) {
        const keepTemplate = container.contains(template) ? [template] : [];
        container.replaceChildren(...keepTemplate, ...rows.flatMap(row => row.nodes));
      }
      collections.set(container, { template, rows });
      if (atBottom && container.scrollHeight > container.clientHeight) container.scrollTop = container.scrollHeight;
    }
  }
  function render(root: HTMLElement) {
    const service = root.dataset.service || '';
    const state = states.get(service);
    const status = state?.status || 'idle';
    const available = active && allowed.includes(service);
    root.dataset.serviceState = available ? status : 'unavailable';
    root.setAttribute('aria-busy', String(status === 'loading'));
    for (const node of owned(root, '[data-service-status]')) {
      const expected = node.dataset.serviceStatus;
      if (expected) node.hidden = expected !== status;
      else node.textContent = node.getAttribute(`data-status-${status}`) || '';
    }
    for (const field of ['text', 'error', 'note'] as const) for (const node of owned(root, `[data-service-${field}]`)) if (!node.closest('input,textarea,select,option,button')) node.textContent = state?.[field] || '';
    for (const field of ['urgent', 'stopped'] as const) for (const node of owned(root, `[data-service-${field}]`)) node.hidden = !state?.[field];
    const filled = Boolean(state?.messages?.length || state?.items?.length);
    for (const node of owned(root, '[data-service-empty]')) node.hidden = filled;
    for (const node of owned(root, '[data-service-filled]')) node.hidden = !filled;
    for (const node of owned(root, 'button,input,textarea,select')) {
      if (!(node instanceof HTMLButtonElement || node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement || node instanceof HTMLSelectElement)) continue;
      if (!disabledInitially.has(node)) disabledInitially.set(node, node.disabled);
      const operation = node.dataset.serviceOperation;
      const submit = node instanceof HTMLButtonElement && node.type === 'submit' || node instanceof HTMLInputElement && node.type === 'submit';
      const whileLoading = operation !== 'cancel' && operation !== 'clear' && (Boolean(operation) || submit || node.hasAttribute('data-service-disable-loading'));
      node.disabled = Boolean(disabledInitially.get(node) || !available || status === 'loading' && whileLoading || operation === 'cancel' && status !== 'loading');
    }
    list(root, 'messages', 'message', state?.messages || []);
    list(root, 'items', 'item', state?.items || []);
    list(root, 'sources', 'source', state?.sources || []);
  }
  const request = (root: HTMLElement, operation: string, input: Record<string, unknown> = {}) => {
    const service = root.dataset.service || '';
    if (voiceActions) voiceServiceAction = true;
    if (!active || !allowed.includes(service) || serviceActions.size >= 64) { voiceActions?.push(Promise.resolve(false)); return; }
    const requestId = ++nextAction;
    const result = new Promise<boolean>(resolve => {
      serviceActions.set(requestId, { service, resolve });
      send('service.request', { requestId, request: { service, operation, input } });
    });
    voiceActions?.push(result);
  };
  document.addEventListener('input', event => {
    const node = event.target;
    if (!(node instanceof HTMLTextAreaElement || node instanceof HTMLInputElement && ['text', 'search'].includes(node.type)) || node.name !== 'message') return;
    const root = node.closest<HTMLElement>('[data-service]');
    if (root && node.form?.closest('[data-service]') === root) rememberDraft(root, node.value);
  });
  document.addEventListener('reset', event => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const root = form.closest<HTMLElement>('[data-service]');
    // Native reset restores controls after dispatching this event.
    if (root) queueMicrotask(() => { if (!event.defaultPrevented) rememberDraft(root, messageInputs(root)[0]?.value || ''); });
  });
  document.addEventListener('click', event => {
    if (event.defaultPrevented || !(event.target instanceof Element)) return;
    const link = event.target.closest<HTMLAnchorElement>('a[data-service-link]');
    if (link) { event.preventDefault(); if (active && allowed.includes(link.dataset.serviceLink || '')) send('service.open', { service: link.dataset.serviceLink, url: link.href }); return; }
    const control = event.target.closest<HTMLButtonElement>('button[data-service-operation],input[data-service-operation]');
    if (control) {
      if (control.disabled || control.form && control.type === 'submit') return;
      event.preventDefault();
      const root = control.closest<HTMLElement>('[data-service]');
      if (root) {
        if (control.dataset.serviceOperation === 'clear') {
          for (const input of messageInputs(root)) input.value = '';
          rememberDraft(root, '');
        }
        request(root, control.dataset.serviceOperation || 'submit', object(control.dataset.serviceInput));
      }
      return;
    }
    const button = event.target.closest<HTMLButtonElement>('button[data-action],a[data-action]');
    if (!button || button.disabled || button.form && button.type === 'submit') return;
    event.preventDefault();
    if (active && !button.closest('[data-service]')) void dispatch(object(button.dataset.action));
  });
  document.addEventListener('submit', event => {
    event.preventDefault();
    if (!(event.target instanceof HTMLFormElement) || !active) return;
    const form = event.target;
    const input = Object.fromEntries([...new FormData(form)].filter((entry): entry is [string, string] => typeof entry[1] === 'string'));
    const root = form.closest<HTMLElement>('[data-service]');
    const submitter = event.submitter instanceof HTMLElement ? event.submitter : undefined;
    if (root) {
      request(root, submitter?.dataset.serviceOperation || form.dataset.serviceOperation || 'submit', input);
      if (form.hasAttribute('data-service-reset-on-submit')) form.reset();
      rememberDraft(root, messageInputs(root)[0]?.value || '');
    } else if (form.hasAttribute('data-action') && ![...form.elements].some(control => control.closest('[data-service]'))) {
      void dispatch({ ...object(form.dataset.action), ...input });
    }
  });
  window.addEventListener('message', event => {
    if (event.source !== parent || event.origin !== config.parentOrigin || event.data?.channel !== 'living-space-host' || event.data?.bridgeKey !== config.key) return;
    if (event.data.type === 'voice.snapshot' || event.data.type === 'voice.execute') {
      const { requestId, version } = event.data;
      if (!Number.isSafeInteger(requestId) || !Number.isSafeInteger(version)) return;
      const reply = (result: Record<string, unknown>) => send('voice.result', { requestId, version, ...result });
      if (!active || version < lastHtmlChangeVersion || version > renderedVersion) { reply({ ok: false, message: 'The space changed or is still being built. Read its controls again.' }); return; }
      if (event.data.type === 'voice.snapshot') { reply({ ok: true, surface: voice.read(version, event.data.viewport) }); return; }
      voiceActions = [];
      voiceGameAction = false;
      voiceServiceAction = false;
      const result = voice.execute(event.data.action, version);
      const dispatched = voiceActions;
      const wasGameAction = voiceGameAction;
      const wasServiceAction = voiceServiceAction;
      voiceActions = null;
      void Promise.all(dispatched).then(saved => {
        if (!saved.every(Boolean)) { reply({ ok: false, message: wasServiceAction ? 'The request was not accepted. Read the current controls and try again.' : 'The space could not complete that action. Read its current state and try again.' }); return; }
        const acknowledgement = wasServiceAction ? ' The request was accepted.' : wasGameAction ? ' The game accepted the command.' : ' The change was saved.';
        reply({ ...result, message: `${result.message}${dispatched.length && result.ok ? acknowledgement : ''}` });
      });
      return;
    }
    if (event.data.type === 'render' || event.data.type === 'action.result') {
      const version = event.data.version;
      if (typeof event.data.html === 'string' && Number.isFinite(version) && version >= renderedVersion) {
        renderedVersion = version;
        if (event.data.html !== renderedHtml) {
          lastHtmlChangeVersion = version;
          voice.invalidate();
          updateHtml(event.data.html);
          renderedHtml = event.data.html;
          for (const root of roots()) render(root);
          painting.reapply();
          for (const game of games.values()) game.reapply();
          // Out-of-flow content can change without resizing the body's box.
          resize();
        }
      }
      if (event.data.type === 'action.result') {
        actions.get(event.data.requestId)?.(event.data.ok === true);
        actions.delete(event.data.requestId);
      }
    }
    if (event.data.type === 'service.configure') {
      active = event.data.active === true;
      if (!active) {
        voice.invalidate();
        painting.cancel();
        for (const game of games.values()) game.cancel();
        for (const resolve of actions.values()) resolve(false);
        actions.clear();
        for (const { resolve } of gameActions.values()) resolve(false);
        gameActions.clear();
        for (const { resolve } of serviceActions.values()) resolve(false);
        serviceActions.clear();
      }
      allowed = Array.isArray(event.data.capabilities) ? event.data.capabilities.filter((value: unknown) => typeof value === 'string') : [];
      for (const [requestId, pending] of serviceActions) if (!allowed.includes(pending.service)) { pending.resolve(false); serviceActions.delete(requestId); }
      for (const [service, state] of Object.entries(event.data.states || {})) if (allowed.includes(service)) states.set(service, state as FrameServiceState);
      for (const root of roots()) {
        const service = root.dataset.service || '';
        const value = event.data.drafts?.[service];
        if (allowed.includes(service) && draftService(service) && !locallyEdited.has(service) && typeof value === 'string' && value.length <= 4000 && !value.includes('\0')) {
          for (const input of messageInputs(root)) input.value = value;
        }
      }
      for (const root of roots()) render(root);
      for (const game of games.values()) game.reapply();
      for (const root of roots()) if (active && root.dataset.service === 'finance-news' && root.hasAttribute('data-service-auto') && allowed.includes('finance-news') && !states.has('finance-news') && !autoStarted.has('finance-news')) {
        autoStarted.add('finance-news'); request(root, 'load');
      }
    }
    if (event.data.type === 'service.state' && active && allowed.includes(event.data.service)) {
      states.set(event.data.service, event.data.state);
      for (const root of roots()) if (root.dataset.service === event.data.service) render(root);
    }
    if (event.data.type === 'service.result' && Number.isSafeInteger(event.data.requestId)) {
      serviceActions.get(event.data.requestId)?.resolve(event.data.ok === true);
      serviceActions.delete(event.data.requestId);
    }
    if (event.data.type === 'game.configure') configureGames(Array.isArray(event.data.configs) ? event.data.configs : event.data.config ? [event.data.config] : event.data.id ? [{ id: event.data.id }] : []);
    if (event.data.type === 'game.event') games.get(event.data.gameId)?.receive(event.data.gameId, event.data.event);
    if (event.data.type === 'game.result' && Number.isSafeInteger(event.data.requestId)) {
      gameActions.get(event.data.requestId)?.resolve(event.data.ok === true);
      gameActions.delete(event.data.requestId);
    }
  });
  let lastHeight = -1;
  const resize = () => {
    const root = document.documentElement;
    const { scrollTop, scrollLeft } = root;
    // Measure at full width: a scrollbar makes responsive artwork shorter,
    // which would otherwise lock the frame into that narrower layout forever.
    root.style.setProperty('overflow-y', 'hidden', 'important');
    const horizontalGutter = Math.max(0, window.innerHeight - root.clientHeight);
    const naturalHeight = Math.ceil(Math.max(document.body.scrollHeight, document.body.getBoundingClientRect().height) + horizontalGutter);
    const capped = naturalHeight > config.maxHeight;
    root.style.setProperty('overflow-y', capped ? 'auto' : 'hidden', 'important');
    if (capped) {
      root.scrollTop = scrollTop;
      root.scrollLeft = scrollLeft;
    }
    const height = Math.min(config.maxHeight, naturalHeight);
    if (height !== lastHeight) { lastHeight = height; send('resize', { height }); }
  };
  new ResizeObserver(resize).observe(document.body);
  window.addEventListener('resize', resize);
  document.addEventListener('toggle', resize, true);
  document.addEventListener('change', resize);
  resize();
  send('ready');
}

export function frameBridgeScript(key: string, parentOrigin: string): string {
  const config = JSON.stringify({ key, parentOrigin, origins: officialOrigins, maxHeight: MAX_FRAME_HEIGHT }).replaceAll('<', '\\u003c');
  return `(()=>{${gameValidationCode}\n${paintValidationCode}\n(${installFrameBridge.toString()})(${config}, ${installFrameRenderer.toString()}, ${installPaintGestures.toString()}, ${installFrameVoice.toString()}, ${installFrameGame.toString()}, validateGameView, validatePaintConfig, validatePaintPixels);})();`;
}
