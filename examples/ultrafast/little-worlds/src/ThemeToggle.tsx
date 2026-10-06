import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { Moon, Sun } from 'lucide-react';
import { runThemeTransition } from './theme-transition';

export type Theme = 'light' | 'dark';
export const THEME_STORAGE_KEY = 'little-worlds-theme';
let pendingTheme: { value: Theme } | undefined;

export function readSavedTheme(storage?: Pick<Storage, 'getItem'> | null): Theme {
  try {
    const source = storage === undefined ? window.localStorage : storage;
    return source?.getItem(THEME_STORAGE_KEY) === 'light' ? 'light' : 'dark';
  } catch {
    // A route can remount these controls while private-browser storage is
    // blocked. The document retains the appearance chosen in this session.
    if (storage === undefined && typeof document !== 'undefined') {
      return document.documentElement.dataset.theme === 'light' ? 'light' : 'dark';
    }
    return 'dark';
  }
}

/** Capture the current choice even while the native palette fade is pending. */
export function readAppTheme(): Theme {
  if (pendingTheme) return pendingTheme.value;
  const current = typeof document === 'undefined' ? undefined : document.documentElement.dataset.theme;
  return current === 'light' || current === 'dark' ? current : readSavedTheme();
}

export function applyTheme(theme: Theme, target: Document = document) {
  target.documentElement.dataset.theme = theme;
  target.documentElement.style.colorScheme = theme;
  target.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'light' ? '#f7f8fa' : '#000000');
}

/** Curated worlds follow the host palette; custom worlds keep authored colors. */
export default function ThemeToggle() {
  const [theme, setTheme] = useState<Theme>(() => pendingTheme?.value ?? readSavedTheme());
  const requestedTheme = useRef(theme);
  const changeTheme = useCallback((next: Theme, persist = true) => {
    requestedTheme.current = next;
    // Publish user intent once. Re-publishing a delayed capture or storage event
    // can send stale choices back and forth between open app tabs.
    if (persist) {
      try { window.localStorage.setItem(THEME_STORAGE_KEY, next); } catch { /* Optional storage. */ }
    }
    const request = { value: next };
    pendingTheme = request;
    runThemeTransition(() => {
      // The icon joins the same palette commit even if navigation remounts
      // this control while the browser is preparing its snapshot.
      applyTheme(next);
      flushSync(() => setTheme(next));
      if (pendingTheme === request) pendingTheme = undefined;
    });
  }, []);

  useLayoutEffect(() => {
    applyTheme(theme);
  }, [theme]);

  useEffect(() => {
    function syncTheme(event: StorageEvent) {
      if (event.key === THEME_STORAGE_KEY || event.key === null) changeTheme(readSavedTheme(), false);
    }
    window.addEventListener('storage', syncTheme);
    return () => window.removeEventListener('storage', syncTheme);
  }, [changeTheme]);

  const label = `Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`;
  const Icon = theme === 'dark' ? Sun : Moon;
  return <button type="button" className="theme-toggle" data-theme={theme} aria-label={label} title={label}
    onClick={() => changeTheme(requestedTheme.current === 'dark' ? 'light' : 'dark')}>
    <Icon size={17} strokeWidth={1.6} aria-hidden="true" />
  </button>;
}
