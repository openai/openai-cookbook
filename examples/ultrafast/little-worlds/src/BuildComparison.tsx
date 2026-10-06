import { useId, useLayoutEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import type { ReactNode } from 'react';
import { ChevronLeft, ChevronRight, LoaderCircle } from 'lucide-react';
import { gsap } from 'gsap';
import { BEFORE_THEME_CHANGE, finishThemeTransition } from './theme-transition';
import { fitComparisonPreviews } from './comparison-preview';
import './build-comparison.css';


export type ComparisonLaneStats = {
  model?: string;
  status: 'waiting' | 'running' | 'completed' | 'failed' | 'cancelled';
  stage?: string;
  elapsedMs?: number;
};

type Props = {
  active: boolean;
  children: ReactNode;
  ultrafastActivity: ReactNode;
  standardActivity: ReactNode;
  standardPreview?: ReactNode;
  ultrafast: ComparisonLaneStats;
  standard: ComparisonLaneStats;
  /** True only once the current primary turn's published world is displayed. */
  primaryInteractive?: boolean;
  onTransitionChange?: (transitioning: boolean) => void;
  onLayoutChange?: (split: boolean) => void;
};

function elapsed(milliseconds: number | undefined) {
  if (milliseconds === undefined || !Number.isFinite(milliseconds) || milliseconds < 0) return '';
  return `${(milliseconds / 1000).toFixed(1)}s`;
}

function LaneHeader({ name, stats }: { name: string; stats: ComparisonLaneStats }) {
  const busy = stats.status === 'running' || stats.status === 'waiting';
  const status = stats.status === 'running' ? stats.stage || 'Building'
    : stats.status === 'completed' ? 'Complete' : stats.status === 'failed' ? 'Failed'
    : stats.status === 'cancelled' ? 'Stopped' : 'Starting';
  return <header className="build-comparison-heading">
    <div className="build-comparison-identity"><h2>{name}</h2>{stats.model && <span>{stats.model}</span>}</div>
    <div className={`build-comparison-status is-${stats.status}`}><span className="build-comparison-status-label">{busy && <LoaderCircle className="build-comparison-spinner" size={12} strokeWidth={1.7} aria-hidden="true"/>}<span>{status}</span></span>{elapsed(stats.elapsedMs) && <time>{elapsed(stats.elapsedMs)}</time>}</div>
  </header>;
}

function ActivityToggle({ name, open, panelId, busy, side = 'right', onToggle }: { name: string; open: boolean; panelId: string; busy: boolean; side?: 'left' | 'right'; onToggle: () => void }) {
  return <button type="button" className={`comparison-activity-toggle${busy ? ' is-active' : ''}`} aria-label={`${open ? 'Hide' : 'Show'} ${name} activity`} aria-expanded={open} aria-controls={panelId} onClick={onToggle}>
    {open === (side === 'right') ? <ChevronRight size={14}/> : <ChevronLeft size={14}/>}<span>Activity</span>
  </button>;
}

type ViewTransitionHandle = { finished: Promise<void>; ready: Promise<void>; skipTransition: () => void };
type TransitionDocument = Document & { startViewTransition?: (update: () => Promise<void> | void) => ViewTransitionHandle };

/** Commit responsive layout once; animate browser snapshots, never iframe reflows. */
export default function BuildComparison({ active, children, ultrafastActivity, standardActivity, standardPreview, ultrafast, standard, primaryInteractive = false, onTransitionChange, onLayoutChange }: Props) {
  const root = useRef<HTMLDivElement>(null);
  const grid = useRef<HTMLDivElement>(null);
  const primary = useRef<HTMLElement>(null);
  const secondary = useRef<HTMLElement>(null);
  const [split, setSplit] = useState(active);
  const [activityOpen, setActivityOpen] = useState({ ultrafast: true, standard: true });
  const panelId = useId();
  const lastTarget = useRef(active);
  const callbacks = useRef({ onTransitionChange, onLayoutChange });
  callbacks.current = { onTransitionChange, onLayoutChange };
  const generation = useRef(0);
  const nativeTransition = useRef<ViewTransitionHandle | null>(null);
  const finishNativeTransition = useRef<(() => void) | null>(null);
  const fallback = useRef<gsap.core.Tween | null>(null);
  const alive = useRef(true);

  const clearFallbackStyles = () => {
    const element = grid.current;
    if (element && (fallback.current || element.style.opacity || element.style.transform)) {
      gsap.set(element, { clearProps: 'opacity,transform' });
    }
  };
  const settle = () => {
    if (finishNativeTransition.current) finishNativeTransition.current();
    else nativeTransition.current?.skipTransition();
    fallback.current?.progress(1);
  };
  useLayoutEffect(() => {
    if (!split || !root.current) return;
    return fitComparisonPreviews(root.current);
  }, [split]);

  useLayoutEffect(() => {
    alive.current = true;
    callbacks.current.onLayoutChange?.(lastTarget.current);
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const preference = () => { if (query.matches) settle(); };
    window.addEventListener('resize', settle);
    document.addEventListener(BEFORE_THEME_CHANGE, settle);
    query.addEventListener('change', preference);
    return () => {
      alive.current = false;
      generation.current++;
      nativeTransition.current?.skipTransition();
      finishNativeTransition.current = null;
      fallback.current?.kill();
      document.documentElement.removeAttribute('data-world-transition');
      window.removeEventListener('resize', settle);
      document.removeEventListener(BEFORE_THEME_CHANGE, settle);
      query.removeEventListener('change', preference);
    };
  }, []);

  useLayoutEffect(() => {
    if (lastTarget.current === active) return;
    lastTarget.current = active;
    const version = ++generation.current;
    nativeTransition.current?.skipTransition();
    fallback.current?.kill();
    clearFallbackStyles();
    // Start outside React's commit so the snapshot callback can commit both the
    // world layout and its surrounding toolbar/composer in a single flush.
    queueMicrotask(() => {
      if (!alive.current || version !== generation.current) return;
      finishThemeTransition();
      let finished = false;
      const finish = () => {
        if (finished || !alive.current || version !== generation.current) return;
        finished = true;
        nativeTransition.current = null;
        finishNativeTransition.current = null;
        fallback.current = null;
        clearFallbackStyles();
        root.current?.removeAttribute('data-morphing');
        document.documentElement.removeAttribute('data-world-transition');
        callbacks.current.onTransitionChange?.(false);
      };
      let committed = false;
      const update = () => {
        if (committed || !alive.current || version !== generation.current) return;
        committed = true;
        flushSync(() => {
          if (active) setActivityOpen({ ultrafast: true, standard: true });
          setSplit(active);
          callbacks.current.onLayoutChange?.(active);
        });
        // Enter at the top of the finished world. One instant scroll, inside
        // the captured layout update, cannot race a separate smooth scroll.
        window.scrollTo({ top: 0, left: 0, behavior: 'instant' });
      };
      callbacks.current.onTransitionChange?.(true);
      const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      root.current?.setAttribute('data-morphing', active ? 'opening' : 'closing');
      if (reduced || root.current?.closest('[inert]')) { update(); finish(); return; }
      const doc = document as TransitionDocument;
      // Stacked mobile worlds can be very tall. Avoid capturing those surfaces
      // when there is no horizontal expansion for the snapshot to convey.
      const stacked = window.matchMedia('(max-width: 700px)').matches;
      if (doc.startViewTransition && !stacked) {
        document.documentElement.setAttribute('data-world-transition', active ? 'opening' : 'closing');
        try {
          const transition = doc.startViewTransition(update);
          nativeTransition.current = transition;
          finishNativeTransition.current = () => {
            update();
            transition.skipTransition();
            finish();
          };
          void transition.ready.catch(() => {});
          void transition.finished.then(finish, finish);
          return;
        } catch {
          // A browser that exposes the API can still reject starting a capture.
          // Keep the requested layout usable through the ordinary fade fallback.
          nativeTransition.current = null;
          document.documentElement.removeAttribute('data-world-transition');
        }
      }
      update();
      fallback.current = gsap.fromTo(grid.current, { opacity: .65, y: 6 }, {
        opacity: 1, y: 0, duration: .28, ease: 'power3.out', clearProps: 'opacity,transform', onComplete: finish,
      });
    });
  }, [active]);

  const toggleActivity = (lane: 'ultrafast' | 'standard') => {
    setActivityOpen(current => ({ ...current, [lane]: !current[lane] }));
  };

  return <div ref={root} className="build-comparison" data-comparing={split ? 'true' : 'false'}>
    <div className="build-comparison-size-reference" aria-hidden="true"/>
    <div ref={grid} className="build-comparison-grid">
      <section ref={primary} className="build-comparison-lane build-comparison-ultrafast" data-activity-open={activityOpen.ultrafast} aria-label={split ? 'Ultrafast build' : undefined}>
        <div className="build-comparison-lane-layout">
          <div className="build-comparison-chrome" aria-hidden={!split}><LaneHeader name="Ultrafast" stats={ultrafast}/></div>
          <div className="build-comparison-preview build-comparison-primary" tabIndex={split ? 0 : undefined} aria-label={split ? 'Ultrafast world preview' : undefined}><div className="build-comparison-world-size"><div className="build-comparison-world" inert={split && !(primaryInteractive && ultrafast.status === 'completed')}>{children}</div></div></div>
          <div id={`${panelId}-ultrafast`} className="build-comparison-activity" inert={!active || !activityOpen.ultrafast} aria-hidden={!active || !activityOpen.ultrafast}>{ultrafastActivity}</div>
          {split && <ActivityToggle name="Ultrafast" open={activityOpen.ultrafast} panelId={`${panelId}-ultrafast`} busy={ultrafast.status === 'running'} onToggle={() => toggleActivity('ultrafast')}/>}
        </div>
      </section>
      <section ref={secondary} className="build-comparison-lane build-comparison-standard" data-activity-open={activityOpen.standard} aria-label="Standard build" inert={!active} aria-hidden={!active}>
        <div className="build-comparison-lane-layout">
          <div className="build-comparison-chrome"><LaneHeader name="Standard" stats={standard}/></div>
          <div className="build-comparison-preview" tabIndex={split ? 0 : undefined} aria-label="Standard world preview"><div className="build-comparison-world-size"><div className="build-comparison-world" inert>{standardPreview || <div className="build-comparison-preview-empty"><span>Preview appears as the build takes shape</span></div>}</div></div></div>
          <div id={`${panelId}-standard`} className="build-comparison-activity" inert={!active || !activityOpen.standard} aria-hidden={!active || !activityOpen.standard}>{standardActivity}</div>
          {split && <ActivityToggle name="Standard" side="left" open={activityOpen.standard} panelId={`${panelId}-standard`} busy={standard.status === 'running'} onToggle={() => toggleActivity('standard')}/>}
        </div>
      </section>
    </div>
  </div>;
}
