type ThemeViewTransition = {
  ready: Promise<void>;
  finished: Promise<void>;
  skipTransition(): void;
};
type ThemeDocument = Document & {
  startViewTransition?: (update: () => void) => ThemeViewTransition;
};
type ThemeChange = {
  commit(): void;
  clean(): void;
  transition?: ThemeViewTransition;
};

const changes = new WeakMap<Document, ThemeChange>();
export const BEFORE_THEME_CHANGE = 'little-worlds:before-theme-change';

/** A layout transition takes priority without losing a pending theme choice. */
export function finishThemeTransition(target: Document = document) {
  const change = changes.get(target);
  if (!change) return;
  change.commit();
  change.transition?.skipTransition();
  change.clean();
}

/** Capture one palette change, rather than independently fading every element. */
export function runThemeTransition(update: () => void, target: Document = document) {
  finishThemeTransition(target);
  // Finish any existing layout snapshots before capturing a different palette.
  // Otherwise their independently timed layers could retain the old colors.
  target.dispatchEvent?.(new Event(BEFORE_THEME_CHANGE));
  const root = target.documentElement;
  const view = target.defaultView;
  let committed = false;
  const flushStyles = () => { void view?.getComputedStyle(root).backgroundColor; };
  const change: ThemeChange = {
    commit() {
      if (committed || changes.get(target) !== change) return;
      committed = true;
      // Legacy hover transitions have different durations and some surfaces
      // (gradients, canvas, native controls) cannot interpolate their palette.
      // Resolve all of them before the browser captures the new root image.
      root.setAttribute('data-theme-commit', '');
      try {
        flushStyles();
        update();
        flushStyles();
      } finally {
        root.removeAttribute('data-theme-commit');
      }
    },
    clean() {
      if (changes.get(target) !== change) return;
      root.removeAttribute('data-theme-transition');
      changes.delete(target);
    },
  };
  changes.set(target, change);
  const doc = target as ThemeDocument;
  const reduced = view?.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const morphing = root.hasAttribute('data-world-transition') || target.querySelector('.build-comparison[data-morphing]');
  if (!doc.startViewTransition || reduced || target.visibilityState === 'hidden' || morphing) {
    try { change.commit(); } finally { change.clean(); }
    return;
  }
  root.setAttribute('data-theme-transition', '');
  try {
    change.transition = doc.startViewTransition(change.commit);
    // A rejected capture still runs the update. The commit guard also covers
    // engines that fail before calling it, and an interrupted rapid toggle.
    void change.transition.ready.catch(() => {});
    void change.transition.finished.then(
      () => { change.commit(); change.clean(); },
      () => { change.commit(); change.clean(); },
    );
  } catch {
    try { change.commit(); } finally { change.clean(); }
  }
}
