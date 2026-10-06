import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowDown, ArrowLeft, ArrowUp, ArrowUpRight, Check, ChevronLeft, ChevronRight, CircleHelp, ExternalLink, History, ImagePlus, LoaderCircle, LogOut, MessageCircle, Orbit, RotateCcw, Square, X } from 'lucide-react';
import { AfterHours, SmallHours, Tidepool } from './artworks';
import GeneratedFrame from './GeneratedFrame';
import type { FrameGameSource } from './GeneratedFrame';
import type { GamePayload } from './game-controller';
import { gameConfigs } from '../shared/game-schema.mjs';
import CanvasArrival from './CanvasArrival';
import Community from './Community';
import AccountGate from './AccountGate';
import ResetDemo from './ResetDemo';
import ThemeToggle, { readAppTheme } from './ThemeToggle';
import { listenForDemoReset, returnToWelcomeAfterReset } from './reset-session';
import Avatar from './Avatar';
import SpaceIcon from './SpaceIcon';
import SpaceIconEditor from './SpaceIconEditor';
import FriendshipButton from './FriendshipButton';
import VoiceLayer from './VoiceLayer';
import type { VoiceActionResult } from './live-voice';
import { registerVoiceForm } from './voice-action-registry';
import LiveBuildActivity from './BuildActivityPanel';
import BuildComparison from './BuildComparison';
import { useBuildComparison, watchPendingComparison } from './useBuildComparison';
import InspirationPrompts from './InspirationPrompts';
import { createSpaceServices } from './space-services';
import NavigationControls from './NavigationControls';
import type { NavigationActions } from './NavigationControls';
import { useAppNavigation } from './navigation';
import type { AppRoute, Navigate } from './navigation';
import { api, ApiError, captureSessionApi, hasSessionToken, setSessionToken, watchEvents } from './api';
import { canvasEvent, createSnapshotRefresher, mergeCanvasEvents, selectCanvasUpdate, snapshotEventId } from './snapshot-sync';
import type { AccountPerson, Revision, RuntimeEvent, SavedTurn, SignedIn, Snapshot, SpaceIcon as SpaceIconData, SpaceSummary } from './types';
import DevDayBrand, { WorldBrackets } from './DevDayBrand';
import './canvas-workspace.css';

export default function App() {
  const { route, navigate, navigation } = useAppNavigation();
  const [auth, setAuth] = useState<SignedIn | null>(null);
  const [people, setPeople] = useState<AccountPerson[]>([]);
  const [initializing, setInitializing] = useState(true);
  const [signingIn, setSigningIn] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [arrivalSpaceId, setArrivalSpaceId] = useState<string | null>(null);
  const startupVersion = useRef(0);
  const finishArrival = useCallback(() => setArrivalSpaceId(null), []);
  useEffect(listenForDemoReset, []);
  useEffect(() => { if (!auth || route.screen === 'home') document.title = 'Little Worlds · OpenAI DevDay 2026'; }, [auth, route.screen]);
  const loadPeople = useCallback(() => api<{ users: AccountPerson[] }>('/api/auth/people').then(data => setPeople(data.users)), []);
  useEffect(() => {
    let current = true;
    let pending = false;
    let retryNeeded = true;
    const version = startupVersion.current;
    async function restore() {
      if (!current || pending || !retryNeeded || version !== startupVersion.current) return;
      pending = true;
      setInitializing(true);
      const [directory, session] = await Promise.allSettled([
        api<{ users: AccountPerson[] }>('/api/auth/people'),
        hasSessionToken() ? api<SignedIn>('/api/auth/session') : Promise.resolve(null),
      ]);
      if (!current || version !== startupVersion.current) return;
      pending = false;
      retryNeeded = directory.status === 'rejected';
      if (directory.status === 'fulfilled') setPeople(directory.value.users);
      if (session.status === 'fulfilled') {
        if (session.value) setAuth(session.value);
        setAuthError(directory.status === 'rejected' ? 'Cannot reach the local server. Start Little Worlds, then return to this tab to retry.' : null);
      } else {
        if (session.reason instanceof ApiError && session.reason.status === 401) {
          setSessionToken(null);
          setAuthError(directory.status === 'rejected' ? 'Cannot reach the local server. Start Little Worlds, then return to this tab to retry.' : null);
        } else {
          retryNeeded = true;
          setAuthError('Cannot reach the local server. Start Little Worlds, then return to this tab to retry.');
        }
      }
      setInitializing(false);
    }
    const retry = () => { void restore(); };
    retry();
    window.addEventListener('focus', retry);
    window.addEventListener('online', retry);
    return () => { current = false; window.removeEventListener('focus', retry); window.removeEventListener('online', retry); };
  }, []);
  useEffect(() => { if (route.screen === 'home') void loadPeople().catch(() => {}); }, [route.screen, loadPeople]);
  const expired = useCallback(() => { setSessionToken(null); setAuth(null); setAuthError(null); void loadPeople().catch(() => {}); }, [loadPeople]);
  async function signIn(body: { userId: string } | { name: string }) {
    if (signingIn) return;
    startupVersion.current++;
    setInitializing(false);
    setSigningIn(true); setAuthError(null);
    try {
      const session = 'userId' in body && auth?.user.id === body.userId ? auth : await api<SignedIn & { token: string }>('/api/auth/sign-in', body);
      if ('token' in session) setSessionToken(session.token as string);
      setAuth(session);
      // Signing in can open the same deep-linked route without a navigation.
      window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
      const target = route.screen === 'home' ? session.ownSpaceId : route.spaceId;
      setArrivalSpaceId(!('userId' in body) && target === session.ownSpaceId ? target : null);
      if (route.screen !== 'community') navigate({ screen: 'space', spaceId: target });
    } catch (error) { setAuthError(error instanceof Error ? error.message : 'Could not open your space.'); }
    finally { setSigningIn(false); }
  }
  async function signOut() {
    startupVersion.current++;
    try { await api('/api/auth/sign-out', {}); }
    finally { setSessionToken(null); setAuth(null); setAuthError(null); navigate({ screen: 'home' }); void loadPeople().catch(() => {}); }
  }
  const page = !auth || route.screen === 'home'
    ? <AccountGate navigation={navigation} people={people} busy={initializing || signingIn} error={authError} onChoose={id => void signIn({ userId: id })} onCreate={name => void signIn({ name })}/>
    : <Workspace key={`${auth.user.id}:${route.spaceId}`} auth={auth} route={route} navigation={navigation} arrivalRequested={arrivalSpaceId === route.spaceId} onArrived={finishArrival} onRoute={navigate} onSignOut={() => void signOut().catch(() => {})} onExpired={expired}/>;
  return <><VoiceLayer identity={auth?.user.id || null} ready={!initializing && (!!auth || !hasSessionToken())} context={`Screen: ${route.screen}. ${auth ? `Signed in as ${auth.user.name}. Own space: ${auth.ownSpaceId}.` : 'Welcome screen, not signed in.'} Voice actions use the same visible controls as typing and clicking.`}/>{page}{(!auth || route.screen !== 'community') && <DemoUtilities/>}</>;
}

function DemoUtilities() {
  return <div className="demo-utilities"><ResetDemo onReset={returnToWelcomeAfterReset}/><ThemeToggle/></div>;
}

function Workspace({ auth, route, navigation, arrivalRequested, onArrived, onRoute, onSignOut, onExpired }: { auth: SignedIn; route: Exclude<AppRoute, { screen: 'home' }>; navigation: NavigationActions; arrivalRequested: boolean; onArrived: () => void; onRoute: Navigate; onSignOut: () => void; onExpired: () => void }) {
  const spaceId = route.spaceId;
  const onNavigate = (id: string) => onRoute({ screen: 'space', spaceId: id });
  const base = `/api/spaces/${encodeURIComponent(spaceId)}`;
  const own = spaceId === auth.ownSpaceId;
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [events, setEvents] = useState<RuntimeEvent[]>([]);
  const [spaces, setSpaces] = useState<SpaceSummary[]>([]);
  const [accountIcon, setAccountIcon] = useState<SpaceIconData>();
  const [prompt, setPrompt] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const submitLock = useRef(false);
  const [acceptedTurnId, setAcceptedTurnId] = useState<string | null>(null);
  const [arriving, setArriving] = useState(arrivalRequested);
  const [showHistory, setShowHistory] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [showThread, setShowThread] = useState(false);
  const [showAccount, setShowAccount] = useState(false);
  const [showIconEditor, setShowIconEditor] = useState(false);
  const [showGuide, setShowGuide] = useState(false);
  const [showActivity, setShowActivity] = useState(false);
  const [activityTurn, setActivityTurn] = useState<SavedTurn>();
  const [activitySelectionRequest, setActivitySelectionRequest] = useState(0);
  const [comparisonStarting, setComparisonStarting] = useState(false);
  const [pendingComparisonId, setPendingComparisonId] = useState<string | null>(null);
  const [comparisonFinishing, setComparisonFinishing] = useState(false);
  const [comparisonMorphing, setComparisonMorphing] = useState(false);
  const [comparisonLayout, setComparisonLayout] = useState(false);
  const [dismissedComparison, setDismissedComparison] = useState<string | null>(null);
  const activityToggle = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (activityTurn && snapshot && !snapshot.session.turns?.some(turn => turn.id === activityTurn.id)) setActivityTurn(undefined);
  }, [snapshot, activityTurn]);
  const showCommunity = route.screen === 'community';
  const communityPlace = route.screen === 'community' ? route.place : 'map';
  const services = useMemo(() => snapshot && !showCommunity
    ? createSpaceServices({ spaceId, revisionId: snapshot.revision.id, onExpired }) : undefined,
  [spaceId, snapshot?.revision.id, showCommunity, onExpired]);
  useEffect(() => () => services?.dispose(), [services]);
  const [revisions, setRevisions] = useState<Revision[]>([]);
  const [publishFlash, setPublishFlash] = useState(false);
  const canvasUpdate = selectCanvasUpdate(snapshot, events, acceptedTurnId);
  const busy = sending || canvasUpdate.running;
  useEffect(() => {
    // This bridges only POST acceptance to the first authoritative observation.
    // Do not keep an old ID alive across a later reset or pruned event history.
    if (acceptedTurnId && (snapshot?.session.turns?.some(turn => turn.id === acceptedTurnId)
      || events.some(event => event.turnId === acceptedTurnId))) setAcceptedTurnId(null);
  }, [acceptedTurnId, snapshot, events]);
  const canEdit = !!snapshot?.permissions.canEdit;
  const canViewActivity = canEdit && !!snapshot?.permissions.canViewRuntime;
  const { comparison: observedComparison, connected: comparisonConnected, refreshComparison } = useBuildComparison(base, canViewActivity, onExpired);
  useEffect(() => { if (observedComparison?.id === pendingComparisonId) setPendingComparisonId(null); }, [observedComparison?.id, pendingComparisonId]);
  useEffect(() => {
    if (!pendingComparisonId || !canViewActivity) return;
    // Every read starts after POST acceptance. Retry failed reads so a reset
    // or missing SSE connection cannot leave the split waiting indefinitely.
    return watchPendingComparison(pendingComparisonId, refreshComparison, () => {
      setPendingComparisonId(current => current === pendingComparisonId ? null : current);
    });
  }, [pendingComparisonId, canViewActivity, refreshComparison]);
  const comparison = comparisonStarting || pendingComparisonId && observedComparison?.id !== pendingComparisonId ? null : observedComparison;
  const finishContext = useRef({ base, screen: route.screen, comparisonId: comparison?.id, canViewActivity, snapshot });
  finishContext.current = { base, screen: route.screen, comparisonId: comparison?.id, canViewActivity, snapshot };
  const finishRequest = useRef<object | null>(null);
  useEffect(() => {
    // A route, permission, or comparison change invalidates an in-flight exit.
    // Cleanup also prevents its later continuation from acting after unmount.
    finishRequest.current = null;
    setComparisonFinishing(false);
    return () => { finishRequest.current = null; };
  }, [base, auth.user.id, route.screen, comparison?.id, canViewActivity]);
  const comparing = canViewActivity && (comparisonStarting || comparisonFinishing || !!pendingComparisonId || !!comparison && !comparison.finished && comparison.id !== dismissedComparison);
  const splitOpen = comparing && !showCommunity;
  const visualComparison = splitOpen || comparisonLayout || comparisonMorphing;

  useEffect(() => {
    if (!splitOpen) return;
    setShowThread(false);
    setShowHistory(false);
    setShowGuide(false);
    setShowActivity(false);
  }, [splitOpen]);
  const comparisonTerminal = !!comparison && ['completed', 'failed', 'cancelled'].includes(comparison.ultrafast.status);
  const activityOpen = canViewActivity && showActivity && !showCommunity && (!splitOpen || !!activityTurn);
  const openActivity = (turn?: SavedTurn) => {
    setActivityTurn(turn);
    setActivitySelectionRequest(value => value + 1);
    setShowActivity(true);
  };
  const closeActivity = useCallback(() => {
    setShowActivity(false);
    activityToggle.current?.focus({ preventScroll: true });
  }, []);
  const owner = snapshot?.space.owner;
  const name = owner?.name || (own ? auth.user.name : 'Your neighbor');
  useEffect(() => { document.title = `Little Worlds · ${showCommunity ? communityPlace === 'map' ? 'Community' : `${communityPlace[0].toUpperCase()}${communityPlace.slice(1)}’s space` : `${name}’s space`} · DevDay 2026`; }, [name, showCommunity, communityPlace]);
  const studio = snapshot?.space.kind === 'studio';
  const composerInput = useRef<HTMLTextAreaElement>(null);
  const composerForm = useRef<HTMLFormElement>(null);
  const focusedOnArrival = useRef(false);
  useEffect(() => {
    if (arriving && snapshot && !showCommunity && !focusedOnArrival.current) {
      focusedOnArrival.current = true;
      composerInput.current?.focus({ preventScroll: true });
    }
  }, [arriving, snapshot, showCommunity]);
  const actionLock = useRef(false);
  const latestSnapshotRef = useRef<Snapshot | null>(null);
  const historyDialog = useRef<HTMLDialogElement>(null);
  const threadDialog = useRef<HTMLDialogElement>(null);
  const accountDialog = useRef<HTMLDialogElement>(null);
  const guideDialog = useRef<HTMLDialogElement>(null);
  const revisionRef = useRef<number | null>(null);
  const refreshRef = useRef<() => Promise<void>>(() => Promise.resolve());
  const connectedRef = useRef(false);
  const refresh = useCallback(() => refreshRef.current(), []);
  // Publication metadata may be rehydrated after every checkpoint. Depend on
  // its content so one tile saving never remounts the other running games.
  const gameConfigKey = JSON.stringify(snapshot?.revision.meta?.games ?? snapshot?.revision.meta?.game ?? null);
  const games = useMemo<FrameGameSource[]>(() => {
    const revisionId = snapshot?.revision.id;
    if (revisionId === undefined || showCommunity) return [];
    let configs;
    try { configs = gameConfigs(snapshot?.revision.meta); } catch { return []; }
    const gameApi = captureSessionApi();
    // Capture this revision and viewer. Final checkpoints may finish after
    // navigation, but can never be redirected to a newly opened space.
    return configs.map(config => ({
      id: config.id,
      async load() {
        const payload = await gameApi<GamePayload>(`${base}/game?gameId=${encodeURIComponent(config.id)}`);
        if (payload.revisionId !== revisionId || payload.actor.id !== auth.user.id || payload.config.id !== config.id) throw new Error('The space changed. Open the game again.');
        return payload;
      },
      async save(action) {
        if (action.game.actorId !== auth.user.id || action.type !== config.saveAction) return false;
        try { await gameApi(`${base}/action`, { action, revisionId }); await refresh(); return true; }
        catch { return false; }
      },
    }));
  }, [base, snapshot?.revision.id, gameConfigKey, auth.user.id, showCommunity, refresh]);
  const updateIcon = useCallback((icon: SpaceIconData) => {
    setSnapshot(current => current ? { ...current, space: { ...current.space, icon } } : current);
    void refreshRef.current();
  }, []);
  useEffect(() => {
    const openedAt = Date.now();
    let flashTimer: ReturnType<typeof setTimeout> | undefined;
    let connectedOnce = false;
    const refresher = createSnapshotRefresher(() => api<Snapshot>(base), data => {
      latestSnapshotRef.current = data;
      setSnapshot(data); setEvents(prev => mergeCanvasEvents(prev, data.events || [])); setError(null);
      if (revisionRef.current !== null && data.revision.id !== revisionRef.current) {
        setPublishFlash(true); clearTimeout(flashTimer);
        flashTimer = setTimeout(() => setPublishFlash(false), 900);
      }
      revisionRef.current = data.revision.id;
    }, error => {
      if (error instanceof ApiError && error.status === 401) { onExpired(); return; }
      setError(error instanceof Error ? error.message : 'Could not open this space.');
    });
    refreshRef.current = refresher.request;
    void refresher.request();
    const stop = watchEvents(`${base}/events`, incoming => {
      const updates = incoming.filter(canvasEvent);
      if (!updates.length) return;
      setEvents(prev => mergeCanvasEvents(prev, updates));
      // Cursor coverage makes replay free once the opening snapshot arrives.
      // Timestamps cannot distinguish replay: a transaction may be timestamped
      // before this view opens, but commit after the first snapshot is read.
      const changed = updates.filter(event => event.type !== 'draft.preview');
      if (changed.length) void refresher.request(Math.max(...changed.map(event => Number(event.id))));
      const failure = changed.find(event => event.type === 'turn.failed' && Date.parse(event.time) >= openedAt);
      if (failure) setToast(failure.detail || failure.title);
    }, connected => {
      connectedRef.current = connected;
      if (connected && connectedOnce) void refresher.request();
      if (connected) connectedOnce = true;
    }, onExpired);
    return () => { stop(); refresher.dispose(); connectedRef.current = false; clearTimeout(flashTimer); };
  }, [base, onExpired]);
  // Owner and signed-in visitor artwork already arrive in their snapshots.
  // Load other contributors together, without one request for every avatar.
  const contributorDirectoryKey = JSON.stringify(Array.from(new Set(snapshot?.state.contributions.map(item => item.actorId) || []))
    .filter(id => id !== owner?.id && id !== auth.user.id).sort());
  useEffect(() => {
    if (!showCommunity && contributorDirectoryKey === '[]') return;
    let current = true;
    void api<{ spaces: SpaceSummary[] }>('/api/spaces').then(data => { if (current) setSpaces(data.spaces); }).catch(e => { if (current) setToast(e.message); });
    return () => { current = false; };
  }, [showCommunity, contributorDirectoryKey]);
  useEffect(() => {
    if (own) return;
    let current = true;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function loadAccountIcon() {
      try {
        const result = await api<{ icon: SpaceIconData }>(`/api/spaces/${encodeURIComponent(auth.ownSpaceId)}/icon`);
        if (!current) return;
        setAccountIcon(result.icon);
        if (result.icon.status === 'generating') timer = setTimeout(() => void loadAccountIcon(), 2000);
      } catch (failure) { if (current && failure instanceof ApiError && failure.status === 401) onExpired(); }
    }
    void loadAccountIcon();
    return () => { current = false; clearTimeout(timer); };
  }, [own, auth.ownSpaceId, onExpired]);
  useEffect(() => { if (!toast) return; const timer = setTimeout(() => setToast(null), 5000); return () => clearTimeout(timer); }, [toast]);
  useEffect(() => { if (showHistory) { setHistoryError(null); historyDialog.current?.showModal(); void api<Revision[] | { revisions: Revision[] }>(`${base}/revisions`).then(data => setRevisions(Array.isArray(data) ? data : data.revisions)).catch(e => setHistoryError(e.message)); } else historyDialog.current?.close(); }, [showHistory, base]);
  useEffect(() => { if (showGuide) guideDialog.current?.showModal(); else guideDialog.current?.close(); }, [showGuide]);
  useEffect(() => { if (showThread) threadDialog.current?.showModal(); else threadDialog.current?.close(); }, [showThread]);
  useEffect(() => { if (showAccount) accountDialog.current?.showModal(); else accountDialog.current?.close(); }, [showAccount]);
  async function submit(message = prompt, options: { preserveDraft?: boolean; onlyWhenIdle?: boolean } = {}): Promise<VoiceActionResult> {
    if (!message.trim()) return { ok: false, submitted: false, message: 'Describe what you would like to create before submitting.' };
    if (submitLock.current) return { ok: false, submitted: false, message: 'The previous request is still being accepted. This draft has not been submitted.' };
    if (!canEdit) return { ok: false, submitted: false, message: 'You cannot edit this space. This draft has not been submitted.' };
    if (!snapshot?.config.keyAvailable) return { ok: false, submitted: false, message: 'The builder is unavailable until an API key is configured on the server. This draft has not been submitted.' };
    if (comparing) return { ok: false, submitted: false, message: comparisonTerminal ? 'Finish this build comparison before submitting your next change. Your draft is preserved.' : 'The two builds are running. Finish or stop this comparison before submitting another change. Your draft is preserved.' };
    if (options.onlyWhenIdle && busy) return { ok: false, submitted: false, message: 'A build is already running. This suggested idea has not been submitted.' };
    submitLock.current = true;
    setSending(true); setError(null);
    setComparisonStarting(true); setShowActivity(false); setActivityTurn(undefined);
    try {
      const result = await api<{ turnId: string; comparisonId?: string }>(`${base}/turn`, { message: message.trim(), compare: true, appTheme: readAppTheme() });
      setPendingComparisonId(result.comparisonId || null);
      setAcceptedTurnId(result.turnId);
      // A suggested idea never replaces a typed thought. Also keep anything
      // the person typed while an ordinary submission was being accepted.
      if (!options.preserveDraft) setPrompt(current => current === message ? '' : current);
      // turn.started is authoritative and already invalidates the snapshot.
      // Retain the explicit fallback while the stream is reconnecting.
      // Acceptance is final even if refreshing the page fails or takes longer.
      if (!connectedRef.current) void Promise.resolve().then(refresh).catch(() => {});
      return { ok: true, submitted: true, turnId: result.turnId, message: 'The builder accepted the request and started a build. The page is not finished yet.' };
    }
    catch (e) {
      const message = e instanceof Error ? e.message : 'Could not start the change.';
      setToast(message);
      return { ok: false, message: `Could not confirm the build started: ${message} The draft has been preserved.` };
    }
    finally { submitLock.current = false; setSending(false); setComparisonStarting(false); }
  }
  useEffect(() => {
    // Register after each commit so voice submits the current draft and uses
    // the same permission, request-lock, and acceptance checks as the keyboard.
    if (composerForm.current) return registerVoiceForm(composerForm.current, () => submit());
  });
  async function act(action: Record<string, unknown>) {
    if (!snapshot || actionLock.current) return { ok: false };
    actionLock.current = true;
    try { await api(`${base}/action`, { action, revisionId: snapshot.revision.id }); await refresh(); return { ok: true, html: latestSnapshotRef.current?.html, version: latestSnapshotRef.current ? snapshotEventId(latestSnapshotRef.current) : undefined }; }
    catch (e) { setToast(e instanceof Error ? e.message : 'Could not save your contribution.'); await refresh(); return { ok: false, html: latestSnapshotRef.current?.html, version: latestSnapshotRef.current ? snapshotEventId(latestSnapshotRef.current) : undefined }; }
    finally { actionLock.current = false; }
  }
  async function cancel() {
    const pendingAtCancellation = pendingComparisonId;
    try {
      const result = await api<{ cancelled: boolean }>(`${base}/cancel`, {});
      await refresh();
      void refreshComparison().then(() => setPendingComparisonId(current => current === pendingAtCancellation ? null : current)).catch(() => {});
      setToast(result.cancelled ? 'Stopped further work. Your published space stays live.' : 'This change has already finished.');
    } catch (e) { setToast((e as Error).message); }
  }
  async function finishComparison() {
    if (!comparison || !comparisonTerminal || comparisonFinishing || finishRequest.current) return;
    const work = {};
    finishRequest.current = work;
    const scopedApi = captureSessionApi();
    const current = () => finishRequest.current === work && finishContext.current.base === base
      && finishContext.current.screen === 'space' && finishContext.current.comparisonId === comparison.id
      && finishContext.current.canViewActivity;
    setComparisonFinishing(true);
    try {
      // The ordinary background refresher intentionally absorbs network errors.
      // Here, verify a real snapshot before dismissing the comparison so entering
      // can never leave the user with an old or inert draft after a failed GET.
      const loaded = await scopedApi<Snapshot>(base);
      if (!current()) return;
      // The completed world remains interactive during this read. Preserve any
      // newer action/SSE snapshot that arrived while the exit request was waiting.
      const completed = [latestSnapshotRef.current, finishContext.current.snapshot].reduce<Snapshot>((freshest, candidate) =>
        candidate && snapshotEventId(candidate) > snapshotEventId(freshest) ? candidate : freshest, loaded);
      if (comparison.ultrafast.status === 'completed' && !completed.session.turns?.some(turn => turn.id === comparison.primaryTurnId && turn.status === 'completed' && turn.revisionId === completed.revision.id)) {
        throw new Error('The finished world is still syncing. Please try Enter your world again.');
      }
      latestSnapshotRef.current = completed;
      setSnapshot(completed);
      setEvents(previous => mergeCanvasEvents(previous, completed.events || []));
      await scopedApi(`${base}/comparison/${encodeURIComponent(comparison.id)}/finish`, {});
      if (!current()) return;
      setDismissedComparison(comparison.id);
      setShowActivity(false);
    } catch (e) { if (current()) setToast(e instanceof Error ? e.message : 'Could not finish this comparison. Try again.'); }
    finally {
      if (finishRequest.current === work) { finishRequest.current = null; setComparisonFinishing(false); }
    }
  }
  async function restore(id: number) { try { await api(`${base}/restore`, { revisionId: id }); await refresh(); setShowHistory(false); setToast('Restored the design. Your community’s contributions stay.'); } catch (e) { setHistoryError((e as Error).message); } }
  async function reset() { try { await api(`${base}/reset`, {}); setEvents([]); setAcceptedTurnId(null); setPendingComparisonId(null); revisionRef.current = null; await refresh(); setShowGuide(false); setToast(null); focusedOnArrival.current = false; setArriving(true); onRoute({ screen: 'space', spaceId }); } catch (e) { setToast((e as Error).message); } }
  const projects = snapshot?.state.projects || [];
  const contributions = snapshot?.state.contributions || [];
  const people = new Set(contributions.map(c => c.actorId)).size;
  const hasBuilt = !!snapshot && snapshot.space.hasBuilt;
  const draftEvent = canEdit ? canvasUpdate.draft : undefined;
  const draftHtml = typeof draftEvent?.data?.html === 'string' ? draftEvent.data.html : undefined;
  const canvas = snapshot?.revision.meta?.layout === 'canvas' || !!draftHtml && draftEvent?.data?.layout === 'canvas';
  const legacyStudio = studio && hasBuilt && !canvas;
  const turns = snapshot?.session.turns || [];
  const turnCount = snapshot?.session.turnCount || 0;
  // Comparison telemetry can finish before the published snapshot arrives.
  // Only unlock the matching committed revision, never its streamed draft.
  const primaryInteractive = comparison?.ultrafast.status === 'completed' && !draftHtml && !busy
    && turns.some(turn => turn.id === comparison.primaryTurnId && turn.status === 'completed' && turn.revisionId === snapshot?.revision.id);
  const comparisonStats = (lane: 'ultrafast' | 'standard') => ({
    model: comparison?.model || snapshot?.config.model,
    status: comparison?.[lane].status === 'preparing' || !comparison ? 'waiting' as const : comparison[lane].status,
  });
  const comparisonProgress = (lane: 'ultrafast' | 'standard') => ({
    id: comparison?.id || pendingComparisonId || 'starting',
    status: comparison?.progress?.status || 'pending' as const,
    expectedOutputTokens: comparison?.progress?.expectedOutputTokens,
    completedReferenceTokens: lane === 'standard' && comparison?.ultrafast.status === 'completed'
      ? comparison.ultrafast.outputTokens : undefined,
    outputTokens: comparison?.[lane].outputTokens || 0,
    laneStatus: comparison?.[lane].status || 'preparing' as const,
  });
  return <div className={`app-shell canvas-workspace${activityOpen ? ' with-build-activity' : ''}${comparisonLayout ? ' with-build-comparison' : ''}`} data-persona={owner?.id} data-voice-context={JSON.stringify({ space: name, spaceId, canEdit, building: busy, comparison: splitOpen ? { ultrafast: comparison?.ultrafast.status || 'preparing', standard: comparison?.standard.status || 'preparing', canFinish: comparisonTerminal } : null, latestTurn: turns.at(-1)?.status || 'none', view: showCommunity ? 'community' : 'space', revision: snapshot?.revision.id })}>
    {showCommunity && <Community navigation={navigation} place={communityPlace} onPlaceChange={place => onRoute({ screen: 'community', spaceId, place })} spaces={spaces} currentUserId={auth.user.id} onVisit={onNavigate} onClose={() => onNavigate(spaceId)} onExpired={onExpired} footerControl={<DemoUtilities/>}/>}
    <header className="topbar" inert={showCommunity}>
      <div className="page-header-leading"><NavigationControls navigation={navigation}/><a className="brand" href="/" onClick={e => { e.preventDefault(); onRoute({ screen: 'home' }); }} aria-label="Little Worlds home"><DevDayBrand compact/><span className="app-wordmark">Little Worlds</span></a></div>
      <div className="topbar-actions">
        {!own && <button className="text-button my-space-button" aria-label="My space" onClick={() => onNavigate(auth.ownSpaceId)}><ArrowLeft size={15}/><span>My space</span></button>}
        <button className="text-button community-button" aria-label="Community" onClick={() => onRoute({ screen: 'community', spaceId, place: 'map' })}><Orbit size={16}/><span>Community</span></button>
        <button className="text-button account-button" onClick={() => setShowAccount(true)} aria-label={`Account for ${auth.user.name}`}><SpaceIcon icon={own ? snapshot?.space.icon : accountIcon} size={29}/><span>{auth.user.name}</span></button>
      </div>
    </header>
    <div className="workspace" inert={showCommunity}>
      <main className={`space-main ${!legacyStudio ? 'personal-canvas' : ''} ${!hasBuilt ? 'blank-space' : ''} ${publishFlash ? 'just-published' : ''} ${busy ? 'is-generating' : ''} ${arriving ? 'is-arriving' : ''}`}>
        <div className="workspace-chrome" data-collapsed={comparisonLayout} aria-hidden={comparisonLayout} inert={comparisonLayout}><div className="workspace-chrome-content">
        <div className="space-toolbar"><div className="toolbar-right">
          {canEdit && <><button className="subtle-button thread-button" onClick={() => setShowThread(true)}><MessageCircle size={14}/><span>Thread{turnCount > 0 ? ` · ${turnCount}` : ''}</span></button><button className="subtle-button" onClick={() => setShowHistory(true)}><History size={14}/><span>History</span></button><button className="icon-button help-button" onClick={() => setShowGuide(true)} aria-label="Demo guide"><CircleHelp size={16}/></button></>}
        </div></div>
        <section className="studio-intro"><div className="profile-kicker"><>{own && canEdit ? <button className="space-icon-edit-button" onClick={() => setShowIconEditor(true)} aria-label="Change your space icon" title="Change your space icon"><SpaceIcon icon={snapshot?.space.icon} size={35}/><span className="space-icon-edit-mark" aria-hidden="true"><ImagePlus size={10}/></span></button> : <SpaceIcon icon={snapshot?.space.icon} size={35}/>}</><span>{name.toLocaleUpperCase()}’S SPACE</span>{snapshot?.space.profile && <span className="location">{snapshot.space.profile.role.toUpperCase()}</span>}{!own && owner && <FriendshipButton currentUserId={auth.user.id} targetId={owner.id} name={name}/>}</div>
          {legacyStudio && <div className="studio-heading"><div><h1>Small ideas.<br/><em>Room to grow.</em></h1><p>A few things I’m dreaming up. Come make something of them.</p></div><WorldBrackets/></div>}
        </section>
        </div></div>
        <BuildComparison active={splitOpen} primaryInteractive={primaryInteractive} onTransitionChange={setComparisonMorphing} onLayoutChange={setComparisonLayout} ultrafast={comparisonStats('ultrafast')} standard={comparisonStats('standard')}
          standardPreview={comparison?.standard.html ? <GeneratedFrame html={comparison.standard.html} renderVersion={0} onAction={async () => ({ ok: false })} pending dimmed={false}/> : undefined}
          ultrafastActivity={visualComparison ? <LiveBuildActivity path={`${base}/activity`} turnId={comparison?.primaryTurnId || '__preparing__'} comparisonProgress={comparisonProgress('ultrafast')} embedded id="ultrafast-build-activity" label="Ultrafast build activity" busy={comparisonStarting || comparison?.ultrafast.status === 'running' || comparison?.ultrafast.status === 'preparing'} model={comparison?.model || snapshot?.config.model} tier="ultrafast" onClose={() => {}} onExpired={onExpired}/> : null}
          standardActivity={visualComparison && comparison ? <LiveBuildActivity key={comparison.id} path={`${base}/comparison/${encodeURIComponent(comparison.id)}/activity`} comparisonProgress={comparisonProgress('standard')} embedded id="standard-build-activity" label="Standard build activity" busy={comparison.standard.status === 'running' || comparison.standard.status === 'preparing'} model={comparison.model} tier="standard" onClose={() => {}} onExpired={onExpired}/> : null}>
        <section className="projects-section" aria-label={studio ? 'Projects and community features' : `${name}’s living canvas`}>
          {legacyStudio && <><div className="section-label"><h2>ON MY WORKTABLE</h2><span>{String(projects.length).padStart(2, '0')} ONGOING CURIOSITIES <ArrowDown size={12}/></span></div><div className="project-grid">{projects.map((p, i) => <article className="project" key={p.id}><div className={`project-art project-art-${i}`}><span className="art-index">0{i + 1}</span>{i === 0 ? <Tidepool/> : i === 1 ? <AfterHours/> : <SmallHours/>}</div><div className="project-caption"><div><h3>{p.title}</h3><p>{p.description}</p></div><span className="project-arrow" aria-hidden="true"><ArrowUpRight size={18} strokeWidth={1.2}/></span></div></article>)}</div></>}
          {snapshot && arriving && !showCommunity && <CanvasArrival onComplete={() => { setArriving(false); onArrived(); }}/>}
          {snapshot && !hasBuilt && !draftHtml && <div className="empty-canvas" aria-label="Blank canvas"><div className="empty-canvas-copy"><WorldBrackets/><p className="canvas-edition"><span className="canvas-edition-name">LITTLE WORLDS</span> / DEVDAY 2026</p><h1>Describe what you want to create.</h1></div></div>}
          <div className={`living-extension ${hasBuilt ? 'has-built' : ''} ${draftHtml ? 'showing-draft' : ''}`} aria-label="Community features">
            {snapshot ? (hasBuilt || draftHtml) && <GeneratedFrame html={draftHtml || snapshot.html} appearance={draftHtml ? undefined : snapshot.space.appearance} renderVersion={Math.max(snapshotEventId(snapshot), Number(draftEvent?.id) || 0)} onAction={act} pending={!!draftHtml || splitOpen && !primaryInteractive} dimmed={!!draftHtml} capabilities={snapshot.revision.meta?.capabilities} services={services} revisionId={snapshot.revision.id} games={games}/> : <div className="loading-space"><LoaderCircle size={16} className="spin"/><span>{error || 'Opening this space…'}</span>{error && <><button onClick={() => void refresh()}>Retry</button>{!own && <button onClick={() => onNavigate(auth.ownSpaceId)}>My space</button>}</>}</div>}

          </div>

          {people > 0 && <div className="community-presence"><span className="presence-avatars">{Array.from(new Set(contributions.map(c => c.actorId))).slice(0, 3).map(id => {
            const contributor = id === owner?.id ? snapshot?.space : spaces.find(space => space.owner.id === id);
            const contributorIcon = id === auth.user.id && !own ? accountIcon || contributor?.icon : contributor?.icon;
            return <span key={id}><Avatar personId={id} displayName={contributor?.owner.name || (id === auth.user.id ? auth.user.name : undefined)} icon={contributorIcon} size={19}/></span>;
          })}</span><span>{people === 1 ? 'One person has' : `${people} people have`} made a little mark here.</span><span className="saved-indicator"><Check size={12}/> Saved live</span></div>}
        </section>
        </BuildComparison>
        <div className="composer-area">{!canEdit && snapshot ? <div className="visitor-note"><Avatar personId={auth.user.id} displayName={auth.user.name} icon={own ? snapshot.space.icon : accountIcon || spaces.find(space => space.owner.id === auth.user.id)?.icon} size={35}/><div><strong>You’re visiting {name} as {auth.user.name}.</strong><p>A shared place. Your contributions belong to you.</p></div><button className="subtle-button" onClick={() => onNavigate(auth.ownSpaceId)}>My space <ArrowUpRight size={15}/></button></div> : <>
          <div className="composer-slot">
            <div className="composer-feedback" role="status" aria-live="polite">{busy && <><span className="streaming-pulse"/><span>{draftHtml ? 'Taking shape…' : 'Creating…'}</span></>}</div>
            <div className="comparison-composer-row">
            <form ref={composerForm} className={`composer ${busy ? 'is-building' : ''}`} aria-label="Space builder" aria-description="Create or edit this space through the builder. Filling the request creates a draft; submitting starts a build." onSubmit={e => { e.preventDefault(); void submit(); }}><textarea ref={composerInput} aria-label="Describe a change to your space" aria-description="Host space builder request. Typing here only prepares a draft. Submit the form to create or edit the space." rows={1} value={prompt} onChange={e => setPrompt(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); void submit(); } }} placeholder={comparing ? 'Draft your next idea while both builds run…' : busy ? 'Add a thought while it’s working…' : hasBuilt ? 'What would you like to change?' : 'What would you like to create?'} maxLength={3000}/><button className="send-button" type="submit" disabled={!prompt.trim() || sending || comparing || !snapshot?.config.keyAvailable || !canEdit} aria-label={busy ? 'Send a follow-up' : 'Make it real'} aria-description="Submit the current host space builder draft to create or edit the space. The request is accepted before the build finishes.">{sending ? <LoaderCircle size={18} className="spin"/> : <ArrowUp size={20}/>}</button>{busy && <button type="button" className="cancel-button" onClick={() => void cancel()} aria-label="Stop this change"><Square size={13} fill="currentColor"/></button>}</form>
            {comparisonLayout && comparisonTerminal && <button type="button" className="finish-build-button" disabled={comparisonFinishing} onClick={() => void finishComparison()} aria-description="Enter your world, also called Finish build: close the comparison, stop any unfinished standard run, and open your ultrafast world.">{comparisonFinishing ? <LoaderCircle size={17} className="spin"/> : <ArrowUpRight size={17}/>}<span>{comparison?.ultrafast.status === 'completed' ? 'Enter your world' : 'Return to world'}</span></button>}
            </div>
            {comparisonLayout && !comparisonConnected && <p className="comparison-connection" role="status">{comparisonStarting ? 'Starting both builds…' : 'Reconnecting to the build comparison…'}</p>}
            {comparisonLayout && comparison?.ultrafast.error && <p className="comparison-error" role="status">Ultrafast: {comparison.ultrafast.error}</p>}
            {comparisonLayout && comparison?.standard.error && <p className="comparison-error" role="status">Standard: {comparison.standard.error}</p>}
          </div>

          <InspirationPrompts canEdit={canEdit && !showCommunity && !comparisonLayout} disabled={busy || !snapshot?.config.keyAvailable} onChoose={message => void submit(message, { preserveDraft: true, onlyWhenIdle: true })}/>
          {snapshot && canEdit && !snapshot.config.keyAvailable && <p className="key-note">Add an OpenAI API key on the server to start creating.</p>}
        </>}</div>
        <footer className="workspace-edition"><span>Little Worlds</span><span>A DEVDAY [2026] EXPERIENCE</span></footer>

      </main>
    </div>
    {canViewActivity && !showCommunity && (!splitOpen || activityOpen) && <>
      <button ref={activityToggle} className={`build-activity-toggle${busy ? ' is-active' : ''}`} onClick={() => activityOpen ? closeActivity() : openActivity()} aria-label={`${activityOpen ? 'Close' : 'Open'} build activity`} aria-expanded={activityOpen} aria-controls={activityOpen ? 'build-activity-panel' : undefined} title={`${activityOpen ? 'Close' : 'Open'} build activity`}>{activityOpen ? <ChevronRight size={16}/> : <ChevronLeft size={16}/>}<span>Activity</span></button>
    </>}
    {activityOpen && <LiveBuildActivity path={`${base}/activity`} busy={busy} model={snapshot?.config.model} tier={snapshot?.config.requestedTier} selectedTurn={turns.find(turn => turn.id === activityTurn?.id) || activityTurn} selectionRequest={activitySelectionRequest} savedEvents={snapshot?.events} onReturnToLive={() => setActivityTurn(undefined)} onClose={closeActivity} onExpired={onExpired}/>}
    {toast && <div className="toast" role="status"><span>{toast}</span><button aria-label="Dismiss notification" onClick={() => setToast(null)}><X size={14}/></button></div>}
    {showIconEditor && own && canEdit && <SpaceIconEditor spaceId={spaceId} icon={snapshot?.space.icon} hasBuilt={hasBuilt} onChanged={updateIcon} onClose={() => setShowIconEditor(false)} onExpired={onExpired}/>}
    <dialog ref={accountDialog} onClose={() => setShowAccount(false)} onClick={e => { if (e.target === e.currentTarget) setShowAccount(false); }} className="modal account-modal"><div className="modal-header"><div><DevDayBrand compact/><h2>At home here, {auth.user.name}.</h2></div><button className="icon-button" onClick={() => setShowAccount(false)} aria-label="Close account"><X size={20}/></button></div><p className="modal-note">Your space and its conversation stay here when you sign out. Come back and pick up where you left off.</p><div className="account-actions"><button onClick={() => { setShowAccount(false); onNavigate(auth.ownSpaceId); }}>Go to my space <ArrowUpRight size={17}/></button><button onClick={onSignOut}><LogOut size={16}/> Sign out</button></div></dialog>
    <dialog ref={threadDialog} onClose={() => setShowThread(false)} onClick={e => { if (e.target === e.currentTarget) setShowThread(false); }} className="modal"><div className="modal-header"><div><span className="eyebrow">ONE SPACE. AN ONGOING CONVERSATION.</span><h2>Pick up the thread.</h2></div><button className="icon-button" onClick={() => setShowThread(false)} aria-label="Close thread"><X size={20}/></button></div><p className="modal-note">Every change builds on the code, data, and conversation already here.</p>{turns.length ? <ol className="saved-thread">{turns.map((turn, i) => <li key={turn.id} className="thread-turn"><button className="thread-activity-link" onClick={() => { threadDialog.current?.close(); setShowThread(false); openActivity(turn); }} aria-label={`View activity for request ${i + 1}: ${turn.message}`}><span className="thread-turn-number">{String(i + 1).padStart(2, '0')}</span><span className="thread-turn-content"><span className="thread-turn-message">{turn.message}</span><small>{turn.status === 'completed' ? 'Saved in this conversation' : turn.status} · {new Date(turn.startedAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</small></span><ArrowUpRight size={16} aria-hidden="true"/></button></li>)}</ol> : <div className="thread-empty"><MessageCircle size={26}/><p>Your first idea starts the conversation.</p></div>}<button className="continue-thread" onClick={() => { setShowThread(false); document.querySelector<HTMLTextAreaElement>('.composer textarea')?.focus(); }}>Continue creating <ArrowUpRight size={16}/></button></dialog>
    <dialog ref={historyDialog} onClose={() => setShowHistory(false)} onClick={e => { if (e.target === e.currentTarget) setShowHistory(false); }} className="modal"><div className="modal-header"><div><span className="eyebrow">EVERY POSSIBILITY, KEPT</span><h2>Your space, over time.</h2></div><button className="icon-button" onClick={() => setShowHistory(false)} aria-label="Close history"><X size={20}/></button></div><p className="modal-note">Restore a design without removing community contributions.</p>{historyError && <p className="history-error" role="alert">{historyError}</p>}<div className="revision-list">{[...revisions].reverse().map(r => <div key={r.id}><span className="revision-number">{String(r.id).padStart(2, '0')}</span><div><strong>{r.meta?.title || r.title}</strong><p>{new Date(r.createdAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</p></div>{r.id === snapshot?.revision.id ? <span className="current-pill">LIVE</span> : <button disabled={busy} className="subtle-button" onClick={() => void restore(r.id)}><RotateCcw size={14}/>Restore</button>}</div>)}</div></dialog>
    <dialog ref={guideDialog} onClose={() => setShowGuide(false)} onClick={e => { if (e.target === e.currentTarget) setShowGuide(false); }} className="modal guide-modal"><div className="modal-header"><div><span className="eyebrow">THE TWO-MINUTE TOUR</span><h2>From mine to ours.</h2></div><button className="icon-button" onClick={() => setShowGuide(false)} aria-label="Close demo guide"><X size={20}/></button></div><ol className="guide-steps"><li><span>01</span><div><strong>Make a place of your own.</strong><p>Enter your name to begin with a blank canvas, or log in to return to your space.</p></div></li><li><span>02</span><div><strong>Give it a possibility.</strong><p>Describe a place you imagine. Watch it come to life, then refine it with a thought.</p></div></li><li><span>03</span><div><strong>Let someone else step inside.</strong><p>Sign in as another person in a separate tab. Visit through Community and leave a contribution.</p></div></li><li><span>04</span><div><strong>Come back. Keep going.</strong><p>The owner’s conversation and code remain. A follow-up changes the space while contributions stay.</p></div></li></ol><div className="guide-bottom"><a href={`/?space=${encodeURIComponent(spaceId)}`} target="_blank" rel="noreferrer">Open a visitor tab <ExternalLink size={13}/></a><button disabled={busy} className="reset-button" data-voice-confirm aria-description="This removes the current space content and starts a blank space. Confirm before resetting." onClick={() => void reset()}><RotateCcw size={14}/>Reset this space</button></div></dialog>
  </div>;
}
