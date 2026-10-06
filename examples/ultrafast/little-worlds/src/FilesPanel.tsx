import { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { ArrowDown, ChevronDown, FileCode2, FolderOpen, X } from 'lucide-react';
import { changedFileRanges, type WorkspaceFile, type WorkspaceFilePath, type WorkspaceFilesSnapshot } from './workspace-files';
import { useWorkspaceFiles } from './useWorkspaceFiles';
import './files-panel.css';

type FilesPanelProps = {
  snapshot: WorkspaceFilesSnapshot | null;
  connected: boolean;
  connecting: boolean;
  onClose: () => void;
};

const count = (value: number) => value.toLocaleString();
const statusLabel = { published: 'Published', working: 'Working', streaming: 'Writing' };

type FileEdit = {
  content: string;
  ranges: Array<{ start: number; end: number }>;
  revision: number;
  fresh: boolean;
};

function FileContents({ file }: { file: WorkspaceFile }) {
  const viewport = useRef<HTMLDivElement>(null);
  const code = useRef<HTMLElement>(null);
  const caret = useRef<HTMLSpanElement>(null);
  const previous = useRef(file.content);
  const revision = useRef(0);
  const [edit, setEdit] = useState<FileEdit | null>(() => file.status === 'streaming' ? {
    content: file.content, ranges: [{ start: file.content.length, end: file.content.length }], revision: 0, fresh: true,
  } : null);
  const lines = useMemo(() => file.content.split('\n'), [file.content]);
  const visibleEdit = edit?.content === file.content ? edit : null;
  const target = visibleEdit?.ranges.at(-1)?.end;
  const location = target === undefined ? null : {
    line: file.content.slice(0, target).split('\n').length,
    column: target === 0 ? 1 : target - file.content.lastIndexOf('\n', target - 1),
  };

  function revealChange() {
    const scroller = viewport.current;
    const marker = caret.current;
    if (!scroller || !marker) return;
    const bounds = scroller.getBoundingClientRect();
    // The caret is at the changed character, not the top of its logical line.
    // Long wrapped lines and patches in the middle of a file stay visible.
    scroller.scrollTop += marker.getBoundingClientRect().top - bounds.top - scroller.clientHeight * .42;
  }
  useLayoutEffect(() => {
    const ranges = changedFileRanges(previous.current, file.content);
    previous.current = file.content;
    if (ranges.length) setEdit({ content: file.content, ranges, revision: ++revision.current, fresh: true });
  }, [file.content]);
  useLayoutEffect(revealChange, [edit?.revision]);
  useEffect(() => {
    if (!edit) return;
    const currentRevision = edit.revision;
    const timer = setTimeout(() => setEdit(current => current?.revision === currentRevision ? { ...current, fresh: false } : current), 2400);
    return () => clearTimeout(timer);
  }, [edit?.revision]);
  useLayoutEffect(() => {
    const observer = new ResizeObserver(revealChange);
    if (viewport.current) observer.observe(viewport.current);
    if (code.current) observer.observe(code.current);
    return () => observer.disconnect();
  }, []);

  let offset = 0;
  return <>
    <div className="workspace-file-heading"><span><FileCode2 size={13}/><strong>{file.path}</strong></span><span className={`workspace-file-state is-${file.status}`}><i/>{statusLabel[file.status]}</span></div>
    <div ref={viewport} className={`workspace-file-editor${visibleEdit?.fresh ? ' has-recent-edit' : ''}`} tabIndex={0} aria-label={`${file.path} source`} data-voice-ignore>
      <pre aria-label={`${file.path} code`}><code ref={code}>{lines.map((line, index) => {
        const start = offset;
        const end = start + line.length;
        offset = end + 1;
        const ranges = visibleEdit?.ranges.filter(range => range.start <= end && (range.end > start || range.start === range.end && range.end === start)) || [];
        const hasTarget = target !== undefined && target >= start && target <= end;
        const boundaries = [...new Set([start, end, ...ranges.flatMap(range => [Math.max(start, range.start), Math.min(end, range.end)]), ...(hasTarget ? [target] : [])])].sort((a, b) => a - b);
        const pieces: ReactNode[] = [];
        for (let i = 0; i < boundaries.length; i++) {
          const position = boundaries[i];
          if (hasTarget && position === target) pieces.push(<span key="caret" ref={caret} className="workspace-file-edit-caret" aria-hidden="true"/>);
          const next = boundaries[i + 1];
          if (next === undefined || next <= position) continue;
          const text = file.content.slice(position, next);
          const updated = ranges.some(range => range.start <= position && range.end > position);
          pieces.push(updated ? <mark className="workspace-file-change" key={position}>{text}</mark> : text);
        }
        return <span key={index} data-file-line={index + 1} className={`workspace-file-line${ranges.length || hasTarget ? ' is-updated' : ''}`}><i aria-hidden="true">{index + 1}</i><span>{pieces.length ? pieces : ' '}</span></span>;
      })}</code></pre>
    </div>
    <footer className="workspace-files-footer" data-voice-ignore><span>{count(lines.length)} {lines.length === 1 ? 'line' : 'lines'} · {count(file.content.length)} chars</span><span title={location ? 'Following the latest edit' : undefined}><ArrowDown size={11}/>{location ? `Ln ${location.line} · Col ${location.column}` : 'Follow edits'}</span></footer>
  </>;
}

export function FilesPanel({ snapshot, connected, connecting, onClose }: FilesPanelProps) {
  const [selectedPath, setSelectedPath] = useState<WorkspaceFilePath>('space.js');
  const firstFile = useRef<HTMLButtonElement>(null);
  const hasFocused = useRef(false);
  const files = snapshot?.files || [];
  const selected = files.find(file => file.path === selectedPath) || files[0];
  const status = !connected ? connecting ? snapshot ? 'Reconnecting' : 'Connecting' : 'Disconnected'
    : !snapshot ? 'Loading' : statusLabel[snapshot.status];
  useEffect(() => {
    if (!hasFocused.current && firstFile.current) { firstFile.current.focus({ preventScroll: true }); hasFocused.current = true; }
  }, [files.length]);

  return <aside id="workspace-files-panel" className="workspace-files-panel" aria-label="Files" onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); onClose(); } }}>
    <header className="workspace-files-header"><span className={`workspace-files-connection${connected ? ' is-connected' : ''}`} role="status"><i/>{status}</span><button className="workspace-files-close" type="button" aria-label="Close files" onClick={onClose}><X size={15}/></button></header>
    <nav className="workspace-file-tree" aria-label="Workspace files">
      <div className="workspace-file-root"><ChevronDown size={12}/><FolderOpen size={14}/><span>space</span>{snapshot && <small>r{snapshot.revisionId}</small>}</div>
      {files.length > 0 && <ul>{files.map((file, index) => <li key={file.path}><button ref={index === 0 ? firstFile : undefined} type="button" aria-label={`Open ${file.path}`} aria-pressed={selected?.path === file.path} aria-controls="workspace-file-content" onClick={() => setSelectedPath(file.path)}><FileCode2 size={13}/><span>{file.path}</span><i className={`workspace-file-dot is-${file.status}`} aria-hidden="true"/></button></li>)}</ul>}
    </nav>
    <section id="workspace-file-content" className="workspace-file-content" aria-label="Selected file">
      {selected ? <FileContents key={`${snapshot?.sessionId}:${selected.path}`} file={selected}/>
        : <p className="workspace-files-empty">{connected || connecting ? 'Loading files…' : 'Files unavailable.'}</p>}
    </section>
  </aside>;
}

export default function LiveFilesPanel({ path, onClose, onExpired }: { path: string; onClose: () => void; onExpired: () => void }) {
  const files = useWorkspaceFiles(path, onExpired);
  return <FilesPanel {...files} onClose={onClose}/>;
}
