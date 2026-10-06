export type WorkspaceFileStatus = 'published' | 'working' | 'streaming';
export type WorkspaceFilePath = 'space.js' | 'tests.js';

export interface WorkspaceFile {
  path: WorkspaceFilePath;
  content: string;
  language: 'javascript';
  status: WorkspaceFileStatus;
  updatedAt: string;
}

export interface WorkspaceFilesSnapshot {
  sessionId: string;
  revisionId: number;
  turnId?: string;
  status: WorkspaceFileStatus;
  files: WorkspaceFile[];
}

export const WORKSPACE_FILE_MAX_BYTES = 80_000;
const paths: WorkspaceFilePath[] = ['space.js', 'tests.js'];
const statuses = new Set(['published', 'working', 'streaming']);
const record = (value: unknown): value is Record<string, unknown> => !!value && typeof value === 'object' && !Array.isArray(value);
const identifier = (value: unknown): value is string => typeof value === 'string' && value.length > 0 && value.length <= 256;

/** Only the generated workspace's two files belong in this inspector. */
export function parseWorkspaceFilesEvent(event: unknown): WorkspaceFilesSnapshot | null {
  if (!record(event) || event.type !== 'files.snapshot' || !record(event.data)) return null;
  const data = event.data;
  if (!identifier(data.sessionId) || !Number.isSafeInteger(data.revisionId) || (data.revisionId as number) < 1
    || typeof data.status !== 'string' || !statuses.has(data.status)
    || data.turnId !== undefined && !identifier(data.turnId)
    || !Array.isArray(data.files) || data.files.length !== paths.length) return null;
  const files: WorkspaceFile[] = [];
  for (const path of paths) {
    const matches = data.files.filter(file => record(file) && file.path === path);
    if (matches.length !== 1) return null;
    const file = matches[0];
    if (!record(file) || typeof file.content !== 'string' || file.content.length > WORKSPACE_FILE_MAX_BYTES
      || new TextEncoder().encode(file.content).byteLength > WORKSPACE_FILE_MAX_BYTES
      || file.language !== 'javascript' || typeof file.status !== 'string' || !statuses.has(file.status)
      || typeof file.updatedAt !== 'string' || file.updatedAt.length > 80 || !Number.isFinite(Date.parse(file.updatedAt))) return null;
    files.push({ path, content: file.content, language: 'javascript', status: file.status as WorkspaceFileStatus, updatedAt: file.updatedAt });
  }
  return {
    sessionId: data.sessionId, revisionId: data.revisionId as number,
    ...(typeof data.turnId === 'string' ? { turnId: data.turnId } : {}),
    status: data.status as WorkspaceFileStatus, files,
  };
}

/** Snapshots are authoritative, including after reset, restore, and reconnect. */
export function mergeWorkspaceFilesEvents(current: WorkspaceFilesSnapshot | null, events: readonly unknown[]): WorkspaceFilesSnapshot | null {
  let next = current;
  for (const event of events) {
    const incoming = parseWorkspaceFilesEvent(event);
    if (!incoming) continue;
    if (next && incoming.sessionId === next.sessionId && incoming.revisionId === next.revisionId
      && incoming.turnId === next.turnId && incoming.status === next.status
      && incoming.files.every((file, index) => Object.keys(file).every(key => file[key as keyof WorkspaceFile] === next!.files[index]?.[key as keyof WorkspaceFile]))) continue;
    next = incoming;
  }
  return next;
}

/** The changed range in the new file, including an anchor for pure deletions. */
export function changedFileLines(previous: string, current: string): { start: number; end: number } | null {
  if (previous === current) return null;
  let start = 0;
  while (start < previous.length && start < current.length && previous[start] === current[start]) start++;
  let previousEnd = previous.length;
  let currentEnd = current.length;
  while (previousEnd > start && currentEnd > start && previous[previousEnd - 1] === current[currentEnd - 1]) { previousEnd--; currentEnd--; }
  const line = (position: number) => current.slice(0, position).split('\n').length;
  return { start: line(start), end: line(Math.max(start, currentEnd - 1)) };
}

export interface ChangedFileRange { start: number; end: number }

type LineMatch = [previous: number, current: number];

/** Bound both edit distance and comparisons, including heavily repeated lines. */
function matchingLines(previous: string[], current: string[]): LineMatch[] | null {
  const frontier = new Map<number, number>([[1, 0]]);
  const trace: Map<number, number>[] = [];
  let comparisons = 250_000;
  for (let distance = 0; distance <= Math.min(128, previous.length + current.length); distance++) {
    trace.push(new Map(frontier));
    for (let diagonal = -distance; diagonal <= distance; diagonal += 2) {
      let x = diagonal === -distance || diagonal !== distance && (frontier.get(diagonal - 1) ?? -1) < (frontier.get(diagonal + 1) ?? -1)
        ? frontier.get(diagonal + 1) ?? 0 : (frontier.get(diagonal - 1) ?? 0) + 1;
      let y = x - diagonal;
      while (x < previous.length && y < current.length) {
        if (--comparisons < 0) return null;
        if (previous[x] !== current[y]) break;
        x++; y++;
      }
      frontier.set(diagonal, x);
      if (x < previous.length || y < current.length) continue;
      const matches: LineMatch[] = [];
      for (let step = distance; step >= 0; step--) {
        const earlier = trace[step];
        const k = x - y;
        const preceding = k === -step || k !== step && (earlier.get(k - 1) ?? -1) < (earlier.get(k + 1) ?? -1) ? k + 1 : k - 1;
        const priorX = earlier.get(preceding) ?? 0;
        const priorY = priorX - preceding;
        while (x > priorX && y > priorY) matches.push([--x, --y]);
        x = priorX; y = priorY;
      }
      return matches.reverse();
    }
  }
  return null;
}

/** A linearithmic fallback retains unchanged unique lines after a large rewrite. */
function uniqueLineMatches(previous: string[], current: string[]): LineMatch[] {
  const positions = (lines: string[]) => {
    const result = new Map<string, number>();
    lines.forEach((line, index) => result.set(line, result.has(line) ? -1 : index));
    return result;
  };
  const before = positions(previous);
  const after = positions(current);
  const candidates: LineMatch[] = [];
  previous.forEach((line, index) => {
    const next = after.get(line);
    if (before.get(line) === index && next !== undefined && next >= 0) candidates.push([index, next]);
  });
  const tails: number[] = [];
  const predecessors = new Int32Array(candidates.length).fill(-1);
  candidates.forEach(([, next], index) => {
    let low = 0;
    let high = tails.length;
    while (low < high) {
      const middle = (low + high) >>> 1;
      if (candidates[tails[middle]][1] < next) low = middle + 1;
      else high = middle;
    }
    if (low > 0) predecessors[index] = tails[low - 1];
    tails[low] = index;
  });
  const matches: LineMatch[] = [];
  for (let index = tails.at(-1) ?? -1; index >= 0; index = predecessors[index]) matches.push(candidates[index]);
  return matches.reverse();
}

function previousCharacterStart(value: string, end: number): number {
  const last = value.charCodeAt(end - 1);
  const first = value.charCodeAt(end - 2);
  return last >= 0xdc00 && last <= 0xdfff && first >= 0xd800 && first <= 0xdbff ? end - 2 : end - 1;
}

function trimUnchanged(previous: string, current: string, previousStart: number, previousEnd: number, start: number, end: number) {
  while (previousStart < previousEnd && start < end && previous.codePointAt(previousStart) === current.codePointAt(start)) {
    const width = current.codePointAt(start)! > 0xffff ? 2 : 1;
    previousStart += width; start += width;
  }
  while (previousEnd > previousStart && end > start) {
    const prior = previousCharacterStart(previous, previousEnd);
    const next = previousCharacterStart(current, end);
    if (previous.slice(prior, previousEnd) !== current.slice(next, end)) break;
    previousEnd = prior; end = next;
  }
  return { previousStart, previousEnd, start, end };
}

/**
 * Changed spans use UTF-16 offsets in the new file, with exclusive ends and
 * zero-width anchors for deletions. Unchanged lines separate edit hunks; each
 * hunk is trimmed to whole Unicode characters. Streaming appends take one scan.
 */
export function changedFileRanges(previous: string, current: string): ChangedFileRange[] {
  if (previous === current) return [];
  const outer = trimUnchanged(previous, current, 0, previous.length, 0, current.length);
  if (outer.previousStart === outer.previousEnd
    || !previous.slice(outer.previousStart, outer.previousEnd).includes('\n') && !current.slice(outer.start, outer.end).includes('\n')) {
    return [{ start: outer.start, end: outer.end }];
  }
  const tokenize = (value: string) => value.match(/[^\n]*\n|[^\n]+$/g) ?? [];
  // Keep complete lines here: a shared first character after a deletion must
  // not prevent the rest of that unchanged line from becoming an anchor.
  const before = tokenize(previous);
  const after = tokenize(current);
  const offsets = (lines: string[], start: number) => {
    const result = [start];
    for (const line of lines) result.push(result[result.length - 1] + line.length);
    return result;
  };
  const beforeOffsets = offsets(before, 0);
  const afterOffsets = offsets(after, 0);
  const matches = matchingLines(before, after) ?? uniqueLineMatches(before, after);
  const ranges: ChangedFileRange[] = [];
  let prior = 0;
  let next = 0;
  for (const [priorMatch, nextMatch] of [...matches, [before.length, after.length]]) {
    if (prior < priorMatch || next < nextMatch) {
      const range = trimUnchanged(previous, current, beforeOffsets[prior], beforeOffsets[priorMatch], afterOffsets[next], afterOffsets[nextMatch]);
      if (range.previousStart < range.previousEnd || range.start < range.end) ranges.push({ start: range.start, end: range.end });
    }
    prior = priorMatch + 1;
    next = nextMatch + 1;
  }
  return ranges;
}
