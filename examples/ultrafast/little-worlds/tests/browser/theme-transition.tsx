// Real React, app styles, and native browser transitions. No app data or services.
import { useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import ThemeToggle, { THEME_STORAGE_KEY, type Theme } from '../../src/ThemeToggle';
import { finishThemeTransition } from '../../src/theme-transition';
import '../../src/styles.css';
import '../../src/account.css';
import '../../src/community.css';
import '../../src/theme.css';
import '../../src/presentation.css';

const pause = (ms: number) => new Promise<void>(resolve => setTimeout(resolve, ms));
const opposite = (theme: Theme): Theme => theme === 'dark' ? 'light' : 'dark';
const palette = {
  dark: {
    paper: 'rgb(0, 0, 0)', ink: 'rgb(245, 245, 245)', surface: 'rgb(17, 17, 17)',
    composerBorder: 'rgb(69, 69, 69)', account: 'rgb(16, 16, 16)',
    accountBorder: 'rgb(72, 72, 72)', edge: 'rgb(160, 160, 160)', toggle: 'rgb(87, 220, 140)',
  },
  light: {
    paper: 'rgb(247, 248, 250)', ink: 'rgb(32, 38, 48)', surface: 'rgb(255, 255, 255)',
    composerBorder: 'rgb(220, 224, 230)', account: 'rgb(255, 255, 255)',
    accountBorder: 'rgb(220, 224, 230)', edge: 'rgb(98, 106, 118)', toggle: 'rgb(113, 64, 184)',
  },
} satisfies Record<Theme, Record<string, string>>;

function activeAnimations() {
  return document.getAnimations().filter(animation => animation.playState !== 'finished' && animation.playState !== 'idle');
}

function colorTransitions() {
  return activeAnimations().filter((animation): animation is CSSTransition =>
    animation instanceof CSSTransition && /(?:color|^fill$|^stroke$|shadow)/.test(animation.transitionProperty));
}

function Fixture() {
  const samples = useRef<HTMLDivElement>(null);
  const running = useRef(false);
  const [checking, setChecking] = useState(false);
  const [result, setResult] = useState('Ready. Checks run in this page and restore the starting theme.');
  const [failures, setFailures] = useState<string[]>([]);
  const [status, setStatus] = useState('ready');
  const [toggleKey, setToggleKey] = useState(0);

  async function check() {
    if (running.current) return;
    running.current = true;
    setChecking(true);
    setFailures([]);
    setStatus('running');
    setResult('Running theme transition checks…');
    const root = document.documentElement;
    const originalTheme: Theme = root.dataset.theme === 'light' ? 'light' : 'dark';
    let savedTheme: string | null = null;
    let storageAvailable = false;
    try { savedTheme = localStorage.getItem(THEME_STORAGE_KEY); storageAvailable = true; } catch { /* Storage is optional. */ }
    const started = performance.now();
    const deadline = started + 4500;
    const errors: string[] = [];
    const captures: { id: number; theme: string; update: string; ready: string; finished: string }[] = [];
    const nativeStart = document.startViewTransition;
    const nativeStartDescriptor = Object.getOwnPropertyDescriptor(document, 'startViewTransition');
    let observingNative = false;
    let checks = 0;
    const assert = (ok: boolean, message: string) => { checks++; if (!ok) errors.push(message); };
    const element = <T extends Element = HTMLElement,>(selector: string): T => {
      const match = samples.current?.querySelector<T>(selector);
      if (!match) throw new Error(`Missing fixture element: ${selector}`);
      return match;
    };
    let toggle = element<HTMLButtonElement>('.theme-toggle');
    const motion = element<HTMLElement>('[data-probe="motion"]');
    const describeState = () => {
      const animations = activeAnimations().map(animation => {
        const name = animation instanceof CSSAnimation ? animation.animationName
          : animation instanceof CSSTransition ? animation.transitionProperty : animation.constructor.name;
        const effect = animation.effect;
        return `${name} (${animation.playState}, ${effect instanceof KeyframeEffect ? effect.pseudoElement ?? 'element' : 'no effect'})`;
      });
      const trace = captures.slice(-3).map(capture =>
        `#${capture.id} from ${capture.theme}: update=${capture.update}; ready=${capture.ready}; finished=${capture.finished}`).join(' | ');
      return `root=${root.dataset.theme}, toggle=${toggle.dataset.theme}, label=${toggle.getAttribute('aria-label')}, `
        + `transition=${root.hasAttribute('data-theme-transition')}, commit=${root.hasAttribute('data-theme-commit')}, `
        + `visibility=${document.visibilityState}, animations=[${animations.join(', ')}], captures=[${trace}]`;
    };
    const waitFor = async (predicate: () => boolean, message: string, timeout = 850) => {
      const expires = Math.min(deadline, performance.now() + timeout);
      while (!predicate()) {
        if (performance.now() >= expires) throw new Error(`${message}. ${describeState()}`);
        await pause(10);
      }
    };
    const expectStyle = (selector: string, property: string, expected: string, phase: string) => {
      const actual = getComputedStyle(element(selector)).getPropertyValue(property);
      assert(actual === expected, `${phase}: ${selector} ${property} was ${actual}, expected ${expected}`);
    };
    const inspectPalette = (theme: Theme, phase: string) => {
      const expected = palette[theme];
      assert(root.dataset.theme === theme && toggle.dataset.theme === theme, `${phase}: document and toggle agree on ${theme}`);
      assert(toggle.getAttribute('aria-label') === `Switch to ${opposite(theme)} mode`, `${phase}: toggle describes the next theme`);
      assert(getComputedStyle(document.body).backgroundColor === expected.paper, `${phase}: page background uses the final palette`);
      expectStyle('.theme-toggle', 'color', expected.toggle, phase);
      expectStyle('.composer', 'background-color', expected.surface, phase);
      expectStyle('.composer', 'border-top-color', expected.composerBorder, phase);
      expectStyle('.composer textarea', 'color', expected.ink, phase);
      expectStyle('.account-name-row', 'background-color', expected.account, phase);
      expectStyle('.account-name-row', 'border-top-color', expected.accountBorder, phase);
      expectStyle('.account-name-row input', 'color', expected.ink, phase);
      expectStyle('.constellation-edge > path', 'stroke', expected.edge, phase);
      for (const selector of ['[data-probe="fast"]', '[data-probe="slow"]']) {
        expectStyle(selector, 'background-color', expected.paper, phase);
        expectStyle(selector, 'color', expected.ink, phase);
        expectStyle(selector, 'border-top-color', expected.ink, phase);
      }
      expectStyle('[data-probe="inherited"]', 'color', expected.ink, phase);
      expectStyle('[data-probe="svg-fill"]', 'fill', expected.ink, phase);
      const gradient = getComputedStyle(element('[data-probe="gradient"]')).backgroundImage;
      assert(gradient.includes(expected.paper) && gradient.includes(expected.ink), `${phase}: gradient uses both final palette colors`);
      const lagging = colorTransitions();
      assert(lagging.length === 0, `${phase}: no independent color transitions (${lagging.map(animation => animation.transitionProperty).join(', ')})`);
    };
    const inspectFade = async (theme: Theme, phase: string) => {
      await waitFor(() => root.dataset.theme === theme && activeAnimations().some(animation =>
        animation instanceof CSSAnimation && animation.animationName === 'theme-palette-in'), `${phase}: no native palette fade appeared`);
      const animations = activeAnimations().filter((animation): animation is CSSAnimation => animation instanceof CSSAnimation);
      assert(animations.length === 1 && animations[0]?.animationName === 'theme-palette-in', `${phase}: exactly one CSS animation drives the whole page`);
      assert(animations[0]?.effect?.getComputedTiming().duration === 180, `${phase}: shared fade lasts 180 ms`);
      const effect = animations[0]?.effect;
      assert(effect instanceof KeyframeEffect && effect.target === root && effect.pseudoElement === '::view-transition-new(root)', `${phase}: the animation fades the complete new root snapshot`);
      const frames = effect instanceof KeyframeEffect ? effect.getKeyframes() : [];
      assert(String(frames[0]?.opacity) === '0' && String(frames.at(-1)?.opacity) === '1', `${phase}: the new root fades from transparent to opaque`);
      assert(root.hasAttribute('data-theme-transition'), `${phase}: native fade retains its theme marker`);
      assert(!root.hasAttribute('data-theme-commit'), `${phase}: per-element transition suppression ends immediately after commit`);
      assert(getComputedStyle(element('[data-probe="fast"]')).transitionDuration.includes('0.15s'), `${phase}: fast transition rules are restored during the fade`);
      assert(getComputedStyle(element('[data-probe="slow"]')).transitionDuration.includes('0.65s'), `${phase}: slow transition rules are restored during the fade`);
      inspectPalette(theme, `${phase}, during fade`);
      await waitFor(() => !root.hasAttribute('data-theme-transition'), `${phase}: native fade did not clean up`);
      assert(!activeAnimations().some(animation => animation instanceof CSSAnimation && animation.animationName === 'theme-palette-in'), `${phase}: palette animation finishes`);
      inspectPalette(theme, `${phase}, after fade`);
    };

    try {
      if (typeof document.startViewTransition !== 'function') throw new Error('Native View Transitions are required for these checks');
      if (matchMedia('(prefers-reduced-motion: reduce)').matches) throw new Error('These animation checks require the browser’s normal-motion preference');
      if (document.visibilityState !== 'visible') throw new Error('Keep this fixture visible while running the checks');
      // Observe the actual native promises without replacing capture or callbacks.
      document.startViewTransition = function (update) {
        const capture = { id: captures.length + 1, theme: root.dataset.theme ?? 'unset', update: 'pending', ready: 'pending', finished: 'pending' };
        captures.push(capture);
        const transition = nativeStart.call(this, update);
        for (const [key, promise] of [
          ['update', transition.updateCallbackDone], ['ready', transition.ready], ['finished', transition.finished],
        ] as const) {
          void promise.then(
            () => { capture[key] = 'resolved'; },
            reason => { capture[key] = reason instanceof Error ? `${reason.name}: ${reason.message}` : String(reason); },
          );
        }
        return transition;
      };
      observingNative = true;
      await waitFor(() => colorTransitions().length === 0, 'Initial page colors did not settle');

      toggle.click();
      await inspectFade(opposite(originalTheme), `${originalTheme} to ${opposite(originalTheme)}`);
      toggle.click();
      await inspectFade(originalTheme, `${opposite(originalTheme)} to ${originalTheme}`);

      // All three clicks precede the first snapshot callback. The last intent wins.
      toggle.click();
      toggle.click();
      toggle.click();
      await inspectFade(opposite(originalTheme), 'Three rapid clicks');
      if (storageAvailable) assert(localStorage.getItem(THEME_STORAGE_KEY) === opposite(originalTheme), 'Three rapid clicks persist only the latest theme');

      // Replace the real control in the same task, before native capture can commit.
      const previousToggle = toggle;
      toggle.click();
      assert(root.dataset.theme === opposite(originalTheme), 'The remount happens before the pending native palette callback');
      flushSync(() => setToggleKey(key => key + 1));
      toggle = element<HTMLButtonElement>('.theme-toggle');
      assert(toggle !== previousToggle && !previousToggle.isConnected, 'The pending toggle is replaced by a new component instance');
      await inspectFade(originalTheme, 'Remount before palette commit');
      toggle.click();
      await inspectFade(opposite(originalTheme), 'Next click after remount');

      // A new geometry transition must still run after the palette commit.
      void getComputedStyle(motion).transform;
      motion.dataset.shifted = 'true';
      await waitFor(() => motion.getAnimations().some(animation => animation instanceof CSSTransition && animation.transitionProperty === 'transform'), 'Geometry transitions remain available after the theme fade', 200);
      assert(getComputedStyle(element('[data-probe="fast"]')).transitionDuration.includes('0.15s'), 'Fast per-element transition rules are restored');
      assert(getComputedStyle(element('[data-probe="slow"]')).transitionDuration.includes('0.65s'), 'Slow per-element transition rules are restored');
      assert(motion.getAnimations().some(animation => animation instanceof CSSTransition && animation.transitionProperty === 'transform'), 'A subsequent transform transition runs normally');
    } catch (error) {
      errors.push(error instanceof Error ? error.message : String(error));
    } finally {
      if (observingNative) {
        if (nativeStartDescriptor) Object.defineProperty(document, 'startViewTransition', nativeStartDescriptor);
        else Reflect.deleteProperty(document, 'startViewTransition');
      }
      finishThemeTransition();
      if (root.dataset.theme !== originalTheme) {
        toggle.click();
        finishThemeTransition();
      }
      delete motion.dataset.shifted;
      try {
        if (storageAvailable) {
          if (savedTheme === null) localStorage.removeItem(THEME_STORAGE_KEY);
          else localStorage.setItem(THEME_STORAGE_KEY, savedTheme);
        }
      } catch { errors.push('Could not restore the saved theme preference'); }
      assert(root.dataset.theme === originalTheme && toggle.dataset.theme === originalTheme, 'The original theme is restored');
      assert(!root.hasAttribute('data-theme-commit') && !root.hasAttribute('data-theme-transition'), 'No theme transition markers remain');
      setFailures(errors);
      setStatus(errors.length ? 'failed' : 'passed');
      setResult(errors.length ? `Failed: ${errors.length} issue${errors.length === 1 ? '' : 's'} (${checks} assertions)` : `Passed ${checks} checks in ${((performance.now() - started) / 1000).toFixed(2)} s`);
      setChecking(false);
      running.current = false;
    }
  }

  return <main className="theme-fixture">
    <style>{`
      .theme-fixture { max-width: 760px; margin: 0 auto; padding: 32px 24px; }
      .theme-fixture h1 { font-size: 24px; margin: 0 0 12px; }
      .theme-fixture p { line-height: 1.5; margin: 12px 0; }
      .theme-fixture .run-checks { padding: 10px 14px; color: var(--ink); background: var(--surface); border: 1px solid var(--line); border-radius: 6px; }
      .theme-fixture [data-testid="theme-transition-result"] { font-weight: 600; }
      .theme-fixture ol { padding-left: 22px; font-size: 13px; line-height: 1.6; }
      .theme-fixture-samples { display: grid; gap: 16px; margin-top: 24px; }
      .theme-fixture-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
      .theme-fixture-probe { min-height: 68px; padding: 16px; color: var(--ink); background: var(--paper); border: 1px solid var(--ink); border-radius: 6px; }
      .theme-fixture-fast { transition: background-color .15s, color .15s, border-color .15s; }
      .theme-fixture-slow { transition: background-color .65s, color .65s, border-color .65s; }
      .theme-fixture-parent { color: var(--ink); transition: color .15s; }
      .theme-fixture-child { color: inherit; transition: color .65s; }
      .theme-fixture-gradient { height: 32px; border-radius: 6px; background: linear-gradient(90deg, var(--paper), var(--ink)); }
      .theme-fixture-svg { width: 100%; height: 48px; }
      .theme-fixture-svg circle { fill: var(--ink); transition: fill .65s; }
      .theme-fixture-motion { width: 28px; height: 8px; background: var(--ink); transform: translateX(0); transition: transform .65s linear; }
      .theme-fixture-motion[data-shifted] { transform: translateX(40px); }
    `}</style>
    <h1>Theme transition checks</h1>
    <p>Real app controls, a gradient, inherited text, and SVG colors share one 180 ms page fade. Run in a visible tab with normal motion enabled.</p>
    <button className="run-checks" type="button" disabled={checking} onClick={() => void check()}>Run checks</button>
    <p role="status" aria-live="polite" data-testid="theme-transition-result" data-status={status}>{result}</p>
    {failures.length > 0 && <ol>{failures.map((failure, index) => <li key={index}>{failure}</li>)}</ol>}
    <div ref={samples} className="theme-fixture-samples">
      <ThemeToggle key={toggleKey} />
      <div className="composer"><textarea aria-label="Composer example" readOnly value="A composer using the real app styles" /></div>
      <div className="account-name-row"><input aria-label="Account name example" readOnly value="Theme fixture" /><button type="button" aria-label="Account example">→</button></div>
      <div className="theme-fixture-pair">
        <div className="theme-fixture-probe theme-fixture-fast" data-probe="fast">150 ms color rules</div>
        <div className="theme-fixture-probe theme-fixture-slow" data-probe="slow">650 ms color rules</div>
      </div>
      <div className="theme-fixture-parent"><span className="theme-fixture-child" data-probe="inherited">Inherited text with a different transition duration</span></div>
      <div className="theme-fixture-gradient" data-probe="gradient" aria-label="Paper to ink gradient" />
      <svg className="theme-fixture-svg" viewBox="0 0 600 48" aria-label="Community edge and palette fill">
        <g className="constellation-edge"><path d="M 16 24 L 560 24" /></g>
        <circle data-probe="svg-fill" cx="580" cy="24" r="8" />
      </svg>
      <div className="theme-fixture-motion" data-probe="motion" aria-label="Geometry transition example" />
    </div>
  </main>;
}

createRoot(document.getElementById('root')!).render(<Fixture />);
