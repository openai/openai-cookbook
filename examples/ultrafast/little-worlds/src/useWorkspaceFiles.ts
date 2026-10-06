import { useEffect, useMemo, useRef, useState } from 'react';
import { watchEvents } from './api';
import { mergeWorkspaceFilesEvents, type WorkspaceFilesSnapshot } from './workspace-files';

type FileScope = { path: string };
type FileView = { scope: FileScope; snapshot: WorkspaceFilesSnapshot | null; connected: boolean; connecting: boolean };

/** Each mounted inspector owns one credential-bound subscription. */
export function useWorkspaceFiles(path: string, onExpired: () => void) {
  const scope = useMemo(() => ({ path }), [path]);
  const current = useRef(scope);
  current.current = scope;
  const expired = useRef(onExpired);
  expired.current = onExpired;
  const [view, setView] = useState<FileView>(() => ({ scope, snapshot: null, connected: false, connecting: true }));

  useEffect(() => {
    const fresh = (): FileView => ({ scope, snapshot: null, connected: false, connecting: true });
    setView(previous => previous.scope === scope ? { ...previous, connected: false, connecting: true } : fresh());
    let active = true;
    const sameScope = () => current.current === scope;
    const canReceive = () => active && sameScope();
    let stop = () => {};
    stop = watchEvents(path, events => {
      if (!canReceive()) return;
      setView(previous => {
        if (!canReceive()) return previous;
        const next = previous.scope === scope ? previous : fresh();
        const snapshot = mergeWorkspaceFilesEvents(next.snapshot, events);
        return snapshot === next.snapshot ? next : { ...next, snapshot };
      });
    }, connected => {
      if (!canReceive()) return;
      setView(previous => {
        if (!canReceive()) return previous;
        return { ...(previous.scope === scope ? previous : fresh()), connected, connecting: !connected };
      });
    }, () => {
      if (!canReceive()) return;
      active = false;
      stop();
      setView(previous => sameScope()
        ? { ...(previous.scope === scope ? previous : fresh()), snapshot: null, connected: false, connecting: false }
        : previous);
      expired.current();
    });
    return () => { active = false; stop(); };
  }, [path, scope]);

  // Navigation renders before effects clean up. Never expose another scope's
  // files during that render, even if it returns to a previously opened URL.
  return view.scope === scope
    ? { snapshot: view.snapshot, connected: view.connected, connecting: view.connecting }
    : { snapshot: null, connected: false, connecting: true };
}
