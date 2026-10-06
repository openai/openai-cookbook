import { applyCodexPatch, applyCodexPatchOperations, parseCodexPatchPrefix } from './codex-patch.mjs';

const MAX_INPUT = 2 * 1024 * 1024;
const MAX_FILE = 80_000;

// Project a freeform patch into memory only. Complete lines use the same parser
// and matching rules as execution; an arriving '+' line can extend an already
// identified addition/replacement so long wrapped lines remain visibly live.
// Unfinished paths, removed lines, context, and patch markers never choose a
// location. Errors leave the supplied workspace intact.
export function projectCodexPatch(workspace, input, { complete = false } = {}) {
  if (typeof input !== 'string' || input.length > MAX_INPUT) return workspace;
  try {
    if (complete) return { ...workspace, ...applyCodexPatch(workspace, input) };
    const { operations, pendingLine, ended } = parseCodexPatchPrefix(input);
    if (ended) return { ...workspace, ...applyCodexPatch(workspace, input) };
    const projectedOperations = structuredClone(operations);
    const last = projectedOperations.at(-1);
    if (pendingLine.startsWith('+')) {
      // Avoid displaying half of a UTF-16 surrogate pair between transport
      // chunks. The next cumulative projection will include the whole glyph.
      const addition = pendingLine.slice(1).replace(/[\uD800-\uDBFF]$/, '');
      if (last?.type === 'add') last.content += addition;
      else if (last?.type === 'update') {
        const chunk = last.chunks.at(-1);
        if (chunk && !chunk.isEndOfFile) chunk.newLines.push(addition);
      }
    }
    // A header or bare @@ alone is not an edit. In particular, do not normalize
    // an existing file's trailing newline before any hunk content has arrived.
    const readyOperations = projectedOperations.filter(operation => operation.type !== 'update'
      || operation.chunks.some(chunk => chunk.oldLines.length || chunk.newLines.length));
    const candidate = applyCodexPatchOperations(workspace, readyOperations, { preview: true });
    const result = { ...workspace };
    for (const key of ['source', 'tests']) {
      // Required files may temporarily disappear in a delete/add patch. Keep
      // their last view until replacement source arrives.
      if (candidate[key] === undefined) continue;
      if (typeof candidate[key] !== 'string' || Buffer.byteLength(candidate[key]) > MAX_FILE) return workspace;
      result[key] = candidate[key];
    }
    return result;
  } catch { return workspace; }
}
