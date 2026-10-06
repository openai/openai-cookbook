// The grammar is copied verbatim from Codex core/assets/tools/apply_patch.lark.
// Parsing and updates follow apply-patch/src/{parser,streaming_parser,
// seek_sequence,file_update}.rs, using Codex's default NormalizeToLf mode.
// This adapter is entirely in-memory: its only additional restrictions are the
// two-file workspace, bounded work, and retaining both required files at commit.
export const CODEX_PATCH_GRAMMAR = `start: begin_patch hunk+ end_patch
begin_patch: "*** Begin Patch" LF
end_patch: "*** End Patch" LF?

hunk: add_hunk | delete_hunk | update_hunk
add_hunk: "*** Add File: " filename LF add_line+
delete_hunk: "*** Delete File: " filename LF
update_hunk: "*** Update File: " filename LF change_move? change?

filename: /(.+)/
add_line: "+" /(.*)/ LF -> line

change_move: "*** Move to: " filename LF
change: (change_context | change_line)+ eof_line?
change_context: ("@@" | "@@ " /(.+)/) LF
change_line: ("+" | "-" | " ") /(.*)/ LF
eof_line: "*** End of File" LF

%import common.LF
`;

const MAX_PATCH_BYTES = 512_000;
const MAX_FILE_BYTES = 80_000;
const MAX_OPERATIONS = 64;
const MAX_CHUNKS = 256;
const MAX_MATCH_WORK = 8_000_000;
const BEGIN = '*** Begin Patch';
const END = '*** End Patch';
const EOF = '*** End of File';
const paths = new Map([['space.js', 'source'], ['tests.js', 'tests']]);
// Rust str::trim uses Unicode White_Space (unlike JS trim, it includes NEL and
// excludes BOM). Keep matching and marker parsing aligned with the Rust code.
const trim = (text) => text.replace(/^\p{White_Space}+|\p{White_Space}+$/gu, '');
const trimEnd = (text) => text.replace(/\p{White_Space}+$/u, '');

function fileKey(path) {
  if (!paths.has(path)) throw new Error('Only space.js and tests.js are editable.');
  return paths.get(path);
}

function boundedInput(input) {
  if (typeof input !== 'string') throw new Error('The patch must be a string.');
  if (Buffer.byteLength(input) > MAX_PATCH_BYTES) throw new Error('The patch exceeds the 512,000-byte limit.');
  return input;
}

function emptyChunk(context = null) {
  return { context, oldLines: [], newLines: [], contextLineIndices: [], isEndOfFile: false };
}

function parseLines(lines, complete) {
  const operations = [];
  let mode = 'notStarted';
  let chunkCount = 0;
  let lineNumber = 0;
  const invalid = (message) => { throw new Error(`Invalid patch at line ${lineNumber}: ${message}`); };
  const last = () => operations.at(-1);
  const ensureUpdate = (line) => {
    if (mode !== 'update') return;
    const operation = last();
    if (!operation.chunks.length) invalid(`Update file hunk for path '${operation.path}' is empty.`);
    const chunk = operation.chunks.at(-1);
    if (!chunk.oldLines.length && !chunk.newLines.length) {
      invalid(line === END ? 'Update hunk does not contain any lines.' : `Unexpected line found in update hunk: '${line}'.`);
    }
  };
  const addChunk = (operation, context = null) => {
    if (++chunkCount > MAX_CHUNKS) invalid('A patch may contain at most 256 update chunks.');
    const chunk = emptyChunk(context);
    operation.chunks.push(chunk);
    return chunk;
  };
  const header = (line) => {
    if (line === END) {
      ensureUpdate(line);
      mode = 'ended';
      return true;
    }
    for (const [prefix, type] of [['*** Add File: ', 'add'], ['*** Delete File: ', 'delete'], ['*** Update File: ', 'update']]) {
      if (!line.startsWith(prefix)) continue;
      ensureUpdate(line);
      const path = line.slice(prefix.length);
      fileKey(path);
      if (operations.length >= MAX_OPERATIONS) invalid('A patch may contain at most 64 file operations.');
      operations.push(type === 'add' ? { type, path, content: '' } : type === 'delete' ? { type, path } : { type, path, moveTo: null, chunks: [] });
      mode = type;
      return true;
    }
    return false;
  };

  for (const line of lines) {
    lineNumber++;
    const trimmed = trim(line);
    // StreamingPatchParser.finish accepts a whitespace-padded final marker.
    if (complete && lineNumber === lines.length && trimmed === END && mode !== 'notStarted') {
      ensureUpdate(END);
      mode = 'ended';
      continue;
    }
    if (mode === 'notStarted') {
      if (trimmed !== BEGIN) invalid(`The first line of the patch must be '${BEGIN}'.`);
      mode = 'started';
      continue;
    }
    if (mode === 'ended') {
      if (trimmed) invalid(`The last line of the patch must be '${END}'.`);
      continue;
    }
    if (mode !== 'update') {
      if (header(trimmed)) continue;
      if (mode === 'add' && line.startsWith('+')) {
        last().content += `${line.slice(1)}\n`;
        continue;
      }
      invalid(`'${trimmed}' is not a valid file hunk header or added line.`);
    }

    // Codex preserves leading whitespace on update lines, because one leading
    // space distinguishes a context line from a file/header marker.
    const updateLine = trimEnd(line);
    if (header(updateLine)) continue;
    const operation = last();
    let chunk = operation.chunks.at(-1);
    const contextMarker = updateLine === '@@' || updateLine.startsWith('@@ ');
    if (chunk?.isEndOfFile) {
      if (!updateLine) continue;
      if (!contextMarker) invalid(`Expected update hunk to start with a @@ context marker, got: '${line}'.`);
    }
    if (!operation.chunks.length && operation.moveTo === null && updateLine.startsWith('*** Move to: ')) {
      operation.moveTo = updateLine.slice('*** Move to: '.length);
      fileKey(operation.moveTo);
      continue;
    }
    if (contextMarker) {
      if (chunk && !chunk.oldLines.length && !chunk.newLines.length) invalid(`Unexpected line found in update hunk: '${line}'.`);
      addChunk(operation, updateLine === '@@' ? null : updateLine.slice(3));
      continue;
    }
    if (updateLine === EOF) {
      if (chunk && !chunk.oldLines.length && !chunk.newLines.length) invalid('Update hunk does not contain any lines.');
      if (chunk) chunk.isEndOfFile = true;
      continue;
    }
    if (line === '' || line.startsWith(' ') || line.startsWith('+') || line.startsWith('-')) {
      chunk ||= addChunk(operation);
      const value = line.slice(1);
      if (line === '' || line.startsWith(' ')) {
        chunk.contextLineIndices.push([chunk.oldLines.length, chunk.newLines.length]);
        chunk.oldLines.push(value);
        chunk.newLines.push(value);
      } else if (line.startsWith('+')) chunk.newLines.push(value);
      else chunk.oldLines.push(value);
      continue;
    }
    invalid(`Unexpected line found in update hunk: '${line}'. Every line must start with ' ', '+', or '-'.`);
  }
  if (complete && mode !== 'ended') throw new Error(`The last line of the patch must be '${END}'.`);
  return { operations, ended: mode === 'ended' };
}

/** Parse a complete patch. No filesystem paths are resolved or accessed. */
export function parseCodexPatch(input) {
  let lines = trim(boundedInput(input)).split(/\r?\n/);
  // Match Codex's lenient literal-heredoc handling; this never invokes a shell.
  if (['<<EOF', "<<'EOF'", '<<"EOF"'].includes(lines[0]) && lines.length >= 4 && lines.at(-1).endsWith('EOF')) lines = lines.slice(1, -1);
  if (trim(lines[0] || '') !== BEGIN) throw new Error(`The first line of the patch must be '${BEGIN}'.`);
  if (trim(lines.at(-1) || '') !== END) throw new Error(`The last line of the patch must be '${END}'.`);
  return parseLines(lines, true).operations;
}

/** Inert streaming view. Only newline-terminated lines have been parsed. */
export function parseCodexPatchPrefix(input) {
  const text = boundedInput(input).replace(/^\p{White_Space}+/u, '');
  const lines = text.split(/\r?\n/);
  const pendingLine = lines.pop();
  return { ...parseLines(lines, false), pendingLine };
}

function normalizedPunctuation(value) {
  return trim(value)
    .replace(/[\u2010-\u2015\u2212]/g, '-')
    .replace(/[\u2018-\u201B]/g, "'")
    .replace(/[\u201C-\u201F]/g, '"')
    .replace(/[\u00A0\u2002-\u200A\u202F\u205F\u3000]/g, ' ');
}

function seekSequence(lines, pattern, start, eof, budget) {
  if (!pattern.length) return start;
  if (pattern.length > lines.length) return -1;
  // This is Codex's default NormalizeToLf behavior, including its EOF anchor.
  const searchStart = eof ? lines.length - pattern.length : start;
  for (const normalize of [(value) => value, trimEnd, trim, normalizedPunctuation]) {
    const expected = pattern.map(normalize);
    for (let index = searchStart; index <= lines.length - pattern.length; index++) {
      let matches = true;
      for (let offset = 0; offset < pattern.length; offset++) {
        const actual = lines[index + offset];
        budget.remaining -= actual.length + pattern[offset].length + 1;
        if (budget.remaining < 0) throw new Error('Patch matching exceeded the work limit. Include more specific context or use Add File for a complete write.');
        if (normalize(actual) !== expected[offset]) { matches = false; break; }
      }
      if (matches) return index;
    }
  }
  return -1;
}

function updateContents(contents, operation, budget, preview) {
  const original = contents.split('\n');
  if (original.at(-1) === '') original.pop();
  const replacements = [];
  let lineIndex = 0;
  for (const chunk of operation.chunks) {
    if (preview && !chunk.oldLines.length && !chunk.newLines.length) continue;
    if (chunk.context !== null) {
      const index = seekSequence(original, [chunk.context], lineIndex, false, budget);
      if (index < 0) throw new Error(`Failed to find context '${chunk.context}' in ${operation.path}.`);
      lineIndex = index + 1;
    }
    if (!chunk.oldLines.length) {
      const insertionIndex = original.at(-1) === '' ? original.length - 1 : original.length;
      replacements.push([insertionIndex, 0, chunk.newLines]);
      continue;
    }
    let pattern = chunk.oldLines;
    let newLines = chunk.newLines;
    let found = seekSequence(original, pattern, lineIndex, chunk.isEndOfFile, budget);
    if (found < 0 && pattern.at(-1) === '') {
      pattern = pattern.slice(0, -1);
      if (newLines.at(-1) === '') newLines = newLines.slice(0, -1);
      found = seekSequence(original, pattern, lineIndex, chunk.isEndOfFile, budget);
    }
    if (found < 0) throw new Error(`Failed to find expected lines in ${operation.path}:\n${chunk.oldLines.join('\n')}`);
    replacements.push([found, pattern.length, newLines]);
    lineIndex = found + pattern.length;
  }
  replacements.sort((a, b) => a[0] - b[0]);
  let result = original;
  for (const [start, count, lines] of replacements.reverse()) {
    if (start > result.length) throw new Error(`Patch chunks overlap incompatibly in ${operation.path}.`);
    // Slice/concat avoids spread argument limits on large multiline files.
    result = result.slice(0, start).concat(lines, result.slice(start + count));
  }
  if (result.at(-1) !== '') result.push('');
  return result.join('\n');
}

function checkSize(path, content, minimum = false) {
  if (typeof content !== 'string') throw new Error(`The patch must retain ${path}.`);
  const bytes = Buffer.byteLength(content);
  if (bytes > MAX_FILE_BYTES || (minimum && bytes < 10)) throw new Error(`${path} must contain between 10 and 80,000 bytes of JavaScript.`);
}

/** Apply parser output to a copy. preview is only for inert, unpublished UI. */
export function applyCodexPatchOperations(workspace, operations, { preview = false } = {}) {
  if (!Array.isArray(operations) || operations.length > MAX_OPERATIONS) throw new Error('A patch may contain at most 64 file operations.');
  if (!preview && !operations.length) throw new Error('No files were modified.');
  const next = { source: workspace.source, tests: workspace.tests };
  for (const [path, key] of paths) checkSize(path, next[key]);
  const budget = { remaining: MAX_MATCH_WORK };
  let chunkCount = 0;
  let operationBytes = 0;
  for (const operation of operations) {
    const key = fileKey(operation.path);
    if (operation.type === 'add') {
      checkSize(operation.path, operation.content);
      operationBytes += Buffer.byteLength(operation.content);
      next[key] = operation.content;
    } else if (operation.type === 'delete') {
      if (typeof next[key] !== 'string') throw new Error(`Failed to delete missing file ${operation.path}.`);
      delete next[key];
    } else if (operation.type === 'update') {
      if (!Array.isArray(operation.chunks) || (chunkCount += operation.chunks.length) > MAX_CHUNKS) throw new Error('A patch may contain at most 256 update chunks.');
      if (!preview && !operation.chunks.length) throw new Error(`Update file hunk for path '${operation.path}' is empty.`);
      for (const chunk of operation.chunks) {
        if ((chunk.context !== null && typeof chunk.context !== 'string') || !Array.isArray(chunk.oldLines) || !Array.isArray(chunk.newLines) || ![...chunk.oldLines, ...chunk.newLines].every((line) => typeof line === 'string')) throw new Error('Invalid update chunk.');
        if (!preview && !chunk.oldLines.length && !chunk.newLines.length) throw new Error('Update hunk does not contain any lines.');
        operationBytes += Buffer.byteLength(chunk.context || '') + Buffer.byteLength(chunk.oldLines.join('\n')) + Buffer.byteLength(chunk.newLines.join('\n'));
      }
      if (operationBytes > MAX_PATCH_BYTES) throw new Error('The patch exceeds the 512,000-byte limit.');
      checkSize(operation.path, next[key]);
      const content = updateContents(next[key], operation, budget, preview);
      checkSize(operation.path, content);
      if (operation.moveTo !== null) {
        next[fileKey(operation.moveTo)] = content;
        delete next[key];
      } else next[key] = content;
    } else throw new Error('Unknown patch operation.');
    if (operationBytes > MAX_PATCH_BYTES) throw new Error('The patch exceeds the 512,000-byte limit.');
  }
  if (!preview) for (const [path, key] of paths) checkSize(path, next[key], true);
  return next;
}

/** Match every hunk atomically before returning a complete two-file draft. */
export function applyCodexPatch(workspace, input) {
  return applyCodexPatchOperations(workspace, parseCodexPatch(input));
}
