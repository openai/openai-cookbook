import { useMemo, useRef, useState } from 'react';
import { frameTheme } from '../../src/frame-theme';
import { withSpaceAppearance } from '../../src/space-appearance';
import type { SpaceAppearance } from '../../src/types';
import sharedCss from '../../server/demo-presentation/shared.css?raw';
import creativeCss from '../../server/demo-presentation/creative.css?raw';
import lightCss from '../../server/demo-appearance/karen.css?raw';

export const arcadeAppearance: SpaceAppearance = { lightCss, presentationCss: `${sharedCss}\n${creativeCss}` };

/** A script-free copy lets the test measure authored geometry without relaxing
 * the actual GeneratedFrame's opaque-origin sandbox or touching a real save. */
export function ArcadeLayoutProbe({ html }: { html: string }) {
  const mirror = useRef<HTMLIFrameElement>(null);
  const [report, setReport] = useState<object>({ status: 'idle' });
  const [busy, setBusy] = useState(false);
  const srcDoc = useMemo(() => `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; font-src data:; img-src data:; script-src 'none'; connect-src 'none'"><style>${frameTheme}</style></head><body><div id="living-space-content">${withSpaceAppearance(html, arcadeAppearance)}</div></body></html>`, [html]);

  const run = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const doc = mirror.current?.contentDocument;
      const view = mirror.current?.contentWindow;
      if (!doc || !view) throw new Error('Layout mirror has not loaded.');
      await doc.fonts.ready;
      const failures: string[] = [];
      let checks = 0;
      const check = (condition: boolean, label: string) => { checks += 1; if (!condition) failures.push(label); };
      const rect = (element: Element) => element.getBoundingClientRect();
      const visible = (element: Element) => view.getComputedStyle(element).display !== 'none' && rect(element).height > 0;
      const round = (value: number) => Math.round(value * 100) / 100;
      const cabinets = [...doc.querySelectorAll<HTMLElement>('.arcade-cabinet')];
      check(cabinets.length === 4, 'All four cabinets render.');
      const phases = ['idle', 'loading', 'running', 'paused', 'error'] as const;
      const statusText = { idle: 'Ready when you are', loading: 'Preparing game…', running: 'You’re playing', paused: 'Paused · progress saved', error: 'The game could not continue. Try starting it again.' };
      const measurements: object[] = [];
      for (const phase of phases) {
        // Mirror only the host controller's visibility/status; no simulation runs here.
        for (const cabinet of cabinets) {
          cabinet.dataset.gameStatus = phase;
          cabinet.dataset.gameReady = String(phase === 'running' || phase === 'paused');
          for (const button of cabinet.querySelectorAll<HTMLElement>('[data-game-command]')) {
            const command = button.dataset.gameCommand;
            const shown = phase === 'idle' ? ['start'] : phase === 'loading' ? [] : phase === 'running' ? ['pause', 'restart'] : phase === 'paused' ? ['resume', 'restart'] : ['start', 'restart'];
            button.hidden = !shown.includes(command || '');
          }
          const runtime = cabinet.querySelector<HTMLElement>('[data-game-runtime-status]');
          if (runtime) runtime.textContent = statusText[phase];
        }
        await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
        for (const cabinet of cabinets) {
          const id = cabinet.dataset.game!;
          const screen = cabinet.querySelector<HTMLElement>('.arcade-screen')!;
          const canvas = cabinet.querySelector<HTMLCanvasElement>('canvas[data-game-canvas]')!;
          const title = cabinet.querySelector<HTMLElement>('.arcade-title')!;
          const score = cabinet.querySelector<HTMLElement>('.arcade-score')!;
          const buttons = [...cabinet.querySelectorAll<HTMLElement>('.arcade-command,.arcade-key')].filter(visible);
          const bounds = rect(cabinet), field = rect(screen), bitmap = rect(canvas);
          const heading = rect(title), stats = rect(score);
          const scale = Math.min(bitmap.width / canvas.width, bitmap.height / canvas.height);
          const paintedWidth = canvas.width * scale, paintedHeight = canvas.height * scale;
          const availableWidth = screen.clientWidth, availableHeight = screen.clientHeight;
          const containScale = Math.min(availableWidth / canvas.width, availableHeight / canvas.height);
          const expectedPaintedWidth = canvas.width * containScale, expectedPaintedHeight = canvas.height * containScale;
          const prefix = `${id} ${phase}`;
          check(paintedWidth > 0 && paintedHeight > 0, `${prefix}: game board is visible.`);
          // Matching cabinet sizes can legitimately letterbox native game art,
          // especially Tetris's taller 320×480 board. Fill the available box as
          // much as object-fit:contain permits without distorting coordinates.
          check(Math.abs(paintedWidth - expectedPaintedWidth) <= 2 && Math.abs(paintedHeight - expectedPaintedHeight) <= 2, `${prefix}: game art fills the available playfield at its native aspect ratio.`);
          const sameWidthCabinets = cabinets.filter(peer => Math.abs(rect(peer).width - bounds.width) <= 2);
          check(sameWidthCabinets.every(peer => { const peerField = rect(peer.querySelector('.arcade-screen')!); return Math.abs(peerField.width - field.width) <= 2 && Math.abs(peerField.height - field.height) <= 2; }), `${prefix}: equal-width cabinets use matching playfield containers.`);
          check(field.top - bounds.top <= Math.max(105, doc.documentElement.clientWidth * .065), `${prefix}: header remains compact.`);
          check(heading.right <= stats.left + 1 || stats.right <= heading.left + 1 || heading.bottom <= stats.top + 1 || stats.bottom <= heading.top + 1, `${prefix}: title and score do not overlap.`);
          // Narrow screens keep minimum touch targets and wrap pause feedback,
          // so a little more cabinet area is reserved for usable controls.
          const minimumBoardArea = doc.documentElement.clientWidth < 600 ? .45 : .5;
          const nativeContainCoverage = expectedPaintedWidth * expectedPaintedHeight / (availableWidth * availableHeight);
          check(paintedWidth * paintedHeight / (bounds.width * bounds.height) > minimumBoardArea * nativeContainCoverage, `${prefix}: playfield dominates the cabinet after allowing native-aspect letterboxing.`);
          check(view.getComputedStyle(canvas).objectFit === 'contain', `${prefix}: game geometry keeps its aspect ratio.`);
          check(cabinet.scrollWidth <= cabinet.clientWidth + 1, `${prefix}: cabinet has no horizontal overflow.`);
          check(field.left >= bounds.left && field.right <= bounds.right + 1, `${prefix}: playfield stays inside the cabinet.`);
          check(buttons.every(button => { const box = rect(button); return box.left >= bounds.left - 1 && box.right <= bounds.right + 1; }), `${prefix}: every control fits inside its cabinet.`);
          check(buttons.every(button => rect(button).height >= 40), `${prefix}: touch controls keep a usable height.`);
          check(buttons.every(button => { const box = rect(button); return box.top >= field.bottom - 1 || box.bottom <= field.top + 1 || box.right <= field.left + 1 || box.left >= field.right - 1; }), `${prefix}: controls do not cover the board.`);
          if (doc.documentElement.clientWidth >= 1200) {
            check(Math.abs(bounds.width - bounds.height) <= 2, `${prefix}: desktop cabinet is square.`);
            check(cabinets.every(peer => { const peerBounds = rect(peer); return Math.abs(peerBounds.width - bounds.width) <= 2 && Math.abs(peerBounds.height - bounds.height) <= 2; }), `${prefix}: all desktop cabinets have equal dimensions.`);
            check(heading.right <= stats.left + 1 && Math.abs((heading.top + heading.bottom) / 2 - (stats.top + stats.bottom) / 2) < Math.max(heading.height, stats.height) / 2, `${prefix}: desktop title and score share one clear header row.`);
            check(buttons.every(button => { const box = rect(button); return box.left >= field.right - 1 && box.top >= field.top - 1 && box.bottom <= field.bottom + 1; }), `${prefix}: desktop controls stay beside the board.`);
          }
          if (phase === 'loading' || phase === 'error' || phase === 'paused') {
            const runtime = cabinet.querySelector<HTMLElement>('[data-game-runtime-status]')!;
            check(visible(runtime) && rect(runtime).height > 1 && view.getComputedStyle(runtime).clipPath === 'none', `${prefix}: loading, error and pause feedback stays visible.`);
          }
          measurements.push({ game: id, phase, cabinet: { width: round(bounds.width), height: round(bounds.height) }, playfield: { width: round(field.width), height: round(field.height) }, board: { width: round(paintedWidth), height: round(paintedHeight), nativeWidth: canvas.width, nativeHeight: canvas.height, widthCoverage: round(paintedWidth / field.width), areaCoverage: round(paintedWidth * paintedHeight / (field.width * field.height)), expectedContainCoverage: round(nativeContainCoverage) }, titleHeight: round(rect(title).height), titleFontSize: view.getComputedStyle(title.querySelector('h2')!).fontSize, scoreHeight: round(rect(score).height), topChrome: round(field.top - bounds.top), bottomChrome: round(bounds.bottom - field.bottom), visibleControls: buttons.length });
        }
        check(doc.documentElement.scrollWidth <= doc.documentElement.clientWidth + 1, `${phase}: page has no horizontal overflow.`);
      }
      // Leave the mirror in the same state as the untouched live fixture.
      for (const button of doc.querySelectorAll<HTMLElement>('[data-game-command]')) button.hidden = button.dataset.gameCommand !== 'start';
      for (const cabinet of cabinets) {
        cabinet.dataset.gameStatus = 'idle'; cabinet.dataset.gameReady = 'false';
        const runtime = cabinet.querySelector<HTMLElement>('[data-game-runtime-status]');
        if (runtime) runtime.textContent = statusText.idle;
      }
      setReport({ status: failures.length ? 'failed' : 'passed', checks, failures, viewport: { width: window.innerWidth, height: window.innerHeight }, frameWidth: doc.documentElement.clientWidth, measurements });
    } catch (error) { setReport({ status: 'failed', failures: [String(error)] }); }
    finally { setBusy(false); }
  };

  return <>
    <button type="button" disabled={busy} onClick={() => void run()}>{busy ? 'Checking layout…' : 'Run layout checks'}</button>
    <details className="layout-report"><summary>Layout measurements</summary><pre data-arcade-layout-report>{JSON.stringify(report, null, 2)}</pre></details>
    <iframe ref={mirror} title="Script-free arcade layout measurements" aria-hidden="true" tabIndex={-1} inert sandbox="allow-same-origin" srcDoc={srcDoc} className="arcade-layout-mirror" />
  </>;
}
