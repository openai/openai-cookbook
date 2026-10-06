import '../../src/fonts.css';
// Isolated UI fixture: synthetic activity only, with no auth, API, or model calls.
// Run with node tests/browser/build-activity-server.mjs and open
// http://127.0.0.1:5190/tests/browser/build-speedometer.html.
import { useEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { createRoot } from 'react-dom/client';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { BuildActivityPanel } from '../../src/BuildActivityPanel';
import { BuildSpeedometer } from '../../src/BuildSpeedometer';
import { BUILD_SPEEDOMETER_MAX_TPS } from '../../src/build-speedometer-geometry';
import type { ActivityEntry } from '../../src/build-activity';
import '../../src/styles.css';

type Throughput = {
  tokens: number;
  durationMs: number;
  rate: number;
  sampledAt: number;
  lastDeltaAt: number | null;
  state: 'waiting' | 'streaming' | 'complete';
  estimated: true;
};
type FixtureEntry = ActivityEntry & { throughput?: Throughput };
type Sample = { at: string; phase: string; rate: string; mode: string; scrollTop: number };
type Scenario = 'Waiting' | 'Disconnected' | 'Completed' | 'Missing telemetry';

const patchHeader = '*** Begin Patch\n*** Add File: space.js\n';
const initialPatch = patchHeader + '+export const palette = { leaf: "#789665", paper: "#f3f1e7" };\n';
const date = (time: number) => new Date(time).toISOString();

function entriesFor(start: number, throughput?: Throughput, patch = initialPatch, complete = false): FixtureEntry[] {
  return [
    { id: 'speed-request', turnId: 'speed-turn', time: date(start), kind: 'request', title: 'Request', eventType: 'turn.started', status: 'completed', text: 'Create a quiet, animated garden with responsive controls.' },
    { id: 'speed-model', turnId: 'speed-turn', time: date(start + 20), kind: 'event', title: 'Generating', eventType: 'model.started', status: complete ? 'completed' : 'running', throughput },
    { id: 'speed-patch', turnId: 'speed-turn', time: date(start + 50), kind: 'tool', title: 'apply_patch', tool: 'apply_patch', inputFormat: 'patch', arguments: patch, status: complete ? 'completed' : 'running' },
    ...(complete ? [{ id: 'speed-complete', turnId: 'speed-turn', time: date(start + 10_000), kind: 'event' as const, title: 'Published', eventType: 'turn.completed', status: 'completed' as const }] : []),
  ];
}

function AlignmentCheck() {
  const [rate, setRate] = useState(0);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState({ state: 'ready', text: 'Ready to check animated fill and needle alignment.' });
  const root = useRef<HTMLDivElement>(null);
  const runId = useRef(0);
  useEffect(() => () => { runId.current++; }, []);

  async function run() {
    if (running) return;
    const currentRun = ++runId.current;
    setRunning(true);
    setResult({ state: 'running', text: 'Checking each animation frame, including interrupted transitions…' });
    const failures: string[] = [];
    let checks = 0;
    let movingFrames = 0;
    let maxError = 0;
    let previousAngle: number | undefined;
    const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const phases = [
      { name: 'settle at zero', fraction: 0, duration: 280 },
      { name: 'full upward sweep', fraction: 1, duration: 280 },
      { name: 'full downward sweep', fraction: 0, duration: 280 },
      { name: 'interrupt upward sweep', fraction: 1, duration: 70 },
      { name: 'reverse before settling', fraction: 0.1, duration: 70 },
      { name: 'interrupt reverse sweep', fraction: 0.85, duration: 70 },
      { name: 'settle after interruptions', fraction: 0, duration: 280 },
      { name: 'above maximum', fraction: 1.25, duration: 280 },
      { name: 'settle at midpoint', fraction: 0.5, duration: 280 },
    ];
    for (const phase of phases) {
      if (runId.current !== currentRun) return;
      flushSync(() => setRate(phase.fraction * BUILD_SPEEDOMETER_MAX_TPS));
      const started = performance.now();
      await new Promise<void>(resolve => {
        function sample(now: number) {
          if (runId.current !== currentRun) { resolve(); return; }
          try {
            const fill = root.current!.querySelector<SVGPathElement>('.build-speed-fill')!;
            const needle = root.current!.querySelector<SVGGElement>('.build-speed-needle')!;
            const fillFraction = 1 - parseFloat(getComputedStyle(fill).strokeDashoffset) / 100;
            const style = getComputedStyle(needle);
            const matrix = new DOMMatrixReadOnly(style.transform);
            const angle = Math.atan2(matrix.b, matrix.a) * 180 / Math.PI;
            const origin = style.transformOrigin.split(' ').map(parseFloat);
            const start = fill.getPointAtLength(0);
            const end = fill.getPointAtLength(fill.getTotalLength());
            const center = { x: (start.x + end.x) / 2, y: (start.y + end.y) / 2 };
            const expectedAngle = -90 + 180 * Math.min(1, phase.fraction);
            const error = Math.abs(angle - (-90 + fillFraction * 180));
            checks++;
            maxError = Math.max(maxError, error);
            if (!Number.isFinite(error) || error > 1) throw new Error(`${phase.name}: fill and needle differ by ${error.toFixed(3)}°`);
            if (Math.hypot(origin[0] - center.x, origin[1] - center.y) > 0.1) throw new Error(`${phase.name}: needle origin differs from the arc center`);
            if (previousAngle !== undefined && Math.abs(angle - previousAngle) > 0.1 && Math.abs(angle - expectedAngle) > 1) movingFrames++;
            previousAngle = angle;
            if (now - started >= phase.duration && phase.duration >= 280 && Math.abs(angle - expectedAngle) > 1) throw new Error(`${phase.name}: needle did not reach its target`);
          } catch (error) {
            const message = error instanceof Error ? error.message : String(error);
            if (failures.length < 8) failures.push(message);
          }
          if (now - started < phase.duration) requestAnimationFrame(sample);
          else resolve();
        }
        requestAnimationFrame(sample);
      });
    }
    if (runId.current !== currentRun) return;
    if (!reducedMotion && movingFrames < 10) failures.push(`Only ${movingFrames} moving frames were sampled; expected at least 10.`);
    const passed = failures.length === 0;
    setResult({
      state: passed ? 'passed' : 'failed',
      text: `${passed ? 'PASS' : 'FAIL'}: ${checks} sampled frames, ${movingFrames} moving frames, ${maxError.toFixed(3)}° maximum alignment error.${reducedMotion ? ' Reduced motion is enabled.' : ''}${failures.length ? ` ${failures.join(' ')}` : ''}`,
    });
    setRunning(false);
  }

  return <section aria-label="Animated speedometer alignment check">
    <h2 style={{ fontSize: 15 }}>Animation alignment</h2>
    <button type="button" onClick={run} disabled={running}>Run animation alignment check</button>
    <div ref={root} className="build-metrics" style={{ justifyContent: 'flex-start' }}><BuildSpeedometer rate={rate} mode="streaming"/></div>
    <p role="status" data-testid="alignment-result" data-state={result.state}>{result.text}</p>
  </section>;
}

function Fixture() {
  const [entries, setEntries] = useState<FixtureEntry[]>([]);
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(true);
  const [open, setOpen] = useState(true);
  const [phase, setPhase] = useState('Ready');
  const [samples, setSamples] = useState<Sample[]>([]);
  const timer = useRef<ReturnType<typeof setInterval> | undefined>(undefined);
  const phaseRef = useRef(phase);
  phaseRef.current = phase;

  function stop() {
    clearInterval(timer.current);
    timer.current = undefined;
  }
  useEffect(() => {
    const capture = setInterval(() => {
      const gauge = document.querySelector<HTMLElement>('.build-activity-panel .build-speedometer');
      const feed = document.querySelector<HTMLElement>('.build-feed');
      if (!gauge) return;
      const sample = {
        at: new Date().toLocaleTimeString(), phase: phaseRef.current,
        rate: gauge.dataset.rate ?? '(none)', mode: gauge.dataset.mode ?? '(none)',
        scrollTop: Math.round(feed?.scrollTop ?? 0),
      };
      setSamples(previous => {
        const last = previous.at(-1);
        if (last?.phase === sample.phase && last.rate === sample.rate && last.mode === sample.mode && last.scrollTop === sample.scrollTop) return previous;
        return [...previous.slice(-13), sample];
      });
    }, 750);
    return () => { clearInterval(capture); clearInterval(timer.current); };
  }, []);

  function scenario(next: Scenario) {
    stop();
    setOpen(true);
    setSamples([]);
    setPhase(next);
    const now = Date.now();
    const complete = next === 'Completed';
    setBusy(!complete);
    setConnected(next !== 'Disconnected');
    const throughput: Throughput | undefined = next === 'Missing telemetry' ? undefined : {
      tokens: complete ? 3150 : next === 'Waiting' ? 0 : 500,
      durationMs: complete ? 5000 : next === 'Waiting' ? 0 : 1000,
      rate: complete ? 630 : next === 'Waiting' ? 0 : 500,
      sampledAt: now, lastDeltaAt: next === 'Waiting' ? null : now,
      state: complete ? 'complete' : next === 'Waiting' ? 'waiting' : 'streaming', estimated: true,
    };
    const patch = complete ? initialPatch + '+export function render() { return "<main>A little garden.</main>"; }\n*** End Patch' : initialPatch;
    setEntries(entriesFor(complete ? now - 10_000 : now, throughput, patch, complete));
  }

  function start() {
    stop();
    setOpen(true);
    setBusy(true);
    setConnected(true);
    setSamples([]);
    const started = Date.now();
    let tokens = 0;
    let lastDeltaAt: number | null = null;
    let previousTime = started;
    let patch = initialPatch;
    let line = 0;
    setPhase('Waiting');
    setEntries(entriesFor(started, { tokens: 0, durationMs: 0, rate: 0, sampledAt: started, lastDeltaAt: null, state: 'waiting', estimated: true }));
    timer.current = setInterval(() => {
      const now = Date.now();
      const elapsed = now - started;
      const rate = elapsed < 1000 ? 0 : elapsed < 3000 ? 200 : elapsed < 6000 ? 850 : 0;
      const complete = elapsed >= 10_000;
      const isStreaming = rate > 0;
      if (isStreaming) {
        tokens += Math.round(rate * (now - previousTime) / 1000);
        lastDeltaAt = now;
        const extra = rate === 850 ? 8 : 2;
        for (let index = 0; index < extra; index++) patch += `+// Garden detail ${++line}: a gentle shape follows the light and remains easy to control.\n`;
      }
      previousTime = now;
      const durationMs = Math.max(0, Math.min(elapsed, 6000) - 1000);
      setPhase(complete ? 'Completed' : elapsed < 1000 ? 'Waiting' : elapsed < 3000 ? '200 tokens/s' : elapsed < 6000 ? '850 tokens/s' : 'Stalled; needle should settle');
      // Keep the completed streaming sample during the pause. The panel must
      // age it out, and metadata-only updates must not scroll away from the code.
      setEntries(entriesFor(started, {
        tokens, durationMs, rate: complete ? tokens / (durationMs / 1000) : elapsed < 6000 ? rate : 850,
        sampledAt: isStreaming || !lastDeltaAt || complete ? now : lastDeltaAt,
        lastDeltaAt, state: complete ? 'complete' : lastDeltaAt ? 'streaming' : 'waiting', estimated: true,
      }, patch + (complete ? '*** End Patch' : ''), complete));
      if (complete) { stop(); setBusy(false); }
    }, 250);
  }

  return <div className="canvas-workspace with-build-activity">
    <style>{`
      .speed-fixture-nav { position: fixed; inset: 0 0 auto; z-index: 90; height: 72px; display: flex; align-items: center; gap: 8px; padding: 10px 18px; background: #f4f2e8; border-bottom: 1px solid #d4dbc7; overflow-x: auto; }
      .speed-fixture-nav button { flex-shrink: 0; border: 1px solid #becbad; border-radius: 7px; padding: 9px 12px; color: #394c2f; background: #edf0e2; font-size: 12px; }
      .speed-fixture-main { padding: 110px 32px 32px; max-width: min(740px, calc(100% - var(--build-panel-width) - 48px)); color: #405538; }
      .speed-fixture-main h1 { font: 42px/1.1 system-ui, sans-serif; font-weight: 400; }
      .speed-fixture-main p { font-size: 13px; line-height: 1.8; }
      .speed-fixture-main table { font: 10px/1.8 ui-monospace, monospace; width: 100%; text-align: left; border-collapse: collapse; }
      .speed-fixture-main th, .speed-fixture-main td { border-bottom: 1px solid #cdd8bf; padding: 6px 4px; }
      @media (max-width: 700px) { .speed-fixture-main { max-width: none; width: 100%; padding: 100px 14px; } }
    `}</style>
    <nav className="speed-fixture-nav" aria-label="Speedometer fixture controls">
      <button type="button" onClick={start}>Start sample stream</button>
      {(['Waiting', 'Disconnected', 'Completed', 'Missing telemetry'] as const).map(name => <button key={name} type="button" onClick={() => scenario(name)}>{name}</button>)}
    </nav>
    <main className="speed-fixture-main">
      <p>Synthetic browser fixture · no model calls</p>
      <h1>A little garden.</h1>
      <p>Start the sample to see a brief wait, 200 tokens/s, 850 tokens/s, a pause, then the completed average. The streamed patch grows at the same time.</p>
      <p role="status" data-testid="fixture-phase">{phase}</p>
      <AlignmentCheck/>
      <h2 style={{ fontSize: 15 }}>Latest rendered samples</h2>
      <table data-testid="speedometer-samples">
        <thead><tr><th>Time</th><th>Phase</th><th>Rate</th><th>Mode</th><th>Scroll</th></tr></thead>
        <tbody>{samples.map((sample, index) => <tr key={index}><td>{sample.at}</td><td>{sample.phase}</td><td>{sample.rate}</td><td>{sample.mode}</td><td>{sample.scrollTop}</td></tr>)}</tbody>
      </table>
    </main>
    <button className="build-activity-toggle" type="button" aria-label={open ? 'Close build activity' : 'Open build activity'} aria-controls="build-activity-panel" aria-expanded={open} onClick={() => setOpen(value => !value)}>{open ? <ChevronRight size={15}/> : <ChevronLeft size={15}/>}<span>Activity</span></button>
    {open && <BuildActivityPanel entries={entries} busy={busy} connected={connected} model="astra" tier="ultrafast" onClose={() => setOpen(false)}/>}
  </div>;
}

if (location.port !== '5190') {
  document.getElementById('root')!.textContent = 'Use the isolated fixture at http://127.0.0.1:5190/tests/browser/build-speedometer.html';
} else {
  createRoot(document.getElementById('root')!).render(<Fixture/>);
}
