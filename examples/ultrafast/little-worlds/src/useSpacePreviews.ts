import { useEffect, useMemo, useRef, useState } from 'react';
import { authedFetch } from './api';
import type { SpaceAppearance, SpaceSummary } from './types';

type Preview = { spaceId: string; version: string; html: string; hasBuilt: boolean; appearance?: SpaceAppearance };

/** Published previews share one bounded request queue and never outlive their viewer. */
export function useSpacePreviews(spaces: SpaceSummary[], viewerId: string, onExpired?: () => void) {
  const cache = useMemo(() => new Map<string, Preview>(), [viewerId]);
  const [snapshot, setSnapshot] = useState({ cache, previews: {} as Record<string, Preview> });
  const expired = useRef(onExpired);
  expired.current = onExpired;

  useEffect(() => {
    const controller = new AbortController();
    const present = new Set(spaces.filter(space => space.hasBuilt).map(space => space.id));
    for (const id of cache.keys()) if (!present.has(id)) cache.delete(id);
    setSnapshot({ cache, previews: Object.fromEntries(cache) });
    const queue = spaces.filter(space => space.hasBuilt && space.previewVersion
      && cache.get(space.id)?.version !== space.previewVersion);
    let next = 0;
    async function worker() {
      while (!controller.signal.aborted && next < queue.length) {
        const space = queue[next++];
        try {
          const response = await authedFetch(`/api/spaces/${encodeURIComponent(space.id)}/preview`, { signal: controller.signal });
          if (controller.signal.aborted) return;
          if (response.status === 401) { controller.abort(); expired.current?.(); return; }
          if (!response.ok) continue;
          const preview: Preview = await response.json();
          if (controller.signal.aborted) return;
          // A publication during the request is picked up by the next directory refresh.
          if (preview.spaceId !== space.id || preview.version !== space.previewVersion
            || typeof preview.html !== 'string' || typeof preview.hasBuilt !== 'boolean') continue;
          cache.set(space.id, preview);
          setSnapshot({ cache, previews: Object.fromEntries(cache) });
        } catch { /* Keep the last preview and retry on the next community refresh. */ }
      }
    }
    for (let index = 0; index < Math.min(3, queue.length); index++) void worker();
    return () => controller.abort();
  }, [spaces, cache]);

  return snapshot.cache === cache ? snapshot.previews : {};
}
