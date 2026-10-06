// No API, model, microphone, auth, or saved-world access. Serve with Vite.
// Run both sizes at desktop/mobile. ?reduce exercises JS reduced motion; use
// actual browser reduced-motion emulation to test CSS media rules as well.
// ?responsive uses the production opaque iframe and its asynchronous resize bridge.
import { StrictMode, useEffect, useMemo, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { ArrowUpRight } from 'lucide-react';
import BuildComparison from '../../src/BuildComparison';
import GeneratedFrame from '../../src/GeneratedFrame';
import { BuildActivityPanel } from '../../src/BuildActivityPanel';
import type { ActivityEntry } from '../../src/build-activity';
import '../../src/styles.css';
import '../../src/canvas-workspace.css';
import '../../src/theme.css';
import '../../src/presentation.css';

if (new URLSearchParams(location.search).has('reduce')) {
  const original = window.matchMedia.bind(window);
  window.matchMedia = query => {
    const media = original(query);
    if (query === '(prefers-reduced-motion: reduce)') Object.defineProperty(media, 'matches', { value: true });
    return media;
  };
}
if(new URLSearchParams(location.search).has('fallback')) Object.defineProperty(document,'startViewTransition',{value:undefined,configurable:true});

const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
const responsive = new URLSearchParams(location.search).has('responsive');
const frameMarkup = `<!doctype html><html><body style="margin:0;background:#101b26;color:#e8f5e9;font:20px system-ui"><main style="padding:40px"><h1>A persistent world</h1><button id="counter" onclick="this.textContent=String(Number(this.textContent)+1)">0</button><p>Scroll through this world, then enter it without losing its state.</p>${Array.from({length: 14}, (_, index) => `<section style="height:130px;margin:20px 0;padding:24px;background:hsl(${170 + index * 8} 18% 18%);border-radius:12px">Section ${index + 1}</section>`).join('')}</main></body></html>`;
const responsiveMarkup = `<style>
  *{box-sizing:border-box}body{margin:0;background:#101b26;color:#e8f5e9;font:16px/1.6 system-ui}
  .pressure-world{padding:28px}.pressure-world h1{font:500 34px/1.15 system-ui;margin:0 0 20px}
  .pressure-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:20px}
  .pressure-card{padding:24px;background:#193a38;border:1px solid #387168;border-radius:12px;overflow-wrap:anywhere}
  .pressure-card h2{font:500 24px/1.2 system-ui;margin:0 0 16px}.pressure-card p{margin:0}
  @media(max-width:800px){.pressure-cards{grid-template-columns:repeat(2,minmax(0,1fr))}}
  @media(max-width:500px){.pressure-cards{grid-template-columns:minmax(0,1fr)}.pressure-world{padding:18px}.pressure-card{padding:18px}}
  </style><main class="pressure-world"><h1>A responsive world that keeps its place</h1><div class="pressure-cards">${Array.from({length:9},(_,index)=>`<section class="pressure-card"><h2>World ${index+1}</h2><p>Each card grows naturally as its column narrows. This paragraph deliberately wraps over many lines so the real iframe resize bridge must report a different height when the world expands into its finished layout. The composer should remain steady after the browser hands the page back.</p></section>`).join('')}</div></main>`;
const line = '+const orbit = { speed: 0.25, radius: 160, label: "Continuous motion with stable geometry and no layout read per frame" };\n';
const completedEntries: ActivityEntry[] = [{
  id: 'pressure-request', turnId: 'pressure', time: '2026-01-01T00:00:00Z', kind: 'request', title: 'Request', status: 'completed', text: 'Build an animated world',
}, ...Array.from({length: 12}, (_, index): ActivityEntry => ({
  id: `prior-${index}`, turnId: 'pressure', time: '2026-01-01T00:00:01Z', kind: 'tool', title: 'inspect_space', tool: 'inspect_space', status: 'completed', result: JSON.stringify({files: ['space.js', 'tests.js'], revision: index}),
}))];
type SnapshotFrame = { name: string; progress: number; x: number; y: number; width: number; height: number };
type Sample = { time: number; observedAt: number; gridWidth: number; gridHeight: number; gridTop: number; gridDocumentTop: number; worldTop: number; frameHeight: number; composerTop: number; scroll: number; activity: number; opacity: number; gridOpacity: number; morphing: boolean; snapshots: SnapshotFrame[] };
type Trace = { label: string; settleWaitMs: number; samples: number; intermediateWidths: number; snapshotFrames: number; snapshotNames: string[]; synchronousMs: number; firstChangeMs: number | null; medianMs: number; p95Ms: number; maxFrameMs: number; framesOver50ms: number; largestStepFraction: number; gridViewportTravel: number; gridViewportRange: number; worldViewportTravel: number; worldViewportRange: number; lastFrameJump: number; frameHeightStart: number; frameHeightEnd: number; postHandoffHeightShift: number; postHandoffComposerShift: number };
type TaskAttribution = { name?: string; containerType?: string; containerName?: string; containerId?: string; containerSrc?: string };
type SlowTask = { name: string; startTime: number; duration: number; attribution: TaskAttribution[] };
type ScriptAttribution = { sourceURL?: string; sourceFunctionName?: string; sourceCharPosition?: number; executionStart?: number; startTime?: number; duration?: number; invoker?: string; invokerType?: string; windowAttribution?: string; forcedStyleAndLayoutDuration?: number; pauseDuration?: number };
type SlowFrame = { startTime: number; duration: number; blockingDuration: number; renderStart: number; styleAndLayoutStart: number; firstUIEventTimestamp: number; workDuration: number; renderDuration: number; preLayoutDuration: number; styleAndLayoutDuration: number; scripts: ScriptAttribution[] };
type DiagnosticEntry<T> = T & { phases: string[] };
type PressureDiagnostics = { timeOrigin: number; supported: { longTask: boolean; longAnimationFrame: boolean }; attributionLimitations: string; longTasks: DiagnosticEntry<SlowTask>[]; longAnimationFrames: DiagnosticEntry<SlowFrame>[] };

function Fixture() {
  const [active, setActive] = useState(false);
  const [morphing, setMorphing] = useState(false);
  const [layoutActive, setLayoutActive] = useState(false);
  const [characters, setCharacters] = useState(30_000);
  const [streaming, setStreaming] = useState(false);
  const [chunk, setChunk] = useState(0);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState('Ready. Run 30k and 100k at desktop and mobile widths.');
  const [report, setReport] = useState<Trace[]>([]);
  const [diagnostics, setDiagnostics] = useState<PressureDiagnostics | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const visual = layoutActive;
  useEffect(() => {
    if (!streaming) return;
    const timer = setInterval(() => setChunk(current => current + 1), 60);
    return () => clearInterval(timer);
  }, [streaming]);
  const entries = useMemo<ActivityEntry[]>(() => [...completedEntries, {
    id: 'pressure-code', turnId: 'pressure', time: '2026-01-01T00:00:02Z', kind: 'tool', title: 'apply_patch', tool: 'apply_patch', status: 'running', inputFormat: 'patch',
    arguments: `*** Begin Patch\n*** Add File: space.js\n${line.repeat(Math.ceil(characters / line.length))}${Array.from({length: chunk}, (_, index) => `+// incoming update ${index}: ${line.slice(1)}`).join('')}`,
  }], [characters, chunk]);
  const panel = (name: string) => <BuildActivityPanel embedded label={`${name} pressure activity`} entries={entries} busy connected model="gpt-6-astra" tier={name.toLowerCase()} onClose={() => {}}/>;
  const change = (value: boolean) => flushSync(() => setActive(value));

  async function run(size: number) {
    if (running) return;
    setRunning(true); setResult(`Running ${size.toLocaleString()}-character streaming checks…`); setReport([]); setDiagnostics(null);
    const failures: string[] = [];
    const traces: Trace[] = [];
    const longTasks: number[] = [];
    const slowTasks: SlowTask[] = [];
    const slowFrames: SlowFrame[] = [];
    const phases: { label: string; startTime: number; endTime: number }[] = [];
    const supported = {
      longTask: typeof PerformanceObserver !== 'undefined' && PerformanceObserver.supportedEntryTypes.includes('longtask'),
      longAnimationFrame: typeof PerformanceObserver !== 'undefined' && PerformanceObserver.supportedEntryTypes.includes('long-animation-frame'),
    };
    const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    let baselineMs = 16.7;
    let checks = 0;
    let completed = false;
    const assert = (value: unknown, message: string) => { checks++; if (!value) failures.push(message); };
    // Collect only slow entries, without DOM reads, sorting, logging, or React updates
    // in observer callbacks. Phase attribution is resolved after the run by timestamp.
    const collectTasks = (entries: PerformanceEntry[]) => {
      for (const entry of entries) {
        if (entry.duration < 50) continue;
        longTasks.push(entry.duration);
        const task = entry as PerformanceEntry & { attribution?: TaskAttribution[] };
        slowTasks.push({ name: task.name, startTime: task.startTime, duration: task.duration, attribution: (task.attribution || []).map(value => ({ name: value.name, containerType: value.containerType, containerName: value.containerName, containerId: value.containerId, containerSrc: value.containerSrc })) });
      }
    };
    const collectFrames = (entries: PerformanceEntry[]) => {
      for (const entry of entries) {
        if (entry.duration < 50) continue;
        const frame = entry as PerformanceEntry & { blockingDuration?: number; renderStart?: number; styleAndLayoutStart?: number; firstUIEventTimestamp?: number; scripts?: ScriptAttribution[] };
        const end = frame.startTime + frame.duration, renderStart = frame.renderStart || 0, layoutStart = frame.styleAndLayoutStart || 0;
        slowFrames.push({ startTime: frame.startTime, duration: frame.duration, blockingDuration: frame.blockingDuration || 0, renderStart, styleAndLayoutStart: layoutStart, firstUIEventTimestamp: frame.firstUIEventTimestamp || 0,
          workDuration: renderStart ? renderStart - frame.startTime : frame.duration,
          renderDuration: renderStart ? end - renderStart : 0,
          preLayoutDuration: layoutStart && renderStart ? layoutStart - renderStart : 0,
          styleAndLayoutDuration: layoutStart ? end - layoutStart : 0,
          scripts: (frame.scripts || []).map(script => ({ sourceURL: script.sourceURL, sourceFunctionName: script.sourceFunctionName, sourceCharPosition: script.sourceCharPosition, executionStart: script.executionStart, startTime: script.startTime, duration: script.duration, invoker: script.invoker, invokerType: script.invokerType, windowAttribution: script.windowAttribution, forcedStyleAndLayoutDuration: script.forcedStyleAndLayoutDuration, pauseDuration: script.pauseDuration })),
        });
      }
    };
    const observer = supported.longTask ? new PerformanceObserver(list => collectTasks(list.getEntries())) : undefined;
    const frameObserver = supported.longAnimationFrame ? new PerformanceObserver(list => collectFrames(list.getEntries())) : undefined;
    observer?.observe({ type: 'longtask' });
    frameObserver?.observe({ type: 'long-animation-frame' });
    const element = root.current!;
    const sample = (lane: 'ultrafast' | 'standard', frameTime=Number(document.timeline.currentTime)||performance.now()): Sample => {
      const grid = element.querySelector('.build-comparison-grid')!.getBoundingClientRect();
      const activity = element.querySelector(`.build-comparison-${lane} .build-comparison-activity`)!;
      const snapshots: SnapshotFrame[]=[];
      for(const animation of document.getAnimations()) {
        const effect=animation.effect as (KeyframeEffect & {pseudoElement?:string|null})|null;
        const name=effect?.pseudoElement;
        if (!name?.startsWith('::view-transition-group(') || !name.includes('comparison-')) continue;
        const progress=effect!.getComputedTiming().progress;
        if (progress===null||progress===undefined) continue;
        const style=getComputedStyle(document.documentElement,name), transform=new DOMMatrixReadOnly(!style.transform||style.transform==='none'?undefined:style.transform);
        snapshots.push({name,progress,x:transform.e,y:transform.f,width:parseFloat(style.width),height:parseFloat(style.height)});
      }
      const transform=getComputedStyle(activity).transform;
      const frame=element.querySelector('iframe')!.getBoundingClientRect();
      return {time:frameTime,observedAt:performance.now(),gridWidth:grid.width,gridHeight:grid.height,gridTop:grid.top,gridDocumentTop:grid.top+scrollY,worldTop:frame.top,frameHeight:frame.height,composerTop:element.querySelector('.composer-area')!.getBoundingClientRect().top,scroll:scrollY,activity:transform==='none'?0:new DOMMatrixReadOnly(transform).e,opacity:Number(getComputedStyle(activity).opacity),gridOpacity:Number(getComputedStyle(element.querySelector('.build-comparison-grid')!).opacity),morphing:!!element.querySelector('.build-comparison[data-morphing]'),snapshots};
    };
    async function trace(label: string, action: () => void, options: {lane?: 'ultrafast' | 'standard'; axis?: 'activity' | 'gridWidth'; duration?: number; enter?: boolean; assertStart?: boolean; interrupted?: boolean} = {}) {
      const lane = options.lane || 'ultrafast';
      const axis = options.axis || 'activity';
      // An earlier snapshot can outlive a fixed sampling window on a slow device.
      // Settle it before the next independent action; intentional reversals remain
      // inside one trace and are still tested without waiting between reversals.
      const settleStart = performance.now();
      const settling = { label: `settle before ${label}`, startTime: settleStart, endTime: Infinity };
      phases.push(settling);
      const transitionPending = () => !!element.querySelector('.build-comparison[data-morphing]')
        || document.documentElement.hasAttribute('data-world-transition')
        || document.getAnimations().some(animation => (animation.effect as KeyframeEffect & { pseudoElement?: string })?.pseudoElement?.startsWith('::view-transition'));
      while (transitionPending() && performance.now() - settleStart < 3_000) await new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
      const settleWaitMs = performance.now() - settleStart;
      settling.endTime = performance.now();
      if (transitionPending()) throw new Error(`${label}: previous view transition did not settle within 3000ms`);
      const samples: Sample[] = [sample(lane)];
      const started = performance.now();
      const phase = { label, startTime: started, endTime: Infinity };
      phases.push(phase);
      action();
      const synchronousMs = performance.now() - started;
      await new Promise<void>(resolve => {
        const frame = (time:number) => {
          samples.push(sample(lane,time));
          if (performance.now() - started < (options.duration || 650)) requestAnimationFrame(frame);
          else resolve();
        };
        requestAnimationFrame(frame);
      });
      phase.endTime = performance.now();
      const intervals = samples.slice(1).map((value, index) => value.time - samples[index].time);
      const sorted = [...intervals].sort((a,b) => a-b);
      const range = Math.max(...samples.map(s => s[axis])) - Math.min(...samples.map(s => s[axis]));
      const smallest = Math.min(...samples.map(s => s[axis]));
      const intermediateWidths = new Set(samples.map(s=>Math.round(s[axis])).filter(value=>value>smallest+2 && value<smallest+range-2)).size;
      const changes = samples.slice(1).map((value, index) => Math.abs(value[axis] - samples[index][axis]));
      const normalFrameChanges = changes.filter((_, index) => intervals[index] < 50);
      const snapshotFrames=samples.filter(s=>s.snapshots.length>0);
      const snapshotNames=[...new Set(snapshotFrames.flatMap(s=>s.snapshots.map(snapshot=>snapshot.name)))];
      const native=axis==='gridWidth'&&snapshotFrames.length>0;
      const fallback=axis==='gridWidth'&&!native&&samples.some(s=>s.gridOpacity<.99);
      const first = native?samples.find(s=>s.snapshots.some(snapshot=>snapshot.progress>0)):fallback?samples.find(s=>s.gridOpacity<.99):samples.find(s => Math.abs(s[axis] - samples[0][axis]) > .5);
      const viewportSteps = samples.slice(1).map((value, index) => Math.abs(value.gridTop - samples[index].gridTop));
      const viewportRange = Math.max(...samples.map(s => s.gridTop)) - Math.min(...samples.map(s => s.gridTop));
      const worldSteps = samples.slice(1).map((value,index)=>Math.abs(value.worldTop-samples[index].worldTop));
      const worldRange = Math.max(...samples.map(s=>s.worldTop))-Math.min(...samples.map(s=>s.worldTop));
      const ending = samples.findIndex((value, index) => index > 0 && !value.morphing && samples[index - 1].morphing);
      const lastFrameJump = ending < 0 ? 0 : Math.max(Math.abs(samples[ending].gridTop - samples[ending - 1].gridTop), Math.abs(samples[ending].composerTop - samples[ending - 1].composerTop));
      const lastTransition=samples.map(value=>value.morphing||value.snapshots.length>0).lastIndexOf(true);
      const afterHandoff=lastTransition<0?samples.slice(-8):samples.slice(lastTransition+1);
      const span=(key:'frameHeight'|'composerTop')=>afterHandoff.length?Math.max(...afterHandoff.map(value=>value[key]))-Math.min(...afterHandoff.map(value=>value[key])):0;
      const item: Trace = {label, settleWaitMs, samples: samples.length, intermediateWidths, snapshotFrames:snapshotFrames.length,snapshotNames,synchronousMs, firstChangeMs: first ? first.observedAt-started : null, medianMs: sorted[Math.floor(sorted.length*.5)] || 0, p95Ms: sorted[Math.floor(sorted.length*.95)] || 0, maxFrameMs: Math.max(...intervals), framesOver50ms: intervals.filter(ms => ms>50).length, largestStepFraction: range>4 ? Math.max(0,...normalFrameChanges)/range : 0, gridViewportTravel: viewportSteps.reduce((a,b)=>a+b,0), gridViewportRange:viewportRange,worldViewportTravel:worldSteps.reduce((a,b)=>a+b,0),worldViewportRange:worldRange,lastFrameJump,frameHeightStart:samples[0].frameHeight,frameHeightEnd:samples.at(-1)!.frameHeight,postHandoffHeightShift:span('frameHeight'),postHandoffComposerShift:span('composerTop')};
      traces.push(item);
      if(responsive&&options.enter&&!options.interrupted) {
        assert(afterHandoff.length>=3,`${label}: responsive resize must be observed after transition handoff`);
        assert(item.postHandoffHeightShift<3,`${label}: iframe resized ${item.postHandoffHeightShift.toFixed(0)}px after transition handoff`);
        assert(item.postHandoffComposerShift<3,`${label}: responsive resize moved composer ${item.postHandoffComposerShift.toFixed(0)}px after transition handoff`);
        assert(Math.abs(item.frameHeightStart-item.frameHeightEnd)>100,`${label}: fixture must exercise a substantial responsive iframe height change`);
      }
      if (!reduced) {
        // The mobile grid can keep the same width, but a native snapshot still
        // provides a measurable first visual change on every viewport.
        if (options.assertStart !== false || native) assert(item.firstChangeMs !== null && item.firstChangeMs < 150, `${label}: first movement delayed ${item.firstChangeMs?.toFixed(0) ?? 'forever'}ms`);
        assert(item.synchronousMs < 150, `${label}: click blocked for ${item.synchronousMs.toFixed(0)}ms`);
        if (native&&!options.interrupted) {
          assert(snapshotFrames.length>=4,`${label}: browser snapshots must animate over multiple frames`);
          assert(snapshotNames.includes('::view-transition-group(comparison-world)')&&snapshotNames.includes('::view-transition-group(comparison-composer)'),`${label}: world and composer must both be captured`);
          for(const name of snapshotNames) {
            const values=snapshotFrames.flatMap(s=>s.snapshots.filter(snapshot=>snapshot.name===name));
            assert(values.every((value,index)=>!index||value.progress>=values[index-1].progress),`${label}: ${name} progress must not reverse`);
            const travel=values.slice(1).reduce((sum,value,index)=>sum+Math.abs(value.y-values[index].y),0);
            const rangeY=Math.max(...values.map(value=>value.y))-Math.min(...values.map(value=>value.y));
            assert(travel<=rangeY+4,`${label}: ${name} visually bounces down then up`);
          }
          const lastSnapshot=samples.map(value=>value.snapshots.length>0).lastIndexOf(true);
          const handoff=samples.slice(lastSnapshot+1,lastSnapshot+5);
          if (handoff.length>=3) for(const key of ['gridTop','worldTop','composerTop'] as const) {
            assert(Math.max(...handoff.map(value=>value[key]))-Math.min(...handoff.map(value=>value[key]))<3,`${label}: ${key} shifts after the browser releases its snapshot`);
          }
        } else if (fallback&&!options.interrupted) {
          const faded=samples.filter(s=>s.gridOpacity<1);
          assert(new Set(faded.map(s=>Math.round(s.gridOpacity*1000))).size>=4,`${label}: fallback opacity must animate over multiple frames`);
          assert(samples.at(-1)!.gridOpacity===1,`${label}: fallback must restore full opacity`);
        } else if (!options.interrupted && range>10) {
          assert(intermediateWidths>=4, `${label}: only ${intermediateWidths} intermediate widths were painted`);
          const duration = axis==='activity'?360:280;
          // cubic-bezier(.22,1,.36,1) has maximum slope 1/.22 at t=0.
          // CSS uses frame timeline time, not when layout reads finish.
          assert(changes.every((distance,index)=>intervals[index]>=50 || distance<=(1/.22)*range*intervals[index]/duration+2), `${label}: geometry moved faster than a continuous eased transition`);
        }
        assert(item.p95Ms<=Math.max(50,baselineMs*3), `${label}: p95 frame time ${item.p95Ms.toFixed(0)}ms exceeds idle baseline ${baselineMs.toFixed(1)}ms`);
        assert(item.maxFrameMs < 250, `${label}: main thread stalled ${item.maxFrameMs.toFixed(0)}ms`);
        if (options.enter&&!native&&!fallback) {
          assert(item.gridViewportTravel <= item.gridViewportRange + 12, `${label}: viewport moved down and back up (${item.gridViewportTravel.toFixed(0)}px travel, ${item.gridViewportRange.toFixed(0)}px range)`);
          assert(item.worldViewportTravel <= item.worldViewportRange + 12, `${label}: the iframe content moved down and back up (${item.worldViewportTravel.toFixed(0)}px travel, ${item.worldViewportRange.toFixed(0)}px range)`);
          assert(lastFrameJump < 48, `${label}: final cleanup moved world/composer ${lastFrameJump.toFixed(0)}px`);
        }
      }
    }
    try {
      const setup = { label: 'setup and idle baseline', startTime: performance.now(), endTime: Infinity };
      phases.push(setup);
      flushSync(() => {setActive(false);setCharacters(size);setChunk(0);setStreaming(false);});
      window.scrollTo({top:0,behavior:'instant'});
      await wait(1100);
      const baseline: number[]=[];
      await new Promise<void>(resolve=>{
        let previous=Number(document.timeline.currentTime)||performance.now();
        const frame=(time:number)=>{sample('ultrafast',time);baseline.push(time-previous);previous=time;if(baseline.length<20)requestAnimationFrame(frame);else resolve();};
        requestAnimationFrame(frame);
      });
      baseline.sort((a,b)=>a-b); baselineMs=baseline[Math.floor(baseline.length/2)];
      const frame = element.querySelector('iframe')!;
      const windowBefore = frame.contentWindow, sourceBefore = frame.srcdoc;
      const documentBefore = frame.contentDocument;
      const counter = documentBefore?.querySelector<HTMLButtonElement>('#counter');
      counter?.click();
      const valueBefore = counter?.textContent;
      const preserved = () => element.querySelector('iframe')===frame && frame.contentWindow===windowBefore && frame.srcdoc===sourceBefore
        && (responsive ? frame.contentDocument===null && frame.getBoundingClientRect().height>500 : frame.contentDocument===documentBefore && counter?.textContent===valueBefore);
      if(responsive) {
        assert(frame.contentDocument===null && !frame.sandbox.contains('allow-same-origin'), 'responsive world uses the production opaque sandbox');
        assert(frame.getBoundingClientRect().height>500, 'the real resize bridge has replaced its initial 120px height');
      }
      setup.endTime = performance.now();
      setStreaming(true);
      await trace('open comparison with live code', () => change(true), {axis:'gridWidth',duration:1000,assertStart:innerWidth>700});
      const button=element.querySelector('.finish-build-button')!, icon=button.querySelector('svg')!, label=button.querySelector('span')!;
      const buttonBox=button.getBoundingClientRect(), iconBox=icon.getBoundingClientRect(), labelBox=label.getBoundingClientRect();
      const contentLeft=iconBox.width>0?iconBox.left:labelBox.left;
      assert(Math.abs((contentLeft-buttonBox.left)-(buttonBox.right-labelBox.right))<4, 'Enter your world has balanced horizontal padding without unused icon space');
      const maxPadding = innerWidth >= 1100 ? 56 * Math.min(2, Math.max(.75, innerWidth / 1920)) + 3 : 55;
      assert(buttonBox.width-labelBox.width<maxPadding, 'Enter your world has compact proportional horizontal padding');
      for (let repetition=0; repetition<2; repetition++) for (const lane of ['ultrafast','standard'] as const) {
        const toggle = () => element.querySelector<HTMLButtonElement>(`.build-comparison-${lane} .comparison-activity-toggle`)!.click();
        await trace(`${lane} close ${repetition+1}`, toggle, {lane});
        await trace(`${lane} open ${repetition+1}`, toggle, {lane});
      }
      const preview = element.querySelector<HTMLElement>('.build-comparison-ultrafast .build-comparison-preview')!;
      preview.scrollTop = 900;
      assert(preview.scrollTop>300, 'the long world can scroll independently');
      await trace('enter from a scrolled world', () => change(false), {axis:'gridWidth',duration:1300,enter:true,assertStart:innerWidth>700});
      assert(preserved(), responsive ? 'Enter preserves the live opaque iframe and its resize bridge' : 'Enter preserves iframe, document, and interaction state');
      window.scrollTo({top:600,behavior:'instant'});
      await trace('split from a scrolled page', () => change(true), {axis:'gridWidth',duration:1100,assertStart:innerWidth>700});
      await trace('enter while page is scrolled', () => change(false), {axis:'gridWidth',duration:1300,enter:true,assertStart:innerWidth>700});
      assert(Math.abs(window.scrollY)<2,'Enter settles at the top of the completed world');
      window.scrollTo({top:0,behavior:'instant'});
      change(true); await wait(900);
      await trace('rapid sidebar reversal', () => {
        const toggle = () => element.querySelector<HTMLButtonElement>('.build-comparison-ultrafast .comparison-activity-toggle')!.click();
        toggle(); setTimeout(toggle,70); setTimeout(toggle,140); setTimeout(toggle,210);
      }, {duration:800,interrupted:true});
      await trace('rapid split reversal', () => {change(false);setTimeout(()=>change(true),80);setTimeout(()=>change(false),160);}, {axis:'gridWidth',duration:1400,assertStart:innerWidth>700,interrupted:true});
      assert(!element.querySelector('.build-comparison[data-morphing]'), 'rapid reversal settles and clears animation state');
      assert(!document.documentElement.hasAttribute('data-world-transition')&&!document.getAnimations().some(animation=>(animation.effect as KeyframeEffect & {pseudoElement?:string})?.pseudoElement?.startsWith('::view-transition')), 'snapshot pseudo-elements and transition attributes are cleaned up');
      assert(preserved(), 'all repeated transitions preserve the live iframe');
      assert(element.scrollWidth<=element.clientWidth+1, 'pressure layout does not overflow horizontally');
      completed = true;
    } catch(error) {setResult(`FAIL: ${error instanceof Error?error.message:String(error)}`);}
    finally {
      const teardown = { label: 'final frame and teardown', startTime: performance.now(), endTime: Infinity };
      phases.push(teardown);
      setStreaming(false);
      // The final trace resolves from rAF. Let that render finish before draining
      // observers, otherwise its LoAF entry has not been constructed yet.
      await new Promise<void>(resolve => requestAnimationFrame(() => setTimeout(resolve, 0)));
      teardown.endTime = performance.now();
      collectTasks(observer?.takeRecords() || []); collectFrames(frameObserver?.takeRecords() || []);
      observer?.disconnect(); frameObserver?.disconnect();
      const attribute = <T extends { startTime: number; duration: number }>(entry: T): DiagnosticEntry<T> => ({ ...entry, phases: phases.filter(phase => entry.startTime < phase.endTime && entry.startTime + entry.duration > phase.startTime).map(phase => phase.label) });
      setDiagnostics({ timeOrigin: performance.timeOrigin, supported, attributionLimitations: 'LoAF attributes main-thread page and same-origin iframe scripts over 5ms. Extension isolated worlds, cross-origin frames, workers, and unattributed browser work may affect duration without script attribution. Empty attribution does not establish the cause.', longTasks: slowTasks.map(attribute), longAnimationFrames: slowFrames.map(attribute) });
      if (completed) setResult(`${failures.length?'FAIL':'PASS'}: ${checks} checks, ${size.toLocaleString()} initial chars/lane, ${innerWidth}×${innerHeight}${responsive?' (responsive GeneratedFrame)':''}${reduced?' (JS reduced motion)':''}; idle ${baselineMs.toFixed(1)}ms, ${longTasks.length} long tasks, max ${Math.max(0,...longTasks).toFixed(0)}ms${failures.length?`; ${failures.join('; ')}`:''}`);
      setRunning(false);setReport(traces);
    }
  }

  return <div ref={root} className={`app-shell canvas-workspace${visual?' with-build-comparison':''}`}>
    <header className="topbar"><strong>Animation pressure fixture{responsive?' · Responsive iframe':''}</strong><span>No APIs · {characters.toLocaleString()} chars + {chunk} streamed chunks</span></header>
    <aside data-pressure-controls style={{position:'fixed',top:4,left:10,zIndex:1000,padding:8,maxWidth:'min(700px,95vw)',background:'#14202fee',color:'#fff',font:'12px system-ui'}}>
      <button disabled={running} onClick={()=>void run(30_000)}>Run 30k pressure checks</button>{' '}
      <button disabled={running} onClick={()=>void run(100_000)}>Run 100k pressure checks</button>{' '}
      <button disabled={running} onClick={()=>change(!active)}>{active?'Enter your world':'Split screen'}</button>{' '}
      <label><input type="checkbox" checked={streaming} onChange={event=>setStreaming(event.target.checked)}/>Stream output</label>
      <output data-pressure-result data-pressure-report={JSON.stringify(report)} data-pressure-diagnostics={JSON.stringify(diagnostics)} style={{display:'block',maxHeight:90,overflow:'auto'}}>{result}</output>
    </aside>
    <div className="workspace"><main className="space-main personal-canvas">
      <div className="workspace-chrome" data-collapsed={visual} aria-hidden={visual} inert={visual}><div className="workspace-chrome-content">
        <div className="space-toolbar"><div className="toolbar-right"><button>Thread</button><button>History</button></div></div>
        <div className="studio-intro" style={{height:70}}>Pressure test world</div>
      </div></div>
      <BuildComparison active={active} primaryInteractive onTransitionChange={setMorphing} onLayoutChange={setLayoutActive} ultrafast={{status:'completed',model:'gpt-6-astra'}} standard={{status:'running',model:'gpt-6-astra'}} ultrafastActivity={active||layoutActive||morphing?panel('Ultrafast'):null} standardActivity={active||layoutActive||morphing?panel('Standard'):null} standardPreview={<div style={{padding:32}}>Standard world preview</div>}>
        {responsive ? <GeneratedFrame html={responsiveMarkup} renderVersion={1} onAction={async()=>({ok:true})} pending={false}/>
          : <iframe title="Persistent pressure world" srcDoc={frameMarkup} style={{width:'100%',height:2800,border:0,display:'block'}}/>}
      </BuildComparison>
      <div className="composer-area"><div className="composer-slot"><div className="comparison-composer-row">
        <form className="composer" onSubmit={event=>event.preventDefault()}><textarea rows={1} aria-label="Draft next request" placeholder="Draft your next idea…"/></form>
        {layoutActive&&<button className="finish-build-button" onClick={()=>change(false)}><ArrowUpRight size={17}/><span>Enter your world</span></button>}
      </div></div></div>
    </main></div>
  </div>;
}
const fixtureRoot=createRoot(document.getElementById('root')!);
fixtureRoot.render(<StrictMode><Fixture/></StrictMode>);
import.meta.hot?.dispose(()=>fixtureRoot.unmount());
