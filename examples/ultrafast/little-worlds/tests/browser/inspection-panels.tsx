import '../../src/fonts.css';
// Run on the isolated build-activity-server fixture (port 5190), sign in as
// Mira, then run at desktop and narrow widths. Real UI/API, mocked models,
// no microphone. Also run with browser reduced motion enabled.
// Repeat with another signed-in app tab open on the same origin to catch
// long-lived event streams starving the snapshot/Enter your world requests.
import { useState } from 'react';
import { createRoot } from 'react-dom/client';
import App from '../../src/App';
import { captureSessionApi } from '../../src/api';
import { createVoiceSurface } from '../../src/voice-surface';
import type { Snapshot } from '../../src/types';
import '../../src/styles.css';

function assert(condition: unknown, message: string): asserts condition {
  if (!condition) throw Error(message);
}
const delay = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
async function until(predicate: () => unknown, description: string, timeout = 12000) {
  const deadline = Date.now() + timeout;
  while (!predicate()) {
    assert(Date.now() < deadline, `Timed out: ${description}`);
    await delay(30);
  }
}

function Checks() {
  const [status, setStatus] = useState('Sign in as Mira, then run checks.');
  const [motion, setMotion] = useState('');
  const [progressReport, setProgressReport] = useState('');
  const [running, setRunning] = useState(false);
  async function run(estimate: 'ready' | 'offline' | 'slow' | 'small' = 'ready') {
    setRunning(true);
    setStatus('Running comparison integration checks…');
    const voice = createVoiceSurface({ context: () => 'Parallel build inspection regression fixture', userSpeech: () => 'Create a quick notebook, then enter your world' });
    const visible = (element: Element | null) => !!element && element.getClientRects().length > 0 && getComputedStyle(element).visibility !== 'hidden';
    let watchToolbar = true;
    let toolbarOverlap = false;
    let watchedFrames = 0;
    const progressSamples: Record<string, { pending: number; values: Set<number>; budgets: Set<number>; backwards: boolean; prematureCompletion: boolean; last: number; moving: Set<string> }> = {};
    let previousLayout: { grid: number; composer: number; scroll: number; phase: string } | undefined;
    const layoutSteps: { grid: number; composer: number; documentGrid: number; scroll: number; phase: string }[] = [];
    const inspectTransition = () => {
      for (const element of document.querySelectorAll<HTMLElement>('.build-activity-panel.is-embedded .build-progress')) {
        const tier = element.dataset.tier!;
        const sample = progressSamples[tier] ||= { pending: 0, values: new Set(), budgets: new Set(), backwards: false, prematureCompletion: false, last: 0, moving: new Set() };
        const track = element.querySelector('[role="progressbar"]')!;
        const value = track.getAttribute('aria-valuenow');
        if (value === null) {
          sample.pending++;
          const highlight = element.querySelector('.build-progress-highlight');
          if (highlight) sample.moving.add(getComputedStyle(highlight).transform);
        } else {
          const current = Number(value);
          sample.values.add(current);
          sample.backwards ||= current < sample.last;
          sample.prematureCompletion ||= current === 100 && element.dataset.progressState !== 'completed';
          sample.last = current;
        }
        if (element.dataset.expectedOutputTokens) sample.budgets.add(Number(element.dataset.expectedOutputTokens));
      }
      const comparison = document.querySelector('.build-comparison');
      const grid = document.querySelector('.build-comparison-grid')?.getBoundingClientRect();
      const composer = document.querySelector('.composer-area')?.getBoundingClientRect();
      const phase = comparison?.getAttribute('data-morphing') || comparison?.getAttribute('data-comparing') || '';
      if (grid && composer) {
        if (previousLayout && (phase !== 'false' || previousLayout.phase !== 'false')) {
          layoutSteps.push({ grid: Math.abs(grid.top - previousLayout.grid), composer: Math.abs(composer.top - previousLayout.composer), documentGrid: Math.abs(grid.top + scrollY - previousLayout.grid - previousLayout.scroll), scroll: scrollY - previousLayout.scroll, phase: `${previousLayout.phase} → ${phase}` });
        }
        previousLayout = { grid: grid.top, composer: composer.top, scroll: scrollY, phase };
      }
      if (comparison?.getAttribute('data-comparing') === 'true' || comparison?.hasAttribute('data-morphing')) {
        watchedFrames++;
        toolbarOverlap ||= visible(document.querySelector('.space-toolbar'));
      }
      if (watchToolbar) requestAnimationFrame(inspectTransition);
    };
    try {
      const click = async (label: string) => {
        const snapshot = await voice.read();
        const control = snapshot.controls.find(item => item.label === label && !item.disabled);
        assert(control, `${label} must be discoverable by voice`);
        const result = await voice.execute({ type: 'click', target: control.id });
        assert(result.ok, `${label}: ${result.message}`);
        return result;
      };
      assert(document.querySelector('.composer textarea'), 'Sign in as Mira before running these checks.');
      if (document.querySelector('.finish-build-button')) {
        await click('Enter your world');
        await until(() => !document.querySelector('.build-comparison[data-morphing]') && visible(document.querySelector('.space-toolbar')), 'the previous comparison closes');
      }
      assert(!document.querySelector('.space-address,.space-breadcrumb'), 'The redundant space address must be removed.');
      assert(visible(document.querySelector('.space-toolbar')), 'Thread, History and help must start visible in the single-world view.');
      assert(!document.querySelector('.workspace-files-toggle,#workspace-files-panel'), 'Files must be removed from the workspace.');
      if (document.querySelector('.build-activity-toggle[aria-expanded="true"]')) await click('Close build activity');
      await click('Open build activity');
      assert(document.querySelector('#build-activity-panel'), 'Standalone Activity still opens.');
      await click('Close build activity');

      const before = await voice.read();
      const readFixture = captureSessionApi();
      type Calls = { calls: { startedAt: number }[]; estimates: { startedAt: number; endedAt?: number; status: string; expectedOutputTokens?: number }[] };
      const callsBefore = await readFixture<Calls>('/api/_fixture/builds');
      const composer = before.controls.find(item => item.label === 'Describe a change to your space');
      assert(composer, 'The builder composer must be discoverable by voice.');
      const filled = await voice.execute({ type: 'fill', target: composer.id, value: `quick make a notebook for this interactive comparison estimate ${estimate}` });
      assert(filled.ok && filled.submitted === false, 'Filling must remain a draft until submitted.');
      inspectTransition();
      const submitted = await click('Make it real');
      assert(submitted.submitted === true, 'Voice submission must confirm real API acceptance.');
      await until(() => document.querySelectorAll('.build-activity-panel.is-embedded').length === 2, 'both automatic Activity streams');
      await until(() => document.querySelectorAll('.build-activity-panel.is-embedded .build-progress').length === 2, 'both build progress bars');
      for (const tier of ['ultrafast', 'standard']) {
        const bar = document.querySelector(`.build-progress[data-tier="${tier}"]`)!;
        assert(bar.querySelector('.build-progress-heading')?.textContent === 'Build progress', 'Progress headings must be concise.');
        assert(!bar.textContent?.includes('%'), 'Progress percentages should not add visible text.');
        assert(bar.querySelector('[role="progressbar"]')?.getAttribute('aria-label') === `${tier === 'ultrafast' ? 'Ultrafast' : 'Standard'} build progress`, 'Each bar needs a distinct accessible label.');
      }
      assert(!document.querySelector('.finish-build-button'), 'Enter your world must not appear before ultrafast is ready.');
      assert(!document.activeElement?.classList.contains('build-feed'), 'Opening both streams must not steal focus.');
      await until(() => !document.querySelector('.build-comparison[data-morphing]'), 'split animation finishes');
      assert(!visible(document.querySelector('.space-toolbar')), 'Thread, History and help must be hidden during comparison.');
      assert(!document.querySelector('.build-comparison-ratio'), 'The comparison must not show the output ratio widget.');
      const panels = [...document.querySelectorAll<HTMLElement>('.build-activity-panel.is-embedded')];
      assert(new Set(panels.map(panel => panel.id)).size === 2, 'Embedded Activity IDs must be unique.');
      const left = panels[0].getBoundingClientRect(), right = panels[1].getBoundingClientRect();
      assert(left.right <= right.left + 1 || left.bottom <= right.top + 1, 'The two Activity panels must not overlap.');
      for (const panel of panels) {
        const rect = panel.getBoundingClientRect();
        assert(rect.left >= -1 && rect.right <= innerWidth + 1 && rect.height > 100, 'Each Activity stream must fit its lane.');
        const slot = panel.parentElement!.getBoundingClientRect();
        assert(Math.abs(rect.top - slot.top) <= 1 && rect.bottom <= slot.bottom + 1, 'Embedded Activity must not inherit the floating panel offset, including below the mobile voice bar.');
        const lane = panel.closest('.build-comparison-lane')!;
        const preview = lane.querySelector('.build-comparison-preview')!.getBoundingClientRect();
        assert(lane.classList.contains('build-comparison-standard') ? slot.right <= preview.left + 1 : preview.right <= slot.left + 1, 'Activity streams must face the center, with each world unobscured on the outer side.');
        assert(preview.width > slot.width, 'The world must receive more horizontal space than Activity.');
        assert(panel.getAttribute('aria-label')?.includes('build activity'), 'Each Activity stream needs its lane label.');
        const feed = panel.querySelector<HTMLElement>('.build-feed')!;
        feed.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      }
      assert(document.querySelectorAll('.build-activity-panel.is-embedded').length === 2, 'Escape inside a stream must not close the comparison.');
      for (const name of ['Ultrafast', 'Standard']) {
        const lane = document.querySelector<HTMLElement>(`.build-comparison-${name.toLowerCase()}`)!;
        const preview = lane.querySelector<HTMLElement>('.build-comparison-preview')!;
        const initialWidth = preview.getBoundingClientRect().width;
        await click(`Hide ${name} activity`);
        await until(() => preview.getBoundingClientRect().width > initialWidth + 20, `${name} world expands when its Activity closes`);
        await click(`Show ${name} activity`);
        await until(() => Math.abs(preview.getBoundingClientRect().width - initialWidth) < 1, `${name} mirrored Activity returns`);
      }
      await until(() => document.querySelector('.finish-build-button'), 'ultrafast finishes');
      const primaryFrame = document.querySelector('.build-comparison-primary iframe');
      assert(primaryFrame, 'The finished ultrafast world must have a preview.');
      await until(() => document.querySelector('.build-comparison-standard iframe'), 'Standard has a visible draft');
      await until(() => !document.querySelector('.build-comparison-primary .build-comparison-world[inert],.build-comparison-primary iframe[inert]'), 'the committed Ultrafast world becomes interactive');
      assert(document.querySelector('.build-comparison-standard .build-comparison-status.is-running'), 'Standard must still be building while Ultrafast becomes interactive.');
      const expectedStatus = estimate === 'offline' || estimate === 'slow' ? 'fallback' : 'ready';
      await until(() => document.querySelectorAll(`.build-progress[data-estimator-status="${expectedStatus}"]`).length === 2, 'the shared estimate reaches both lanes');
      const progressBars = [...document.querySelectorAll<HTMLElement>('.build-activity-panel.is-embedded .build-progress')];
      const budgets = progressBars.map(bar => Number(bar.dataset.expectedOutputTokens));
      assert(budgets[0] > 0 && budgets[0] === budgets[1], 'Both lanes must use the same positive token budget.');
      assert(progressBars[0].querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow') === '100', 'A successful Ultrafast build must fill its bar.');
      assert(Number(progressBars[1].querySelector('[role="progressbar"]')?.getAttribute('aria-valuenow')) < 100, 'Standard must not claim completion while still building.');
      const callsAfter = await readFixture<Calls>('/api/_fixture/builds');
      const estimates = callsAfter.estimates.slice(callsBefore.estimates.length);
      const builds = callsAfter.calls.slice(callsBefore.calls.length);
      assert(estimates.length === 1 && builds.length === 2, 'A comparison must launch exactly one estimate and two builds.');
      assert(builds.every(call => call.startedAt < (estimates[0].endedAt ?? Infinity)), 'Neither build may wait for the estimate to finish.');
      assert(estimates[0].status === (estimate === 'offline' ? 'failed' : estimate === 'slow' ? 'cancelled' : 'completed'), 'The fixture must exercise the requested estimator outcome.');
      assert(!document.querySelector('.build-comparison-primary .build-comparison-world[inert]'), 'A completed Ultrafast world must be interactive before leaving the comparison.');
      for (const lane of document.querySelectorAll('.build-comparison-lane')) {
        for (const surface of [lane, lane.querySelector('.build-comparison-world')!, lane.querySelector('iframe')!]) {
          assert(Number(getComputedStyle(surface).opacity) === 1, 'Both settled worlds and their iframes must remain at full opacity.');
        }
      }
      const readSnapshot = captureSessionApi();
      const spaceId = new URLSearchParams(location.search).get('space');
      assert(spaceId, 'The current space must be represented in the route.');
      const snapshotPath = `/api/spaces/${encodeURIComponent(spaceId)}`;
      const savedNote = async () => {
        const snapshot = await readSnapshot<Snapshot>(snapshotPath);
        const notes = snapshot.state.extras.notes as Record<string, { text: string }> | undefined;
        return notes?.[snapshot.actor.id]?.text;
      };
      const saveNote = async (phase: string) => {
        let world = await voice.read();
        let noteField = world.controls.find(control => control.label === 'Your latest note');
        const voiceDeadline = Date.now() + 12000;
        // Removing inert precedes the frame's ready handshake. Query again as
        // Live does when a freshly published document is still updating.
        while (!noteField && Date.now() < voiceDeadline) {
          await delay(60);
          world = await voice.read();
          noteField = world.controls.find(control => control.label === 'Your latest note');
        }
        assert(noteField, `The finished generated world must expose its note field to voice. ${world.text?.slice(-1000)}`);
        const note = `Saved ${phase} ${Date.now()}`;
        const noteFilled = await voice.execute({ type: 'fill', target: noteField.id, value: note });
        assert(noteFilled.ok, `A generated field must accept input ${phase}.`);
        await click('Keep this note');
        const saveDeadline = Date.now() + 12000;
        while (await savedNote() !== note) {
          assert(Date.now() < saveDeadline, `A generated form must persist its data ${phase}.`);
          await delay(60);
        }
        return note;
      };
      const comparisonNote = await saveNote('during comparison');
      assert(document.querySelector('.build-comparison-standard .build-comparison-status.is-running'), 'Standard must still be running after interacting with the finished Ultrafast world.');
      assert(document.querySelector('.build-comparison-primary iframe') === primaryFrame, 'Saving while Standard builds must preserve the Ultrafast iframe.');
      const themeLabel = [...document.querySelectorAll<HTMLButtonElement>('button[aria-label]')]
        .map(button => button.getAttribute('aria-label'))
        .find(label => label === 'Switch to light mode' || label === 'Switch to dark mode');
      assert(themeLabel, 'The theme control must be available during the comparison.');
      const oppositeThemeLabel = themeLabel === 'Switch to light mode' ? 'Switch to dark mode' : 'Switch to light mode';
      await click(themeLabel);
      await until(() => document.querySelector(`button[aria-label="${oppositeThemeLabel}"]`), 'theme changes');
      assert(document.querySelector('.build-comparison-primary iframe') === primaryFrame, 'Changing the app theme must not remount the generated world.');
      await click(oppositeThemeLabel);
      await until(() => document.querySelector(`button[aria-label="${themeLabel}"]`), 'original theme returns');
      assert(document.querySelector('.build-comparison-primary iframe') === primaryFrame, 'Restoring the app theme must preserve the generated world.');
      const ready = await voice.read();
      assert(ready.controls.some(control => control.label === 'Enter your world' && !control.disabled), 'Enter your world must be exposed to voice.');
      await click('Enter your world');
      await until(() => document.querySelector('.build-comparison[data-comparing="false"]:not([data-morphing])'), 'morph back to one world');
      assert(!document.querySelector('.build-comparison-primary .build-comparison-world[inert]'), 'The finished world must become interactive.');
      assert(document.querySelector('.build-comparison-primary iframe') === primaryFrame, 'The primary iframe must survive the morph.');
      assert(!document.querySelector('.finish-build-button'), 'Enter your world must disappear when the comparison closes.');
      await until(() => visible(document.querySelector('.space-toolbar')), 'Thread, History and help return after the morph');
      assert(watchedFrames > 0 && !toolbarOverlap, 'Workspace controls must stay hidden through both transition animations.');
      assert(await savedNote() === comparisonNote, 'Entering the world must preserve the interaction saved during comparison.');
      await saveNote('after entering the world');
      await click('Community');
      await until(() => document.querySelector('.community-overlay'), 'Community opens');
      assert(document.querySelectorAll('.demo-utilities').length === 1, 'Demo utilities must appear once on Community.');
      assert(document.querySelector(`.community-overlay button[aria-label="${themeLabel}"]`), 'Community must include the theme toggle inside its focus scope.');
      await click(themeLabel);
      await until(() => document.querySelector(`.community-overlay button[aria-label="${oppositeThemeLabel}"]`), 'Community theme changes by voice');
      await click(oppositeThemeLabel);
      await click('Close community and return to the space');
      await until(() => !document.querySelector('.community-overlay'), 'Community closes');
      assert(document.querySelectorAll('.demo-utilities').length === 1, 'Returning to a world must restore a single utility group.');
      const reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
      for (const tier of ['ultrafast', 'standard']) {
        const sample = progressSamples[tier];
        assert(sample?.pending > 0, `${tier} must show indeterminate progress before the estimate.`);
        assert(sample.budgets.size === 1, `${tier} must keep its original token budget throughout the comparison.`);
        assert(!sample.backwards && !sample.prematureCompletion, `${tier} progress must be monotonic and reserve completion for success.`);
        assert(sample.values.size >= (estimate === 'slow' ? 1 : 3), `${tier} must advance from streamed output, not just jump when done.`);
        assert(reduced || sample.moving.size > 1, `${tier} pending progress must animate while awaiting the estimate.`);
      }
      setStatus(`Passed at ${innerWidth} × ${innerHeight}${reduced ? ', reduced motion' : ''} (${estimate} estimate): shared budget, streaming progress, mirrored Activity, full-opacity worlds, voice submit/Enter, saved interactions during Standard build, world and Community themes, focus, Escape, and preserved interactive iframe.`);
    } catch (error) {
      setStatus(`Failed: ${error instanceof Error ? error.message : String(error)}`);
    } finally {
      watchToolbar = false;
      setMotion(JSON.stringify(layoutSteps.sort((a, b) => Math.max(b.grid, b.composer) - Math.max(a.grid, a.composer)).slice(0, 5)));
      setProgressReport(JSON.stringify(Object.fromEntries(Object.entries(progressSamples).map(([tier, sample]) => [tier, { ...sample, values: [...sample.values], budgets: [...sample.budgets], moving: sample.moving.size }]))));
      voice.clear();
      setRunning(false);
    }
  }
  return <div data-voice-ignore style={{ position: 'fixed', zIndex: 200, top: 2, left: 8, maxWidth: '40vw', font: '10px sans-serif', background: '#f7f9f0ee' }}>
    <button onClick={() => run()} disabled={running} style={{ padding: 4 }}>Run comparison voice checks</button>
    {(['offline', 'slow', 'small'] as const).map(mode => <button key={mode} onClick={() => run(mode)} disabled={running} style={{ padding: 4 }}>{mode} estimate checks</button>)}
    <p role="status" data-inspection-result data-inspection-motion={motion} data-inspection-progress={progressReport} style={{ margin: 2 }}>{status}</p>
  </div>;
}

// Refuse the live demo origin; this fixture's authentication is disposable.
if (location.port !== '5190') {
  document.getElementById('root')!.textContent = 'Use the isolated fixture at http://127.0.0.1:5190/tests/browser/inspection-panels.html';
} else {
  createRoot(document.getElementById('root')!).render(<><App/><Checks/></>);
}
