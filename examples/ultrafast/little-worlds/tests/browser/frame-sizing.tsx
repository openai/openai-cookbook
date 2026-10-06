import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import GeneratedFrame from '../../src/GeneratedFrame';

type Scene = 'cards' | 'tall' | 'boundary' | 'nested' | 'horizontal' | 'absolute';
const scenes: { value: Scene; label: string }[] = [
  { value: 'cards', label: 'Responsive cards' },
  { value: 'tall', label: 'Tall content' },
  { value: 'boundary', label: 'Near 8000px' },
  { value: 'nested', label: 'Nested scrollbox' },
  { value: 'horizontal', label: 'Horizontal overflow' },
  { value: 'absolute', label: 'Out-of-flow content' },
];

function sceneHtml(scene: Scene, grown: boolean) {
  const contents = {
    cards: `<div class="cards"><section class="card"><h2>First square</h2></section><section class="card"><h2>Second square</h2></section></div><details><summary>Expand extra content</summary><section class="disclosure-content"><h2>400px of disclosed content</h2></section></details>`,
    tall: `<section class="tall"><h2>9200px tall content</h2><p>The bottom action must remain reachable.</p></section>`,
    boundary: `<section class="boundary"><h2>Responsive cap boundary</h2><p>7900px at widths above 1140px; 8100px at or below 1140px. A stray 15px scrollbar crosses the breakpoint at a 1148px frame width.</p></section>`,
    nested: `<h2>Intentional inner scrolling</h2><section class="nested" tabindex="0" aria-label="Nested scrollbox"><div class="nested-content"><p>Scroll inside this 180px box.</p><button data-action='{"type":"nested-bottom"}'>Nested bottom action</button></div></section>`,
    horizontal: `<section class="horizontal"><h2>1600px wide by 300px tall</h2><p>Scroll horizontally to reach the action at the far end of the final row.</p><div class="horizontal-end"><button data-action='{"type":"horizontal-end"}'>Horizontal end action</button></div></section>`,
    absolute: `<section class="absolute-wrapper"><p>Fixed 120px wrapper; its child extends beyond normal flow.</p><div class="absolute-child" style="top:${grown ? 400 : 80}px;height:${grown ? 1200 : 240}px"><h2>Absolute content: ${grown ? 'grown' : 'small'}</h2><button data-action='{"type":"absolute-end"}'>Out-of-flow end action</button></div></section>`,
  };
  return `<style>
    .fixture{color:#eaeae7;background:#151a20;font-family:Arial,sans-serif}
    .fixture h2,.fixture p{margin:0;padding:12px}
    .cards{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}
    .card{aspect-ratio:1;min-width:0;background:#214a59;border:1px solid #9ab9b1;display:grid;place-items:center}
    .card:nth-child(2){background:#503c63}
    .fixture summary{padding:12px;cursor:pointer}.disclosure-content{height:400px;background:#566647}
    .tall{height:9200px;background:linear-gradient(#214a59,#503c63)}
    .boundary{height:7900px;background:linear-gradient(#503c63,#214a59)}
    .nested{height:180px;overflow:auto;border:2px solid #9ab9b1;margin:12px}
    .nested-content{height:720px;display:flex;flex-direction:column;justify-content:space-between}
    .horizontal{width:1600px;height:300px;background:linear-gradient(90deg,#214a59,#503c63);display:flex;flex-direction:column}
    .horizontal-end{margin-top:auto;padding:12px;text-align:right}
    .absolute-wrapper{position:relative;height:120px}
    .absolute-child{position:absolute;left:30%;width:65%;background:#503c63;display:flex;flex-direction:column;justify-content:space-between}
    .growth{height:1200px;background:linear-gradient(#566647,#214a59)}
    .fixture footer{padding:12px}
    .fixture button{padding:10px 16px;background:#dce9dd;color:#162019;border:0;border-radius:4px}
    @media(max-width:760px){.cards{grid-template-columns:minmax(0,1fr)}}
    @media(max-width:1140px){.boundary{height:8100px}}
  </style><main class="fixture" data-scene="${scene}">${contents[scene]}${grown && scene !== 'absolute' ? '<section class="growth"><h2>Added 1200px of content</h2></section>' : ''}<footer><button data-action='{"type":"bottom"}'>Bottom action</button></footer></main>`;
}

function App() {
  const [width, setWidth] = useState(1148);
  const [scene, setScene] = useState<Scene>('cards');
  const [grown, setGrown] = useState(false);
  const [version, setVersion] = useState(1);
  const [revision, setRevision] = useState(1);
  const [loads, setLoads] = useState(0);
  const [metrics, setMetrics] = useState({ width: 0, height: 0 });
  const [action, setAction] = useState({ count: 0, type: 'none' });
  const container = useRef<HTMLDivElement>(null);
  const html = sceneHtml(scene, grown);

  useEffect(() => {
    const frame = container.current!.querySelector('iframe')!;
    const measure = () => {
      const rect = frame.getBoundingClientRect();
      setMetrics(previous => previous.width === rect.width && previous.height === rect.height
        ? previous : { width: rect.width, height: rect.height });
    };
    const loaded = () => { setLoads(value => value + 1); measure(); };
    const observer = new ResizeObserver(measure);
    observer.observe(frame);
    frame.addEventListener('load', loaded);
    measure();
    return () => { observer.disconnect(); frame.removeEventListener('load', loaded); };
  }, []);

  return <main className="test-page">
    <style>{`
      body{margin:0;background:#eef0eb;color:#18231c;font:14px/1.4 system-ui,sans-serif}
      .test-page{padding:16px}.fixture-controls{position:sticky;top:0;z-index:1;background:#eef0eb;padding:8px 0 12px}
      h1{font-size:20px;margin:0 0 8px}p{margin:6px 0}
      button{font:inherit;padding:6px 10px;margin:3px;border:1px solid #819080;border-radius:5px;cursor:pointer}
      button[aria-pressed=true]{background:#233b2b;color:white}button:disabled{opacity:.45;cursor:default}
      .frame-container{outline:1px solid #819080;margin-top:12px}.generated-frame{display:block;width:100%;border:0}
      output{display:block;font-variant-numeric:tabular-nums}
    `}</style>
    <section className="fixture-controls" aria-label="Sizing fixture controls">
      <h1>Generated frame sizing checks</h1>
      <p>Real sandboxed frame; local fixture actions only. Scene and growth changes keep the same revision.</p>
      <div aria-label="Frame width">
        {[1148, 360].map(value => <button key={value} aria-pressed={width === value} onClick={() => setWidth(value)}>Width {value}px</button>)}
      </div>
      <div aria-label="Frame content">
        {scenes.map(item => <button key={item.value} aria-pressed={scene === item.value} onClick={() => {
          setScene(item.value); setGrown(false); setVersion(value => value + 1);
        }}>{item.label}</button>)}
        <button disabled={grown} onClick={() => { setGrown(true); setVersion(value => value + 1); }}>Grow content</button>
        <button disabled={!grown} onClick={() => { setGrown(false); setVersion(value => value + 1); }}>Shrink content</button>
        <button onClick={() => setRevision(value => value + 1)}>New revision</button>
      </div>
      <output id="fixture-state" aria-label="Frame state" data-scene={scene} data-version={version} data-revision={revision} data-loads={loads}>
        Scene: {scene}. Content growth: {grown ? 'on' : 'off'}. Render version: {version}. Revision: {revision}. Frame loads: {loads}.
      </output>
      <output id="frame-dimensions" aria-label="Frame dimensions" data-width={metrics.width} data-height={metrics.height}>
        Frame border box: {metrics.width} × {metrics.height}px. Requested width: {width}px.
      </output>
      <output id="fixture-actions" aria-label="Fixture actions" data-count={action.count}>
        Actions: {action.count}. Last action: {action.type}.
      </output>
    </section>
    <div ref={container} className="frame-container" style={{ width }}>
      <GeneratedFrame html={html} renderVersion={version} revisionId={revision} pending={false} onAction={async payload => {
        setAction(previous => ({ count: previous.count + 1, type: String(payload.type) }));
        return { ok: true, html, version };
      }} />
    </div>
  </main>;
}

createRoot(document.getElementById('root')!).render(<App />);
