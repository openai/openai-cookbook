// Actual service controller and sandbox bridge, entirely in memory. No model,
// accounts, stored paintings, or service network requests are involved.
import { useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import GeneratedFrame from '../../src/GeneratedFrame';
import { createSpaceServices } from '../../src/space-services';
import type { SpaceServiceEvent } from '../../src/space-services';
import type { FrameServiceController } from '../../src/frame-service-bridge';

type Mode = 'complete-open' | 'stall';
type Entry = { ms: number; event: string; detail: string };
const names: Record<Mode, string> = { 'complete-open': 'Complete with connection open', stall: 'Stall after painting' };
const deadline = 1500;

function markup(marks: number, version: number) {
  return `<style>
    .painting-check{font:16px/1.4 system-ui,sans-serif;background:#111722;color:#f5f7fa;padding:24px}
    .painting-check *{box-sizing:border-box}.painting-check h2{font-size:24px;margin:0 0 16px}
    .painting-check [hidden]{display:none!important}.painting-check .layout{display:grid;grid-template-columns:minmax(0,1fr) 300px;gap:24px}
    .painting-check .canvas{height:220px;padding:20px;background:white;display:flex;align-items:center;gap:10px;flex-wrap:wrap;border-radius:4px;color:#173755}
    .painting-check .mark{display:inline-block;background:#899b77;width:25px;height:25px}
    .painting-check input{font:inherit;width:100%;padding:10px;background:#070c13;color:white;border:1px solid #8290a3;border-radius:5px}
    .painting-check button{font:inherit;padding:8px 15px;border:1px solid #8290a3;border-radius:5px;background:#263346;color:white}
    .painting-check button:disabled{opacity:.4}.painting-check .commands{display:flex;gap:8px;margin:10px 0}
    .painting-check [data-service-status]{color:#b58cff}.painting-check [data-service-error]{color:#ffaf80}
    .painting-check .footnote{font-size:13px;color:#a6b3c5;margin-top:14px}
  </style><main class="painting-check" data-key="painting-check">
    <h2>The shared canvas</h2><div class="layout">
      <div><div class="canvas" aria-label="Saved painting" data-key="canvas">${'<span class="mark" aria-label="Saved mark"></span>'.repeat(marks)}</div><p class="footnote" data-key="version">Saved marks: ${marks}. World render: ${version}.</p></div>
      <section class="chat" data-key="chat" data-service="space-agent">
        <h2>Paint with words</h2><form><input name="message" maxlength="1200" aria-label="Describe what to paint" placeholder="A forest…" required value="Paint a forest">
        <div class="commands"><button type="submit">Paint</button><button type="button" data-service-operation="cancel">Stop</button></div></form>
        <div data-service-messages hidden></div><template data-service-message><p data-field="content"></p></template>
        <div data-service-error></div><div data-service-note></div><div data-service-status="loading" hidden>Painting…</div>
        <div data-service-stopped hidden>Stopped. Your saved marks remain.</div>
      </section>
    </div></main>`;
}

function Fixture() {
  const [mode, setMode] = useState<Mode>('complete-open');
  const selected = useRef(mode);
  const [marks, setMarks] = useState(0);
  const [version, setVersion] = useState(1);
  const [status, setStatus] = useState<SpaceServiceEvent>({ status: 'ready' });
  const [entries, setEntries] = useState<Entry[]>([]);
  const [requests, setRequests] = useState(0);
  const [settled, setSettled] = useState(0);
  const [canceledStreams, setCanceledStreams] = useState(0);
  const requestNumber = useRef(0);
  const mounted = useRef(true);
  const epoch = useRef(performance.now());
  const timerSet = useRef(new Set<ReturnType<typeof setTimeout>>());
  const log = (event: string, detail: string) => {
    if (mounted.current) setEntries(previous => [...previous, { ms: Math.round(performance.now() - epoch.current), event, detail }]);
  };
  const services = useMemo(() => {
    const controller = createSpaceServices({
      spaceId: 'isolated-painting-fixture', revisionId: 1, requestTimeoutMs: deadline,
      fetchImpl: async (_path, init) => {
        const currentMode = selected.current;
        const number = ++requestNumber.current;
        setRequests(number);
        log('request', `${number}: ${names[currentMode]}`);
        let canceled = false;
        const timers = new Set<ReturnType<typeof setTimeout>>();
        const schedule = (callback: () => void, delay: number) => {
          const timer = setTimeout(() => { timers.delete(timer); timerSet.current.delete(timer); if (!canceled && mounted.current) callback(); }, delay);
          timers.add(timer); timerSet.current.add(timer);
        };
        // Intentionally do not close or error this stream on abort. This
        // reproduces a transport which hangs after its last application event.
        init?.signal?.addEventListener('abort', () => log('abort', `request ${number}`), { once: true });
        const body = new ReadableStream<Uint8Array>({
          start(stream) {
            const emit = (event: Record<string, unknown>) => {
              stream.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(event)}\n\n`));
              log('stream', `${number}: ${String(event.type)}`);
            };
            const paint = () => {
              setMarks(value => value + 1); setVersion(value => value + 1);
              emit({ type: 'action', action: 'paint_pixels' });
            };
            schedule(paint, 250);
            if (currentMode === 'complete-open') {
              schedule(paint, 550);
              schedule(() => emit({ type: 'complete', actionsApplied: 2 }), 900);
            }
          },
          cancel() {
            canceled = true;
            timers.forEach(timer => { clearTimeout(timer); timerSet.current.delete(timer); });
            timers.clear();
            if (mounted.current) setCanceledStreams(value => value + 1);
            log('stream canceled', `request ${number}`);
          },
        });
        return new Response(body, { headers: { 'Content-Type': 'text/event-stream' } });
      },
    });
    const bridge: FrameServiceController = {
      async request(request, emit) {
        try {
          await controller.request(request, next => { setStatus(next); log('state', `${next.status}${next.error ? `: ${next.error}` : ''}`); emit(next); });
        } finally {
          if (request.operation !== 'cancel' && request.operation !== 'clear') setSettled(value => value + 1);
          log('settled', request.operation || 'submit');
        }
      },
      cancel(service) { controller.cancel(service); },
    };
    return { controller, bridge };
  }, []);
  useEffect(() => () => {
    mounted.current = false; services.controller.dispose();
    timerSet.current.forEach(timer => clearTimeout(timer));
  }, [services]);

  return <main className="fixture">
    <style>{`
      body{margin:0;background:#080e18;color:#e7eef8;font:15px/1.45 system-ui,sans-serif}.fixture{padding:20px;max-width:1150px;margin:auto}
      h1{font-size:25px;margin:0 0 8px}p{margin:0 0 12px}.controls{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:15px}
      button{font:inherit;padding:9px 13px;border:1px solid #8290a3;border-radius:5px;background:#263346;color:white;cursor:pointer}
      button[aria-pressed=true]{background:#e2eafa;color:#111722}.diagnostics{background:#1a2639;padding:12px;margin-bottom:15px;border-radius:5px}
      output{display:block;font:13px/1.65 ui-monospace,monospace}.generated-frame{width:100%;border:1px solid #8290a3;display:block}
      pre{font:12px/1.5 ui-monospace,monospace;white-space:pre-wrap;max-height:300px;overflow:auto}
    `}</style>
    <h1>Painting service lifecycle checks</h1>
    <p>Actual service controller and sandboxed frame; mock stream only. Deadline: {deadline} ms. Use Paint inside the frame.</p>
    <div className="controls">{(['complete-open', 'stall'] as Mode[]).map(value => <button key={value} aria-pressed={mode === value} onClick={() => { selected.current = value; setMode(value); }}>{names[value]}</button>)}<button onClick={() => setVersion(value => value + 1)}>Rerender world</button></div>
    <section className="diagnostics" aria-label="Painting lifecycle diagnostics">
      <output id="service-state" data-status={status.status}>Status: {status.status}. {status.error || status.note || ''}</output>
      <output id="service-counts" data-requests={requests} data-settled={settled} data-canceled={canceledStreams} data-marks={marks} data-version={version}>Requests: {requests}. Settled: {settled}. Streams canceled: {canceledStreams}. Saved marks: {marks}. World render: {version}.</output>
    </section>
    <GeneratedFrame html={markup(marks, version)} renderVersion={version} revisionId={1} pending={false} capabilities={['space-agent']} services={services.bridge} onAction={async () => ({ ok: true })} />
    <details open><summary>Service events</summary><pre id="service-events">{entries.map(entry => `${entry.ms} ms · ${entry.event}: ${entry.detail}`).join('\n')}</pre></details>
  </main>;
}

createRoot(document.getElementById('root')!).render(<Fixture />);
