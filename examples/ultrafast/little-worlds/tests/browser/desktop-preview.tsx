// Real sandboxed frames and comparison layout. No server, model, or saved data.
// Run at 1920×1080, 1366×768, 3840×2160, and 390×844, with ?reduce as well.
import { StrictMode, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import BuildComparison from '../../src/BuildComparison';
import { BuildActivityPanel } from '../../src/BuildActivityPanel';
import GeneratedFrame from '../../src/GeneratedFrame';
import { getVoiceFrame } from '../../src/voice-frame-registry';
import type { FrameVoiceSurface } from '../../src/voice-frame-registry';
import '../../src/fonts.css';
import '../../src/styles.css';
import '../../src/canvas-workspace.css';
import '../../src/theme.css';
import '../../src/presentation.css';

if (new URLSearchParams(location.search).has('reduce')) {
  const original = window.matchMedia.bind(window);
  window.matchMedia = query => {
    const result = original(query);
    if (query === '(prefers-reduced-motion: reduce)') Object.defineProperty(result, 'matches', { value: true });
    return result;
  };
}

const worldHtml = `<style>
  .preview-fixture{box-sizing:border-box;background:#080c14;color:#f4f7ff;font:24px/1.5 Arial,sans-serif;padding:32px}
  .preview-fixture *{box-sizing:border-box}
  .preview-fixture h1{font-size:52px;line-height:1.1;margin:0 0 16px}.preview-fixture h2{font-size:30px}
  .preview-fixture p{margin:0 0 16px}.preview-fixture .tiles{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:28px}
  .preview-fixture .tile{padding:28px;background:#132b29;border:2px solid #28754c;border-radius:16px;min-width:0}
  .preview-fixture .tile:nth-child(2){background:#272034;border-color:#8157b5}
  .preview-fixture .orb{width:130px;aspect-ratio:1;border-radius:50%;background:linear-gradient(135deg,#63e68e,#5645b7);margin:24px auto}
  .preview-fixture input,.preview-fixture button{font:inherit;padding:12px;max-width:100%}
  .preview-fixture input{display:block;width:100%;color:#fff;background:#111;border:1px solid #8299a6}
  .preview-fixture button{background:#20c968;color:#041b0b;border:0;border-radius:5px;cursor:pointer}
  .preview-fixture .phone-layout{display:none}.preview-fixture .tall-content{height:5000px;background:linear-gradient(#101924,#192338);margin-top:28px;padding:28px}
  .preview-fixture details{margin-top:24px}.preview-fixture summary{cursor:pointer}.preview-fixture .expanded-content{height:800px;padding:28px;background:#302943}
  .preview-fixture footer{padding-top:24px}
  @media(max-width:1050px){.preview-fixture .tiles{grid-template-columns:minmax(0,1fr)}.preview-fixture .desktop-layout{display:none}.preview-fixture .phone-layout{display:block}}
</style><main class="preview-fixture"><h1>Two tiles. One world.</h1>
  <p class="desktop-layout">Desktop arrangement: second tile to the right.</p><p class="phone-layout">Narrow arrangement: second tile underneath.</p>
  <div class="tiles"><section class="tile"><h2>Left tile</h2><p>This is the first tile.</p><label>Keep this note<input aria-label="Keep this note" value=""/></label><div class="orb"></div><button data-action='{"type":"first-tile"}'>Use left tile</button></section>
  <section class="tile"><h2>Right tile</h2><p>This tile belongs beside the first.</p><div class="orb"></div><button data-action='{"type":"second-tile"}'>Use right tile</button></section></div>
  <details><summary>Expand extra world content</summary><section class="expanded-content"><h2>Expanded world content</h2><p>This adds exactly 800 logical pixels without replacing the iframe.</p></section></details>
  <section class="tall-content"><h2>Scroll through this world</h2><p>The scaled preview must reserve only its visible height.</p></section>
  <footer><button data-action='{"type":"bottom"}'>Use bottom action</button></footer></main>`;

const entries = [{ id: 'preview-patch', time: new Date().toISOString(), turnId: 'preview-turn', kind: 'tool' as const, title: 'apply_patch', tool: 'apply_patch', inputFormat: 'patch' as const, status: 'completed' as const, arguments: '*** Begin Patch\n*** Update File: space.js\n+// Two tiles, side by side.\n*** End Patch' }];
const wait = (milliseconds: number) => new Promise(resolve => setTimeout(resolve, milliseconds));
async function until(test: () => boolean, label: string, timeout = 6000) {
  const end = performance.now() + timeout;
  while (performance.now() < end) {
    if (test()) return;
    await wait(25);
  }
  throw new Error(label);
}
async function surface(): Promise<FrameVoiceSurface> {
  const end = performance.now() + 6000;
  while (performance.now() < end) {
    const frame = getVoiceFrame();
    if (frame) {
      try { return await frame.read(); } catch { /* Wait for published-frame configuration. */ }
    }
    await wait(25);
  }
  throw new Error('Published world voice surface did not become ready');
}

function Fixture() {
  const [active, setActive] = useState(false);
  const [published, setPublished] = useState(true);
  const [standardContent, setStandardContent] = useState(true);
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState('Ready');
  const [actionCount, setActionCount] = useState(0);
  const actions = useRef(0);
  const root = useRef<HTMLDivElement>(null);
  const checkRoot = useRef<HTMLDivElement>(null);
  const transition = useRef(false);
  const panel = (name: string) => <BuildActivityPanel embedded label={`${name} activity`} entries={entries} busy={false} connected model="gpt-6-astra" tier={name} onClose={() => {}}/>;
  const change = (next: boolean) => flushSync(() => setActive(next));
  const settle = async () => {
    await wait(60);
    await until(() => !transition.current && !root.current?.querySelector('[data-morphing]'), 'World transition did not finish');
    await wait(100);
  };

  async function check() {
    if (running) return;
    setRunning(true);
    setReport('Running');
    const failures: string[] = [];
    const measurements: Record<string, unknown>[] = [];
    let checks = 0;
    const assert = (pass: boolean, message: string) => { checks++; if (!pass) failures.push(message); };
    try {
      change(false);
      flushSync(() => { setPublished(true); setStandardContent(true); });
      await settle();
      root.current!.scrollIntoView({ block: 'start', behavior: 'instant' });
      const primaryFrame = root.current!.querySelector<HTMLIFrameElement>('.build-comparison-ultrafast iframe')!;
      await until(() => primaryFrame.clientHeight > 2000, 'Tall world did not finish sizing');
      const frameWindow = primaryFrame.contentWindow;
      const frameSource = primaryFrame.srcdoc;
      const finalWidth = primaryFrame.clientWidth;
      const before = await surface();
      const note = before.controls.find(control => control.label === 'Keep this note');
      assert(!!note, 'Published world exposes its note control');
      if (note) assert((await getVoiceFrame()!.execute({ type: 'fill', id: note.id, value: 'Keep my live input across the split' }, before.version)).ok, 'Native input can be filled before splitting');
      const desktop = finalWidth > 1050;
      assert(before.text.includes(desktop ? 'second tile to the right' : 'second tile underneath'), 'Baseline layout follows the final world viewport');
      flushSync(() => setPublished(false));
      change(true);
      await settle();
      const lanes = [...root.current!.querySelectorAll<HTMLElement>('.build-comparison-lane')];
      const frames = lanes.map(lane => lane.querySelector<HTMLIFrameElement>('iframe')!);
      await until(() => frames.every(frame => frame.clientHeight > 2000), 'Both preview frames did not finish sizing');
      assert(lanes.length === 2, 'Both build lanes are present');
      for (const [index, lane] of lanes.entries()) {
        const name = index === 0 ? 'Ultrafast' : 'Standard';
        const frame = frames[index];
        const preview = lane.querySelector<HTMLElement>('.build-comparison-preview')!;
        const logical = frame.clientWidth;
        const bounds = frame.getBoundingClientRect();
        const scale = bounds.width / logical;
        measurements.push({ lane: name, logical, finalWidth, visibleWidth: bounds.width, scale, scrollHeight: preview.scrollHeight, visibleHeight: bounds.height });
        assert(Math.abs(logical - finalWidth) <= 1, `${name} uses the same logical width as the finished world`);
        assert(Math.abs(bounds.width - preview.clientWidth) <= 2, `${name} fits the available pane without clipping or horizontal blank space`);
        assert(scale > 0 && scale < 1, `${name} scales the world down inside its comparison pane`);
        assert(Math.abs(bounds.height / frame.clientHeight - scale) < .002, `${name} uses uniform scaling so circles remain round`);
        assert(preview.scrollWidth <= preview.clientWidth + 1, `${name} has no horizontal overflow`);
        assert(Math.abs(preview.scrollHeight - Math.max(preview.clientHeight, bounds.height)) <= 3, `${name} scroll range matches its scaled content with no unscaled blank tail`);
        assert(lane.querySelector('.build-comparison-world')!.hasAttribute('inert'), `${name} is inert while building`);
        preview.scrollTop = preview.scrollHeight;
        await wait(40);
        const atBottom = frame.getBoundingClientRect();
        const previewBottom = preview.getBoundingClientRect().top + preview.clientHeight;
        assert(Math.abs(atBottom.bottom - previewBottom) <= 3, `${name} bottom action remains reachable at the end of its scroll range`);
        preview.scrollTop = 0;
        const close = lane.querySelector<HTMLButtonElement>(`button[aria-label="Hide ${name} activity"]`)!;
        close.click();
        await wait(460);
        assert(frame.clientWidth === logical, `${name} Activity collapse does not change the responsive breakpoint`);
        assert(frame.getBoundingClientRect().width > bounds.width + 20, `${name} Activity collapse enlarges the same layout`);
        assert(Math.abs(frame.getBoundingClientRect().width - preview.clientWidth) <= 2, `${name} expanded preview still fits its pane`);
        lane.querySelector<HTMLButtonElement>(`button[aria-label="Show ${name} activity"]`)!.click();
        await wait(460);
        assert(frame.clientWidth === logical, `${name} Activity reopen preserves the logical viewport`);
        assert(Math.abs(frame.getBoundingClientRect().width - bounds.width) <= 2, `${name} returns to the original visual size`);
      }
      assert(frames[0].clientWidth === frames[1].clientWidth, 'Both variants are compared at an identical logical viewport');
      assert(primaryFrame === root.current!.querySelector('.build-comparison-ultrafast iframe') && primaryFrame.contentWindow === frameWindow && primaryFrame.srcdoc === frameSource, 'Entering comparison preserves the primary iframe instance and document');
      flushSync(() => setPublished(true));
      const splitSurface = await surface();
      assert(splitSurface.text.includes(desktop ? 'second tile to the right' : 'second tile underneath'), 'Published split preview retains the final world responsive layout');
      assert(splitSurface.controls.find(control => control.label === 'Keep this note')?.value === 'Keep my live input across the split', 'Live input state survives entering comparison');
      assert(!lanes[0].querySelector('.build-comparison-world')!.hasAttribute('inert'), 'Published completed Ultrafast is interactive before entering the world');
      assert(lanes[1].querySelector('.build-comparison-world')!.hasAttribute('inert') && frames[1].hasAttribute('inert'), 'Standard remains inert at both host and sandbox boundaries');
      const leftAction = splitSurface.controls.find(control => control.label === 'Use left tile');
      const previousActions = actions.current;
      assert(!!leftAction, 'Voice finds the scaled primary action');
      if (leftAction) assert((await getVoiceFrame()!.execute({ type: 'click', id: leftAction.id }, splitSurface.version)).ok, 'Scaled primary action accepts a voice click');
      await until(() => actions.current > previousActions, 'Scaled primary action did not reach the host');
      assert(actions.current === previousActions + 1, 'Scaled primary action runs exactly once');
      const primaryPreview = lanes[0].querySelector<HTMLElement>('.build-comparison-preview')!;
      const compactHeight = primaryFrame.clientHeight;
      const compactFootprint = primaryPreview.scrollHeight;
      const disclosureSurface = await surface();
      const disclosure = disclosureSurface.controls.find(control => control.label === 'Expand extra world content');
      assert(!!disclosure && disclosure.expanded === false, 'The native disclosure starts collapsed');
      if (disclosure) assert((await getVoiceFrame()!.execute({ type: 'click', id: disclosure.id }, disclosureSurface.version)).ok, 'Native disclosure can expand inside the scaled preview');
      await until(() => primaryFrame.clientHeight >= compactHeight + 799, 'Expanded disclosure did not increase the frame height');
      await wait(80);
      assert(primaryFrame.clientWidth === finalWidth, 'Native content growth keeps the logical viewport width');
      const grownBounds = primaryFrame.getBoundingClientRect();
      const grownScale = grownBounds.width / primaryFrame.clientWidth;
      assert(Math.abs(primaryFrame.clientHeight - compactHeight - 800) <= 1, 'Native disclosure adds its authored logical height');
      assert(Math.abs(primaryPreview.scrollHeight - compactFootprint - 800 * grownScale) <= 3, 'Native growth adds only its scaled height to the outer scroll range');
      assert(Math.abs(primaryPreview.scrollHeight - Math.max(primaryPreview.clientHeight, grownBounds.height)) <= 3, 'Expanded content has no unscaled blank scroll tail');
      primaryPreview.scrollIntoView({ block: 'end', behavior: 'instant' });
      primaryPreview.scrollTop = primaryPreview.scrollHeight;
      await wait(80);
      const bottomSurface = await surface();
      assert(bottomSurface.controls[0]?.label === 'Use bottom action', 'Voice prioritizes the visible bottom action after scrolling the clipped scaled preview');
      const closeDisclosure = bottomSurface.controls.find(control => control.label === 'Expand extra world content');
      assert(closeDisclosure?.expanded === true, 'Native disclosure remains open while scrolling');
      if (closeDisclosure) assert((await getVoiceFrame()!.execute({ type: 'click', id: closeDisclosure.id }, bottomSurface.version)).ok, 'Offscreen native disclosure can collapse through its current voice control');
      await until(() => primaryFrame.clientHeight === compactHeight, 'Collapsed disclosure did not restore the frame height');
      await wait(80);
      assert(Math.abs(primaryPreview.scrollHeight - compactFootprint) <= 2, 'Collapsing content restores the scaled scroll footprint');
      assert(primaryFrame.contentWindow === frameWindow && primaryFrame.srcdoc === frameSource, 'Native growth and shrink preserve the interactive document');
      primaryPreview.scrollTop = 0;
      change(false);
      await settle();
      await until(() => Math.abs(primaryFrame.getBoundingClientRect().width - primaryFrame.clientWidth) < 1, 'Final world did not return to full scale');
      const after = await surface();
      assert(primaryFrame.clientWidth === finalWidth, 'Entering the world keeps the same logical viewport width');
      assert(primaryFrame === root.current!.querySelector('.build-comparison-ultrafast iframe') && primaryFrame.contentWindow === frameWindow && primaryFrame.srcdoc === frameSource, 'Entering the world preserves the primary iframe instance and document');
      assert(after.text.includes(desktop ? 'second tile to the right' : 'second tile underneath'), 'Entering the world preserves tile arrangement');
      assert(after.controls.find(control => control.label === 'Keep this note')?.value === 'Keep my live input across the split', 'Live input state survives entering the finished world');
      assert(root.current!.scrollWidth <= root.current!.clientWidth + 1, 'Final world does not create horizontal page overflow');
      change(true);
      await settle();
      assert(primaryFrame.clientWidth === finalWidth, 'A second split preserves the same logical viewport');
      assert(primaryFrame.contentWindow === frameWindow, 'Repeated split preserves the interactive document');
      flushSync(() => setStandardContent(false));
      await wait(100);
      const standardPreview = lanes[1].querySelector<HTMLElement>('.build-comparison-preview')!;
      const placeholder = lanes[1].querySelector<HTMLElement>('.build-comparison-preview-empty')!;
      const placeholderBounds = placeholder.getBoundingClientRect();
      const standardBounds = standardPreview.getBoundingClientRect();
      assert(!!placeholder && placeholderBounds.width > 0 && placeholderBounds.height > 0, 'Standard displays a visible placeholder before its first preview arrives');
      assert(placeholderBounds.left >= standardBounds.left - 1 && placeholderBounds.right <= standardBounds.right + 1, 'Empty placeholder remains inside the preview pane');
      assert(standardPreview.scrollWidth <= standardPreview.clientWidth + 1 && standardPreview.scrollHeight <= standardPreview.clientHeight + 2, 'Empty placeholder creates no extra scrolling');
      assert(primaryFrame.contentWindow === frameWindow && primaryFrame.clientWidth === finalWidth, 'Replacing Standard content with a placeholder leaves Ultrafast intact');
      flushSync(() => setStandardContent(true));
      await until(() => lanes[1].querySelector<HTMLIFrameElement>('iframe')?.clientWidth === finalWidth, 'Restored Standard frame did not use the same logical viewport');
      assert(primaryFrame.contentWindow === frameWindow, 'Restoring Standard preview leaves the live Ultrafast document intact');
    } catch (error) {
      failures.push(error instanceof Error ? error.message : String(error));
    } finally {
      setReport(JSON.stringify({ status: failures.length ? 'FAIL' : 'PASS', viewport: `${innerWidth}×${innerHeight}`, checks, failures, measurements }, null, 2));
      setRunning(false);
      checkRoot.current!.scrollIntoView({ block: 'start', behavior: 'instant' });
    }
  }

  return <>
    <section ref={checkRoot} className="desktop-preview-tools">
      <h1>Desktop world preview checks</h1>
      <p>Real sandboxed frames. Same responsive layout in comparison and the finished world. No model or saved data.</p>
      <button disabled={running} onClick={() => void check()}>Run desktop preview checks</button>
      <button disabled={running} onClick={() => change(!active)}>{active ? 'Enter your world' : 'Compare builds'}</button>
      <button disabled={running} onClick={() => setPublished(value => !value)}>{published ? 'Mark building' : 'Publish Ultrafast'}</button>
      <output data-action-count={actionCount}>Local actions: {actionCount}</output>
      <pre data-desktop-preview-report>{report}</pre>
    </section>
    <div ref={root} className="desktop-preview-root">
      <BuildComparison active={active} primaryInteractive={published} onTransitionChange={value => { transition.current = value; }}
        ultrafast={{ model: 'gpt-6-astra', status: published ? 'completed' : 'running' }} standard={{ model: 'gpt-6-astra', status: 'running' }}
        ultrafastActivity={panel('Ultrafast')} standardActivity={panel('Standard')}
        standardPreview={standardContent ? <GeneratedFrame html={worldHtml} renderVersion={1} revisionId="standard-preview" pending dimmed={false} onAction={async () => ({ ok: false })}/> : undefined}
      ><GeneratedFrame html={worldHtml} renderVersion={1} revisionId="primary-preview" pending={!published} onAction={async () => {
        actions.current++;
        setActionCount(actions.current);
        return { ok: true };
      }}/></BuildComparison>
    </div>
    <style>{`
      body{margin:0}.desktop-preview-tools{padding:20px;font:14px/1.4 system-ui,sans-serif}.desktop-preview-tools h1{font-size:24px}.desktop-preview-tools button{font:inherit;padding:8px 12px;margin:4px;border:1px solid #758494;border-radius:5px}.desktop-preview-tools output{margin:12px}.desktop-preview-tools pre{white-space:pre-wrap;max-height:260px;overflow:auto}.desktop-preview-root{padding:12px}.desktop-preview-root .generated-frame{display:block;width:100%;border:0}
    `}</style>
  </>;
}

createRoot(document.getElementById('root')!).render(<StrictMode><Fixture/></StrictMode>);
