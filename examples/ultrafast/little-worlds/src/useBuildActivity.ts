import { useEffect, useMemo, useRef, useState } from 'react';
import { watchEvents } from './api';
import { mergeActivityEvents, type ActivityEntry } from './build-activity';

type ActivityScope = { path: string };
type ActivitySnapshot = {
  scope: ActivityScope;
  entries: ActivityEntry[];
  connected: boolean;
  connecting: boolean;
  clockOffsetMs: number;
};

/** Subscribe while open, retaining the last view only for this mounted workspace. */
export function useBuildActivity(path: string, enabled: boolean, onExpired: () => void) {
  const scope = useMemo(() => ({ path }), [path]);
  const current = useRef({ scope, enabled });
  current.current = { scope, enabled };
  const expired = useRef(onExpired);
  expired.current = onExpired;
  const [snapshot, setSnapshot] = useState<ActivitySnapshot>(() => ({
    scope, entries: [], connected: false, connecting: enabled, clockOffsetMs: 0,
  }));

  useEffect(() => {
    const fresh = (): ActivitySnapshot => ({ scope, entries: [], connected: false, connecting: enabled, clockOffsetMs: 0 });
    setSnapshot(previous => previous.scope === scope
      ? { ...previous, connected: false, connecting: enabled }
      : fresh());
    if (!enabled) return;

    let active = true;
    const sameScope = () => current.current.scope === scope && current.current.enabled;
    const canReceive = () => active && sameScope();
    let stop = () => {};
    stop = watchEvents(path, incoming => {
      if (!canReceive()) return;
      // The replay envelope has a fresh server timestamp. Calibrate once per
      // connection, rather than treating client/server clock skew as idle time.
      const serverTime = Date.parse(incoming.find(event => event.type === 'activity.reset')?.time || '');
      const clockOffset = Number.isFinite(serverTime) ? serverTime - Date.now() : undefined;
      setSnapshot(previous => {
        if (!canReceive()) return previous;
        const next = previous.scope === scope ? previous : fresh();
        const entries = mergeActivityEvents(next.entries, incoming);
        const clockOffsetMs = clockOffset ?? next.clockOffsetMs;
        return entries === next.entries && clockOffsetMs === next.clockOffsetMs ? next : { ...next, entries, clockOffsetMs };
      });
    }, connected => {
      if (!canReceive()) return;
      setSnapshot(previous => {
        if (!canReceive()) return previous;
        const next = previous.scope === scope ? previous : fresh();
        return { ...next, connected, connecting: !connected };
      });
    }, () => {
      if (!canReceive()) return;
      active = false;
      stop();
      setSnapshot(previous => sameScope()
        ? { ...(previous.scope === scope ? previous : fresh()), connected: false, connecting: false }
        : previous);
      expired.current();
    });
    return () => { active = false; stop(); };
  }, [path, scope, enabled]);

  // Effects clean up after rendering. Never expose a previous space's entries
  // during that intervening render, even when navigation returns to its URL.
  return snapshot.scope === scope
    ? { entries: snapshot.entries, connected: enabled && snapshot.connected, connecting: enabled && snapshot.connecting, clockOffsetMs: snapshot.clockOffsetMs }
    : { entries: [] as ActivityEntry[], connected: false, connecting: enabled, clockOffsetMs: 0 };
}
