// Isolated layout and animation checks. No API, microphone, or model calls.
import { StrictMode, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import BuildComparison from '../../src/BuildComparison';
import { BuildActivityPanel } from '../../src/BuildActivityPanel';
import '../../src/fonts.css';
import '../../src/styles.css';
import '../../src/canvas-workspace.css';
import '../../src/theme.css';
import '../../src/presentation.css';

// A deterministic reduced-motion fixture without changing the user's OS settings.
if (new URLSearchParams(location.search).has('reduce')) {
  const match = window.matchMedia.bind(window);
  window.matchMedia = query => {
    const media = match(query);
    if (query === '(prefers-reduced-motion: reduce)') Object.defineProperty(media, 'matches', { value: true });
    return media;
  };
}

const frameMarkup = '<!doctype html><html><body style="margin:0;background:#070d14;color:white;font:20px sans-serif"><main style="padding:60px"><h1>A world that stays alive</h1><button id="state" onclick="this.textContent=Number(this.textContent)+1">0</button><p>Its iframe and state survive the split.</p></main></body></html>';
const sleep = (time: number) => new Promise(resolve => window.setTimeout(resolve, time));
const entries = [{ id: 'fixture-code', time: new Date().toISOString(), turnId: 'fixture-turn', kind: 'tool' as const, title: 'apply_patch', tool: 'apply_patch', inputFormat: 'patch' as const, status: 'running' as const, arguments: '*** Begin Patch\n*** Add File: space.js\n' + Array.from({ length: 90 }, (_, index) => `+const orbit_${index} = ${index};`).join('\n') }];

function Fixture() {
  const [active, setActive] = useState(false);
  const [result, setResult] = useState('Ready');
  const [running, setRunning] = useState(false);
  const [frameHeight, setFrameHeight] = useState(430);
  const [primaryComplete, setPrimaryComplete] = useState(false);
  const [primaryPublished, setPrimaryPublished] = useState(false);
  const transitioning = useRef(false);
  const root = useRef<HTMLDivElement>(null);
  const stats = { model: 'gpt-6-astra', status: 'running' as const, elapsedMs: 1250 };
  const panel = (name: string) => <BuildActivityPanel embedded label={`${name} activity`} entries={entries} busy connected model="gpt-6-astra" tier={name} onClose={() => {}}/>;
  const change = (value: boolean) => flushSync(() => setActive(value));

  async function check() {
    if (running) return;
    setRunning(true);
    const failures: string[] = [];
    let checks = 0;
    const assert = (ok: boolean, text: string) => { checks++; if (!ok) failures.push(text); };
    const element = root.current!;
    change(false);
    flushSync(() => { setFrameHeight(1800); setPrimaryComplete(false); setPrimaryPublished(false); });
    await sleep(850);
    const frame = element.querySelector('iframe')!;
    const frameDocument = frame.contentDocument!;
    const counter = frameDocument.querySelector<HTMLButtonElement>('#state')!;
    counter.click();
    let original = counter.textContent;
    const focus = element.querySelector<HTMLButtonElement>('[data-toggle]')!;
    focus.focus();
    const widths = new Set<number>();
    const snapshotProgress = new Set<number>();
    const intervals: number[] = [];
    const geometryProblems = new Set<string>();
    let sampling = true;
    let inspectHeightContinuity = !matchMedia('(prefers-reduced-motion: reduce)').matches;
    let previousFrame = 0;
    let previousLayout = { time: performance.now(), height: element.querySelector('.build-comparison-grid')!.getBoundingClientRect().height };
    const sampleFrames = (time: number) => {
      const container = element.querySelector('.build-comparison')!;
      const first = element.querySelector('.build-comparison-ultrafast')!;
      const second = element.querySelector('.build-comparison-standard')!;
      const a = first.getBoundingClientRect(), b = second.getBoundingClientRect();
      const overall = container.getBoundingClientRect();
      const layoutHeight = element.querySelector('.build-comparison-grid')!.getBoundingClientRect().height;
      const frameTime = time - previousLayout.time;
      const snapshotAnimation = document.getAnimations().find(animation => (animation.effect as (KeyframeEffect & {pseudoElement?: string}) | null)?.pseudoElement === '::view-transition-group(comparison-world)');
      const nativeTransition = document.documentElement.hasAttribute('data-world-transition');
      if (snapshotAnimation) {
        const progress = snapshotAnimation.effect?.getComputedTiming().progress;
        if (progress !== null && progress !== undefined) snapshotProgress.add(Math.round(progress * 1000));
        const width = parseFloat(getComputedStyle(document.documentElement, '::view-transition-group(comparison-world)').width);
        if (Number.isFinite(width)) widths.add(Math.round(width));
      }
      // The 2,100px fixture can move more than 400px across two display frames
      // during its eased height reveal; judge continuity against elapsed time.
      // Native transitions commit final DOM geometry behind browser snapshots.
      // Their painted trajectory is measured above, not by the hidden DOM jump.
      if (inspectHeightContinuity && !nativeTransition && frameTime < 40 && Math.abs(layoutHeight - previousLayout.height) > Math.max(400, frameTime * 16)) geometryProblems.add(`tall world or composer jumps ${Math.round(Math.abs(layoutHeight - previousLayout.height))}px in ${frameTime.toFixed(1)}ms (${Math.round(previousLayout.height)} to ${Math.round(layoutHeight)}, ${container.getAttribute('data-morphing') || 'settled'})`);
      previousLayout = { time, height: layoutHeight };
      if (container.hasAttribute('data-morphing')) {
        if (previousFrame) intervals.push(time - previousFrame);
        previousFrame = time;
        if (!nativeTransition) widths.add(Math.round(a.width));
        const overlapX = Math.min(a.right, b.right) - Math.max(a.left, b.left);
        const overlapY = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top);
        if (b.width > 2 && b.height > 2 && overlapX > 1 && overlapY > 1) geometryProblems.add('lane shells overlap during a transition');
        if (innerWidth > 700 && b.width > overall.width / 2 + 2) geometryProblems.add('Standard briefly grows beyond its half');
        for (const lane of [first, second]) {
          const transform = getComputedStyle(lane).transform;
          if (transform !== 'none') {
            const matrix = new DOMMatrixReadOnly(transform);
            if (Math.abs(matrix.a - 1) > .001 || Math.abs(matrix.d - 1) > .001) geometryProblems.add('a live world is scaled during a transition');
          }
        }
      } else previousFrame = 0;
      if (sampling) requestAnimationFrame(sampleFrames);
    };
    requestAnimationFrame(sampleFrames);
    change(true);
    setTimeout(() => flushSync(() => setFrameHeight(2100)), 180);
    await sleep(100);
    assert(element.querySelector('.build-comparison')?.getAttribute('data-comparing') === 'true', 'split is active');
    assert(document.activeElement === focus, 'opening streams does not steal focus');
    assert(element.querySelector('.build-comparison-world')?.hasAttribute('inert') === true, 'preview content is inert while the outer preview can scroll');
    await sleep(850);
    const lanes = [...element.querySelectorAll<HTMLElement>('.build-comparison-lane')];
    const rects = lanes.map(lane => lane.getBoundingClientRect());
    assert(Math.abs(rects[0].width - rects[1].width) < 1, 'lanes have equal width');
    assert(Math.abs(rects[0].height - rects[1].height) < 1, 'lanes have equal height');
    assert(element.scrollWidth <= element.clientWidth + 1, 'layout has no horizontal overflow');
    assert(element.querySelector('iframe') === frame && frame.contentDocument === frameDocument, 'iframe survives split');
    const dimensions = (node: Element) => {
      const box = node.getBoundingClientRect();
      return { width: box.width, height: box.height, left: box.left, right: box.right, top: box.top };
    };
    for (const [index, lane] of lanes.entries()) {
      const name = index ? 'Standard' : 'Ultrafast';
      const preview = lane.querySelector<HTMLElement>('.build-comparison-preview')!;
      const activity = lane.querySelector<HTMLElement>('.build-comparison-activity')!;
      const panel = activity.querySelector<HTMLElement>('.build-activity-panel')!;
      const laneBox = lane.getBoundingClientRect();
      const previewBox = preview.getBoundingClientRect();
      const panelBox = panel.getBoundingClientRect();
      const headingBox = lane.querySelector('.build-comparison-heading')!.getBoundingClientRect();
      const mirrored = name === 'Standard';
      const identity = lane.querySelector('.build-comparison-identity')!;
      const identityBox = identity.getBoundingClientRect();
      const statusBox = lane.querySelector('.build-comparison-status')!.getBoundingClientRect();
      const headingPadding = parseFloat(getComputedStyle(lane.querySelector('.build-comparison-heading')!).paddingInlineStart);
      assert(mirrored ? Math.abs(identityBox.left - headingBox.left - headingPadding) <= 2 && identityBox.right < statusBox.left
        : Math.abs(headingBox.right - identityBox.right - headingPadding) <= 2 && statusBox.right < identityBox.left,
      `${name} label sits above its Activity side while status remains separate`);
      assert(getComputedStyle(identity).textAlign === (mirrored ? 'start' : 'right'), `${name} model and label share the intended alignment`);
      const spinner = lane.querySelector('.build-comparison-status-label .build-comparison-spinner');
      assert(!!spinner && spinner.getAttribute('aria-hidden') === 'true', `${name} running status has a decorative activity spinner`);
      assert((mirrored
        ? Math.abs(previewBox.right - (laneBox.right - 1)) <= 2 && panelBox.right <= previewBox.left + 1
        : Math.abs(previewBox.left - (laneBox.left + 1)) <= 2 && previewBox.right <= panelBox.left + 1) && previewBox.width > panelBox.width,
      `${name} world sits ${mirrored ? 'right' : 'left'} of Activity without covered content`);
      assert(Math.abs(previewBox.top - headingBox.bottom) <= 2 && Math.abs(previewBox.bottom - (laneBox.bottom - 1)) <= 2, `${name} world fills the lane below its header`);
      assert(previewBox.height > laneBox.height * .7, `${name} world occupies most of the lane height`);
      const displayUnit = Math.min(2, Math.max(.75, innerWidth / 1920));
      const panelCap = innerWidth >= 1100 ? 360 * displayUnit : 320;
      assert(panelBox.width > 0 && panelBox.width <= laneBox.width * .36 + 1 && panelBox.width <= panelCap + 1, `${name} Activity reserves at most 36% of its lane and obeys the responsive cap`);
      assert(mirrored ? Math.abs(panelBox.left - (laneBox.left + 1)) <= 2 : Math.abs(panelBox.right - (laneBox.right - 1)) <= 2, `${name} Activity is aligned with the ${mirrored ? 'left' : 'right'} edge`);
      assert(Math.abs(panelBox.top - previewBox.top) <= 2 && Math.abs(panelBox.bottom - previewBox.bottom) <= 2, `${name} Activity and world share aligned top and bottom edges`);
      assert(getComputedStyle(activity).backgroundColor !== getComputedStyle(preview).backgroundColor, `${name} sidebar has a distinct surface color`);
      const close = lane.querySelector<HTMLButtonElement>(`button[aria-label="Hide ${name} activity"]`);
      assert(!!close && close.getAttribute('aria-expanded') === 'true' && !close.closest('[inert]'), `${name} Activity opens automatically with an accessible collapse button`);
      const toggleBox = close!.getBoundingClientRect();
      assert(mirrored ? Math.abs(toggleBox.left - panelBox.right) <= 2 : Math.abs(toggleBox.right - panelBox.left) <= 2, `${name} Activity toggle sits outside the transcript on its world-facing edge`);
      assert(Math.min(toggleBox.right, panelBox.right) - Math.max(toggleBox.left, panelBox.left) <= 1, `${name} Activity toggle never covers transcript text`);
      assert(!!close!.querySelector(mirrored ? '.lucide-chevron-left' : '.lucide-chevron-right'), `${name} collapse arrow points toward its sidebar edge`);
      const before = dimensions(preview);
      if (close) {
        close.click();
        await sleep(450);
        const open = lane.querySelector<HTMLButtonElement>(`button[aria-label="Show ${name} activity"]`);
        assert(!!open && open.getAttribute('aria-expanded') === 'false', `${name} Activity can be collapsed`);
        const collapsed = dimensions(preview);
        assert(collapsed.width > before.width + 40 && [mirrored ? 'right' : 'left', 'top', 'height'].every(key => Math.abs(before[key as keyof typeof before] - collapsed[key as keyof typeof collapsed]) < 1), `${name} collapsing Activity smoothly expands the world without moving its outer edge`);
        assert(frame.contentDocument === frameDocument && counter.textContent === original, `${name} collapse preserves the primary iframe and its state`);
        if (open) {
          open.click();
          await sleep(450);
          assert(!!lane.querySelector(`button[aria-label="Hide ${name} activity"]`), `${name} Activity can reopen`);
          const reopened = dimensions(preview);
          assert(Object.keys(before).every(key => Math.abs(before[key as keyof typeof before] - reopened[key as keyof typeof reopened]) < 1), `${name} reopening Activity leaves world geometry unchanged`);
        }
      }
    }
    const primaryWorld = element.querySelector('.build-comparison-primary .build-comparison-world')!;
    assert(!element.querySelector('.build-comparison-ratio'), 'comparison omits misleading output percentages');
    flushSync(() => setPrimaryComplete(true));
    assert(primaryWorld.hasAttribute('inert'), 'completion telemetry alone does not unlock an unpublished world');
    flushSync(() => setPrimaryPublished(true));
    assert(!primaryWorld.hasAttribute('inert'), 'published completed Ultrafast world is interactive while still split');
    counter.focus();
    assert(frameDocument.activeElement === counter, 'completed primary iframe accepts focus before leaving comparison');
    counter.click();
    original = counter.textContent;
    assert(element.querySelector('.build-comparison')?.getAttribute('data-comparing') === 'true' && frame.contentDocument === frameDocument, 'interactive primary world remains mounted inside comparison');
    assert(element.querySelector('.build-comparison-standard .build-comparison-world')?.hasAttribute('inert') === true, 'Standard preview stays read-only after primary completes');
    flushSync(() => { setPrimaryComplete(false); setPrimaryPublished(false); });
    assert(primaryWorld.hasAttribute('inert'), 'a new pending primary build relocks the world');
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) {
      assert(element.querySelector('.build-comparison')?.getAttribute('data-morphing') === null, 'reduced motion skips morph');
    } else if (innerWidth > 700) {
      assert(widths.size >= 5 || snapshotProgress.size >= 5, `split visibly animates across frames (${widths.size} distinct widths, ${snapshotProgress.size} snapshot positions)`);
    }
    change(false);
    await sleep(850);
    assert(element.querySelector('.build-comparison-world')?.hasAttribute('inert') === false, 'finished world is interactive');
    assert(frame.contentDocument === frameDocument && counter.textContent === original, 'world state survives merge');
    assert(element.querySelector('.build-comparison')?.getAttribute('data-morphing') === null, 'merge animation cleans up');
    change(true);
    await sleep(850);
    for (const name of ['Ultrafast', 'Standard']) {
      const close = element.querySelector<HTMLButtonElement>(`button[aria-label="Hide ${name} activity"]`);
      close?.click();
    }
    await sleep(50);
    change(false);
    await sleep(850);
    change(true);
    await sleep(850);
    assert(['Ultrafast', 'Standard'].every(name => !!element.querySelector(`button[aria-label="Hide ${name} activity"]`)), 'a fresh comparison automatically reopens both Activity sidebars');
    change(false);
    await sleep(100);
    const opacityBeforeReversal = Number(getComputedStyle(element.querySelector('.build-comparison-standard')!).opacity);
    change(true);
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
      const opacityAfterReversal = Number(getComputedStyle(element.querySelector('.build-comparison-standard')!).opacity);
      assert(Math.abs(opacityBeforeReversal - opacityAfterReversal) < .05, 'reversing a morph preserves the visible lane opacity without flashing');
    }
    await sleep(850);
    assert(element.querySelector('.build-comparison')?.getAttribute('data-morphing') === null, 'interrupted animation cleans up');
    assert(frame.contentDocument === frameDocument, 'iframe survives interrupted transitions');
    // A viewport resize intentionally settles to the destination immediately.
    inspectHeightContinuity = false;
    window.dispatchEvent(new Event('resize'));
    change(false);
    await sleep(60);
    window.dispatchEvent(new Event('resize'));
    await sleep(40);
    assert(element.querySelector('.build-comparison')?.getAttribute('data-morphing') === null, 'resize settles the animation');
    assert(element.scrollWidth <= element.clientWidth + 1, 'merged layout has no horizontal overflow');
    sampling = false;
    assert(geometryProblems.size === 0, [...geometryProblems].join('; ') || 'lane geometry stays clipped, unscaled, and separate throughout every animation frame');
    assert(!transitioning.current, 'parent receives the settled transition state');
    const sorted = intervals.filter(value => value > 0 && value < 1000).sort((a, b) => a - b);
    const median = sorted[Math.floor(sorted.length / 2)] || 0;
    const p95 = sorted[Math.floor(sorted.length * .95)] || 0;
    setResult(`${failures.length ? 'FAIL' : 'PASS'}: ${checks} checks; ${sorted.length} animation frames, median ${median.toFixed(1)}ms, p95 ${p95.toFixed(1)}ms${failures.length ? `; ${failures.join('; ')}` : ''}`);
    setRunning(false);
  }

  return <div ref={root} style={{ padding: 24, maxWidth: 1440, margin: 'auto' }}>
    <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginBottom: 20 }}>
      <button data-check disabled={running} onClick={() => void check()}>Run layout checks</button>
      <button data-toggle onClick={() => setActive(current => !current)}>Toggle comparison</button>
      <output data-testid="comparison-layout-result">{result}</output>
    </div>
    <BuildComparison onTransitionChange={value => { transitioning.current = value; }} active={active} primaryInteractive={primaryPublished} ultrafast={{ ...stats, status: primaryComplete ? 'completed' : 'running' }} standard={stats} ultrafastActivity={panel('Ultrafast')} standardActivity={panel('Standard')}
      standardPreview={<div style={{ padding: 40, color: '#bb91ff' }}><h2>Standard preview</h2><p>The same request, still taking shape.</p></div>}>
      <iframe title="Persistent test world" srcDoc={frameMarkup} style={{ border: 0, width: '100%', height: frameHeight, display: 'block' }}/>
    </BuildComparison>
    <div data-fixture-composer style={{ marginTop: 16, padding: 20, border: '1px solid #343c4d' }}>Composer stays below both worlds</div>
  </div>;
}

const fixtureRoot = createRoot(document.getElementById('root')!);
fixtureRoot.render(<StrictMode><Fixture/></StrictMode>);
import.meta.hot?.dispose(() => fixtureRoot.unmount());
