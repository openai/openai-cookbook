import type { RuntimeEvent, Snapshot } from './types';

export const canvasEvent = (event: RuntimeEvent) => /^(turn\.|draft\.preview|revision\.published|space\.updated|icon\.updated|session\.)/.test(event.type);
export const snapshotEventId = (snapshot: Pick<Snapshot, 'events'>) => Math.max(0, ...snapshot.events.map(event => Number(event.id) || 0));
export const mergeCanvasEvents = (before: RuntimeEvent[], incoming: RuntimeEvent[]) => Array.from(new Map([...before, ...incoming.filter(canvasEvent)].map(event => [event.id, event])).values()).sort((a, b) => Number(a.id) - Number(b.id)).slice(-250);

// At most one render request is in flight. A late event schedules one trailing
// request only if the response did not already include that event's commit.
export function createSnapshotRefresher<T extends Pick<Snapshot, 'events'>>(
  load: () => Promise<T>, apply: (snapshot: T) => void, onError: (error: unknown) => void,
) {
  let active = true;
  let forced = 0;
  let completed = 0;
  let wantedEvent = 0;
  let completedEvent = 0;
  let pending: Promise<void> | undefined;
  const request = (afterEventId?: number) => {
    if (!active) return Promise.resolve();
    if (afterEventId === undefined) forced++;
    else wantedEvent = Math.max(wantedEvent, afterEventId);
    if (!pending && (forced > completed || wantedEvent > completedEvent)) {
      pending = Promise.resolve().then(async () => {
        try {
          while (active && (forced > completed || wantedEvent > completedEvent)) {
            const requestVersion = forced;
            const eventVersion = wantedEvent;
            try {
              const snapshot = await load();
              if (!active) return;
              completedEvent = Math.max(eventVersion, snapshotEventId(snapshot));
              apply(snapshot);
            } catch (error) {
              if (!active) return;
              // A failed request must not retry forever. A later invalidation,
              // reconnection, or explicit Retry starts a fresh attempt.
              completedEvent = eventVersion;
              onError(error);
            }
            completed = requestVersion;
          }
        } finally { pending = undefined; }
      });
    }
    return pending || Promise.resolve();
  };
  return { request, dispose: () => { active = false; } };
}

// A publication event is a commit notification, not the rendered replacement.
// Keep the inert preview until its actual published snapshot reaches the UI.
export function selectCanvasUpdate(snapshot: Snapshot | null, events: RuntimeEvent[], acceptedTurnId: string | null = null) {
  const recent = [...events].reverse();
  const cursor = snapshot ? snapshotEventId(snapshot) : 0;
  const reset = recent.find(event => event.type === 'space.updated' && event.data?.reset === true);
  const currentEvents = reset ? recent.filter(event => Number(event.id) > Number(reset.id)) : recent;
  const resetPending = !!reset && Number(reset.id) > cursor;
  const savedTurn = resetPending ? undefined : snapshot?.session.turns?.at(-1);
  const start = currentEvents.find(event => event.type === 'turn.started');
  const turnId = start && (!savedTurn || Number(start.id) > cursor) ? start.turnId : savedTurn?.id || start?.turnId;
  const terminal = currentEvents.find(event => /^turn\.(completed|cancelled|failed)$/.test(event.type)
    && (event.turnId === turnId || !event.turnId && Number(event.id) > Number(start?.id || 0)));
  const acceptedPending = !!acceptedTurnId && !snapshot?.session.turns?.some(turn => turn.id === acceptedTurnId)
    && !events.some(event => event.turnId === acceptedTurnId);
  const currentRunning = !terminal && (!!start && Number(start.id) > cursor
    || !!snapshot && ['running', 'in_progress', 'working'].includes(snapshot.session.status));
  const publicationFor = (id?: string) => id ? currentEvents.find(event => event.type === 'revision.published' && event.turnId === id && typeof event.data?.revisionId === 'number')
    || currentEvents.find(event => event.type === 'turn.completed' && event.turnId === id && typeof event.data?.revisionId === 'number') : undefined;
  const previews = currentEvents.filter(event => event.type === 'draft.preview' && typeof event.data?.html === 'string');
  const activeDraft = currentRunning && !publicationFor(turnId) ? previews.find(event => event.turnId === turnId) : undefined;
  // A next turn can start before the preceding commit's HTML arrives. Retain
  // that committed preview until the next draft or published snapshot is ready.
  const pendingPublishedDraft = previews.find(event => {
    const published = publicationFor(event.turnId);
    return !!published && (!snapshot || cursor < Number(published.id) || snapshot.revision.id < (published.data!.revisionId as number));
  });
  return { running: !resetPending && (acceptedPending || currentRunning), draft: !resetPending ? activeDraft || pendingPublishedDraft : undefined };
}
