// Real opaque-origin GeneratedFrame, real serialized bridge, in-memory saves.
// No server requests, model calls, stored accounts, or demo reset are involved.
// UI checks: paint/drag each resolution; keyboard arrows + Space/Enter; switch
// brushes; rerender; hold and reject a save; resize while held; scale and crop.
import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import GeneratedFrame from '../../src/GeneratedFrame';

type Raster = { columns: number; rows: number; pixels: string; version: number };
type PaintCell = { cell: number; color: number };
type Receipt = { id: number; type: string; columns: unknown; rows: unknown; cells: unknown; status: 'pending' | 'accepted' | 'rejected'; reason?: string };
type View = 'full' | 'scaled' | 'cropped';
const alphabet = '0123456789abcdefghijklmnopqrstuv';
const palette = ['#3153be', '#ef7966', '#ffffff'];
const sizes = [[48, 32], [96, 64], [192, 128], [256, 256]] as const;
const initial: Raster = { columns: 48, rows: 32, pixels: '.'.repeat(48 * 32), version: 1 };

function markup(state: Raster, brush: number) {
  const config = JSON.stringify({ action: 'paint_pixels', columns: state.columns, rows: state.rows, color: brush, colorValue: palette[brush], palette, background: '#ffffff' });
  return `<style>
    .painting-fixture{font:16px/1.35 Arial,sans-serif;color:#152031;background:#e9eef5;padding:16px}
    .painting-fixture *{box-sizing:border-box}.painting-fixture h2{font-size:22px;margin:0 0 8px}
    .painting-fixture p{margin:8px 0}.painting-tools{display:flex;gap:8px;align-items:center;margin-bottom:12px}
    .painting-tools button{font:inherit;background:#fff;border:1px solid #8290a3;border-radius:5px;padding:7px 12px}
    .painting-tools button[aria-pressed=true]{outline:2px solid #3153be;outline-offset:1px}
    canvas[data-paint-grid]{display:block;width:100%;height:auto;aspect-ratio:${state.columns}/${state.rows};background:#fff;image-rendering:pixelated;outline:1px solid #8290a3}
    canvas[data-paint-grid]:focus-visible{outline:3px solid #3153be;outline-offset:3px}
    .painting-footnote{font-size:14px;color:#44536b}
  </style><section class="painting-fixture" data-key="painting-fixture">
    <h2>Shared painting · ${state.columns} × ${state.rows}</h2>
    <div class="painting-tools" data-key="painting-tools">${palette.map((_, index) => `<button type="button" data-key="brush-${index}" aria-pressed="${brush === index}" data-action='{"type":"brush","color":${index}}'>${['Blue', 'Coral', 'White'][index]}</button>`).join('')}</div>
    <canvas data-key="painting" data-paint-grid='${config}' data-paint-pixels="${state.pixels}" width="${state.columns}" height="${state.rows}" tabindex="0" aria-label="Shared painting">Shared painting. Use arrow keys to choose a pixel, then Space or Enter to paint.</canvas>
    <p class="painting-footnote" data-key="footnote">Arrow keys choose a pixel. Space or Enter paints. Version ${state.version}.</p>
  </section>`;
}

function resize(state: Raster, columns: number, rows: number): Raster {
  const result: string[] = [];
  for (let row = 0; row < rows; row++) for (let column = 0; column < columns; column++) {
    result.push(state.pixels[Math.floor(row * state.rows / rows) * state.columns + Math.floor(column * state.columns / columns)]);
  }
  return { columns, rows, pixels: result.join(''), version: state.version + 1 };
}

function Fixture() {
  const [state, setState] = useState(initial);
  const live = useRef(initial);
  const [brush, setBrush] = useState(0);
  const currentBrush = useRef(0);
  const [receipts, setReceipts] = useState<Receipt[]>([]);
  const journal = useRef<Receipt[]>([]);
  const [held, setHeld] = useState(false);
  const hold = useRef(false);
  const gates = useRef<(() => void)[]>([]);
  const [rejectNext, setRejectNext] = useState(false);
  const rejecting = useRef(false);
  const [view, setView] = useState<View>('full');
  const [revision, setRevision] = useState(1);
  const [height, setHeight] = useState(800);
  const frameHost = useRef<HTMLDivElement>(null);
  const [loads, setLoads] = useState(0);
  const [frameWidth, setFrameWidth] = useState(0);

  const update = (next: Raster) => { live.current = next; setState(next); };
  const record = () => setReceipts(journal.current.map(receipt => ({ ...receipt })));
  const receive = async (action: Record<string, unknown>) => {
    if (action.type === 'brush' && Number.isInteger(action.color) && Number(action.color) >= 0 && Number(action.color) < palette.length) {
      currentBrush.current = Number(action.color); setBrush(currentBrush.current);
      const next = { ...live.current, version: live.current.version + 1 }; update(next);
      return { ok: true, html: markup(next, currentBrush.current), version: next.version };
    }
    const receipt: Receipt = { id: journal.current.length + 1, type: String(action.type), columns: action.columns, rows: action.rows, cells: action.cells, status: 'pending' };
    journal.current.push(receipt); record();
    const shouldReject = rejecting.current;
    rejecting.current = false; setRejectNext(false);
    if (hold.current) await new Promise<void>(resolve => gates.current.push(resolve));
    const current = live.current;
    const cells = action.cells as PaintCell[] | undefined;
    let reason = '';
    if (shouldReject) reason = 'Intentional fixture rejection';
    else if (action.type !== 'paint_pixels') reason = 'Unknown action';
    else if (action.columns !== current.columns || action.rows !== current.rows) reason = 'Stale raster dimensions';
    else if (!Array.isArray(cells) || !cells.length || cells.length > 120) reason = 'Invalid bounded batch';
    else if (cells.some(mark => !mark || !Number.isInteger(mark.cell) || mark.cell < 0 || mark.cell >= current.columns * current.rows || !Number.isInteger(mark.color) || mark.color < 0 || mark.color >= palette.length)) reason = 'Invalid pixel or color';
    if (reason) {
      receipt.status = 'rejected'; receipt.reason = reason; record();
      return { ok: false, html: markup(current, currentBrush.current), version: current.version };
    }
    const pixels = [...current.pixels];
    for (const mark of cells!) pixels[mark.cell] = alphabet[mark.color];
    const next = { ...current, pixels: pixels.join(''), version: current.version + 1 };
    update(next); receipt.status = 'accepted'; record();
    return { ok: true, html: markup(next, currentBrush.current), version: next.version };
  };

  useEffect(() => {
    const frame = frameHost.current!.querySelector('iframe')!;
    const measure = () => { setHeight(frame.clientHeight); setFrameWidth(frame.clientWidth); };
    const loaded = () => { setLoads(value => value + 1); measure(); };
    const observer = new ResizeObserver(measure);
    observer.observe(frame); frame.addEventListener('load', loaded); measure();
    return () => { observer.disconnect(); frame.removeEventListener('load', loaded); };
  }, []);

  const html = markup(state, brush);
  const painted = [...state.pixels].filter(pixel => pixel !== '.').length;
  const accepted = receipts.filter(receipt => receipt.status === 'accepted');
  const rejected = receipts.filter(receipt => receipt.status === 'rejected');
  const pending = receipts.filter(receipt => receipt.status === 'pending');
  const scale = view === 'full' ? 1 : .5;
  const sampleCells = [0, state.columns - 1, state.columns * Math.floor(state.rows / 2) + Math.floor(state.columns / 2), state.columns * (state.rows - 1), state.columns * state.rows - 1];
  return <main className="fixture">
    <style>{`
      body{margin:0;background:#111722;color:#e7eef8;font:14px/1.4 system-ui,sans-serif}.fixture{padding:18px}
      h1{font-size:23px;margin:0 0 8px}p{margin:5px 0 10px}.controls{max-width:1180px}
      .control-row{display:flex;flex-wrap:wrap;gap:6px;margin:7px 0;align-items:center}.control-row strong{width:95px}
      button{font:inherit;padding:7px 10px;border:1px solid #8192aa;border-radius:5px;background:#263346;color:#e7eef8;cursor:pointer}
      button[aria-pressed=true]{background:#cbd9f3;color:#111722}button:disabled{opacity:.45;cursor:default}
      output{display:block;font:13px/1.5 ui-monospace,monospace;overflow-wrap:anywhere}.diagnostics{margin:12px 0;padding:10px;background:#202b3c;border-radius:5px;max-width:1160px}
      .raster-viewport{width:960px;max-width:100%;outline:1px solid #6d829f;overflow:auto;background:#e9eef5}
      .raster-viewport[data-view=scaled],.raster-viewport[data-view=cropped]{width:480px}
      .raster-viewport[data-view=cropped]{height:220px}
      .raster-footprint{position:relative}.raster-logical{width:960px;max-width:100%;transform-origin:top left}
      .raster-viewport[data-view=scaled] .raster-logical,.raster-viewport[data-view=cropped] .raster-logical{position:absolute;max-width:none;transform:scale(.5)}
      .generated-frame{display:block;width:100%;border:0}details{margin-top:14px;max-width:960px}pre{font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:360px;overflow:auto}
    `}</style>
    <section className="controls" aria-label="Raster fixture controls">
      <h1>Raster painting checks</h1>
      <p>Real sandboxed frame. Saves and resolution changes affect this isolated in-memory fixture only.</p>
      <div className="control-row"><strong>Resolution</strong>{sizes.map(([columns, rows]) => <button key={columns} aria-pressed={state.columns === columns && state.rows === rows} onClick={() => update(resize(live.current, columns, rows))}>{columns} × {rows}</button>)}</div>
      <div className="control-row"><strong>Preview</strong>{(['full', 'scaled', 'cropped'] as View[]).map(mode => <button key={mode} aria-pressed={view === mode} onClick={() => setView(mode)}>{mode === 'full' ? 'Full size' : mode === 'scaled' ? '50% scale' : '50% cropped'}</button>)}</div>
      <div className="control-row"><strong>Saves</strong>
        <button aria-pressed={held} onClick={() => { hold.current = !hold.current; setHeld(hold.current); if (!hold.current) gates.current.splice(0).forEach(resolve => resolve()); }}>Hold saves</button>
        <button disabled={!pending.length} onClick={() => gates.current.splice(0).forEach(resolve => resolve())}>Release pending saves</button>
        <button aria-pressed={rejectNext} onClick={() => { rejecting.current = !rejecting.current; setRejectNext(rejecting.current); }}>Reject next save</button>
      </div>
      <div className="control-row"><strong>State</strong>
        <button onClick={() => update({ ...live.current, version: live.current.version + 1 })}>Rerender same pixels</button>
        <button onClick={() => setRevision(value => value + 1)}>Reload frame</button>
        <button onClick={() => { const next = live.current; const pixels = [...'.'.repeat(next.columns * next.rows)]; pixels[0] = '0'; pixels[next.columns - 1] = '1'; pixels[next.columns * (next.rows - 1)] = '1'; pixels[pixels.length - 1] = '0'; update({ ...next, pixels: pixels.join(''), version: next.version + 1 }); }}>Seed corners</button>
        <button onClick={() => update({ ...live.current, pixels: '.'.repeat(live.current.columns * live.current.rows), version: live.current.version + 1 })}>Clear fixture canvas</button>
      </div>
    </section>
    <section className="diagnostics" aria-label="Raster diagnostics">
      <output id="raster-state" data-columns={state.columns} data-rows={state.rows} data-painted={painted} data-version={state.version} data-brush={brush} data-html-length={html.length}>Raster: {state.columns} × {state.rows}. Painted: {painted}. Version: {state.version}. Brush: {['Blue', 'Coral', 'White'][brush]}. HTML: {html.length} characters.</output>
      <output id="raster-saves" data-accepted={accepted.length} data-rejected={rejected.length} data-pending={pending.length} data-max-batch={Math.max(0, ...receipts.map(receipt => Array.isArray(receipt.cells) ? receipt.cells.length : 0))}>Saves: {accepted.length} accepted, {rejected.length} rejected, {pending.length} pending. Hold: {String(held)}. Reject next: {String(rejectNext)}.</output>
      <output id="raster-samples">Samples: {sampleCells.map(cell => `${cell}=${state.pixels[cell]}`).join(', ')}.</output>
      <output id="raster-frame" data-loads={loads} data-revision={revision} data-view={view} data-width={frameWidth} data-height={height}>Frame: {frameWidth} × {height}. View: {view}. Loads: {loads}. Revision: {revision}.</output>
      <output id="raster-last-action">Last action: {receipts.length ? JSON.stringify(receipts[receipts.length - 1]) : 'none'}.</output>
    </section>
    <div className="raster-viewport" data-view={view} aria-label="Painting viewport">
      <div className="raster-footprint" style={view === 'full' ? undefined : { height: height * scale }}>
        <div className="raster-logical" ref={frameHost}>
          <GeneratedFrame html={html} onAction={receive} renderVersion={state.version} revisionId={revision} pending={false} />
        </div>
      </div>
    </div>
    <details><summary>Received paint batches</summary><pre id="raster-journal">{JSON.stringify(receipts, null, 2)}</pre></details>
    <details><summary>Authoritative raster pixels</summary><pre id="raster-pixels">{state.pixels}</pre></details>
  </main>;
}

createRoot(document.getElementById('root')!).render(<Fixture />);
