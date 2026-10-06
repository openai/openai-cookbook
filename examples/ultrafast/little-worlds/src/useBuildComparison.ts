import { useEffect, useMemo, useRef, useState } from 'react';
import { ApiError, captureSessionApi, watchEvents } from './api';

export interface ComparisonLane {
  turnId?: string;
  status: 'preparing' | 'running' | 'completed' | 'failed' | 'cancelled';
  startedAt: string;
  endedAt?: string;
  outputTokens: number;
  html?: string;
  error?: string;
  requestedTier?: string;
  servedTier?: string;
}

export interface BuildComparisonState {
  id: string;
  primaryTurnId: string;
  model: string;
  reasoningEffort: string;
  startedAt: string;
  finished: boolean;
  progress?: { status: 'pending' | 'ready' | 'fallback'; expectedOutputTokens?: number };
  ultrafast: ComparisonLane;
  standard: ComparisonLane;
}

function mergeComparisonUpdate(previous: BuildComparisonState | null, next: BuildComparisonState | null, retainPreviews: boolean) {
  if (!previous || !next || previous.id !== next.id) return next;
  const estimate = previous.progress;
  const frozenEstimate = estimate && estimate.status !== 'pending'
    && Number.isFinite(estimate.expectedOutputTokens) && (estimate.expectedOutputTokens ?? 0) > 0;
  const retain = (before: ComparisonLane, after: ComparisonLane): ComparisonLane => {
    if (!after.turnId || before.turnId !== after.turnId) return after;
    // Cumulative output is monotonic within a turn. Replayed or lagging
    // telemetry must not make a live progress bar move backwards.
    const outputTokens = Math.max(Number.isFinite(before.outputTokens) ? Math.max(0, before.outputTokens) : 0,
      Number.isFinite(after.outputTokens) ? Math.max(0, after.outputTokens) : 0);
    const staleActive = ['completed', 'failed', 'cancelled'].includes(before.status)
      && (after.status === 'preparing' || after.status === 'running');
    // A replay may deliver old active metadata with a newer cumulative count.
    // Keep the finished result (including the absence of a failed preview).
    const latest = staleActive ? { ...after, status: before.status, endedAt: before.endedAt,
      error: before.error, html: before.html } : after;
    const lane = outputTokens === latest.outputTokens ? latest : { ...latest, outputTokens };
    if (!retainPreviews || lane.status === 'failed' || lane.status === 'cancelled'
      || Object.hasOwn(lane, 'html') || before.html === undefined) return lane;
    return { ...lane, html: before.html };
  };
  const progress = frozenEstimate && (next.progress?.status !== estimate.status
    || next.progress?.expectedOutputTokens !== estimate.expectedOutputTokens) ? estimate : next.progress;
  const ultrafast = retain(previous.ultrafast, next.ultrafast), standard = retain(previous.standard, next.standard);
  if (progress === next.progress && ultrafast === next.ultrafast && standard === next.standard) return next;
  return { ...next, progress, ultrafast, standard };
}

/** Reconcile POST acceptance even if its initial refresh or SSE connection fails. */
export function watchPendingComparison(id: string, refresh: () => Promise<Pick<BuildComparisonState, 'id'> | null>, onResolved: () => void) {
  let active = true;
  let timer: ReturnType<typeof setTimeout> | undefined;
  const check = async () => {
    try {
      const comparison = await refresh();
      if (!active) return;
      if (!comparison || comparison.id === id) {
        active = false;
        onResolved();
        return;
      }
    } catch { /* Retry at a bounded cadence until acceptance is reconciled. */ }
    if (active) timer = setTimeout(() => { timer = undefined; void check(); }, 1500);
  };
  void check();
  return () => { active = false; clearTimeout(timer); };
}

/** One owner-only replayable stream; never carry another world's comparison over a navigation. */
export function useBuildComparison(base: string, enabled: boolean, onExpired: () => void) {
  const scope = useMemo(() => ({ base }), [base]);
  const current = useRef({ scope, enabled });
  current.current = { scope, enabled };
  const expired = useRef(onExpired);
  expired.current = onExpired;
  const [state, setState] = useState<{ scope: typeof scope; comparison: BuildComparisonState | null; connected: boolean; observation: number }>({ scope, comparison: null, connected: false, observation: 0 });
  const stateRef = useRef(state);
  stateRef.current = state;
  const refreshRef = useRef<() => Promise<BuildComparisonState | null>>(() => Promise.reject(new Error('The comparison is not available.')));
  const refreshComparison = useMemo(() => () => refreshRef.current(), []);
  useEffect(() => {
    let active = true;
    const valid = () => active && current.current.scope === scope && current.current.enabled;
    const previous = stateRef.current;
    let latest = previous.scope === scope && enabled ? previous.comparison : null;
    let observation = previous.scope === scope ? previous.observation : 0;
    let connected = false;
    // Every accepted transport observation invalidates older GETs. In
    // particular a slow fallback response must never overwrite fresh SSE.
    let revision = 0;
    let pollTimer: ReturnType<typeof setTimeout> | undefined;
    let inflight: Promise<BuildComparisonState | null> | null = null;
    setState({ scope, comparison: latest, connected: false, observation });
    if (!enabled) return;
    const scopedApi = captureSessionApi();
    let stop = () => {};
    const clearPoll = () => { clearTimeout(pollTimer); pollTimer = undefined; };
    const visible = () => typeof document === 'undefined' || document.hidden !== true;
    const expiredOnce = () => {
      if (!valid()) return;
      active = false;
      clearPoll();
      stop();
      setState(previous => ({ ...previous, connected: false }));
      expired.current();
    };
    const accept = (comparison: BuildComparisonState | null) => {
      latest = mergeComparisonUpdate(latest, comparison, false);
      revision++;
      observation++;
      setState({ scope, comparison: latest, connected, observation });
    };
    const unavailable = () => new Error('This comparison is no longer open.');
    const load = (): Promise<BuildComparisonState | null> => {
      if (!valid()) return Promise.reject(unavailable());
      if (inflight) return inflight;
      const atStart = revision;
      const request = scopedApi<{ comparison: BuildComparisonState | null }>(`${base}/comparison`).then(result => {
        if (!valid()) throw unavailable();
        if (revision !== atStart) return latest;
        if (!result || !Object.hasOwn(result, 'comparison')) throw new Error('The comparison state is unavailable.');
        accept(result.comparison);
        return latest;
      }).catch(error => {
        if (valid() && error instanceof ApiError && error.status === 401) expiredOnce();
        throw error;
      }).finally(() => { if (inflight === request) inflight = null; });
      inflight = request;
      return request;
    };
    const refresh = async () => {
      // Explicit refreshes are used after an accepted POST/cancel. An earlier
      // GET may have captured state before that mutation, so wait for it and
      // then start a fresh read instead of returning the older result.
      if (inflight) { try { await inflight; } catch { /* A fresh read can retry. */ } }
      if (!valid()) throw unavailable();
      return load();
    };
    refreshRef.current = refresh;
    const schedulePoll = (delay = 1500) => {
      clearPoll();
      if (valid() && !connected && visible()) pollTimer = setTimeout(() => { pollTimer = undefined; void poll(); }, delay);
    };
    const poll = async () => {
      if (!valid() || connected || !visible()) return;
      try { await load(); } catch { /* Keep the last good state and retry. */ }
      finally { schedulePoll(); }
    };
    stop = watchEvents(`${base}/comparison/events`, events => {
      if (!valid()) return;
      let comparison = latest, hasUpdate = false;
      // A batch can contain a new full preview followed by compact telemetry.
      // Fold in order before rendering once so that the preview is retained.
      for (const event of events) {
        if (event.type !== 'comparison.state' || !event.data || !Object.hasOwn(event.data, 'comparison')) continue;
        comparison = mergeComparisonUpdate(comparison, event.data.comparison as BuildComparisonState | null, event.data.retainPreviews === true);
        hasUpdate = true;
      }
      if (hasUpdate) accept(comparison);
    }, nextConnected => {
      if (!valid()) return;
      connected = nextConnected;
      setState({ scope, comparison: latest, connected, observation });
      if (connected) clearPoll(); else schedulePoll(0);
    }, expiredOnce);
    const visibility = () => { if (!visible()) clearPoll(); else if (!connected) schedulePoll(0); };
    if (typeof document !== 'undefined') document.addEventListener('visibilitychange', visibility);
    void poll();
    return () => {
      active = false;
      clearPoll();
      stop();
      if (typeof document !== 'undefined') document.removeEventListener('visibilitychange', visibility);
      if (refreshRef.current === refresh) refreshRef.current = () => Promise.reject(unavailable());
    };
  }, [base, scope, enabled]);
  return state.scope === scope && enabled
    ? { comparison: state.comparison, connected: state.connected, observation: state.observation, refreshComparison }
    : { comparison: null, connected: false, observation: 0, refreshComparison };
}
