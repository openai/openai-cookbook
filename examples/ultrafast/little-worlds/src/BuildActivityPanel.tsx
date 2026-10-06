import { memo, useEffect, useId, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { ArrowDown, Check, FileCode2, LoaderCircle, MessageSquare, Terminal, X } from 'lucide-react';
import { activityCode, parseActivityArguments } from './build-activity';
import type { ActivityEntry } from './build-activity';
import { savedActivityForTurn, type ActivityTurnSelection } from './activity-history';
import type { RuntimeEvent } from './types';
import { useBuildActivity } from './useBuildActivity';
import { buildThroughput } from './build-throughput';
import { BuildSpeedometer } from './BuildSpeedometer';
import BuildProgress, { type BuildProgressProps } from './BuildProgress';
import './build-activity.css';

export type { ActivityTurnSelection } from './activity-history';

type PanelProps = {
  entries: ActivityEntry[]; busy: boolean; connected: boolean; connecting?: boolean;
  clockOffsetMs?: number;
  model?: string; tier?: string; onClose: () => void;
  selectedTurn?: ActivityTurnSelection; selectionRequest?: number; savedEvents?: readonly RuntimeEvent[]; onReturnToLive?: () => void;
  /** Render inside a comparison lane, without overlay positioning or focus changes. */
  embedded?: boolean; id?: string; label?: string;
  /** Keep comparison lanes scoped to their run without changing the history overlay. */
  turnId?: string;
  /** Comparison runs share one frozen estimate while each streams its own output. */
  comparisonProgress?: Omit<BuildProgressProps, 'tier'> & { id: string };
};

const seconds = (milliseconds: number) => `${Math.max(0, milliseconds / 1000).toFixed(1)}s`;
const count = (value: number) => value >= 10_000 ? `${(value / 1000).toFixed(1)}k` : value.toLocaleString();
const formatJson = (value: string) => {
  try { return JSON.stringify(JSON.parse(value), null, 2); } catch { return value; }
};

const OutputChunk = memo(function OutputChunk({ text }: { text: string }) {
  // Each completed block keeps its text layout while the trailing block grows.
  // Keep real newlines in the DOM for selection, copying, and accessibility.
  return <span style={{ display: 'block', contain: 'layout' }}>{text}</span>;
});

const StreamingText = memo(function StreamingText({ text }: { text: string }) {
  const chunks = useMemo(() => {
    const result: string[] = [];
    for (let start = 0; start < text.length;) {
      const limit = Math.min(start + 4096, text.length);
      let end = limit;
      if (limit < text.length) {
        const before = text.lastIndexOf('\n', limit - 1);
        // Never introduce a visual line break inside an original line, even
        // when a generated/minified line is longer than the target block size.
        const newline = before >= start ? before : text.indexOf('\n', limit);
        end = newline < 0 ? text.length : newline + 1;
      }
      result.push(text.slice(start, end));
      start = end;
    }
    return result;
  }, [text]);
  return <>{chunks.map((chunk, index) => <OutputChunk key={index} text={chunk}/>)}</>;
});

function argumentMetadata(entry: ActivityEntry, hasCode: boolean) {
  if (!entry.arguments) return '';
  const parsed = hasCode ? parseActivityArguments(entry.arguments) : null;
  if (!parsed) return formatJson(entry.arguments);
  // Source is already rendered, decoded and line-numbered, immediately above.
  // Keep every other argument without repeating escaped copies of that code.
  const fields = { ...parsed };
  if (entry.tool === 'apply_change') {
    if (typeof fields.source === 'string') delete fields.source;
    if (typeof fields.tests === 'string') delete fields.tests;
  } else if (entry.tool === 'write_file') delete fields.content;
  else if (entry.tool === 'apply_patch' && Array.isArray(fields.edits)) {
    fields.edits = fields.edits.map(edit => {
      if (!edit || typeof edit !== 'object' || typeof edit.replace !== 'string') return edit;
      const { replace: _replacement, ...metadata } = edit;
      return metadata;
    });
  }
  return Object.keys(fields).length ? JSON.stringify(fields, null, 2) : '';
}

const CodeWindow = memo(function CodeWindow({ path, code }: { path: string; code: string }) {
  const lines = useMemo(() => code.split('\n'), [code]);
  return <div className="build-code-window">
    <div className="build-code-title"><FileCode2 size={13}/><strong>{path}</strong><span data-voice-ignore>{count(code.length)} chars</span></div>
    <pre aria-label={`${path} generated code`} data-voice-ignore>
      <code>{lines.map((line, index) => <span className="build-code-line" key={index}><i aria-hidden="true">{index + 1}</i><span>{line || ' '}</span></span>)}</code>
    </pre>
  </div>;
});

const ActivityCard = memo(function ActivityCard({ entry, start, selected }: { entry: ActivityEntry; start: number; selected?: boolean }) {
  const code = useMemo(() => activityCode(entry), [entry]);
  const argumentsText = useMemo(() => argumentMetadata(entry, code.length > 0), [entry, code]);
  const resultText = useMemo(() => entry.result ? formatJson(entry.result) : '', [entry.result]);
  const active = entry.status === 'running';
  const failed = entry.status === 'failed';
  const Icon = failed ? X : active ? LoaderCircle : entry.kind === 'request' || entry.kind === 'message' ? MessageSquare : entry.kind === 'tool' ? Terminal : Check;
  const heading = entry.kind === 'request' ? 'Request' : entry.kind === 'message' ? 'Response' : entry.kind === 'tool' ? entry.tool || entry.title : entry.title;
  return <li data-activity-entry={entry.id} data-activity-turn={entry.turnId} className={`build-entry build-entry-${entry.kind}${active ? ' is-active' : ''}${failed ? ' is-failed' : ''}${selected ? ' is-selected' : ''}`}>
    <span className="build-entry-marker"><Icon size={13} className={active ? 'spin' : undefined}/></span>
    <div className="build-entry-content">
      <div className="build-entry-heading"><strong>{heading}</strong><time title={new Date(entry.time).toLocaleTimeString()}>{seconds(Date.parse(entry.time) - start)}</time></div>
      {(entry.tool || entry.durationMs !== undefined) && <div className="build-tool-status">{entry.kind !== 'tool' && entry.tool && <span>{entry.tool}</span>}<span>{entry.status}</span>{entry.durationMs !== undefined && <span>{seconds(entry.durationMs)}</span>}</div>}
      {entry.text && <p className="build-entry-text" data-voice-ignore><StreamingText text={entry.text}/></p>}
      {(code.length > 0 || argumentsText) && <div className="build-entry-output"><span>Arguments</span>{code.map(file => <CodeWindow key={file.path} {...file}/>)}{argumentsText && <pre data-voice-ignore aria-label={`${entry.tool || 'Tool'} arguments`}><StreamingText text={argumentsText}/></pre>}</div>}
      {resultText && <div className="build-entry-output"><span>Result</span><pre data-voice-ignore aria-label={`${entry.tool || 'Tool'} result`}><StreamingText text={resultText}/></pre></div>}
      {entry.truncated && <p className="build-truncated">Output exceeded the activity capture limit.</p>}
    </div>
  </li>;
});

/** The clock and live rate update without reconciling the retained transcript. */
const ActivityMetrics = memo(function ActivityMetrics({ entries, start, end, running, connected, clockOffsetMs }: {
  entries: ActivityEntry[]; start: number; end: number | undefined; running: boolean; connected: boolean; clockOffsetMs: number;
}) {
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(timer);
  }, [running]);
  const characters = useMemo(() => entries.reduce((sum, entry) => sum + (entry.kind === 'tool' ? entry.arguments?.length || 0 : entry.kind === 'message' ? entry.text?.length || 0 : 0), 0), [entries]);
  const throughput = buildThroughput(entries, now + clockOffsetMs, running, connected);
  return <div className="build-metrics" data-voice-ignore><div><strong>{entries.length ? seconds((end ?? now) - start) : '—'}</strong><span>elapsed</span></div><div><strong>{count(characters)}</strong><span>output chars</span></div><BuildSpeedometer {...throughput}/></div>;
});

export function BuildActivityPanel({ entries: retainedEntries, busy, connected, connecting, clockOffsetMs = 0, model, tier, onClose, selectedTurn, selectionRequest = 0, savedEvents = [], onReturnToLive, embedded = false, id, label = 'Build activity', turnId, comparisonProgress }: PanelProps) {
  const entries = useMemo(() => turnId ? retainedEntries.filter(entry => entry.turnId === turnId) : retainedEntries, [retainedEntries, turnId]);
  const instanceId = useId();
  const panelId = id || (embedded ? `build-activity-${instanceId}` : 'build-activity-panel');
  const scroll = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLDivElement>(null);
  const previousEntries = useRef(new Map<string, ActivityEntry>());
  const latestEntry = useRef<string | undefined>(undefined);
  const selection = useRef(selectedTurn?.id);
  selection.current = selectedTurn?.id;
  const positionedSelection = useRef<string | undefined>(undefined);
  const latestTurn = [...entries].reverse().find(entry => entry.turnId)?.turnId;
  const selectedCaptured = selectedTurn && entries.some(entry => entry.turnId === selectedTurn.id);
  const partialCapture = selectedCaptured && !entries.some(entry => entry.turnId === selectedTurn.id && entry.eventType === 'turn.started');
  const saved = useMemo(() => selectedTurn && (!selectedCaptured || partialCapture)
    ? savedActivityForTurn(selectedTurn, partialCapture ? [] : savedEvents) : null, [selectedTurn, selectedCaptured, partialCapture, savedEvents]);
  const displayed = useMemo(() => {
    if (!saved) return entries;
    const index = entries.findIndex(entry => Date.parse(entry.time) > Date.parse(selectedTurn!.startedAt));
    const insertion = index < 0 ? entries.length : index;
    return [...entries.slice(0, insertion), ...saved.entries, ...entries.slice(insertion)];
  }, [entries, saved, selectedTurn]);
  const viewedTurn = selectedTurn?.id || latestTurn;
  const current = useMemo(() => viewedTurn ? displayed.filter(entry => entry.turnId === viewedTurn) : displayed, [displayed, viewedTurn]);
  const start = selectedTurn ? Date.parse(selectedTurn.startedAt) : current.length ? Date.parse(current[0].time) : 0;
  const terminal = [...current].reverse().find(entry => /^turn\.(completed|failed|cancelled)$/.test(entry.eventType || ''));
  const selectedStatus = terminal?.eventType?.split('.').at(-1) || selectedTurn?.status;
  const selectedFinished = selectedStatus && ['completed', 'failed', 'cancelled'].includes(selectedStatus);
  const running = selectedTurn
    ? !selectedFinished && (current.some(entry => entry.status === 'running') || selectedTurn.status === 'running')
    : busy || current.some(entry => entry.status === 'running') && !terminal;
  const end = terminal ? Date.parse(terminal.time) : running ? undefined : Date.parse(current.at(-1)?.time || '') || start;
  const stageEntry = [...current].reverse().find(entry => entry.tool || entry.eventType === 'model.started' || entry.eventType === 'revision.published');
  const phase = terminal?.eventType === 'turn.completed' ? 4
    : stageEntry?.eventType === 'revision.published' || stageEntry?.tool === 'publish_revision' ? 3
    : stageEntry?.tool === 'verify_workspace' ? 2
    : stageEntry?.tool === 'inspect_space' || stageEntry?.tool === 'read_file' || !stageEntry ? 0 : 1;
  const turnStarts = useMemo(() => {
    const starts = new Map<string | undefined, number>();
    for (const entry of displayed) if (!starts.has(entry.turnId)) starts.set(entry.turnId, Date.parse(entry.time));
    if (selectedTurn) starts.set(selectedTurn.id, Date.parse(selectedTurn.startedAt));
    return starts;
  }, [displayed, selectedTurn]);
  useEffect(() => { if (!embedded) scroll.current?.focus({ preventScroll: true }); }, [embedded, selectedTurn?.id, selectionRequest]);
  function revealLatest() {
    const viewport = scroll.current;
    if (!viewport || selection.current) return;
    const height = viewport.clientHeight;
    if (!height || !viewport.clientWidth) return;
    const row = Array.from(content.current?.querySelectorAll<HTMLElement>('[data-activity-entry]') || [])
      .find(element => element.dataset.activityEntry === latestEntry.current);
    // A streaming call can keep growing above a later preview/status row.
    // Follow the updated text, rather than only the bottom of the timeline.
    const target = row
      ? viewport.scrollTop + row.getBoundingClientRect().bottom - viewport.getBoundingClientRect().top - height + 12
      : viewport.scrollHeight;
    const next = Math.max(0, Math.min(target, viewport.scrollHeight - height));
    if (Math.abs(viewport.scrollTop - next) > .5) viewport.scrollTop = next;
  }
  useLayoutEffect(() => {
    const changed = entries.filter(entry => previousEntries.current.get(entry.id) !== entry);
    const changedContent = changed.filter(entry => {
      const previous = previousEntries.current.get(entry.id);
      return !previous || entry.text !== previous.text || entry.arguments !== previous.arguments || entry.result !== previous.result;
    });
    const visibleChanges = changed.filter(entry => {
      const previous = previousEntries.current.get(entry.id);
      return !previous || entry.status !== previous.status;
    });
    latestEntry.current = (changedContent.at(-1) ?? visibleChanges.at(-1))?.id
      ?? latestEntry.current ?? entries.at(-1)?.id;
    previousEntries.current = new Map(entries.map(entry => [entry.id, entry]));
    // Rate samples update their row without changing visible transcript text.
    // They must not force another full wrapped-feed layout or scroll write.
    if (changedContent.length || visibleChanges.length) revealLatest();
  }, [entries]);
  useLayoutEffect(() => {
    if (!selectedTurn) {
      const returningToLive = positionedSelection.current !== undefined;
      positionedSelection.current = undefined;
      if (returningToLive) revealLatest();
      return;
    }
    const viewport = scroll.current;
    const row = Array.from(content.current?.querySelectorAll<HTMLElement>('[data-activity-turn]') || [])
      .find(element => element.dataset.activityTurn === selectedTurn.id);
    if (!viewport || !row) return;
    const target = `${selectionRequest}:${selectedTurn.id}:${row.dataset.activityEntry}`;
    if (positionedSelection.current === target) return;
    viewport.scrollTop += row.getBoundingClientRect().top - viewport.getBoundingClientRect().top - 12;
    positionedSelection.current = target;
  }, [selectedTurn?.id, selectionRequest, displayed]);
  useLayoutEffect(() => {
    let frame: number | undefined;
    // Both viewport and transcript can resize in one paint. Follow only once,
    // outside the observer delivery, so reading and writing cannot loop there.
    const observer = new ResizeObserver(() => {
      if (frame !== undefined) return;
      frame = requestAnimationFrame(() => { frame = undefined; revealLatest(); });
    });
    if (scroll.current) observer.observe(scroll.current);
    if (content.current) observer.observe(content.current);
    return () => { observer.disconnect(); if (frame !== undefined) cancelAnimationFrame(frame); };
  }, []);
  const status = selectedTurn ? running ? 'In progress' : selectedStatus === 'failed' ? 'Failed' : selectedStatus === 'cancelled' ? 'Stopped' : 'Saved'
    : !connected ? connecting ? 'Connecting' : 'Reconnecting' : running ? 'Live' : terminal?.eventType === 'turn.failed' ? 'Failed' : terminal?.eventType === 'turn.cancelled' ? 'Stopped' : entries.length ? 'Complete' : 'Ready';
  return <aside id={panelId} className={`build-activity-panel${embedded ? ' is-embedded' : ''}`} aria-label={label} onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); if (!embedded) onClose(); } }}>
    <header className="build-activity-overview">
      <div className="build-live-row"><span className={`build-live-status${running && connected ? ' is-live' : ''}`}><i/>{status}</span><span className="build-model">{model || 'Agent'}{tier && <small>{tier}</small>}</span></div>
      <ActivityMetrics entries={current} start={start} end={end} running={!!running} connected={connected} clockOffsetMs={clockOffsetMs}/>
      {embedded && comparisonProgress ? <BuildProgress key={comparisonProgress.id} {...comparisonProgress} phase={phase >= 3 ? 'publish' : phase === 2 ? 'verify' : 'build'} tier={tier === 'standard' ? 'standard' : 'ultrafast'}/>
        : <ol className="build-phases" aria-label="Build stages">{['Read', 'Write', 'Check', 'Publish'].map((label, index) => <li key={label} className={current.length && index < phase ? 'is-done' : running && index === phase ? 'is-current' : ''}><span>{index < phase && current.length ? <Check size={10}/> : String(index + 1).padStart(2, '0')}</span>{label}</li>)}</ol>}
    </header>
    {selectedTurn && <div className="build-turn-selection"><span>Selected request · {new Date(selectedTurn.startedAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</span>{!current.some(entry => entry.kind === 'request') && <p>{selectedTurn.message}</p>}{saved && <p className="build-history-unavailable" role="status">{connecting && !connected ? 'Loading activity…' : partialCapture ? 'Earlier output is no longer available. Showing the saved request and retained activity.' : saved.hasSavedEvents ? 'Full output is no longer available. Showing saved activity.' : 'Activity output is no longer available. Showing the saved request.'}</p>}</div>}
    <div ref={scroll} className="build-feed" tabIndex={0} aria-label={`${label} stream`}>
      <div ref={content}>{displayed.length ? <ol className="build-entry-list">{displayed.map(entry => <ActivityCard key={entry.id} entry={entry} start={turnStarts.get(entry.turnId) ?? start} selected={!!selectedTurn && entry.turnId === selectedTurn.id}/>)}</ol> : <p className="build-empty">Waiting for a build.</p>}</div>
    </div>
    <footer className="build-activity-footer"><span>{displayed.length} entries</span>{selectedTurn ? <button className="build-return-live" type="button" onClick={onReturnToLive}><ArrowDown size={12}/>Return to live</button> : <span className="build-auto-scroll"><ArrowDown size={12}/>Auto-scroll</span>}</footer>
    <span className="build-sr-only" role="status" aria-live="polite">{label}: {status}.</span>
  </aside>;
}

export default function LiveBuildActivity({ path, onExpired, ...props }: Omit<PanelProps, 'entries' | 'connected' | 'connecting'> & { path: string; onExpired: () => void }) {
  const activity = useBuildActivity(path, true, onExpired);
  return <BuildActivityPanel {...activity} {...props}/>;
}
