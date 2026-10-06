import { readAppStorage, writeAppStorage } from './storage';
import { useCallback, useEffect, useRef, useState } from 'react';
import type { NavigationActions } from './NavigationControls';
import type { CommunityPlace } from './Community';

export type AppRoute = { screen: 'home' } | { screen: 'space'; spaceId: string } | { screen: 'community'; spaceId: string; place: CommunityPlace };
export type Navigate = (route: AppRoute, options?: { replace?: boolean }) => void;
type Entry = { key: string; href: string };
type Trail = { id: string; entries: Entry[]; index: number };
const storageKey = 'little-worlds:navigation:v1';
const stateKey = 'littleWorldsNavigation';
// Entries already in the browser's back/forward stack retain their old state.
function historyEntry(state: Record<string, unknown> | null) {
  return (state?.[stateKey] ?? state?.livingSpacesNavigation) as { id: string; key: string; index: number } | undefined;
}

function readRoute(): AppRoute {
  const params = new URLSearchParams(window.location.search);
  const spaceId = params.get('space') || (params.has('visitor') ? 'mira' : '');
  if (!spaceId) return { screen: 'home' };
  if (params.get('view') === 'community') {
    const place = params.get('place');
    return { screen: 'community', spaceId, place: place === 'noor' || place === 'jules' || place === 'sol' ? place : 'map' };
  }
  return { screen: 'space', spaceId };
}
function routeHref(route: AppRoute) {
  if (route.screen === 'home') return '/';
  const params = new URLSearchParams({ space: route.spaceId });
  if (route.screen !== 'space') params.set('view', route.screen);
  if (route.screen === 'community' && route.place !== 'map') params.set('place', route.place);
  return `/?${params}`;
}
function save(trail: Trail) {
  try { writeAppStorage(sessionStorage, storageKey, JSON.stringify({ id: trail.id, entries: trail.entries })); } catch { /* History still works in this page. */ }
}
function entryState(trail: Trail) {
  return { [stateKey]: { id: trail.id, key: trail.entries[trail.index].key, index: trail.index } };
}
function startTrail(): Trail {
  const href = routeHref(readRoute());
  try {
    const saved = JSON.parse(readAppStorage(sessionStorage, storageKey) || 'null');
    const current = historyEntry(window.history.state);
    if (saved && current && saved.id === current.id && Number.isInteger(current.index) && Array.isArray(saved.entries)
      && saved.entries.every((entry: Entry) => typeof entry.key === 'string' && typeof entry.href === 'string' && (entry.href === '/' || entry.href.startsWith('/?')))
      && saved.entries[current.index]?.key === current.key && saved.entries[current.index]?.href === href) {
      const restored = { ...saved, index: current.index };
      window.history.replaceState(entryState(restored), '', href);
      save(restored);
      return restored;
    }
  } catch { /* An older tab or invalidated history starts a new local trail. */ }
  const trail: Trail = { id: crypto.randomUUID(), entries: [{ key: crypto.randomUUID(), href: '/' }], index: 0 };
  // A direct space link still has a useful way home, without navigating out of the app.
  window.history.replaceState(entryState(trail), '', '/');
  if (href !== '/') {
    trail.entries.push({ key: crypto.randomUUID(), href }); trail.index = 1;
    window.history.pushState(entryState(trail), '', href);
  }
  save(trail);
  return trail;
}

export function useAppNavigation(): { route: AppRoute; navigation: NavigationActions; navigate: Navigate } {
  const [trail, setTrail] = useState(startTrail);
  const [route, setRoute] = useState(readRoute);
  const current = useRef(trail);
  const commit = useCallback((next: Trail) => {
    current.current = next; setTrail(next); setRoute(readRoute()); save(next);
  }, []);
  useEffect(() => {
    const pop = (event: PopStateEvent) => {
      const state = historyEntry(event.state);
      const previous = current.current;
      if (state?.id === previous.id && previous.entries[state.index]?.key === state.key) commit({ ...previous, index: state.index });
      else commit(startTrail());
    };
    window.addEventListener('popstate', pop);
    return () => window.removeEventListener('popstate', pop);
  }, [commit]);
  const navigate = useCallback<Navigate>((nextRoute, options) => {
    const href = routeHref(nextRoute);
    const previous = current.current;
    if (previous.entries[previous.index].href === href) return;
    // Explicit navigation opens at the event header. Leave browser back/forward
    // alone so the browser can restore the reader's previous scroll position.
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
    if (options?.replace) {
      const next = { ...previous, entries: previous.entries.map((entry, index) => index === previous.index ? { key: crypto.randomUUID(), href } : entry) };
      window.history.replaceState(entryState(next), '', href);
      commit(next);
      return;
    }
    const next: Trail = { id: previous.id, index: previous.index + 1, entries: [...previous.entries.slice(0, previous.index + 1), { key: crypto.randomUUID(), href }] };
    window.history.pushState(entryState(next), '', href);
    commit(next);
  }, [commit]);
  const goHome = useCallback(() => navigate({ screen: 'home' }), [navigate]);
  return { route, navigate, navigation: { goHome } };
}
