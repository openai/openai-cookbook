import { frameTheme } from './frame-theme';
import { useEffect, useMemo, useRef, useState } from 'react';
import { MAX_FRAME_HEIGHT, approvedServiceUrl, frameBridgeScript, frameCapabilities, frameServiceDraft, frameServiceRequest, frameServiceState, serviceStateUrls } from './frame-service-bridge';
import type { FrameServiceController, FrameServiceName, FrameServiceState } from './frame-service-bridge';
import { registerVoiceFrame } from './voice-frame-registry';
import type { FrameVoiceAction, FrameVoiceResult, FrameVoiceSurface, FrameVoiceViewport } from './voice-frame-registry';
import { createGameController } from './game-controller';
import type { GameCommand, GameControllerOptions, GameEvent } from './game-controller';
import type { SpaceAppearance } from './types';
import { withSpaceAppearance } from './space-appearance';
import { frameVoiceViewport } from './frame-viewport';

export type FrameGameSource = Pick<GameControllerOptions, 'load' | 'save'> & { id: string };

type VoiceReply = { ok: boolean; message?: string; surface?: FrameVoiceSurface };
type VoiceRequest = { version: number; context: object; key: string; snapshot: boolean; resolve: (reply: VoiceReply) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> };

type Props = {
  html: string;
  appearance?: SpaceAppearance;
  onAction: (action: Record<string, unknown>) => Promise<{ ok: boolean; html?: string; version?: number }>;
  renderVersion: number;
  /** Disable host actions, services, games, and voice until content is published. */
  pending: boolean;
  /** Visual treatment is independent of the read-only security boundary. */
  dimmed?: boolean;
  capabilities?: string[];
  services?: FrameServiceController;
  revisionId?: number | string;
  game?: FrameGameSource;
  games?: readonly FrameGameSource[];
};

export default function GeneratedFrame({ html, appearance, renderVersion, onAction, pending, dimmed = pending, capabilities = [], services, revisionId, game, games }: Props) {
  const ref = useRef<HTMLIFrameElement>(null);
  const actionRef = useRef(onAction);
  const pendingRef = useRef(pending);
  const presentedHtml = useMemo(() => withSpaceAppearance(html, appearance), [html, appearance?.lightCss, appearance?.presentationCss]);
  const htmlRef = useRef(presentedHtml);
  htmlRef.current = presentedHtml;
  const appearanceRef = useRef(appearance);
  appearanceRef.current = appearance;
  const versionRef = useRef(renderVersion);
  versionRef.current = renderVersion;
  const actionQueue = useRef(Promise.resolve());
  const queuedActions = useRef(0);
  const voiceRequests = useRef(new Map<number, VoiceRequest>());
  const voiceRequestId = useRef(0);
  const [readyKey, setReadyKey] = useState<string | null>(null);
  actionRef.current = onAction;
  pendingRef.current = pending;
  const capabilityKey = frameCapabilities(capabilities).join(',');
  const gameSources = useMemo(() => {
    const unique = new Map<string, FrameGameSource>();
    for (const source of games ?? (game ? [game] : [])) {
      if (unique.size >= 4) break;
      if (/^[A-Za-z][A-Za-z0-9_-]{0,63}$/.test(source.id) && !['constructor', 'prototype', '__proto__'].includes(source.id) && !unique.has(source.id)) unique.set(source.id, source);
    }
    return [...unique.values()];
  }, [game, games]);
  const context = useMemo(() => ({ services, revisionId, games: gameSources, capabilities: frameCapabilities(capabilities) }), [services, revisionId, gameSources, capabilityKey]);
  const contextRef = useRef(context);
  contextRef.current = context;
  const voiceContent = useRef({ context, html, version: renderVersion });
  if (voiceContent.current.context !== context || voiceContent.current.html !== html) voiceContent.current = { context, html, version: renderVersion };
  const currentVoiceVersion = (version: number) => version >= voiceContent.current.version && version <= versionRef.current;
  const cache = useMemo(() => ({ states: new Map<FrameServiceName, FrameServiceState>(), drafts: new Map<FrameServiceName, string>(), requests: new Map<FrameServiceName, number>(), inflight: new Map<FrameServiceName, number>() }), [context]);
  const cacheRef = useRef(cache);
  cacheRef.current = cache;
  type GameRuntime = { context: object; controller: ReturnType<typeof createGameController>; frame?: GameEvent; status?: GameEvent };
  const gameRuntimes = useRef(new Map<string, GameRuntime>());
  const [height, setHeight] = useState(120);
  const frame = useMemo(() => {
    const nonce = crypto.randomUUID().replaceAll('-', '');
    return { nonce, srcDoc: `<!doctype html><html style="overflow-y:hidden!important"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'nonce-${nonce}'; style-src 'unsafe-inline'; img-src data:; font-src data:; connect-src 'none'; form-action 'none'; base-uri 'none'"><style>${frameTheme}</style></head><body><div id="living-space-content">${presentedHtml}</div><script nonce="${nonce}">${frameBridgeScript(nonce, window.location.origin)}</script></body></html>` };
  }, [context]);
  const bridgeKeyRef = useRef(frame.nonce);
  bridgeKeyRef.current = frame.nonce;
  const send = (type: string, data: Record<string, unknown>) => ref.current?.contentWindow?.postMessage({ channel: 'living-space-host', bridgeKey: bridgeKeyRef.current, type, ...data }, '*');
  const configure = () => {
    send('render', { html: htmlRef.current, version: versionRef.current });
    send('service.configure', { active: !pendingRef.current, capabilities: contextRef.current.services ? contextRef.current.capabilities : [], states: pendingRef.current ? {} : Object.fromEntries(cacheRef.current.states), drafts: Object.fromEntries(cacheRef.current.drafts) });
    const sources = pendingRef.current ? [] : contextRef.current.games;
    send('game.configure', { configs: sources.map(source => ({ id: source.id })) });
    for (const source of sources) {
      const runtime = gameRuntimes.current.get(source.id);
      if (runtime?.context !== contextRef.current) continue;
      if (runtime.frame) send('game.event', { gameId: source.id, event: runtime.frame });
      if (runtime.status) send('game.event', { gameId: source.id, event: runtime.status });
    }
  };

  useEffect(() => {
    const receive = (event: MessageEvent) => {
      if (event.source !== ref.current?.contentWindow || event.data?.channel !== 'living-space' || event.data?.bridgeKey !== bridgeKeyRef.current) return;
      if (event.data.type === 'resize' && Number.isFinite(event.data.height)) setHeight(Math.min(MAX_FRAME_HEIGHT, Math.max(35, Math.ceil(event.data.height))));
      if (event.data.type === 'ready') { configure(); setReadyKey(bridgeKeyRef.current); }
      if (event.data.type === 'voice.result') {
        const request = voiceRequests.current.get(event.data.requestId);
        if (!request) return;
        voiceRequests.current.delete(event.data.requestId); clearTimeout(request.timer);
        if (request.key !== bridgeKeyRef.current || request.context !== contextRef.current || pendingRef.current || event.data.version !== request.version || request.snapshot && !currentVoiceVersion(request.version)) {
          request.reject(new Error('The space changed. Read its controls again.'));
        } else {
          request.resolve({ ok: event.data.ok === true, message: typeof event.data.message === 'string' ? event.data.message.slice(0, 1000) : undefined, surface: event.data.surface });
        }
        return;
      }
      if (pendingRef.current) return;
      const current = contextRef.current;
      if (event.data.type === 'game.command') {
        const { requestId, gameId, command, action, release } = event.data;
        if (!Number.isSafeInteger(requestId)) return;
        const runtime = gameRuntimes.current.get(gameId);
        if (!runtime || runtime.context !== current || !current.games.some(source => source.id === gameId)) {
          send('game.result', { requestId, ok: false });
          return;
        }
        void runtime.controller.handle({ command, action, release: release === true } as GameCommand).then(ok => {
          if (contextRef.current === current && !pendingRef.current) send('game.result', { requestId, ok });
        }).catch(() => {
          if (contextRef.current === current) send('game.result', { requestId, ok: false });
        });
        return;
      }
      if (event.data.type === 'action' && event.data.action && typeof event.data.action === 'object' && !Array.isArray(event.data.action) && typeof event.data.action.type === 'string') {
        const { action, requestId } = event.data;
        if (typeof requestId !== 'number' || !Number.isSafeInteger(requestId)) return;
        if (queuedActions.current >= 64 || JSON.stringify(action).length > 8000) { send('action.result', { requestId, ok: false, html: htmlRef.current, version: versionRef.current }); return; }
        const perform = actionRef.current;
        queuedActions.current++;
        actionQueue.current = actionQueue.current.catch(() => {}).then(async () => {
          if (contextRef.current !== current || pendingRef.current) return;
          let result: { ok: boolean; html?: string; version?: number } = { ok: false };
          try { result = await perform(action); } catch { /* App presents the save error. */ }
          if (contextRef.current === current) send('action.result', { requestId, ...result, html: result.html === undefined ? htmlRef.current : withSpaceAppearance(result.html, appearanceRef.current), version: result.version ?? versionRef.current });
        }).finally(() => { queuedActions.current--; });
        return;
      }
      if (event.data.type === 'service.draft') {
        const service = event.data.service as FrameServiceName;
        if (!current.services || !current.capabilities.includes(service)) return;
        const value = frameServiceDraft(event.data.value, service);
        if (value !== undefined) cacheRef.current.drafts.set(service, value);
        return;
      }
      if (event.data.type === 'service.open') {
        const service = event.data.service as FrameServiceName;
        if (!current.capabilities.includes(service)) return;
        const url = approvedServiceUrl(event.data.url, service);
        if (url && serviceStateUrls(cacheRef.current.states.get(service)).includes(url)) window.open(url, '_blank', 'noopener,noreferrer');
      }
      if (event.data.type !== 'service.request') return;
      const serviceRequestId = event.data.requestId;
      let acknowledged = false;
      const acknowledge = (ok: boolean) => {
        if (acknowledged) return;
        acknowledged = true;
        if (Number.isSafeInteger(serviceRequestId) && contextRef.current === current && !pendingRef.current) send('service.result', { requestId: serviceRequestId, ok });
      };
      if (!current.services) { acknowledge(false); return; }
      const request = frameServiceRequest(event.data.request, current.capabilities);
      if (!request) { acknowledge(false); return; }
      const stateCache = cacheRef.current;
      if (stateCache.inflight.has(request.service) && request.operation !== 'cancel' && request.operation !== 'clear') { acknowledge(false); return; }
      const requestNumber = (stateCache.requests.get(request.service) || 0) + 1;
      stateCache.requests.set(request.service, requestNumber);
      stateCache.inflight.set(request.service, requestNumber);
      const emit = (value: FrameServiceState) => {
        if (contextRef.current !== current || stateCache.requests.get(request.service) !== requestNumber) return;
        const state = frameServiceState(value, request.service);
        if (!state) return;
        stateCache.states.set(request.service, state);
        if (!pendingRef.current) send('service.state', { service: request.service, state });
        acknowledge(state.status !== 'error');
      };
      void Promise.resolve().then(() => {
        if (contextRef.current === current && !pendingRef.current) return current.services?.request(request, emit);
      }).then(() => acknowledge(true)).catch(error => {
        acknowledge(false);
        emit({ ...stateCache.states.get(request.service), status: 'error', error: error instanceof Error ? error.message : 'Request failed.' });
      })
        .finally(() => { if (stateCache.inflight.get(request.service) === requestNumber) stateCache.inflight.delete(request.service); });
    };
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  }, []);
  useEffect(() => { configure(); }, [pending, frame.nonce]);
  useEffect(() => { send('render', { html: presentedHtml, version: renderVersion }); }, [presentedHtml, renderVersion, frame.nonce]);
  useEffect(() => {
    if (pending) return;
    const runtimes = new Map<string, GameRuntime>();
    for (const source of gameSources) {
      const runtime: GameRuntime = {
        context,
        controller: createGameController({ ...source, emit(event) {
          if (gameRuntimes.current.get(source.id) !== runtime || contextRef.current !== context || pendingRef.current) return;
          if (event.type === 'frame') runtime.frame = event;
          else runtime.status = event;
          send('game.event', { gameId: source.id, event });
        } }),
      };
      runtimes.set(source.id, runtime);
    }
    gameRuntimes.current = runtimes;
    configure();
    return () => {
      if (gameRuntimes.current === runtimes) gameRuntimes.current = new Map();
      for (const runtime of runtimes.values()) runtime.controller.dispose();
    };
  }, [context, gameSources, pending]);
  useEffect(() => {
    if (pending || readyKey !== frame.nonce) return;
    const key = frame.nonce;
    const requests = voiceRequests.current;
    let active = true;
    const request = (type: 'voice.snapshot' | 'voice.execute', version: number, action?: FrameVoiceAction): Promise<VoiceReply> => {
      if (!active || contextRef.current !== context || bridgeKeyRef.current !== key || pendingRef.current || !currentVoiceVersion(version)) return Promise.reject(new Error('The space changed. Read its controls again.'));
      const element = ref.current;
      if (!element?.isConnected || element.closest('[hidden],[inert],[aria-hidden="true"]') || !element.getClientRects().length || getComputedStyle(element).visibility === 'hidden' || document.querySelector('dialog[open]')) return Promise.reject(new Error('Close the current overlay before using the space controls.'));
      if (requests.size >= 8) return Promise.reject(new Error('Wait for the current space action to finish.'));
      let viewport: FrameVoiceViewport | undefined;
      if (type === 'voice.snapshot') {
        // The opaque iframe cannot inspect which slice of a tall generated
        // page is visible in its parent window. Send geometry, never host DOM.
        viewport = frameVoiceViewport(element);
      }
      return new Promise((resolve, reject) => {
        const requestId = ++voiceRequestId.current;
        const timer = setTimeout(() => { requests.delete(requestId); reject(new Error('The space did not respond. Try again.')); }, 12000);
        requests.set(requestId, { version, context, key, snapshot: type === 'voice.snapshot', resolve, reject, timer });
        send(type, { requestId, version, ...(action ? { action } : {}), ...(viewport ? { viewport } : {}) });
      });
    };
    const unregister = registerVoiceFrame({
      async read() {
        const reply = await request('voice.snapshot', versionRef.current);
        const surface = reply.surface;
        if (!reply.ok || !surface || !currentVoiceVersion(surface.version) || !Array.isArray(surface.controls) || surface.controls.length > 160 || typeof surface.text !== 'string') throw new Error(reply.message || 'The space controls are not ready.');
        return surface;
      },
      async execute(action, version): Promise<FrameVoiceResult> {
        try {
          const reply = await request('voice.execute', version, action);
          return { ok: reply.ok, message: reply.message || (reply.ok ? 'The control was activated.' : 'The space could not use that control.') };
        } catch (failure) { return { ok: false, message: failure instanceof Error ? failure.message : 'The space controls are not ready.' }; }
      },
    });
    return () => {
      active = false; unregister();
      for (const [id, pendingRequest] of requests) {
        if (pendingRequest.context !== context || pendingRequest.key !== key) continue;
        clearTimeout(pendingRequest.timer); pendingRequest.reject(new Error('The space changed. Read its controls again.')); requests.delete(id);
      }
    };
  }, [context, frame.nonce, pending, readyKey]);
  useEffect(() => () => { for (const service of context.capabilities) context.services?.cancel?.(service); }, [context]);
  // Resize immediately: animating the iframe viewport exposes nested scrollbars
  // after responsive content has already reflowed. Its origin stays opaque.
  return <iframe ref={ref} title="Interactive community space" srcDoc={frame.srcDoc} onLoad={configure} sandbox="allow-scripts allow-forms" inert={pending} tabIndex={pending ? -1 : 0} data-space-appearance={appearance?.lightCss ? '' : undefined} className={`generated-frame ${pending ? 'action-pending' : ''}`} style={{ height, opacity: dimmed ? .75 : 1, transition: 'none' }} />;
}
