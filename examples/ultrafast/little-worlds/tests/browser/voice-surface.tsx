import { useState } from 'react';
import type { ReactNode } from 'react';
import { flushSync } from 'react-dom';
import { createRoot } from 'react-dom/client';
import type { Root } from 'react-dom/client';
import { createVoiceSurface } from '../../src/voice-surface';
import { registerVoiceForm } from '../../src/voice-action-registry';
import VoiceControls from '../../src/VoiceControls';
import GeneratedFrame from '../../src/GeneratedFrame';
import ResetDemo from '../../src/ResetDemo';
import { createLiveVoice } from '../../src/live-voice';
import type { LiveVoiceSnapshot, VoiceActionResult, VoiceControl, VoiceSurface, VoiceTranscript } from '../../src/live-voice';

/** Served directly by Vite. This fixture never mounts App or requests a model. */
type Fixture = {
  mount: (node: ReactNode) => void;
  root: HTMLElement;
  surface: ReturnType<typeof createVoiceSurface>;
  speak: (text: string) => void;
};
type Check = { name: string; run: (fixture: Fixture) => Promise<void> };

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw new Error(message);
}

function equal(actual: unknown, expected: unknown, message: string) {
  assert(Object.is(actual, expected), `${message}. Expected ${JSON.stringify(expected)}; received ${JSON.stringify(actual)}.`);
}

function control(snapshot: VoiceSurface, label: string): VoiceControl {
  const matches = snapshot.controls.filter(item => item.label === label);
  equal(matches.length, 1, `Expected one control labeled “${label}”`);
  return matches[0];
}

function accepted(result: VoiceActionResult, message: string) {
  assert(result.ok, `${message}: ${result.message}`);
}

function refused(result: VoiceActionResult, message: string) {
  assert(!result.ok, `${message}: action unexpectedly succeeded (${result.message}).`);
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(done => { resolve = done; });
  return { promise, resolve };
}

async function until(condition: () => boolean, message: string) {
  for (let attempt = 0; attempt < 100; attempt++) {
    if (condition()) return;
    await new Promise(resolve => setTimeout(resolve, 20));
  }
  throw new Error(message);
}

// These tests mount the real reset UI, but every request is intercepted. Never
// fall through to the running demo: even an unexpected URL fails locally.
function mockResetRequest(respond: () => Response | Promise<Response> = () => Response.json({ ok: true, users: [] })) {
  const original = window.fetch;
  const requests: RequestInit[] = [];
  window.fetch = async (input, init) => {
    equal(typeof input === 'string' ? input : input instanceof URL ? input.pathname : input.url, '/api/demo/reset', 'Reset fixture only accepts the reset API path');
    equal(init?.method, 'POST', 'Reset uses POST');
    equal(init?.body, JSON.stringify({ confirmation: 'reset-demo' }), 'Reset sends the explicit confirmation payload');
    requests.push(init!);
    return respond();
  };
  return { requests, restore: () => { window.fetch = original; } };
}

function transcriptTurn(id: string, text: string, startMs: number, role: 'user' | 'assistant' = 'user'): VoiceTranscript {
  return { id, text, startMs, endMs: startMs + 500, role };
}

const scenarioFields = [['principal', 'Starting amount ($)', '0', '500000', '10000'], ['monthly', 'Monthly contribution ($)', '0', '10000', '250'], ['years', 'Horizon (years)', '1', '40', '20'], ['rate', 'Annual rate (%)', '-10', '20', '5']];
function scenarioHtml(rate = '5') {
  return `<section aria-labelledby="console-title"><h2 id="console-title">The compounding console</h2><form data-action='{"type":"scenario"}'>${scenarioFields.map(([name, label, min, max, value]) => `<label>${label}<input name="${name}" type="number" min="${min}" max="${max}" step="${name === 'years' ? '1' : 'any'}" value="${name === 'rate' ? rate : value}" required></label>`).join('')}<button type="submit">Save my scenario ↗</button></form><p>Saved annual rate: ${rate}%</p></section>`;
}
async function generatedControl(surface: Fixture['surface'], name: string) {
  for (let count = 0; count < 100; count++) {
    const snapshot = await surface.read();
    const match = snapshot.controls.find(item => item.label === name);
    if (match) return { snapshot, control: match };
    await new Promise(resolve => setTimeout(resolve, 30));
  }
  throw new Error(`Generated control “${name}” was not registered`);
}

const checks: Check[] = [
  {
    name: 'Generated pages with internal overflow expose a working voice scroll region',
    async run({ mount, root, surface }) {
      const html = `<div>${Array.from({ length: 210 }, (_, index) => `<button type="button" style="display:block;height:60px;margin:0">Long page item ${index}</button>`).join('')}</div>`;
      const originalScroll = window.scrollY;
      try {
        mount(<GeneratedFrame html={html} renderVersion={1} pending={false} revisionId={1} onAction={async () => ({ ok: true })}/>);
        await generatedControl(surface, 'Scroll generated page');
        root.querySelector('iframe')!.scrollIntoView({ block: 'start', behavior: 'instant' });
        const before = await surface.read();
        const firstBefore = before.controls.find(item => item.label.startsWith('Long page item'))!.label;
        accepted(await surface.execute({ type: 'scroll', target: control(before, 'Scroll generated page').id, direction: 'down' }), 'Scroll inside tall generated page');
        const after = await surface.read();
        const firstAfter = after.controls.find(item => item.label.startsWith('Long page item'))!.label;
        assert(firstAfter !== firstBefore, 'The nearest visible generated controls change after internal scrolling');
      } finally { window.scrollTo({ top: originalScroll, behavior: 'instant' }); }
    },
  },
  {
    name: 'Long generated pages expose later controls after scrolling the host viewport',
    async run({ mount, root, surface }) {
      const actions: Record<string, unknown>[] = [];
      const html = `<div>${Array.from({ length: 210 }, (_, index) => `<button type="button" style="display:block;height:30px;margin:0" data-action='{"type":"choose","item":${index}}'>Catalog item ${index}</button>`).join('')}</div>`;
      const originalScroll = window.scrollY;
      try {
        mount(<GeneratedFrame html={html} renderVersion={1} pending={false} revisionId={1} onAction={async action => { actions.push(action); return { ok: true }; }}/>);
        await generatedControl(surface, 'Catalog item 0');
        root.querySelector('iframe')!.scrollIntoView({ block: 'start', behavior: 'instant' });
        let snapshot = await surface.read();
        assert(/Showing 160 of 21[01] controls/.test(snapshot.text || ''), `Truncation explains how to find the rest: ${snapshot.text?.slice(0, 300)}`);
        assert(!snapshot.controls.some(item => item.label === 'Catalog item 209'), 'Last item starts outside the bounded surface');
        for (let index = 0; index < 20 && !snapshot.controls.some(item => item.label === 'Catalog item 209'); index++) {
          accepted(await surface.execute({ type: 'scroll', direction: 'down' }), 'Scroll toward later controls');
          snapshot = await surface.read();
        }
        const last = control(snapshot, 'Catalog item 209');
        accepted(await surface.execute({ type: 'click', target: last.id }), 'Activate previously omitted item');
        equal(actions.length, 1, 'Only requested late item dispatched'); equal(actions[0].item, 209, 'Correct late item');
      } finally { window.scrollTo({ top: originalScroll, behavior: 'instant' }); }
    },
  },
  {
    name: 'Long host surfaces retain focused controls and expose later actions after scrolling',
    async run({ mount, root, surface }) {
      let activated = -1;
      const originalScroll = window.scrollY;
      try {
        mount(<div><input aria-label="Pinned draft" defaultValue="Keep this draft"/>{Array.from({ length: 180 }, (_, index) => <button key={index} style={{ display: 'block', height: 32 }} onClick={() => { activated = index; }}>Host item {index}</button>)}</div>);
        root.scrollIntoView({ block: 'start', behavior: 'instant' });
        let snapshot = await surface.read();
        assert(snapshot.text?.includes('Showing 135 of 181 host controls'), 'Host truncation is explicit');
        assert(!snapshot.controls.some(item => item.label === 'Host item 179'), 'Last host item starts omitted');
        root.querySelector('input')!.focus({ preventScroll: true });
        for (let index = 0; index < 20 && !snapshot.controls.some(item => item.label === 'Host item 179'); index++) {
          accepted(await surface.execute({ type: 'scroll', direction: 'down' }), 'Scroll host');
          snapshot = await surface.read();
        }
        equal(control(snapshot, 'Pinned draft').value, 'Keep this draft', 'Focused draft stays discoverable');
        accepted(await surface.execute({ type: 'click', target: control(snapshot, 'Host item 179').id }), 'Activate late host control');
        equal(activated, 179, 'Correct late host control');
      } finally { window.scrollTo({ top: originalScroll, behavior: 'instant' }); }
    },
  },
  {
    name: 'Generated settings support disclosures, ranges, selects, radios, and toggles through the same form action',
    async run({ mount, surface }) {
      const saved: Record<string, unknown>[] = [];
      const settings = `<article aria-label="Sound studio"><details><summary>Performance settings</summary><form data-action='{"type":"configure"}'>
        <label>Tempo<input type="range" name="tempo" min="40" max="200" step="5" value="80"></label>
        <label>Instrument<select name="instrument"><option value="piano">Piano</option><option value="marimba">Marimba</option></select></label>
        <fieldset><legend>Playback</legend><label><input type="radio" name="playback" value="once" checked>Play once</label><label><input type="radio" name="playback" value="loop">Loop</label></fieldset>
        <label><input type="checkbox" name="metronome" value="on">Metronome</label>
        <button type="submit">Apply performance</button></form></details></article>`;
      mount(<GeneratedFrame html={settings} renderVersion={1} pending={false} revisionId={1} onAction={async action => { saved.push(action); return { ok: true }; }}/>);
      const first = await generatedControl(surface, 'Performance settings');
      equal(first.control.expanded, false, 'Generated native disclosure expansion reaches the host');
      assert(first.control.description?.includes('collapsed'), 'Collapsed state reaches planner');
      assert(!first.snapshot.controls.some(item => item.label === 'Tempo'), 'Collapsed controls must not be offered');
      accepted(await surface.execute({ type: 'click', target: first.control.id }), 'Expand settings');
      equal(control(await surface.read(), 'Performance settings').expanded, true, 'Expanded generated disclosure state reaches the host');
      const tempo = control(await surface.read(), 'Tempo');
      equal(tempo.role, 'slider', 'Range role'); equal(tempo.step, 5, 'Range step');
      accepted(await surface.execute({ type: 'fill', target: tempo.id, value: '125' }), 'Set tempo');
      const instrument = control(await surface.read(), 'Instrument');
      equal(instrument.options?.length, 2, 'Options are distinct from the field label');
      accepted(await surface.execute({ type: 'select', target: instrument.id, value: 'marimba' }), 'Select instrument');
      const loop = control(await surface.read(), 'Loop');
      equal(loop.checked, false, 'Radio current state');
      accepted(await surface.execute({ type: 'click', target: loop.id }), 'Choose looping');
      const metronome = control(await surface.read(), 'Metronome');
      accepted(await surface.execute({ type: 'click', target: metronome.id }), 'Enable metronome');
      equal(saved.length, 0, 'Draft settings do not claim to persist');
      const submit = control(await surface.read(), 'Apply performance');
      const result = await surface.execute({ type: 'click', target: submit.id });
      accepted(result, 'Apply performance'); assert(result.message.includes('saved'), 'Persistence acknowledged');
      equal(saved.length, 1, 'Only one persisted settings action');
      equal(JSON.stringify(saved[0]), JSON.stringify({ type: 'configure', tempo: '125', instrument: 'marimba', playback: 'loop', metronome: 'on' }), 'All selected values reach the existing reducer');
    },
  },
  {
    name: 'Host disclosures work by voice and a manual state or meaning change invalidates an old action',
    async run({ mount, root, surface }) {
      let invoked = 0;
      mount(<><details><summary>Advanced options</summary><button onClick={() => invoked++}>Reset tempo</button></details><button>Start playback</button></>);
      const closed = await surface.read();
      const summary = control(closed, 'Advanced options');
      equal(summary.expanded, false, 'Host native disclosure expansion is explicit');
      assert(summary.description?.includes('collapsed'), 'Host disclosure exposes state');
      accepted(await surface.execute({ type: 'press', target: summary.id, key: 'Enter' }), 'Open disclosure with Enter');
      assert(root.querySelector('details')?.open, 'Native disclosure opened');
      refused(await surface.execute({ type: 'click', target: summary.id }), 'Stale disclosure must not toggle back');
      const open = await surface.read();
      equal(control(open, 'Advanced options').expanded, true, 'Host native disclosure reports expansion');
      accepted(await surface.execute({ type: 'click', target: control(open, 'Reset tempo').id }), 'Newly revealed control');
      equal(invoked, 1, 'Revealed action invoked once');
      const playback = control(await surface.read(), 'Start playback');
      root.querySelectorAll('button')[1].textContent = 'Erase recording';
      refused(await surface.execute({ type: 'click', target: playback.id }), 'Changed control meaning');
      const current = control(await surface.read(), 'Advanced options');
      accepted(await surface.execute({ type: 'click', target: current.id }), 'Collapse disclosure');
      equal(root.querySelector('details')?.open, false, 'Native disclosure closed');
    },
  },
  {
    name: 'Independent ARIA disclosures remain open together and reject stale same-label or retargeted actions',
    async run({ mount, root, surface }) {
      function Disclosures() {
        const [outline, setOutline] = useState(false);
        const [inspector, setInspector] = useState(false);
        return <>
          <button type="button" aria-expanded={outline} aria-controls="outline-region" onClick={() => setOutline(value => !value)}>Outline</button>
          <button type="button" aria-expanded={inspector} aria-controls="inspector-region" onClick={() => setInspector(value => !value)}>Inspector</button>
          <section id="outline-region" aria-label="Document outline" hidden={!outline}>HIDDEN_OUTLINE_PAYLOAD</section>
          <h2 id="inspector-title">Selection inspector</h2>
          <section id="inspector-region" aria-labelledby="inspector-title" hidden={!inspector}>HIDDEN_INSPECTOR_PAYLOAD</section>
        </>;
      }
      mount(<Disclosures/>);
      const initial = await surface.read();
      const outline = control(initial, 'Outline');
      equal(outline.expanded, false, 'Outline starts collapsed');
      assert(outline.description?.includes('Controls: Document outline.'), 'Only the named controlled region is described');
      assert(!initial.text?.includes('HIDDEN_OUTLINE_PAYLOAD'), 'Collapsed content stays unavailable');
      accepted(await surface.execute({ type: 'click', target: outline.id }), 'Open outline');
      refused(await surface.execute({ type: 'click', target: outline.id }), 'An old action cannot toggle the same-label disclosure back');
      const inspector = control(await surface.read(), 'Inspector');
      equal(inspector.expanded, false, 'Opening outline leaves inspector collapsed');
      assert(inspector.description?.includes('Controls: Selection inspector.'), 'A region labelled by a heading has a useful name');
      accepted(await surface.execute({ type: 'click', target: inspector.id }), 'Open inspector');
      const both = await surface.read();
      equal(control(both, 'Outline').expanded, true, 'Outline remains expanded');
      equal(control(both, 'Inspector').expanded, true, 'Inspector is expanded too');
      accepted(await surface.execute({ type: 'click', target: control(both, 'Outline').id }), 'Close outline independently');
      const after = await surface.read();
      equal(control(after, 'Outline').expanded, false, 'Outline closes');
      equal(control(after, 'Inspector').expanded, true, 'Inspector stays expanded');
      const buttons = root.querySelectorAll('button');
      flushSync(() => buttons[1].click());
      refused(await surface.execute({ type: 'click', target: control(after, 'Inspector').id }), 'A manual state change invalidates the captured action');
      const retargeted = control(await surface.read(), 'Outline');
      buttons[0].setAttribute('aria-controls', 'inspector-region');
      refused(await surface.execute({ type: 'click', target: retargeted.id }), 'Changing a controlled region invalidates the captured action');
    },
  },
  {
    name: 'Generated James numeric form fills 20, requires a fresh read, and saves through the real frame bridge',
    async run({ mount, surface }) {
      const saved: Record<string, unknown>[] = [];
      function Scenario() {
        const [rate, setRate] = useState('5');
        return <GeneratedFrame html={scenarioHtml(rate)} renderVersion={saved.length + 1} pending={false} revisionId={1} onAction={async action => {
          saved.push(action);
          flushSync(() => setRate(String(action.rate)));
          return { ok: true, html: scenarioHtml(String(action.rate)), version: saved.length + 1 };
        }}/>;
      }
      mount(<Scenario/>);
      const first = await generatedControl(surface, 'Annual rate (%)');
      equal(first.control.role, 'spinbutton', 'Numeric semantic role');
      equal(first.control.type, 'number', 'Native numeric type reaches planner');
      equal(first.control.min, -10, 'Minimum reaches planner');
      equal(first.control.max, 20, 'Maximum reaches planner');
      assert(first.control.description?.includes('Save my scenario') && first.control.description.includes('without units'), 'Form and format context must reach planner');
      const fill = await surface.execute({ type: 'fill', target: first.control.id, value: '20' });
      accepted(fill, 'Filling the valid rate boundary');
      assert(fill.message.includes('draft'), 'A filled field must not claim persistence');
      equal(saved.length, 0, 'Filling is not a save');
      refused(await surface.execute({ type: 'click', target: control(first.snapshot, 'Save my scenario ↗').id }), 'Stale pre-edit submit');
      const current = await surface.read();
      equal(control(current, 'Annual rate (%)').value, '20', 'Frame keeps the edited rate');
      accepted(await surface.execute({ type: 'click', target: control(current, 'Save my scenario ↗').id }), 'Saving the current scenario');
      equal(saved.length, 1, 'One persisted action');
      equal(saved[0].type, 'scenario', 'Existing reducer action');
      equal(saved[0].rate, '20', 'Saved rate');
      equal(saved[0].principal, '10000', 'Other fields survive');
      const after = await surface.read();
      equal(control(after, 'Annual rate (%)').value, '20', 'Verified rate after publication');
      assert(after.text?.includes('Saved annual rate: 20%'), 'Saved result is visible to the planner');
    },
  },
  {
    name: 'Generated numeric fields explain invalid format and constraints without losing the current draft',
    async run({ mount, surface }) {
      mount(<GeneratedFrame html={scenarioHtml()} renderVersion={1} pending={false} revisionId={1} onAction={async () => ({ ok: true })}/>);
      let entry = await generatedControl(surface, 'Annual rate (%)');
      const percent = await surface.execute({ type: 'fill', target: entry.control.id, value: '20%' });
      refused(percent, 'Percentage unit in numeric input');
      assert(percent.message.includes('without units or percent signs'), 'Format correction should be actionable');
      for (const value of ['21', '-11', 'Infinity']) {
        entry = await generatedControl(surface, 'Annual rate (%)');
        refused(await surface.execute({ type: 'fill', target: entry.control.id, value }), `Invalid numeric value ${value}`);
        equal(control(await surface.read(), 'Annual rate (%)').value, '5', 'Invalid fill preserves original draft');
      }
      const years = control(await surface.read(), 'Horizon (years)');
      equal(years.step, 1, 'Integer step reaches planner');
      refused(await surface.execute({ type: 'fill', target: years.id, value: '1.5' }), 'Fractional whole-year input');
      equal(control(await surface.read(), 'Horizon (years)').value, '20', 'Invalid step preserves original draft');
      entry = await generatedControl(surface, 'Annual rate (%)');
      accepted(await surface.execute({ type: 'fill', target: entry.control.id, value: '-2.5' }), 'Valid fractional rate');
      equal(control(await surface.read(), 'Annual rate (%)').value, '-2.5', 'Fractional rate retained');
    },
  },
  {
    name: 'Unchanged generated HTML survives host event ticks, while edited HTML and new revisions invalidate captures',
    async run({ mount, surface }) {
      let update: (next: { version: number; html: string; revision: number }) => void = () => {};
      const initialHtml = scenarioHtml();
      function Scenario() {
        const [state, setState] = useState({ version: 1, html: initialHtml, revision: 1 });
        update = setState;
        return <GeneratedFrame html={state.html} renderVersion={state.version} pending={false} revisionId={state.revision} onAction={async () => ({ ok: true })}/>;
      }
      mount(<Scenario/>);
      const first = await generatedControl(surface, 'Annual rate (%)');
      flushSync(() => update({ version: 2, html: initialHtml, revision: 1 }));
      await new Promise(resolve => setTimeout(resolve, 20));
      accepted(await surface.execute({ type: 'fill', target: first.control.id, value: '20' }), 'Event-only refresh must not invalidate the field');
      const second = await surface.read();
      flushSync(() => update({ version: 3, html: scenarioHtml('10'), revision: 1 }));
      await new Promise(resolve => setTimeout(resolve, 20));
      refused(await surface.execute({ type: 'fill', target: control(second, 'Annual rate (%)').id, value: '15' }), 'Changed HTML rejects old field capture');
      const third = await generatedControl(surface, 'Annual rate (%)');
      flushSync(() => update({ version: 4, html: scenarioHtml('10'), revision: 2 }));
      refused(await surface.execute({ type: 'fill', target: third.control.id, value: '15' }), 'New published revision rejects old frame capture');
    },
  },
  {
    name: 'Generated SVG descriptions expose game positions and charts without exposing hidden content',
    async run({ mount, surface }) {
      mount(<GeneratedFrame html={'<section><h2>Maze</h2><svg role="img" aria-label="Player at column 3, row 4. 12 dots remain."></svg><svg role="img" aria-labelledby="chart-description"><title id="chart-description">Illustrative growth is 300 dollars.</title></svg><svg aria-hidden="true" aria-label="Private hidden diagram"></svg><button type="button">Move right</button></section>'} renderVersion={1} pending={false} revisionId={1} onAction={async () => ({ ok: true })}/>);
      const { snapshot } = await generatedControl(surface, 'Move right');
      assert(snapshot.text?.includes('Player at column 3, row 4. 12 dots remain.'), 'Visible game position omitted');
      assert(snapshot.text?.includes('Illustrative growth is 300 dollars.'), 'Visible chart description omitted');
      assert(!snapshot.text?.includes('Private hidden diagram'), 'Hidden diagram leaked');
    },
  },
  {
    name: 'Generated controls leave modal and pending scopes, then become available again when published',
    async run({ mount, root, surface }) {
      let setPending: (value: boolean) => void = () => {};
      function Scenario() {
        const [pending, update] = useState(false);
        setPending = update;
        return <><dialog><button type="button">Modal action</button></dialog><GeneratedFrame html={scenarioHtml()} renderVersion={1} pending={pending} revisionId={1} onAction={async () => ({ ok: true })}/></>;
      }
      mount(<Scenario/>);
      const first = await generatedControl(surface, 'Annual rate (%)');
      const dialog = root.querySelector('dialog')!;
      dialog.showModal();
      refused(await surface.execute({ type: 'fill', target: first.control.id, value: '20' }), 'Modal blocks background frame');
      assert((await surface.read()).controls.every(item => !item.id.startsWith('frame:')), 'Modal leaked frame controls');
      dialog.close();
      const published = await generatedControl(surface, 'Annual rate (%)');
      flushSync(() => setPending(true));
      refused(await surface.execute({ type: 'fill', target: published.control.id, value: '20' }), 'Pending preview cannot mutate');
      assert((await surface.read()).controls.every(item => !item.id.startsWith('frame:')), 'Pending preview leaked controls');
      flushSync(() => setPending(false));
      const resumed = await generatedControl(surface, 'Annual rate (%)');
      accepted(await surface.execute({ type: 'fill', target: resumed.control.id, value: '20' }), 'Published frame becomes interactive again');
    },
  },
  {
    name: 'Host numeric controls keep constraints and preserve their draft after invalid voice input',
    async run({ mount, surface }) {
      mount(<label>Rate<input type="number" min="-10" max="20" step="0.5" defaultValue="5"/></label>);
      const field = control(await surface.read(), 'Rate');
      equal(field.type, 'number', 'Host numeric type');
      equal(field.min, -10, 'Host minimum');
      equal(field.max, 20, 'Host maximum');
      equal(field.step, 0.5, 'Host numeric step');
      refused(await surface.execute({ type: 'fill', target: field.id, value: '20%' }), 'Invalid host format');
      refused(await surface.execute({ type: 'fill', target: field.id, value: '25' }), 'Invalid host range');
      refused(await surface.execute({ type: 'fill', target: field.id, value: '1.2' }), 'Invalid host step');
      equal(control(await surface.read(), 'Rate').value, '5', 'Host original draft preserved');
      const fresh = control(await surface.read(), 'Rate');
      accepted(await surface.execute({ type: 'fill', target: fresh.id, value: '20' }), 'Valid host rate');
    },
  },
  {
    name: 'Routine voice updates stay accessible without opening the conversation panel',
    async run({ mount, root }) {
      const props = { status: 'listening', muted: false, inputLevel: 0, outputLevel: 0, userCaption: 'Go to community', assistantCaption: 'One sec.', error: null, playbackBlocked: false, onStart() {}, onStop() {}, onToggleMute() {}, onResumeAudio() {} };
      mount(<VoiceControls {...props} />);
      mount(<VoiceControls {...props} notice="Please repeat the full request." />);
      await new Promise(resolve => setTimeout(resolve, 0));
      assert(!root.querySelector('.voice-panel'), 'A routine voice update opened a popup');
      assert(root.querySelector('[role="status"]')?.textContent?.includes('Please repeat'), 'The update was not announced accessibly');
      flushSync(() => root.querySelector<HTMLButtonElement>('.voice-primary')!.click());
      assert(root.querySelector('.voice-panel')?.textContent?.includes('Please repeat'), 'Opening the conversation did not expose its update');
    },
  },
  {
    name: 'Connection failures and blocked sound still expose their recovery controls',
    async run({ mount, root }) {
      const props = { status: 'error', muted: false, inputLevel: 0, outputLevel: 0, userCaption: '', assistantCaption: '', error: 'Microphone access is blocked.', playbackBlocked: false, onStart() {}, onStop() {}, onToggleMute() {}, onResumeAudio() {} };
      mount(<VoiceControls key="connection" {...props} />);
      await new Promise(resolve => setTimeout(resolve, 0));
      assert(root.querySelector('.voice-panel [role="alert"]'), 'A connection failure hid its retry control');
      mount(<VoiceControls key="playback" {...props} status="listening" error={null} playbackBlocked />);
      await new Promise(resolve => setTimeout(resolve, 0));
      assert(root.querySelector('.voice-panel')?.textContent?.includes('Enable sound'), 'Blocked sound hid its recovery control');
    },
  },
  {
    name: 'Labels use aria-label, aria-labelledby, associated labels, and placeholders',
    async run({ mount, surface }) {
      mount(<>
        <button aria-label="Open navigation">Decorative text</button>
        <span id="fixture-labelledby">Community controls</span>
        <button aria-labelledby="fixture-labelledby">Unrelated text</button>
        <label htmlFor="fixture-title">Space title</label><input id="fixture-title" defaultValue="Studio" />
        <textarea placeholder="Describe a change" />
      </>);
      const snapshot = await surface.read();
      for (const name of ['Open navigation', 'Community controls', 'Space title', 'Describe a change']) control(snapshot, name);
      assert(snapshot.controls.every(item => item.label !== 'Run checks'), 'Harness controls leaked into the voice surface');
    },
  },
  {
    name: 'Duplicate button labels keep distinct IDs and their local section context',
    async run({ mount, surface }) {
      const selected: string[] = [];
      mount(<>
        <section aria-label="Watercolor revision"><button onClick={() => selected.push('watercolor')}>Restore</button></section>
        <section aria-label="Ceramics revision"><button onClick={() => selected.push('ceramics')}>Restore</button></section>
      </>);
      const matches = (await surface.read()).controls.filter(item => item.label === 'Restore');
      equal(matches.length, 2, 'Duplicate labels remain individually addressable');
      assert(matches[0].id !== matches[1].id, 'Duplicate controls shared an ID');
      equal(matches[0].description, 'Watercolor revision', 'First contextual description');
      equal(matches[1].description, 'Ceramics revision', 'Second contextual description');
      accepted(await surface.execute({ type: 'click', target: matches[1].id }), 'Activating the intended duplicate');
      equal(selected.join(','), 'ceramics', 'Only the requested duplicate activates');
    },
  },
  {
    name: 'Hidden, inert, ignored, and password controls are excluded',
    async run({ mount, surface }) {
      mount(<>
        <button>Visible action</button>
        <div hidden><button>Hidden action</button></div>
        <div style={{ display: 'none' }}><button>Display-none action</button></div>
        <button style={{ visibility: 'hidden' }}>Invisible action</button>
        <div inert><button>Inert action</button></div>
        <div aria-hidden="true"><button>Aria-hidden action</button></div>
        <div data-voice-ignore><button>Ignored action</button></div>
        <input aria-label="Secret password" type="password" defaultValue="fixture-only" />
      </>);
      const snapshot = await surface.read();
      equal(snapshot.controls.length, 1, 'Only the visible fixture control is exposed');
      control(snapshot, 'Visible action');
      assert(!snapshot.text?.includes('fixture-only'), 'Password value leaked into readable context');
    },
  },
  {
    name: 'Disabled controls are described as disabled and cannot activate',
    async run({ mount, surface }) {
      let activated = 0;
      mount(<>
        <button disabled onClick={() => activated++}>Disabled build</button>
        <button aria-disabled="true" onClick={() => activated++}>Unavailable navigation</button>
        <fieldset disabled><input aria-label="Disabled field" defaultValue="Original" /></fieldset>
      </>);
      const snapshot = await surface.read();
      for (const name of ['Disabled build', 'Unavailable navigation', 'Disabled field']) {
        const item = control(snapshot, name);
        assert(item.disabled, `“${name}” was not marked disabled`);
        refused(await surface.execute({ type: 'click', target: item.id }), `Refuse “${name}”`);
      }
      equal(activated, 0, 'Disabled handlers never run');
    },
  },
  {
    name: 'Native and ARIA toggles expose state and refuse stale inversions',
    async run({ mount, surface, root }) {
      const clicks: string[] = [];
      mount(<>
        <input type="checkbox" aria-label="Public space" onClick={() => clicks.push('native')} />
        <button aria-pressed={false} onClick={() => clicks.push('pressed')}>Globe mode</button>
        <div role="switch" tabIndex={0} aria-label="Show friends" aria-checked={true} onClick={() => clicks.push('switch')}>Friends</div>
      </>);
      const snapshot = await surface.read();
      for (const [name, state] of [['Public space', false], ['Globe mode', false], ['Show friends', true]] as const)
        equal(control(snapshot, name).checked, state, `Snapshot state for ${name}`);
      root.querySelector('input')!.checked = true;
      root.querySelector('button')!.setAttribute('aria-pressed', 'true');
      root.querySelector('[role="switch"]')!.setAttribute('aria-checked', 'false');
      for (const name of ['Public space', 'Globe mode', 'Show friends'])
        refused(await surface.execute({ type: 'click', target: control(snapshot, name).id }), `Refuse stale ${name} toggle`);
      equal(clicks.length, 0, 'Stale toggle plans dispatch no clicks');
      const current = await surface.read();
      equal(control(current, 'Globe mode').checked, true, 'A new snapshot sees the manual mode change');
      accepted(await surface.execute({ type: 'click', target: control(current, 'Show friends').id }), 'A current switch may activate');
      equal(clicks.join(','), 'switch', 'Only the freshly observed switch activates');
    },
  },
  {
    name: 'Disabled optgroups are described and cannot be selected',
    async run({ mount, surface, root }) {
      mount(<select aria-label="Space color" defaultValue="green">
        <option value="green">Green</option>
        <optgroup label="Unavailable colors" disabled><option value="red">Red</option></optgroup>
        <option value="hidden" hidden>Hidden color</option>
      </select>);
      const item = control(await surface.read(), 'Space color');
      equal(item.options?.find(option => option.value === 'red')?.disabled, true, 'Parent optgroup makes its option unavailable');
      assert(!item.options?.some(option => option.value === 'hidden'), 'Hidden options are not advertised');
      refused(await surface.execute({ type: 'select', target: item.id, value: 'red' }), 'Disabled optgroup selection');
      refused(await surface.execute({ type: 'select', target: item.id, value: 'hidden' }), 'Hidden option selection');
      equal(root.querySelector('select')!.value, 'green', 'The selected option stays intact');
    },
  },
  {
    name: 'Registered forms keep fills as drafts and await accepted submissions through Enter and the button',
    async run({ mount, root, surface }) {
      for (const method of ['button', 'field Enter', 'button Enter', 'button Space'] as const) {
        let current = '';
        let nativeSubmits = 0;
        const submissions: string[] = [];
        const response = deferred<VoiceActionResult>();
        function Builder() {
          const [value, setValue] = useState('');
          current = value;
          return <form aria-label="Creative draft" onSubmit={event => { event.preventDefault(); nativeSubmits++; }}>
            <label>Registered request<textarea required value={value} onChange={event => setValue(event.target.value)} /></label>
            <button type="submit">Start registered build</button>
          </form>;
        }
        mount(<Builder key={method}/>);
        const unregister = registerVoiceForm(root.querySelector('form')!, async () => { submissions.push(current); return response.promise; });
        try {
          const initial = await surface.read();
          equal(control(initial, 'Start registered build').type, 'submit', 'Submit button type reaches planner');
          equal(control(initial, 'Start registered build').group, 'Creative draft', 'Submit button identifies its form');
          equal(control(initial, 'Registered request').group, 'Creative draft', 'Field and submit button share a form');
          assert(control(initial, 'Registered request').description?.includes('Creative draft'), 'The field identifies its form');
          const fill = await surface.execute({ type: 'fill', target: control(initial, 'Registered request').id, value: `An animated garden via ${method}` });
          accepted(fill, 'Fill registered form');
          equal(fill.submitted, false, 'Fill explicitly reports no submission');
          assert(/no form submission|not.*submit/i.test(fill.message), 'Fill explains that it did not submit');
          equal(submissions.length, 0, 'Filling does not invoke the registered handler');
          const ready = await surface.read();
          let completed = false;
          const pending = surface.execute(method === 'button'
            ? { type: 'click', target: control(ready, 'Start registered build').id }
            : { type: 'press', target: control(ready, method === 'field Enter' ? 'Registered request' : 'Start registered build').id, key: method === 'button Space' ? 'Space' : 'Enter' }).then(result => { completed = true; return result; });
          await until(() => submissions.length === 1, 'The registered submission handler was not invoked');
          await new Promise(resolve => setTimeout(resolve, 40));
          equal(completed, false, 'The action cannot complete before the handler acknowledges acceptance');
          equal(nativeSubmits, 0, 'The registered path does not also dispatch a native submit');
          response.resolve({ ok: true, submitted: true, turnId: `accepted-${method}`, message: 'Build accepted.' });
          const result = await pending;
          accepted(result, 'Await registered acceptance');
          equal(result.submitted, true, 'The accepted submission reaches the caller');
          equal(result.turnId, `accepted-${method}`, 'The actual accepted turn ID reaches the caller');
          equal(submissions.join(','), `An animated garden via ${method}`, 'Exactly one submission receives current React state');
        } finally { response.resolve({ ok: false, message: 'Fixture cleanup.' }); unregister(); }
      }
    },
  },
  {
    name: 'Registered form failures preserve the draft and never claim a submitted build',
    async run({ mount, root, surface }) {
      let calls = 0;
      mount(<form onSubmit={event => { event.preventDefault(); throw new Error('Unexpected native submission'); }}>
        <label>Retryable draft<textarea defaultValue="Keep my floating islands" /></label><button type="submit">Try registered build</button>
      </form>);
      for (const throws of [false, true]) {
        const unregister = registerVoiceForm(root.querySelector('form')!, async () => {
          calls++;
          if (throws) throw new Error('Fixture transport failed');
          return { ok: false, submitted: false, message: 'Fixture rejected the request.' };
        });
        try {
          const result = await surface.execute({ type: 'click', target: control(await surface.read(), 'Try registered build').id });
          refused(result, 'Rejected registered form');
          assert(result.submitted !== true, 'Failure must not report acceptance');
          equal(root.querySelector('textarea')!.value, 'Keep my floating islands', 'Failure preserves the draft');
        } finally { unregister(); }
      }
      equal(calls, 2, 'Each explicit attempt invokes the handler once, without retries');
    },
  },
  {
    name: 'Registered forms still enforce validity, disabled submission, and manual draft changes',
    async run({ mount, root, surface }) {
      let calls = 0;
      mount(<form onSubmit={event => event.preventDefault()}><label>Guarded registered draft<textarea required /></label><button type="submit">Submit guarded build</button></form>);
      const unregister = registerVoiceForm(root.querySelector('form')!, async () => { calls++; return { ok: true, submitted: true, message: 'Unexpected acceptance.' }; });
      try {
        let snapshot = await surface.read();
        refused(await surface.execute({ type: 'press', target: control(snapshot, 'Guarded registered draft').id, key: 'Enter' }), 'Invalid registered Enter');
        refused(await surface.execute({ type: 'click', target: control(snapshot, 'Submit guarded build').id }), 'Invalid registered button');
        accepted(await surface.execute({ type: 'fill', target: control(await surface.read(), 'Guarded registered draft').id, value: 'Reviewed draft' }), 'Fill valid draft');
        root.querySelector('button')!.disabled = true;
        snapshot = await surface.read();
        refused(await surface.execute({ type: 'press', target: control(snapshot, 'Guarded registered draft').id, key: 'Enter' }), 'Disabled registered Enter');
        refused(await surface.execute({ type: 'click', target: control(snapshot, 'Submit guarded build').id }), 'Disabled registered button');
        root.querySelector('button')!.disabled = false;
        snapshot = await surface.read();
        root.querySelector('textarea')!.value = 'The user is still editing';
        refused(await surface.execute({ type: 'press', target: control(snapshot, 'Guarded registered draft').id, key: 'Enter' }), 'Stale registered Enter');
        refused(await surface.execute({ type: 'click', target: control(snapshot, 'Submit guarded build').id }), 'Stale registered button');
        equal(calls, 0, 'No guard can be bypassed through the async handler');
        equal(root.querySelector('textarea')!.value, 'The user is still editing', 'The new manual draft is retained');
      } finally { unregister(); }
    },
  },
  {
    name: 'Registered form Enter respects its submitter confirmation and manual-only guards',
    async run({ mount, root, surface, speak }) {
      let calls = 0;
      mount(<form onSubmit={event => event.preventDefault()}><label>Confirmed draft<textarea defaultValue="Replace the old draft" /></label><button type="submit" data-voice-confirm>Reset this draft</button></form>);
      let unregister = registerVoiceForm(root.querySelector('form')!, async () => { calls++; return { ok: true, submitted: true, message: 'Confirmed request accepted.' }; });
      try {
        speak('Reset this draft.');
        let field = control(await surface.read(), 'Confirmed draft');
        const first = await surface.execute({ type: 'press', target: field.id, key: 'Enter' });
        equal(first.requiresConfirmation, true, 'Enter asks for the submitter confirmation');
        equal(calls, 0, 'The first Enter never invokes the registered handler');
        field = control(await surface.read(), 'Confirmed draft');
        equal((await surface.execute({ type: 'press', target: field.id, key: 'Enter' })).requiresConfirmation, true, 'Repeating Enter is not confirmation');
        equal(calls, 0, 'Repeated activation does not submit');
        speak('Reset this draft.\nYes.');
        accepted(await surface.execute({ type: 'press', target: control(await surface.read(), 'Confirmed draft').id, key: 'Enter' }), 'Fresh user confirmation authorizes Enter');
        equal(calls, 1, 'Only the confirmed request reaches the handler');
      } finally { unregister(); }
      mount(<form onSubmit={event => event.preventDefault()}><label>Manual draft<textarea defaultValue="Keep this manual" /></label><button type="submit" data-voice-manual>Choose draft file</button></form>);
      unregister = registerVoiceForm(root.querySelector('form')!, async () => { calls++; return { ok: true, message: 'Unexpected manual-only submission.' }; });
      try {
        refused(await surface.execute({ type: 'press', target: control(await surface.read(), 'Manual draft').id, key: 'Enter' }), 'Enter cannot bypass a manual-only submitter');
        equal(calls, 1, 'The manual-only form never invokes its handler');
      } finally { unregister(); }
    },
  },
  {
    name: 'Voice fill updates React state, then submits the exact draft once',
    async run({ mount, surface, root }) {
      const changes: string[] = [];
      const submissions: string[] = [];
      function ControlledBuilder() {
        const [value, setValue] = useState('A quiet garden');
        return <form onSubmit={event => { event.preventDefault(); submissions.push(value); }}>
          <label>Build request<textarea value={value} onChange={event => { changes.push(event.target.value); setValue(event.target.value); }} /></label>
          <button type="submit">Build this space</button>
          <output data-testid="controlled-value">{value}</output>
        </form>;
      }
      mount(<ControlledBuilder />);
      const field = control(await surface.read(), 'Build request');
      accepted(await surface.execute({ type: 'fill', target: field.id, value: 'A watercolor studio with a blue sky' }), 'Fill React textarea');
      equal(root.querySelector('output')?.textContent, 'A watercolor studio with a blue sky', 'React state reflects the voice draft');
      equal(changes.length, 1, 'React onChange fires once');
      const button = control(await surface.read(), 'Build this space');
      accepted(await surface.execute({ type: 'click', target: button.id }), 'Submit the builder');
      equal(submissions.length, 1, 'Submit fires exactly once');
      equal(submissions[0], 'A watercolor studio with a blue sky', 'Submission receives the current React value');
    },
  },
  {
    name: 'Enter refuses invalid forms and submits a valid React form exactly once',
    async run({ mount, surface }) {
      const submissions: string[] = [];
      function RequiredForm() {
        const [title, setTitle] = useState('');
        return <form onSubmit={event => { event.preventDefault(); submissions.push(title); }}>
          <label>Required title<input required value={title} onChange={event => setTitle(event.target.value)} /></label>
          <button type="submit">Create space</button>
        </form>;
      }
      mount(<RequiredForm />);
      let field = control(await surface.read(), 'Required title');
      refused(await surface.execute({ type: 'press', target: field.id, key: 'Enter' }), 'Empty required form');
      equal(submissions.length, 0, 'Invalid form was not submitted');
      accepted(await surface.execute({ type: 'fill', target: field.id, value: 'Evening studio' }), 'Complete required field');
      field = control(await surface.read(), 'Required title');
      accepted(await surface.execute({ type: 'press', target: field.id, key: 'Enter' }), 'Submit valid form with Enter');
      equal(submissions.length, 1, 'Valid Enter submits exactly once');
      equal(submissions[0], 'Evening studio', 'Valid Enter sees React state');
    },
  },
  {
    name: 'Enter cannot bypass a disabled submit button',
    async run({ mount, surface }) {
      let submitted = 0;
      mount(<form onSubmit={event => { event.preventDefault(); submitted++; }}>
        <input aria-label="Pending request" defaultValue="Ready text" />
        <button type="submit" disabled>Build in progress</button>
      </form>);
      const field = control(await surface.read(), 'Pending request');
      refused(await surface.execute({ type: 'press', target: field.id, key: 'Enter' }), 'Disabled form submission');
      equal(submitted, 0, 'Disabled form never submits');
    },
  },
  {
    name: 'A manual draft edit after the snapshot blocks a stale voice overwrite',
    async run({ mount, surface, root }) {
      let edit: (value: string) => void = () => undefined;
      function Draft() {
        const [value, setValue] = useState('Captured draft');
        edit = setValue;
        return <label>Concurrent draft<textarea value={value} onChange={event => setValue(event.target.value)} /></label>;
      }
      mount(<Draft />);
      const field = control(await surface.read(), 'Concurrent draft');
      flushSync(() => edit('The user is still writing'));
      refused(await surface.execute({ type: 'fill', target: field.id, value: 'Stale voice replacement' }), 'Overwriting a changed draft');
      equal(root.querySelector('textarea')?.value, 'The user is still writing', 'The user’s new draft is preserved');
      const fresh = control(await surface.read(), 'Concurrent draft');
      accepted(await surface.execute({ type: 'fill', target: fresh.id, value: 'Updated after a fresh read' }), 'Fresh snapshot permits editing');
    },
  },
  {
    name: 'A changed draft cannot be submitted by stale voice Enter',
    async run({ mount, surface }) {
      let edit: (value: string) => void = () => undefined;
      let submitted = 0;
      function Draft() {
        const [value, setValue] = useState('Previously reviewed');
        edit = setValue;
        return <form onSubmit={event => { event.preventDefault(); submitted++; }}>
          <label>Draft to submit<textarea value={value} onChange={event => setValue(event.target.value)} /></label>
          <button type="submit">Submit draft</button>
        </form>;
      }
      mount(<Draft />);
      const field = control(await surface.read(), 'Draft to submit');
      flushSync(() => edit('New unfinished user draft'));
      refused(await surface.execute({ type: 'press', target: field.id, key: 'Enter' }), 'Submitting an edited draft from an old snapshot');
      equal(submitted, 0, 'The unfinished draft is not submitted');
    },
  },
  {
    name: 'Removed and newly hidden controls reject stale IDs',
    async run({ mount, surface }) {
      let activated = 0;
      let change: () => void = () => undefined;
      function ChangingControls() {
        const [changed, setChanged] = useState(false);
        change = () => setChanged(true);
        return <>{!changed && <button onClick={() => activated++}>Removed action</button>}<button hidden={changed} onClick={() => activated++}>Hidden later</button></>;
      }
      mount(<ChangingControls />);
      const snapshot = await surface.read();
      const removed = control(snapshot, 'Removed action');
      const hidden = control(snapshot, 'Hidden later');
      flushSync(change);
      refused(await surface.execute({ type: 'click', target: removed.id }), 'Removed element');
      refused(await surface.execute({ type: 'click', target: hidden.id }), 'Element hidden after capture');
      equal(activated, 0, 'Stale controls never activate');
    },
  },
  {
    name: 'A URL change invalidates the captured page until it is read again',
    async run({ mount, surface }) {
      let activated = 0;
      mount(<button onClick={() => activated++}>Navigate safely</button>);
      const item = control(await surface.read(), 'Navigate safely');
      const previous = location.href;
      try {
        history.replaceState(null, '', `${location.pathname}${location.search}#voice-fixture-navigation`);
        refused(await surface.execute({ type: 'click', target: item.id }), 'Using a snapshot from the previous URL');
        equal(activated, 0, 'Stale navigation target never activates');
        const fresh = control(await surface.read(), 'Navigate safely');
        accepted(await surface.execute({ type: 'click', target: fresh.id }), 'Fresh navigation snapshot');
        equal(activated, 1, 'Fresh target activates once');
      } finally { history.replaceState(null, '', previous); }
    },
  },
  {
    name: 'Select exposes exact option values, changes React state, and rejects disabled options',
    async run({ mount, surface, root }) {
      let changes = 0;
      function Palette() {
        const [value, setValue] = useState('warm');
        return <label>Palette<select value={value} onChange={event => { changes++; setValue(event.target.value); }}>
          <option value="warm">Warm paper</option><option value="cool">Cool blue</option><option value="locked" disabled>Locked palette</option>
        </select></label>;
      }
      mount(<Palette />);
      const item = control(await surface.read(), 'Palette');
      assert(item.options?.some(option => typeof option === 'object' && option.value === 'cool' && option.label === 'Cool blue'), 'Select option labels/values are absent');
      accepted(await surface.execute({ type: 'select', target: item.id, value: 'cool' }), 'Choose an available option');
      equal(root.querySelector('select')?.value, 'cool', 'React select keeps the new value');
      equal(changes, 1, 'React select onChange fires once');
      const fresh = control(await surface.read(), 'Palette');
      refused(await surface.execute({ type: 'select', target: fresh.id, value: 'locked' }), 'Disabled option');
      refused(await surface.execute({ type: 'select', target: fresh.id, value: 'missing' }), 'Unknown option');
      equal(changes, 1, 'Rejected options do not fire onChange');
    },
  },
  {
    name: 'Checkbox activation changes React state once and filling it is refused',
    async run({ mount, surface, root }) {
      let changes = 0;
      function Toggle() {
        const [checked, setChecked] = useState(false);
        return <label><input type="checkbox" checked={checked} onChange={event => { changes++; setChecked(event.target.checked); }} />Show visitors</label>;
      }
      mount(<Toggle />);
      const item = control(await surface.read(), 'Show visitors');
      refused(await surface.execute({ type: 'fill', target: item.id, value: 'true' }), 'Fill checkbox as text');
      accepted(await surface.execute({ type: 'click', target: item.id }), 'Activate checkbox');
      equal(root.querySelector('input')?.checked, true, 'Checkbox state is checked');
      equal(changes, 1, 'Checkbox onChange fires once');
    },
  },
  {
    name: 'Native dialog isolates controls, rejects a stale background action, and accepts Escape',
    async run({ mount, surface, root }) {
      let backgroundClicks = 0;
      let cancels = 0;
      mount(<>
        <button onClick={() => backgroundClicks++}>Background build</button>
        <dialog onCancel={() => cancels++}><p>Confirm a local fixture choice</p><button>Dialog choice</button></dialog>
      </>);
      const background = control(await surface.read(), 'Background build');
      const dialog = root.querySelector('dialog')!;
      dialog.showModal();
      try {
        refused(await surface.execute({ type: 'click', target: background.id }), 'Background control while dialog is open');
        const snapshot = await surface.read();
        equal(snapshot.controls.length, 1, 'Only dialog controls are exposed');
        const choice = control(snapshot, 'Dialog choice');
        accepted(await surface.execute({ type: 'press', target: choice.id, key: 'Escape' }), 'Escape dialog');
        equal(dialog.open, false, 'Escape closes the native dialog');
        equal(cancels, 1, 'Native cancel handler receives one event');
        equal(backgroundClicks, 0, 'Background handler did not run');
      } finally { if (dialog.open) dialog.close(); }
    },
  },
  {
    name: 'Preventing the native dialog cancel event keeps it open',
    async run({ mount, surface, root }) {
      let cancels = 0;
      mount(<dialog onCancel={event => { event.preventDefault(); cancels++; }}><button>Keep this dialog</button></dialog>);
      const dialog = root.querySelector('dialog')!;
      dialog.showModal();
      try {
        const item = control(await surface.read(), 'Keep this dialog');
        accepted(await surface.execute({ type: 'press', target: item.id, key: 'Escape' }), 'Dispatch a cancelable Escape');
        equal(cancels, 1, 'Dialog cancellation was requested once');
        equal(dialog.open, true, 'Prevented cancellation keeps the dialog open');
      } finally { dialog.close(); }
    },
  },
  {
    name: 'Gallery and globe keyboard controls receive real arrow events',
    async run({ mount, surface, root }) {
      const events: string[] = [];
      function KeyboardControls() {
        const [position, setPosition] = useState(0);
        return <>
          <div role="button" tabIndex={0} aria-label="Space gallery" onKeyDown={event => { events.push(`gallery:${event.key}`); if (event.key === 'ArrowRight') setPosition(value => value + 1); }}>Gallery position {position}</div>
          <div role="button" tabIndex={0} aria-label="World globe" onKeyDown={event => events.push(`globe:${event.key}`)}>Rotate the world</div>
        </>;
      }
      mount(<KeyboardControls />);
      const snapshot = await surface.read();
      accepted(await surface.execute({ type: 'press', target: control(snapshot, 'Space gallery').id, key: 'ArrowRight' }), 'Gallery next');
      accepted(await surface.execute({ type: 'press', target: control(snapshot, 'World globe').id, key: 'ArrowLeft' }), 'Globe rotate');
      equal(events.join(','), 'gallery:ArrowRight,globe:ArrowLeft', 'Each target receives the intended keyboard event once');
      assert(root.textContent?.includes('Gallery position 1'), 'Gallery React state did not update');
      equal(document.activeElement?.getAttribute('aria-label'), 'World globe', 'Keyboard target receives focus');
    },
  },
  {
    name: 'Opening a help dialog with a reset option never arms or requests a reset',
    async run({ mount, root, surface, speak }) {
      let resets = 0;
      mount(<>
        <button onClick={() => root.querySelector('dialog')!.showModal()}>Demo guide</button>
        <dialog><h2>The two-minute tour</h2><button data-voice-confirm onClick={() => resets++}>Reset this space</button></dialog>
      </>);
      speak('Open the demo guide.');
      const opened = await surface.execute({ type: 'click', target: control(await surface.read(), 'Demo guide').id });
      accepted(opened, 'Opening help is an ordinary navigation action');
      assert(!opened.requiresConfirmation, 'Help never asks to remove saved content');
      speak('Open the demo guide.\nYes.');
      const reset = await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset this space').id });
      equal(reset.requiresConfirmation, true, 'A later reset attempt still needs its own confirmation');
      equal(resets, 0, 'A yes after opening help cannot authorize resetting');
    },
  },
  {
    name: 'Live transport, user transcripts, and the real reset dialog complete one confirmed reset end to end',
    async run({ mount, root }) {
      let turns: VoiceTranscript[] = [];
      let state: LiveVoiceSnapshot | undefined;
      let resets = 0;
      let microphoneRequests = 0;
      let stoppedTracks = 0;
      const actionResults: VoiceActionResult[] = [];
      const planConversations: { role: string; text: string }[][] = [];
      const response = deferred<Response>();
      const mock = mockResetRequest(() => response.promise);
      const globals = new Map<string, PropertyDescriptor | undefined>();
      const replaceGlobal = (key: string, value: unknown) => {
        globals.set(key, Object.getOwnPropertyDescriptor(window, key));
        Object.defineProperty(window, key, { configurable: true, writable: true, value });
      };
      class FixtureTrack extends EventTarget {
        enabled = true;
        readyState = 'live';
        stop() { if (this.readyState === 'live') { this.readyState = 'ended'; stoppedTracks++; } }
      }
      class FixtureStream {
        track = new FixtureTrack();
        getTracks() { return [this.track]; }
        getAudioTracks() { return [this.track]; }
      }
      class FixtureChannel extends EventTarget {
        readyState = 'open';
        sent: Record<string, unknown>[] = [];
        message(event: Record<string, unknown>) { this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) })); }
        send(raw: string) {
          const event = JSON.parse(raw);
          this.sent.push(event);
          if (event.type === 'session.close') queueMicrotask(() => this.message({ type: 'session.closed', reason: 'close_requested' }));
        }
        close() { if (this.readyState !== 'closed') { this.readyState = 'closed'; this.dispatchEvent(new Event('close')); } }
      }
      let peer: FixturePeer | undefined;
      class FixturePeer extends EventTarget {
        channel = new FixtureChannel();
        connectionState = 'new';
        iceGatheringState = 'complete';
        localDescription?: RTCSessionDescriptionInit;
        constructor() { super(); peer = this; }
        createDataChannel() { return this.channel; }
        addTrack() {}
        async createOffer() { return { type: 'offer', sdp: 'isolated-reset-offer' }; }
        async setLocalDescription(value: RTCSessionDescriptionInit) { this.localDescription = value; }
        async setRemoteDescription() { this.connectionState = 'connected'; }
        close() { if (this.connectionState !== 'closed') { this.connectionState = 'closed'; this.dispatchEvent(new Event('connectionstatechange')); } }
      }
      class FixtureAudio {
        paused = true;
        setAttribute() {}
        async play() { this.paused = false; }
        pause() { this.paused = true; }
      }
      class FixtureAudioContext {
        state = 'running';
        async resume() { this.state = 'running'; }
        async close() { this.state = 'closed'; }
        createMediaStreamSource() { return { connect() {} }; }
        createAnalyser() { return { fftSize: 256, getByteTimeDomainData(samples: Uint8Array) { samples.fill(128); } }; }
      }
      const mediaDescriptor = Object.getOwnPropertyDescriptor(navigator.mediaDevices, 'getUserMedia');
      replaceGlobal('RTCPeerConnection', FixturePeer);
      replaceGlobal('Audio', FixtureAudio);
      replaceGlobal('AudioContext', FixtureAudioContext);
      Object.defineProperty(navigator.mediaDevices, 'getUserMedia', { configurable: true, value: async () => { microphoneRequests++; return new FixtureStream(); } });
      const surface = createVoiceSurface({ context: () => 'Isolated complete voice reset flow', userSpeech: () => turns.filter(turn => turn.role === 'user').map(turn => turn.text).join('\n'), userTurns: () => turns });
      const client = createLiveVoice({
        timings: { connect: 1000, settle: 8, transcriptWait: 70, plan: 1000, close: 30 },
        readSurface: surface.read,
        execute: async action => { const result = await surface.execute(action); actionResults.push(result); return result; },
        onTranscript: value => { turns = value; },
        onState: value => { state = value; },
        fetch: async (path, init = {}) => {
          equal(init.method, 'POST', 'Mock voice transport only accepts POST');
          if (path === '/api/voice/session') return Response.json({ session: { id: 'isolated-reset-live' }, transport: { type: 'webrtc', sdp: 'isolated-answer' }, controlToken: 'isolated-token' });
          if (path === '/api/voice/end') return Response.json({ ok: true });
          equal(path, '/api/voice/plan', 'Unexpected voice request cannot leave the fixture');
          const body = JSON.parse(String(init.body)) as { conversation: { role: string; text: string }[]; surface: VoiceSurface; history: { result: VoiceActionResult }[] };
          planConversations.push(body.conversation);
          if (body.history.length) {
            equal(body.history.at(-1)?.result.ok, true, 'Planner may finish only after the real action succeeds');
            equal(resets, 1, 'Planner never reports completion before the reset callback');
            return Response.json({ action: { type: 'done', message: 'The demo was reset.' } });
          }
          return Response.json({ action: { type: 'click', target: control(body.surface, 'Reset demo').id } });
        },
      });
      try {
        mount(<ResetDemo onReset={() => resets++}/>);
        await client.start();
        assert(peer, 'Mock peer must be created');
        const channel = peer.channel;
        channel.message({ type: 'session.started', session: { id: 'isolated-reset-live' } });
        channel.message({ type: 'session.input_transcript.delta', event_id: 'request', delta: 'Reset the demo.', start_ms: 0, end_ms: 1000 });
        channel.message({ type: 'session.delegation.created', offset_ms: 1000, delegation: { id: 'open-reset', target: 'client' } });
        await until(() => actionResults.length === 1 && !state?.working, 'Live did not open and arm the real reset dialog');
        equal(actionResults[0].requiresConfirmation, true, 'Opening returns the real UI confirmation gate');
        equal(mock.requests.length, 0, 'The opening request never resets the demo');
        const requestTurnId = turns.filter(turn => turn.role === 'user').at(-1)?.id;

        channel.message({ type: 'session.input_transcript.delta', event_id: 'reply', delta: 'Yes, confirm the reset.', start_ms: 1100, end_ms: 1500 });
        const replyTurnId = turns.filter(turn => turn.role === 'user').at(-1)?.id;
        assert(replyTurnId && replyTurnId !== requestTurnId, 'Prompt confirmation is a new user turn before any assistant transcript arrives');
        channel.message({ type: 'session.delegation.created', offset_ms: 1500, delegation: { id: 'confirm-reset', target: 'client' } });
        await until(() => mock.requests.length === 1, 'Fresh user consent did not reach the mocked reset API');
        channel.message({ type: 'session.output_transcript.delta', event_id: 'late-question', delta: 'Please say yes to confirm.', start_ms: 1010, end_ms: 1090 });
        equal(turns.filter(turn => turn.role === 'user').at(-1)?.id, replyTurnId, 'A delayed question transcript does not change the consent identity');
        await new Promise(resolve => setTimeout(resolve, 220));
        equal(resets, 0, 'Slow API has not completed the reset');
        equal(actionResults.length, 1, 'Live waits for the reset result instead of reporting activation as success');
        equal(state?.working, true, 'The accepted reset stays in progress while awaiting its result');
        assert(!channel.sent.some(event => event.type === 'session.commentary.append' && event.content === 'The demo was reset.'), 'No completion is spoken before API success');
        response.resolve(Response.json({ ok: true, users: [] }));
        await until(() => resets === 1 && actionResults.length === 2 && !state?.working, 'Confirmed reset did not finish through Live');
        accepted(actionResults[1], 'Live receives the actual successful reset result');
        assert(!root.querySelector('dialog')?.open, 'Successful reset closes the actual dialog');
        assert(planConversations[1].some(turn => turn.role === 'user' && turn.text === 'Yes, confirm the reset.'), 'Planner receives the separate affirmative request');
        channel.message({ type: 'session.delegation.created', offset_ms: 1500, delegation: { id: 'duplicate-confirm-reset', target: 'client' } });
        await new Promise(resolve => setTimeout(resolve, 110));
        equal(mock.requests.length, 1, 'Duplicate delegation cannot repeat the reset');
        equal(resets, 1, 'The reset completes exactly once');
        equal(actionResults.length, 2, 'Only the opener and the confirmed action execute');
        equal(microphoneRequests, 1, 'Exactly one fake microphone was acquired');
      } finally {
        response.resolve(Response.json({ ok: true, users: [] }));
        try { await client.stop(); }
        finally {
          client.destroy();
          surface.clear();
          if (mediaDescriptor) Object.defineProperty(navigator.mediaDevices, 'getUserMedia', mediaDescriptor);
          else Reflect.deleteProperty(navigator.mediaDevices, 'getUserMedia');
          for (const [key, descriptor] of globals) {
            if (descriptor) Object.defineProperty(window, key, descriptor);
            else Reflect.deleteProperty(window, key);
          }
          mock.restore();
        }
      }
      equal(stoppedTracks, 1, 'Fake microphone is released after the flow');
    },
  },
  {
    name: 'Opening the real reset dialog by voice needs only one fresh natural confirmation',
    async run({ mount, root, surface, speak }) {
      const mock = mockResetRequest();
      let resets = 0;
      try {
        for (const [index, reply] of ['Yes.', 'Yes, confirm the reset.', 'Yes, confirm it.', 'Yes, please do.', 'Yes, reset demo.'].entries()) {
          surface.clear();
          mount(<ResetDemo key={index} onReset={() => resets++}/>);
          speak(`Open reset demo ${index}.`);
          const opened = await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id });
          equal(opened.requiresConfirmation, true, 'Opening the dialog returns its armed confirmation question');
          assert(root.querySelector('dialog')?.open, 'The real reset dialog opens');
          equal(mock.requests.length, index, 'Opening confirmation does not send a reset request');
          speak(`Open reset demo ${index}.\n${reply}`);
          const result = await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id });
          accepted(result, `One fresh reply is sufficient: ${reply}`);
          equal(mock.requests.length, index + 1, 'Exactly one reset request is sent');
          equal(resets, index + 1, 'Successful reset completes once');
          assert(!root.querySelector('dialog')?.open, 'Successful reset closes its dialog');
        }
      } finally { mock.restore(); }
    },
  },
  {
    name: 'Real reset never treats assistant speech or a repeated activation as user confirmation',
    async run({ mount }) {
      const mock = mockResetRequest();
      let resets = 0;
      let turns = [transcriptTurn('request', 'Reset the demo.', 0)];
      const surface = createVoiceSurface({ context: () => 'Isolated reset transcript check', userSpeech: () => turns.filter(turn => turn.role === 'user').map(turn => turn.text).join('\n'), userTurns: () => turns });
      try {
        mount(<ResetDemo onReset={() => resets++}/>);
        equal((await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id })).requiresConfirmation, true, 'Opening reset arms its gate');
        refused(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id }), 'A repeated activation with no new user speech is refused');
        turns = [...turns, transcriptTurn('assistant-yes', 'Yes, confirm the reset.', 1000, 'assistant')];
        refused(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id }), 'Assistant saying yes cannot authorize the reset');
        equal(mock.requests.length, 0, 'No mutation without fresh user consent');
        turns = [...turns, transcriptTurn('user-yes', 'Yes, confirm the reset.', 2000)];
        accepted(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id }), 'A later actual user confirmation succeeds');
        equal(mock.requests.length, 1, 'The genuine confirmation sends exactly one request');
        equal(resets, 1, 'Reset completion fires once');
      } finally { surface.clear(); mock.restore(); }
    },
  },
  {
    name: 'Cancelling and reopening the real reset dialog invalidates the previous confirmation',
    async run({ mount, root, surface, speak }) {
      const mock = mockResetRequest();
      let resets = 0;
      try {
        mount(<ResetDemo onReset={() => resets++}/>);
        speak('Reset the demo.');
        equal((await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id })).requiresConfirmation, true, 'First opening arms confirmation');
        speak('Reset the demo.\nYes.');
        accepted(await surface.execute({ type: 'click', target: control(await surface.read(), 'Cancel').id }), 'Cancel closes the pending request');
        assert(!root.querySelector('dialog')?.open, 'Cancelled dialog closes');
        equal((await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id })).requiresConfirmation, true, 'Reopening asks for a new confirmation');
        refused(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id }), 'Previous yes cannot authorize the reopened dialog');
        equal(mock.requests.length, 0, 'Cancelled confirmation never sends a request');
        speak('Reset the demo.\nYes.\nYes, reset the demo.');
        accepted(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id }), 'New confirmation authorizes the reopened request');
        equal(mock.requests.length, 1, 'Only the newly confirmed reset is sent');
        equal(resets, 1, 'Only the new request completes');
      } finally { mock.restore(); }
    },
  },
  {
    name: 'Real reset awaits slow API completion and blocks duplicate requests while pending',
    async run({ mount, root, surface, speak }) {
      const response = deferred<Response>();
      const mock = mockResetRequest(() => response.promise);
      let resets = 0;
      try {
        mount(<ResetDemo onReset={() => resets++}/>);
        speak('Reset the demo.');
        await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id });
        speak('Reset the demo.\nYes.');
        let finished = false;
        const pending = surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id }).then(result => { finished = true; return result; });
        await until(() => mock.requests.length === 1, 'Confirmed reset did not start its mocked request');
        await new Promise(resolve => setTimeout(resolve, 220));
        equal(finished, false, 'Activation is not reported as completion while the reset is pending');
        equal(resets, 0, 'App reset does not happen before API success');
        equal(root.querySelector('dialog')?.getAttribute('aria-busy'), 'true', 'Dialog exposes its pending state');
        const resetting = control(await surface.read(), 'Resetting…');
        equal(resetting.disabled, true, 'Pending reset disables its confirm control');
        refused(await surface.execute({ type: 'click', target: resetting.id }), 'Duplicate pending activation is refused');
        equal(mock.requests.length, 1, 'Duplicate activation does not send another request');
        response.resolve(Response.json({ ok: true, users: [] }));
        const result = await pending;
        accepted(result, 'Reset success follows API success');
        assert(/reset|restor/i.test(result.message), 'Successful result describes the completed reset');
        equal(resets, 1, 'App reset completes once after the API response');
      } finally { response.resolve(Response.json({ ok: true, users: [] })); mock.restore(); }
    },
  },
  {
    name: 'Real reset reports API failure honestly and preserves the open dialog',
    async run({ mount, root, surface, speak }) {
      const mock = mockResetRequest(() => Response.json({ error: 'Fixture reset could not restore the original spaces.' }, { status: 503 }));
      let resets = 0;
      try {
        mount(<ResetDemo onReset={() => resets++}/>);
        speak('Reset the demo.');
        await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id });
        speak('Reset the demo.\nYes.');
        const result = await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id });
        refused(result, 'Failed reset is not reported as successful activation');
        assert(result.message.includes('Fixture reset could not restore'), 'Voice receives the actual reset error');
        equal(resets, 0, 'Failure never completes app reset');
        equal(mock.requests.length, 1, 'Failure does not automatically retry');
        assert(root.querySelector('dialog')?.open, 'Failure preserves the dialog for review or retry');
        assert(root.querySelector('[role="alert"]')?.textContent?.includes('Fixture reset could not restore'), 'Visible error matches the voice result');
        equal(control(await surface.read(), 'Reset demo').disabled, false, 'Confirm control becomes available again');
      } finally { mock.restore(); }
    },
  },
  {
    name: 'Confirmed reset completes even if revoking the session unmounts its original component',
    async run({ mount, surface, speak }) {
      const response = deferred<Response>();
      const mock = mockResetRequest(() => response.promise);
      let resets = 0;
      try {
        mount(<ResetDemo onReset={() => resets++}/>);
        speak('Reset the demo.');
        await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id });
        speak('Reset the demo.\nYes.');
        const pending = surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id });
        await until(() => mock.requests.length === 1, 'Reset did not start before the simulated session change');
        mount(<p>The old session view has unmounted.</p>);
        response.resolve(Response.json({ ok: true, users: [] }));
        accepted(await pending, 'Successful admitted action remains successful after component unmount');
        equal(mock.requests.length, 1, 'Unmount does not retry the reset request');
        equal(resets, 1, 'Original completion callback runs once despite unmount');
      } finally { response.resolve(Response.json({ ok: true, users: [] })); mock.restore(); }
    },
  },
  {
    name: 'Structured user turns keep reset confirmation valid when older transcript history is compacted',
    async run({ mount }) {
      const mock = mockResetRequest();
      let resets = 0;
      const request = transcriptTurn('reset-request', 'Reset the demo.', 2000);
      let turns = [transcriptTurn('older-user-turn', 'Show me community.', 0), request];
      const surface = createVoiceSurface({ context: () => 'Isolated transcript compaction check', userSpeech: () => turns.filter(turn => turn.role === 'user').map(turn => turn.text).join('\n'), userTurns: () => turns });
      try {
        mount(<ResetDemo onReset={() => resets++}/>);
        equal((await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id })).requiresConfirmation, true, 'Opening reset arms its confirmation with stable turn IDs');
        turns = [request, transcriptTurn('reset-question', 'Please say yes to confirm.', 3000, 'assistant'), transcriptTurn('fresh-confirmation', 'Yes.', 4000)];
        accepted(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id }), 'Dropping older history does not discard fresh explicit consent');
        equal(mock.requests.length, 1, 'Fresh confirmation after compaction sends one request');
        equal(resets, 1, 'Reset completes after transcript compaction');
      } finally { surface.clear(); mock.restore(); }
    },
  },
  {
    name: 'Appending yes to the original structured utterance cannot confirm its own reset request',
    async run({ mount }) {
      const mock = mockResetRequest();
      let resets = 0;
      let turns = [transcriptTurn('same-request-turn', 'Reset the demo.', 0)];
      const surface = createVoiceSurface({ context: () => 'Isolated same-utterance confirmation check', userSpeech: () => turns.filter(turn => turn.role === 'user').map(turn => turn.text).join('\n'), userTurns: () => turns });
      try {
        mount(<ResetDemo onReset={() => resets++}/>);
        await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id });
        turns = [{ ...turns[0], text: 'Reset the demo. Yes.', endMs: 1500 }];
        refused(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id }), 'A delayed fragment of the original request is not separate consent');
        equal(mock.requests.length, 0, 'Delayed original speech never sends a reset request');
        turns = [...turns, transcriptTurn('next-user-reply', 'Yes, please do.', 3000)];
        accepted(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset demo').id }), 'A separate later user reply can confirm');
        equal(mock.requests.length, 1, 'Separate consent resets exactly once');
        equal(resets, 1, 'Only the fresh reply completes reset');
      } finally { surface.clear(); mock.restore(); }
    },
  },
  {
    name: 'Reset requires a new explicit confirmation after a guarded activation attempt',
    async run({ mount, surface, speak }) {
      let resetCount = 0;
      speak('Please reset it. Yes, reset it.');
      mount(<button className="reset-demo-confirm" onClick={() => resetCount++}>Reset this fixture</button>);
      const reset = control(await surface.read(), 'Reset this fixture');
      equal(reset.requiresConfirmation, true, 'Reset is marked as requiring confirmation');
      const first = await surface.execute({ type: 'click', target: reset.id });
      refused(first, 'Confirmation from before the control was shown');
      equal(first.requiresConfirmation, true, 'Refusal asks for confirmation');
      equal(resetCount, 0, 'Early reset did not execute');
      speak('Please reset it. Yes, reset it. Yes, go ahead.');
      const fresh = control(await surface.read(), 'Reset this fixture');
      accepted(await surface.execute({ type: 'click', target: fresh.id }), 'Later explicit confirmation');
      equal(resetCount, 1, 'Confirmed reset executes once');
    },
  },
  {
    name: 'Viewing a reset control and unrelated earlier affirmations never arm a destructive action',
    async run({ mount, surface, speak }) {
      let resets = 0;
      mount(<button data-voice-confirm onClick={() => resets++}>Reset this space</button>);
      speak('Show me the guide.');
      await surface.read();
      speak('Show me the guide.\nYes, that is useful.\nReset this space.');
      let reset = control(await surface.read(), 'Reset this space');
      const first = await surface.execute({ type: 'click', target: reset.id });
      refused(first, 'An unrelated earlier yes cannot approve the first reset attempt');
      equal(first.requiresConfirmation, true, 'First attempt requests a new confirmation');
      equal(resets, 0, 'No destructive action before its own confirmation');
      speak('Show me the guide.\nYes, that is useful.\nReset this space.\nYes, please reset this space.');
      reset = control(await surface.read(), 'Reset this space');
      accepted(await surface.execute({ type: 'click', target: reset.id }), 'Direct affirmation of the pending reset');
      equal(resets, 1, 'The explicitly confirmed reset runs once');
    },
  },
  {
    name: 'Only the latest clear reply can confirm reset and confirmation cannot be reused',
    async run({ mount, surface, speak }) {
      let resets = 0;
      mount(<button data-voice-confirm onClick={() => resets++}>Reset this space</button>);
      speak('Reset this space.');
      let reset = control(await surface.read(), 'Reset this space');
      refused(await surface.execute({ type: 'click', target: reset.id }), 'Arm the reset confirmation');
      speak('Reset this space.\nYes.\nI am still thinking.');
      reset = control(await surface.read(), 'Reset this space');
      refused(await surface.execute({ type: 'click', target: reset.id }), 'An older yes is not the latest reply');
      equal(resets, 0, 'Unrelated latest reply does not reset');
      speak('Reset this space.\nYes.\nI am still thinking.\nYes, but do not reset it.');
      reset = control(await surface.read(), 'Reset this space');
      refused(await surface.execute({ type: 'click', target: reset.id }), 'A negative reply overrides yes');
      speak('Reset this space.\nYes.\nI am still thinking.\nYes, but do not reset it.\nYes.');
      reset = control(await surface.read(), 'Reset this space');
      accepted(await surface.execute({ type: 'click', target: reset.id }), 'A fresh explicit affirmative may reset');
      equal(resets, 1, 'One reset after direct confirmation');
      reset = control(await surface.read(), 'Reset this space');
      refused(await surface.execute({ type: 'click', target: reset.id }), 'The prior confirmation cannot run reset again');
      equal(resets, 1, 'Confirmed action is not repeated');
    },
  },
  {
    name: 'Closing and reopening the same reset dialog requires a new confirmation',
    async run({ mount, surface, root, speak }) {
      let resets = 0;
      mount(<dialog><button data-voice-confirm onClick={() => resets++}>Reset this space</button></dialog>);
      const dialog = root.querySelector('dialog')!;
      dialog.showModal();
      speak('Reset this space.');
      refused(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset this space').id }), 'Arm the first reset');
      const closed = new Promise<void>(resolve => dialog.addEventListener('close', () => resolve(), { once: true }));
      dialog.close();
      await closed;
      dialog.showModal();
      speak('Reset this space.\nYes.');
      const fresh = await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset this space').id });
      refused(fresh, 'The old dialog confirmation cannot authorize a reopened dialog');
      equal(fresh.requiresConfirmation, true, 'Reopened dialog requests confirmation again');
      equal(resets, 0, 'Reopening preserves saved content');
      speak('Reset this space.\nYes.\nYes, reset this space.');
      accepted(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset this space').id }), 'Confirm the reopened request');
      equal(resets, 1, 'Only the newly confirmed reset runs');
    },
  },
  {
    name: 'A cancelled dialog disarms reset even when its cancel event keeps it open',
    async run({ mount, surface, root, speak }) {
      let resets = 0;
      mount(<dialog onCancel={event => event.preventDefault()}><button data-voice-confirm onClick={() => resets++}>Reset this space</button></dialog>);
      const dialog = root.querySelector('dialog')!;
      dialog.showModal();
      speak('Reset this space.');
      const item = control(await surface.read(), 'Reset this space');
      refused(await surface.execute({ type: 'click', target: item.id }), 'Arm the reset');
      dialog.dispatchEvent(new Event('cancel', { cancelable: true }));
      equal(dialog.open, true, 'The prevented cancel leaves the dialog visible');
      speak('Reset this space.\nYes.');
      refused(await surface.execute({ type: 'click', target: item.id }), 'Cancel revokes the pending confirmation without needing a new snapshot');
      equal(resets, 0, 'Cancelled confirmation does not reset');
    },
  },
  {
    name: 'Hiding a reset control or opening another scope revokes pending confirmation',
    async run({ mount, surface, root, speak }) {
      let resets = 0;
      mount(<><section><button data-voice-confirm onClick={() => resets++}>Reset this space</button></section><dialog><button>Other view</button></dialog></>);
      speak('Reset this space.');
      refused(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset this space').id }), 'Arm a visible reset');
      const section = root.querySelector('section')!;
      section.hidden = true;
      await Promise.resolve();
      section.hidden = false;
      speak('Reset this space.\nYes.');
      refused(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset this space').id }), 'Restoring visibility cannot restore old consent');
      const dialog = root.querySelector('dialog')!;
      dialog.showModal();
      await Promise.resolve();
      const closed = new Promise<void>(resolve => dialog.addEventListener('close', () => resolve(), { once: true }));
      dialog.close();
      await closed;
      speak('Reset this space.\nYes.\nYes.');
      refused(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset this space').id }), 'Returning from a different scope requires a new request');
      equal(resets, 0, 'Hidden and background requests preserve saved content');
    },
  },
  {
    name: 'Clearing a Live session revokes confirmation and removes old dialog listeners',
    async run({ mount, surface, root, speak }) {
      let resets = 0;
      mount(<>
        <dialog data-first><button data-voice-confirm onClick={() => resets++}>Reset first space</button></dialog>
        <dialog data-second><button data-voice-confirm onClick={() => resets++}>Reset second space</button></dialog>
      </>);
      const first = root.querySelector<HTMLDialogElement>('dialog[data-first]')!;
      const second = root.querySelector<HTMLDialogElement>('dialog[data-second]')!;
      first.showModal();
      speak('Reset first space.');
      refused(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset first space').id }), 'Arm the old Live session');
      surface.clear();
      speak('Reset first space.\nYes.');
      refused(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset first space').id }), 'A new session cannot reuse old confirmation');
      surface.clear();
      const closed = new Promise<void>(resolve => first.addEventListener('close', () => resolve(), { once: true }));
      first.close();
      await closed;
      second.showModal();
      speak('Reset second space.');
      refused(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset second space').id }), 'The reused surface can arm a new request');
      first.dispatchEvent(new Event('cancel', { cancelable: true }));
      speak('Reset second space.\nYes.');
      accepted(await surface.execute({ type: 'click', target: control(await surface.read(), 'Reset second space').id }), 'A cleared dialog listener cannot affect the new request');
      equal(resets, 1, 'Only the new Live request executes');
    },
  },
  {
    name: 'Negative confirmation refuses reset even when the user also says yes',
    async run({ mount, surface, speak }) {
      let resets = 0;
      speak('Reset the fixture.');
      mount(<button data-voice-confirm onClick={() => resets++}>Confirm reset</button>);
      const reset = control(await surface.read(), 'Confirm reset');
      refused(await surface.execute({ type: 'click', target: reset.id }), 'Initial attempt arms confirmation');
      speak('Reset the fixture. Yes, but do not reset it.');
      refused(await surface.execute({ type: 'click', target: reset.id }), 'Negative reset confirmation');
      equal(resets, 0, 'Negative confirmation preserves the fixture');
    },
  },
  {
    name: 'File upload and manual-only controls cannot be activated by voice',
    async run({ mount, surface }) {
      let clicks = 0;
      mount(<>
        <input aria-label="Upload reference" type="file" onClick={event => { event.preventDefault(); clicks++; }} />
        <div data-voice-manual><button onClick={() => clicks++}>Choose a private file</button></div>
      </>);
      const snapshot = await surface.read();
      const file = control(snapshot, 'Upload reference');
      assert(file.value === undefined, 'File input value must not be captured');
      refused(await surface.execute({ type: 'click', target: file.id }), 'File picker activation');
      refused(await surface.execute({ type: 'fill', target: file.id, value: '/tmp/fixture.txt' }), 'File path injection');
      refused(await surface.execute({ type: 'click', target: control(snapshot, 'Choose a private file').id }), 'Manual-only control');
      equal(clicks, 0, 'Manual controls receive no click');
    },
  },
  {
    name: 'Foreign and new-tab links are refused for clicks and keyboard activation',
    async run({ mount, surface }) {
      let clicks = 0;
      const prevent = (event: React.MouseEvent<HTMLAnchorElement>) => { event.preventDefault(); clicks++; };
      mount(<>
        <a href="https://example.com/voice-fixture-never-opened" onClick={prevent}>Foreign destination</a>
        <a href="#voice-fixture-never-opened" target="_blank" onClick={prevent}>New tab destination</a>
      </>);
      const snapshot = await surface.read();
      for (const name of ['Foreign destination', 'New tab destination']) {
        const item = control(snapshot, name);
        refused(await surface.execute({ type: 'click', target: item.id }), `Click “${name}”`);
        refused(await surface.execute({ type: 'press', target: item.id, key: 'Enter' }), `Enter “${name}”`);
      }
      equal(clicks, 0, 'External and new-tab handlers are never activated');
    },
  },
  {
    name: 'Read-only fields and oversized values are rejected without changing the value',
    async run({ mount, surface, root }) {
      mount(<><input aria-label="Read-only title" readOnly defaultValue="Kept title" /><input aria-label="Short title" maxLength={5} defaultValue="Short" /></>);
      const snapshot = await surface.read();
      refused(await surface.execute({ type: 'fill', target: control(snapshot, 'Read-only title').id, value: 'Changed' }), 'Read-only edit');
      refused(await surface.execute({ type: 'fill', target: control(snapshot, 'Short title').id, value: 'Too many characters' }), 'Oversized edit');
      equal(root.querySelectorAll('input')[0].value, 'Kept title', 'Read-only value stays intact');
      equal(root.querySelectorAll('input')[1].value, 'Short', 'Limited field stays intact');
    },
  },
  {
    name: 'An absent generated frame and cleared snapshots fail safely',
    async run({ mount, surface }) {
      let clicks = 0;
      mount(<button onClick={() => clicks++}>Current host control</button>);
      const snapshot = await surface.read();
      assert(snapshot.controls.every(item => !item.id.startsWith('frame:')), 'Absent frame exposed controls');
      refused(await surface.execute({ type: 'click', target: 'frame:missing-control' }), 'Absent frame target');
      const host = control(snapshot, 'Current host control');
      surface.clear();
      refused(await surface.execute({ type: 'click', target: host.id }), 'Cleared host snapshot');
      equal(clicks, 0, 'Cleared target never activates');
      accepted(await surface.execute({ type: 'done', message: 'Fixture complete.' }), 'Finishing without an action');
    },
  },
];

const button = document.getElementById('run-checks') as HTMLButtonElement;
const results = document.getElementById('results') as HTMLOListElement;
const summary = document.getElementById('summary') as HTMLParagraphElement;
const fixtureRoot = document.getElementById('fixture-root') as HTMLDivElement;
let running = false;

function resultRow(check: Check, index: number) {
  const row = document.createElement('li');
  row.className = 'result-row';
  row.dataset.status = 'pending';
  row.dataset.check = String(index + 1);
  const state = document.createElement('span');
  state.className = 'result-state';
  state.textContent = 'PENDING';
  const content = document.createElement('div');
  content.textContent = check.name;
  const detail = document.createElement('span');
  detail.className = 'result-detail';
  content.append(detail);
  row.append(state, content);
  results.append(row);
  return { row, state, detail };
}

async function runChecks() {
  if (running) return;
  running = true;
  button.disabled = true;
  button.textContent = 'Running checks…';
  results.replaceChildren();
  const rows = checks.map(resultRow);
  let passed = 0;
  let failed = 0;
  document.body.dataset.testStatus = 'running';
  for (let index = 0; index < checks.length; index++) {
    const check = checks[index];
    const { row, state, detail } = rows[index];
    row.dataset.status = 'running';
    state.textContent = 'RUNNING';
    summary.textContent = `Running ${index + 1} of ${checks.length}: ${check.name}`;
    let reactRoot: Root | undefined;
    let speech = '';
    const surface = createVoiceSurface({ context: () => `Isolated browser regression: ${check.name}`, userSpeech: () => speech });
    const fixture: Fixture = {
      root: fixtureRoot,
      surface,
      speak: value => { speech = value; },
      mount(node) {
        reactRoot ??= createRoot(fixtureRoot);
        flushSync(() => reactRoot!.render(node));
      },
    };
    const started = performance.now();
    try {
      await check.run(fixture);
      passed++;
      row.dataset.status = 'pass';
      state.textContent = 'PASS';
      detail.textContent = `${Math.round(performance.now() - started)} ms`;
    } catch (error) {
      failed++;
      row.dataset.status = 'fail';
      state.textContent = 'FAIL';
      detail.textContent = error instanceof Error ? error.message : String(error);
    } finally {
      for (const dialog of fixtureRoot.querySelectorAll('dialog[open]')) (dialog as HTMLDialogElement).close();
      surface.clear();
      if (reactRoot) flushSync(() => reactRoot!.unmount());
      fixtureRoot.replaceChildren();
    }
  }
  fixtureRoot.textContent = 'All fixtures were unmounted. No application data was created or changed.';
  summary.textContent = `${passed}/${checks.length} passed${failed ? ` · ${failed} failed` : ' · All browser checks passed'}.`;
  summary.dataset.passed = String(passed);
  summary.dataset.failed = String(failed);
  document.body.dataset.testStatus = failed ? 'failed' : 'passed';
  button.disabled = false;
  button.textContent = 'Run checks again';
  running = false;
}

button.addEventListener('click', () => { void runChecks(); });
summary.textContent = `Ready to run ${checks.length} browser checks.`;
checks.forEach(resultRow);
