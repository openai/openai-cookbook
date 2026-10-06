// Real React and DOM checks; no app accounts, services, or model requests.
import { useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';
import { BuildActivityPanel, type ActivityTurnSelection } from '../../src/BuildActivityPanel';
import type { ActivityEntry } from '../../src/build-activity';
import '../../src/styles.css';

const pause = (ms: number) => new Promise(resolve => setTimeout(resolve, ms));
const patch = '*** Begin Patch\n*** Add File: space.js\n' + Array.from({ length: 3000 }, (_, index) => `+const detail_${index} = 'A complete line in the retained activity stream';`).join('\n');

function Fixture() {
  const started = useRef(Date.now());
  const argumentReads = useRef(0);
  const measuredEntry = (source: string): ActivityEntry => ({
    id: 'code', time: new Date(started.current + 1).toISOString(), turnId: 'run', kind: 'tool', title: 'Writing source',
    status: 'running', tool: 'apply_patch', inputFormat: 'patch',
    get arguments() { argumentReads.current++; return source; },
  });
  const [entries, setEntries] = useState<ActivityEntry[]>(() => [
    { id: 'request', time: new Date(started.current).toISOString(), turnId: 'run', kind: 'request', title: 'Build', text: 'Build a world', eventType: 'turn.started' },
    { id: 'model', time: new Date(started.current + 1).toISOString(), turnId: 'run', kind: 'event', title: 'Generating', eventType: 'model.started', throughput: { tokens: 100, durationMs: 100, rate: 500, sampledAt: started.current, lastDeltaAt: started.current, state: 'streaming', estimated: true } },
    measuredEntry(patch),
    { id: 'later', time: new Date(started.current + 2).toISOString(), turnId: 'run', kind: 'event', title: 'Later preview status', text: 'The code above is still streaming.' },
  ]);
  const [selectedTurn, setSelectedTurn] = useState<ActivityTurnSelection>();
  const [result, setResult] = useState('Ready');
  const [checking, setChecking] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  async function check() {
    if (checking) return;
    setChecking(true);
    flushSync(() => {
      setSelectedTurn(undefined);
      setEntries(current => current.map(entry => entry.id === 'code' ? measuredEntry(patch) : entry));
    });
    const failures: string[] = [];
    let checks = 0;
    const assert = (ok: boolean, message: string) => { checks++; if (!ok) failures.push(message); };
    await pause(180);
    const feed = root.current!.querySelector<HTMLElement>('.build-feed')!;
    const row = root.current!.querySelector<HTMLElement>('[data-activity-entry="code"]')!;
    const elapsed = () => root.current!.querySelector('.build-metrics strong')!.textContent;
    const initialElapsed = elapsed();
    argumentReads.current = 0;
    await pause(360);
    assert(elapsed() !== initialElapsed, 'The elapsed clock keeps updating.');
    assert(argumentReads.current === 0, 'Clock ticks do not traverse retained source text.');
    assert(row.textContent!.includes('detail_0') && row.textContent!.includes('detail_2999'), 'Every retained source line stays visible in the DOM.');
    assert(!root.current!.querySelector('details'), 'The stream does not introduce collapsed content.');
    const source = row.querySelector<HTMLElement>('pre[aria-label="apply_patch arguments"]')!;
    assert(source.textContent === patch, 'Chunk boundaries preserve every original character and newline.');
    const stableBlocks = [...source.children].slice(0, -1).map(element => ({ element, text: element.textContent, textNode: element.firstChild }));
    assert(stableBlocks.length > 1 && stableBlocks.every(block => block.text!.endsWith('\n')), 'Completed blocks end at existing newline boundaries.');
    const flat = source.cloneNode(false) as HTMLElement;
    flat.textContent = patch;
    flat.setAttribute('aria-hidden', 'true');
    Object.assign(flat.style, { position: 'absolute', visibility: 'hidden', pointerEvents: 'none', width: `${source.getBoundingClientRect().width}px`, left: '0', top: '0' });
    source.parentElement!.append(flat);
    try {
      const chunkedHeight = source.getBoundingClientRect().height;
      const flatHeight = flat.getBoundingClientRect().height;
      assert(Math.abs(chunkedHeight - flatHeight) <= 1, `Wrapped chunks match unchunked height (${chunkedHeight.toFixed(2)}px vs ${flatHeight.toFixed(2)}px), with no extra blank lines.`);
    } finally { flat.remove(); }

    const originalBounds = row.getBoundingClientRect.bind(row);
    let measurements = 0;
    row.getBoundingClientRect = () => { measurements++; return originalBounds(); };
    flushSync(() => setEntries(current => current.map(entry => entry.id === 'model' ? { ...entry, throughput: { ...entry.throughput!, rate: 420, sampledAt: Date.now() } } : entry)));
    await pause(90);
    assert(measurements === 0, 'Rate-only updates do not remeasure the wrapped source row.');
    row.getBoundingClientRect = originalBounds;

    const extra = '\n+const live_tail = "This line arrived after the later preview status";';
    flushSync(() => setEntries(current => current.map(entry => entry.id === 'code' ? measuredEntry(patch + extra) : entry)));
    await pause(90);
    assert(row.textContent!.includes('live_tail'), 'New code streams into the existing source row.');
    assert(source.textContent === patch + extra, 'Appending output preserves exact text across all block boundaries.');
    assert(stableBlocks.every((block, index) => source.children[index] === block.element && block.element.firstChild === block.textNode && block.element.textContent === block.text), 'Appending output preserves completed block and text-node identity.');
    const bottomGap = feed.getBoundingClientRect().bottom - row.getBoundingClientRect().bottom;
    assert(bottomGap >= 0 && bottomGap < 25, 'Auto-scroll follows the updated code above a later status row.');

    flushSync(() => setSelectedTurn({ id: 'run', message: 'Build a world', startedAt: new Date(started.current).toISOString(), status: 'running' }));
    await pause(90);
    const selectedScroll = feed.scrollTop;
    flushSync(() => setEntries(current => current.map(entry => entry.id === 'code' ? measuredEntry(patch + extra + '\n+const newest_tail = true;') : entry)));
    await pause(90);
    assert(Math.abs(feed.scrollTop - selectedScroll) < 1, 'Inspecting selected history does not jump when new code arrives.');
    flushSync(() => setSelectedTurn(undefined));
    await pause(90);
    assert(feed.scrollTop > selectedScroll + 1000, 'Returning to live reveals the current source tail.');
    const finalGap = feed.getBoundingClientRect().bottom - row.getBoundingClientRect().bottom;
    assert(finalGap >= 0 && finalGap < 25, 'Returning to live preserves precise latest-output alignment.');
    setResult(failures.length ? `${failures.length} failed / ${checks}: ${failures.join(' | ')}` : `Passed ${checks} checks`);
    setChecking(false);
  }

  return <main style={{ padding: 20 }}>
    <button type="button" onClick={() => void check()} disabled={checking}>Run Activity checks</button>
    <p role="status" data-testid="activity-performance-result">{result}</p>
    <div ref={root} style={{ width: 340, maxWidth: '100%', height: 560, border: '1px solid #444' }}>
      <BuildActivityPanel entries={entries} busy connected embedded model="gpt-6-astra" tier="ultrafast" selectedTurn={selectedTurn} onReturnToLive={() => setSelectedTurn(undefined)} onClose={() => {}}/>
    </div>
  </main>;
}

if (location.port !== '5190') document.getElementById('root')!.textContent = 'Use the isolated fixture on port 5190.';
else createRoot(document.getElementById('root')!).render(<Fixture/>);
