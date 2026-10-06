// Deterministic presentation examples. No API, microphone, model, or saved-world access.
// Check at 1920×1080, 3840×2160, 1366×768, and a narrow mobile viewport.
// Example timings and token rates are fixture data, never benchmark measurements.
import { StrictMode, useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { ArrowUp, ArrowUpRight, CircleHelp, History, MessageCircle, Orbit, RotateCcw } from 'lucide-react';
import BuildComparison from '../../src/BuildComparison';
import { BuildActivityPanel } from '../../src/BuildActivityPanel';
import GeneratedFrame from '../../src/GeneratedFrame';
import DevDayBrand, { WorldBrackets } from '../../src/DevDayBrand';
import NavigationControls from '../../src/NavigationControls';
import InspirationPrompts from '../../src/InspirationPrompts';
import ThemeToggle from '../../src/ThemeToggle';
import VoiceControls from '../../src/VoiceControls';
import SpaceIcon from '../../src/SpaceIcon';
import type { ActivityEntry } from '../../src/build-activity';
import '../../src/styles.css';
import '../../src/canvas-workspace.css';
import '../../src/account.css';
import '../../src/community.css';
import '../../src/galaxy.css';
import '../../src/community-motion.css';
import '../../src/space-icon.css';
import '../../src/avatar.css';
import '../../src/voice.css';
import '../../src/reset-demo.css';
import '../../src/theme.css';
import '../../src/presentation.css';

const params = new URLSearchParams(location.search);
type Scenario = 'blank' | 'split' | 'world';
type VoiceScenario = 'off' | 'idle' | 'working' | 'speaking';
const initialScenario: Scenario = params.get('scenario') === 'split' ? 'split' : params.get('scenario') === 'world' ? 'world' : 'blank';
const time = (milliseconds: number) => new Date(Date.UTC(2026, 8, 26) + milliseconds).toISOString();
const sampleCode = `*** Begin Patch
*** Add File: space.js
+const planets = [
+  { name: 'Mercury', radius: 64, period: 7 },
+  { name: 'Venus', radius: 104, period: 11 },
+  { name: 'Earth', radius: 148, period: 17 },
+  { name: 'Mars', radius: 196, period: 24 }
+];
+export function render() {
+  return orbitScene(planets);
+}
+// Motion follows elapsed time, independent of frame rate.
+function advance(seconds) {
+  return planets.map(planet => ({
+    ...planet,
+    angle: seconds / planet.period * Math.PI * 2
+  }));
+}
*** End Patch`;
function activity(tier: 'ultrafast' | 'standard'): ActivityEntry[] {
  const complete = tier === 'ultrafast';
  const elapsed = complete ? 11_700 : 21_000;
  const tokens = complete ? 4_800 : 1_420;
  const durationMs = complete ? 10_900 : 20_000;
  return [
    { id: `${tier}-request`, turnId: tier, kind: 'request', title: 'Request', eventType: 'turn.started', status: 'completed', time: time(0), text: 'Create a beautiful, interactive solar system.' },
    { id: `${tier}-model`, turnId: tier, kind: 'event', title: 'Building your world', eventType: 'model.started', status: 'completed', time: time(300), throughput: { tokens, durationMs, rate: tokens * 1000 / durationMs, sampledAt: Date.parse(time(elapsed)), lastDeltaAt: Date.parse(time(elapsed)), state: 'complete', estimated: true } },
    { id: `${tier}-patch`, turnId: tier, kind: 'tool', title: 'apply_patch', tool: 'apply_patch', status: 'completed', inputFormat: 'patch', time: time(600), arguments: complete ? sampleCode : sampleCode.slice(0, 370) },
    { id: `${tier}-status`, turnId: tier, kind: 'event', title: complete ? 'Solar system ready' : 'Adding orbital motion', status: 'completed', eventType: complete ? 'turn.completed' : 'fixture.snapshot', time: time(elapsed), text: complete ? 'Ready to explore.' : 'A frozen example of the same build in progress.' },
  ];
}
const ultrafastEntries = activity('ultrafast');
const standardEntries = activity('standard');
// Opt this fixture into the same host-following palette behavior as curated worlds.
const worldAppearance = { lightCss: '.solar-world { color-scheme: light; }' };
const world = `<style>
  .solar-world { --ink:#f5f5f5;--muted:#b7bdc9;--surface:#0d111c;--line:#293143; color:var(--ink);background:#080b13;padding:clamp(20px,4vw,64px);font:clamp(17px,2vw,30px)/1.5 Arial,sans-serif; }
  .solar-world * { box-sizing:border-box; }
  .solar-world .eyebrow { margin:0 0 12px;color:#54dc92;font:600 .67em/1.4 Arial,sans-serif;letter-spacing:.14em; }
  .solar-world h1 { margin:0 0 12px;font:500 clamp(38px,5.2vw,88px)/1.06 Arial,sans-serif;letter-spacing:-.045em; }
  .solar-world h1 em { color:#54dc92;font-style:normal; }
  .solar-world p { margin:0 0 24px;color:var(--muted); }
  .solar-world .sky { position:relative;aspect-ratio:1.35;border:1px solid var(--line);border-radius:16px;margin:30px 0;background:radial-gradient(ellipse at center,#121c30,#0c101b 70%);overflow:hidden; }
  .solar-world .sun { position:absolute;left:50%;top:50%;width:9%;aspect-ratio:1;border-radius:50%;background:radial-gradient(circle at 35% 30%,#fff6b3,#ffb33b 70%);transform:translate(-50%,-50%);box-shadow:0 0 40px #ffc45440; }
  .solar-world .orbit { position:absolute;left:50%;top:50%;width:var(--diameter);aspect-ratio:1;border:1px solid #64789850;border-radius:50%;transform:translate(-50%,-50%) rotate(var(--angle)); }
  .solar-world .planet { position:absolute;left:50%;top:0;width:var(--size,5%);aspect-ratio:1;border-radius:50%;background:var(--color);transform:translate(-50%,-50%); }
  .solar-world .legend { display:flex;gap:16px 24px;flex-wrap:wrap;color:var(--muted);font-size:.8em; }
  .solar-world .legend span { display:flex;align-items:center;gap:8px; }
  .solar-world .legend i { display:block;width:9px;aspect-ratio:1;background:var(--color);border-radius:50%; }
  .solar-world button { margin-top:28px;padding:12px 20px;background:#08bd55;color:#001c0b;border:0;border-radius:6px;font:600 .8em Arial,sans-serif;cursor:pointer; }
  @media(prefers-color-scheme:light) { .solar-world{--ink:#192333;--muted:#566275;--surface:#fff;--line:#d3dae8;background:#f9fbff}.solar-world .eyebrow,.solar-world h1 em{color:#008d3e}.solar-world .sky{background:radial-gradient(ellipse at center,#edf3ff,#f6f9ff 70%)} }
</style>
<main class="solar-world"><p class="eyebrow">A LITTLE COSMIC PERSPECTIVE</p><h1>Your own<br/><em>solar system.</em></h1><p>Eight worlds. One star. Keep exploring.</p><div class="sky"><div class="sun"></div>${[
  ['22%', '30deg', '#b7a798'], ['35%', '210deg', '#dfc28d'], ['49%', '290deg', '#36b8ed'], ['64%', '145deg', '#ee8d5a'], ['83%', '65deg', '#cbae92'],
].map(([diameter, angle, color]) => `<div class="orbit" style="--diameter:${diameter};--angle:${angle}"><i class="planet" style="--color:${color}"></i></div>`).join('')}</div><div class="legend"><span><i style="--color:#36b8ed"></i>Earth</span><span><i style="--color:#ee8d5a"></i>Mars</span><span><i style="--color:#cbae92"></i>Jupiter</span></div><button data-action="explore">Explore the planets</button></main>`;

const wait = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
function Fixture() {
  const [scenario, setScenario] = useState<Scenario>(initialScenario);
  const [layoutSplit, setLayoutSplit] = useState(initialScenario === 'split');
  const [prompt, setPrompt] = useState('');
  const [report, setReport] = useState('Ready. Example data only.');
  const [checking, setChecking] = useState(false);
  const [voiceStatus, setVoiceStatus] = useState<VoiceScenario>(() => {
    const value = params.get('voice');
    return value === 'idle' || value === 'working' || value === 'speaking' ? value : 'off';
  });
  const [voiceMuted, setVoiceMuted] = useState(false);
  const [playbackBlocked, setPlaybackBlocked] = useState(params.has('blocked'));
  const root = useRef<HTMLDivElement>(null);
  const tools = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.body.classList.contains('with-live-voice');
    document.body.classList.toggle('with-live-voice', voiceStatus !== 'off');
    return () => { document.body.classList.toggle('with-live-voice', previous); };
  }, [voiceStatus]);
  function frameApp() {
    const strip = voiceStatus !== 'off' && innerWidth <= 960
      ? parseFloat(getComputedStyle(document.body).getPropertyValue('--voice-strip-height')) || 60 : 0;
    window.scrollTo({ top: root.current!.getBoundingClientRect().top + scrollY - strip, behavior: 'instant' });
  }
  const active = scenario === 'split';
  const hasWorld = scenario !== 'blank';
  const panel = (tier: 'ultrafast' | 'standard') => <BuildActivityPanel embedded label={`${tier === 'ultrafast' ? 'Ultrafast' : 'Standard'} fixture activity`} entries={tier === 'ultrafast' ? ultrafastEntries : standardEntries} busy={false} connected model="gpt-6-astra" tier={tier} onClose={() => {}} comparisonProgress={{ id: tier, status: 'ready', expectedOutputTokens: 4_800, completedReferenceTokens: tier === 'standard' ? 4_800 : undefined, outputTokens: tier === 'ultrafast' ? 4_800 : 1_420, laneStatus: tier === 'ultrafast' ? 'completed' : 'running' }}/>;

  async function check() {
    setChecking(true);
    // The fixture toolbar sits outside the app. Measure with the app framed so
    // its real sticky composer is not displaced by test-only controls.
    frameApp();
    await wait(650);
    const failures: string[] = [];
    const panelMeasurements: Record<string, unknown>[] = [];
    let count = 0;
    const assert = (pass: boolean, label: string) => { count++; if (!pass) failures.push(label); };
    const app = root.current!;
    const top = app.getBoundingClientRect().top;
    const viewportBottom = top + innerHeight;
    const frame = app.querySelector<HTMLIFrameElement>('iframe');
    assert(app.scrollWidth <= app.clientWidth + 1, 'No horizontal app overflow');
    if (voiceStatus !== 'off') {
      const pill = document.querySelector('.voice-pill')!.getBoundingClientRect();
      const leading = app.querySelector('.page-header-leading')!.getBoundingClientRect();
      const trailing = app.querySelector('.topbar-actions')!.getBoundingClientRect();
      assert(pill.left >= 8 && pill.right <= innerWidth - 8, 'Voice controls stay inside viewport');
      if (innerWidth > 960) {
        assert(leading.right + 12 <= pill.left, 'Voice leaves at least 12px after navigation and branding');
        assert(pill.right + 12 <= trailing.left, 'Voice leaves at least 12px before account actions');
      }
      assert(document.querySelectorAll('.voice-mute-button').length === (voiceStatus === 'idle' ? 0 : 1), 'Connected voice shows its real microphone control');
    }
    for (const circle of app.querySelectorAll<HTMLElement>('.space-icon, .theme-toggle')) {
      const box = circle.getBoundingClientRect();
      assert(Math.abs(box.width - box.height) < .75, `${circle.classList[0]} remains circular`);
      if (circle.classList.contains('space-icon')) {
        const expected = parseFloat(getComputedStyle(circle).width);
        assert(Math.abs(box.width - expected) < .75, 'Space icon is not compressed by its flex container');
      }
    }
    const composer = app.querySelector('.composer')!.getBoundingClientRect();
    assert(composer.width > 120 && composer.left >= -1 && composer.right <= innerWidth + 1, 'Composer remains inside horizontal viewport');
    if (innerWidth >= 1100 && (active || !hasWorld)) assert(composer.bottom <= viewportBottom + 1, 'Composer visible within a full app viewport');
    if (innerWidth >= 1100 && active) {
      const utilities = app.querySelector('.demo-utilities')!.getBoundingClientRect();
      const overlapWidth = Math.min(composer.right, utilities.right) - Math.max(composer.left, utilities.left);
      const overlapHeight = Math.min(composer.bottom, utilities.bottom) - Math.max(composer.top, utilities.top);
      assert(overlapWidth <= 1 || overlapHeight <= 1, 'Bottom reset and theme controls do not cover the composer');
    }
    if (active) {
      const lanes = [...app.querySelectorAll<HTMLElement>('.build-comparison-lane')];
      const boxes = lanes.map(lane => lane.getBoundingClientRect());
      assert(Math.abs(boxes[0].width - boxes[1].width) < 1, 'Equal lane widths');
      assert(Math.abs(boxes[0].height - boxes[1].height) < 1, 'Equal lane heights');
      for (const lane of lanes) {
        const label = lane.getAttribute('aria-label');
        const preview = lane.querySelector('.build-comparison-preview')!.getBoundingClientRect();
        const sidebar = lane.querySelector('.build-comparison-activity')!.getBoundingClientRect();
        const laneBox = lane.getBoundingClientRect();
        const identity = lane.querySelector('.build-comparison-identity')!.getBoundingClientRect();
        const status = lane.querySelector('.build-comparison-status')!.getBoundingClientRect();
        assert(Math.min(identity.right, status.right) - Math.max(identity.left, status.left) <= 1, `${label}: Name and status do not overlap`);
        const isOpen = lane.dataset.activityOpen === 'true';
        if (isOpen) {
          assert(sidebar.width <= laneBox.width * .36 + 1, `${label}: Activity occupies at most 36%`);
          assert(preview.width > sidebar.width, `${label}: World wider than Activity`);
          assert(Math.min(preview.right, sidebar.right) - Math.max(preview.left, sidebar.left) <= 1, `${label}: Activity does not cover world`);
          assert(Math.abs(preview.top - sidebar.top) < 2 && Math.abs(preview.bottom - sidebar.bottom) < 2, `${label}: Aligned top and bottom edges`);
          const metrics = [...lane.querySelectorAll('.build-metrics > div')].map(item => item.getBoundingClientRect());
          metrics.forEach((metric, i) => metrics.slice(i + 1).forEach(other => assert(Math.min(metric.right, other.right) - Math.max(metric.left, other.left) <= 1 || Math.min(metric.bottom, other.bottom) - Math.max(metric.top, other.top) <= 1, `${label}: Metric columns do not overlap`)));
          const metricLabels = [...lane.querySelectorAll<HTMLElement>('.build-metrics > div > span')];
          const sameRowLabels = sidebar.width <= 165 ? metricLabels.slice(0, 2) : metricLabels;
          const labelTops = sameRowLabels.map(item => item.getBoundingClientRect().top);
          assert(Math.max(...labelTops) - Math.min(...labelTops) <= 1, `${label}: Metric labels in the same row share one baseline`);
          for (const metricLabel of metricLabels) {
            const style = getComputedStyle(metricLabel);
            assert(metricLabel.getBoundingClientRect().height <= parseFloat(style.lineHeight) + 1 && metricLabel.scrollWidth <= metricLabel.clientWidth + 1, `${label}: ${metricLabel.textContent} fits on one line`);
          }
          for (const reading of lane.querySelectorAll<HTMLElement>('.build-metrics strong')) {
            const range = document.createRange();
            range.selectNodeContents(reading);
            const text = range.getBoundingClientRect();
            const cell = (reading.closest('.build-tps-metric') || reading.parentElement)!.getBoundingClientRect();
            assert(text.left >= cell.left - 1 && text.right <= cell.right + 1, `${label}: ${reading.textContent} fits inside its metric column`);
          }
          const toggle = lane.querySelector('.comparison-activity-toggle')!.getBoundingClientRect();
          assert(Math.min(toggle.right, sidebar.right) - Math.max(toggle.left, sidebar.left) <= 1, `${label}: Activity tab does not cover the transcript`);
          assert(Math.min(Math.abs(toggle.right - sidebar.left), Math.abs(toggle.left - sidebar.right)) <= 2, `${label}: Activity tab touches the outside edge of its sidebar`);
          const gauge = lane.querySelector('.build-speedometer')!;
          const arc = gauge.querySelector('.build-speed-track')!.getBoundingClientRect();
          const gaugeNumber = gauge.querySelector('strong')!.getBoundingClientRect();
          const gaugeGap = gaugeNumber.top - arc.bottom;
          assert(gaugeGap >= 2, `${label}: Gauge arc has breathing room above its number`);
          const header = lane.querySelector('.build-comparison-heading')!.getBoundingClientRect();
          const feed = lane.querySelector('.build-feed')!.getBoundingClientRect();
          const displayUnit = Math.min(2, Math.max(.75, innerWidth / 1920));
          if (innerWidth >= 1100) {
            assert(header.height <= Math.max(52, 64 * displayUnit) + 1, `${label}: Compact lane header preserves vertical room for code`);
            if (innerHeight >= 700) assert(feed.height >= sidebar.height * .62, `${label}: Transcript keeps most of the sidebar height`);
          }
          panelMeasurements.push({ label, headerHeight: header.height, sidebarHeight: sidebar.height, feedHeight: feed.height, gaugeGap });
          assert(lane.querySelector('.build-progress-track')!.getAttribute('role') === 'progressbar', `${label}: Progress remains accessible`);
        }
      }
      const enter = app.querySelector('.finish-build-button')!;
      const buttonBox = enter.getBoundingClientRect();
      const textBox = enter.querySelector('span')!.getBoundingClientRect();
      assert(Math.abs((textBox.left - buttonBox.left) - (buttonBox.right - textBox.right)) <= 2, 'Enter button has symmetric horizontal text spacing');
      if (innerWidth >= 1100) assert(buttonBox.bottom <= viewportBottom + 1, 'Enter button visible within a full app viewport');
      assert(!app.querySelector('.build-comparison-primary .build-comparison-world')!.hasAttribute('inert'), 'Completed Ultrafast world is interactive');
      assert(app.querySelector('.build-comparison-standard .build-comparison-world')!.hasAttribute('inert'), 'Standard preview stays read-only');
    }
    const font = (selector: string) => parseFloat(getComputedStyle(app.querySelector(selector)!).fontSize);
    const unit = Math.min(2, Math.max(.75, innerWidth / 1920));
    if (innerWidth >= 1100) {
      assert(font('.composer textarea') >= 24 * unit - .1, 'Composer type scales with presentation width');
      if (active) assert(font('.build-comparison-identity h2') >= 22 * unit - .1, 'Lane identity is presentation sized');
      if (!hasWorld) assert(font('.empty-canvas h1') >= 50 * unit - .1, 'Blank-world instruction is presentation sized');
    }
    const surface = getComputedStyle(app.querySelector('.topbar')!).backgroundColor;
    assert(app.querySelector('.theme-toggle')!.getAttribute('aria-label') === `Switch to ${document.documentElement.dataset.theme === 'light' ? 'dark' : 'light'} mode`, 'Theme toggle exposes the next palette correctly');
    const measurement = { viewport: `${innerWidth}×${innerHeight}`, scenario, voiceStatus, playbackBlocked, theme: document.documentElement.dataset.theme, topbarSurface: surface, composerFont: font('.composer textarea'), iframeHeight: frame?.getBoundingClientRect().height, composerBottom: Math.round(composer.bottom - top), panelMeasurements, checks: count, failures };
    setReport(`${failures.length ? 'FAIL' : 'PASS'} · ${count - failures.length}/${count}\n${JSON.stringify(measurement, null, 2)}`);
    setChecking(false);
  }

  return <>
    <style>{`.presentation-fixture-tools{display:flex;align-items:center;flex-wrap:wrap;gap:8px;padding:8px 12px;background:#193d31;color:#fff;font:13px/1.35 Arial,sans-serif;min-height:40px}.presentation-fixture-tools button{border:1px solid #77998a;border-radius:4px;background:#09251c;color:#fff;padding:5px 9px;font:inherit}.presentation-fixture-tools button[aria-pressed=true]{background:#ace4c1;color:#102d1d}.presentation-fixture-report{margin:0;background:#14281f;color:#daffe7;padding:12px;font:13px/1.5 monospace;white-space:pre-wrap;overflow-wrap:anywhere}.presentation-fixture-person{display:inline-grid;place-items:center;width:29px;aspect-ratio:1;border:1px solid var(--line);border-radius:50%;color:var(--green);font-size:18px}.presentation-fixture-tools strong{margin-right:8px}`}</style>
    <div ref={tools} className="presentation-fixture-tools" style={voiceStatus === 'off' ? undefined : { paddingTop: '76px' }}><strong>FIXTURE · example data, no live requests</strong>{(['blank', 'split', 'world'] as const).map(value => <button key={value} aria-pressed={scenario === value} onClick={() => setScenario(value)}>{value === 'blank' ? 'Blank world' : value === 'split' ? 'Split build' : 'Finished world'}</button>)}<label>Voice <select aria-label="Fixture voice state" value={voiceStatus} onChange={event => setVoiceStatus(event.target.value as VoiceScenario)}>{(['off', 'idle', 'working', 'speaking'] as const).map(value => <option key={value} value={value}>{value}</option>)}</select></label><label><input type="checkbox" checked={playbackBlocked} onChange={event => setPlaybackBlocked(event.target.checked)}/>Sound blocked</label><button disabled={checking} onClick={() => void check()}>Check layout</button><button onClick={frameApp}>Frame app</button></div>
    {voiceStatus !== 'off' && <div className="voice-dock"><VoiceControls status={voiceStatus} muted={voiceMuted} inputLevel={.14} outputLevel={voiceStatus === 'speaking' ? .4 : 0} userCaption="Create an interactive solar system." assistantCaption="I’m creating that for you now." error={null} playbackBlocked={playbackBlocked} onStart={() => setVoiceStatus('working')} onStop={() => setVoiceStatus('idle')} onToggleMute={() => setVoiceMuted(value => !value)} onResumeAudio={() => setPlaybackBlocked(false)}/></div>}
    <div ref={root} className={`app-shell canvas-workspace${layoutSplit ? ' with-build-comparison' : ''}`}>
      <header className="topbar"><div className="page-header-leading"><NavigationControls navigation={{ goHome: () => setScenario('blank') }}/><a className="brand" href="#" onClick={event => { event.preventDefault(); setScenario('blank'); }} aria-label="Little Worlds home"><DevDayBrand compact/><span className="app-wordmark">Little Worlds</span></a></div><div className="topbar-actions"><button className="text-button community-button"><Orbit size={16}/><span>Community</span></button><button className="text-button account-button" aria-label="Account for Joe"><SpaceIcon size={29}/><span>Joe</span></button></div></header>
      <div className="workspace"><main className={`space-main personal-canvas${!hasWorld ? ' blank-space' : ''}`}>
        <div className="workspace-chrome" data-collapsed={layoutSplit} aria-hidden={layoutSplit} inert={layoutSplit}><div className="workspace-chrome-content"><div className="space-toolbar"><div className="toolbar-right"><button className="subtle-button thread-button"><MessageCircle size={14}/><span>Thread</span></button><button className="subtle-button"><History size={14}/><span>History</span></button><button className="icon-button help-button" aria-label="Demo guide"><CircleHelp size={16}/></button></div></div><section className="studio-intro"><div className="profile-kicker"><button className="space-icon-edit-button" aria-label="Change fixture icon"><SpaceIcon size={35}/></button><span>JOE’S SPACE</span></div></section></div></div>
        <BuildComparison active={active} primaryInteractive onLayoutChange={setLayoutSplit} ultrafast={{ model: 'gpt-6-astra', status: 'completed', elapsedMs: 11_700 }} standard={{ model: 'gpt-6-astra', status: 'running', elapsedMs: 21_000 }} ultrafastActivity={panel('ultrafast')} standardActivity={panel('standard')} standardPreview={<GeneratedFrame html={world} appearance={worldAppearance} renderVersion={0} pending dimmed={false} onAction={async () => ({ ok: false })}/>}>
          <section className="projects-section" aria-label="Joe’s living canvas">{!hasWorld ? <div className="empty-canvas" aria-label="Blank canvas"><div className="empty-canvas-copy"><WorldBrackets/><p className="canvas-edition"><span className="canvas-edition-name">LITTLE WORLDS</span> / DEVDAY 2026</p><h1>Describe what you want to create.</h1></div></div> : <div className="living-extension has-built"><GeneratedFrame html={world} appearance={worldAppearance} renderVersion={0} pending={false} onAction={async () => ({ ok: true })}/></div>}</section>
        </BuildComparison>
        <div className="composer-area"><div className="composer-slot"><div className="composer-feedback" role="status"/><div className="comparison-composer-row"><form className="composer" aria-label="Space builder" onSubmit={event => { event.preventDefault(); setScenario('split'); }}><textarea aria-label="Describe a change to your space" rows={1} value={prompt} onChange={event => setPrompt(event.target.value)} placeholder={active ? 'Draft your next idea while both builds run…' : hasWorld ? 'What would you like to change?' : 'What would you like to create?'}/><button className="send-button" type="submit" disabled={!prompt.trim() || active} aria-label="Make it real"><ArrowUp size={20}/></button></form>{layoutSplit && <button className="finish-build-button" onClick={() => setScenario('world')}><ArrowUpRight size={17}/><span>Enter your world</span></button>}</div></div><InspirationPrompts canEdit={!layoutSplit} disabled={false} onChoose={message => { setPrompt(message); setScenario('split'); }}/></div>
        <footer className="workspace-edition"><span>Little Worlds</span><span>A DEVDAY [2026] EXPERIENCE</span></footer>
      </main></div>
      <div className="demo-utilities"><button className="reset-demo-trigger" onClick={() => { setScenario('blank'); setPrompt(''); }}><RotateCcw size={14}/>Reset fixture</button><ThemeToggle/></div>
    </div>
    <pre className="presentation-fixture-report" role="status" data-presentation-report>{report}</pre>
  </>;
}
createRoot(document.getElementById('root')!).render(<StrictMode><Fixture/></StrictMode>);
