// Exact replacements keep routine edits small without letting generated tool
// arguments address arbitrary files or silently replace ambiguous matches.
export function applySourceEdits(workspace, edits) {
  if (!Array.isArray(edits) || edits.length < 1 || edits.length > 24) throw new Error('Provide between 1 and 24 exact source edits.');
  const next = { source: workspace.source, tests: workspace.tests };
  for (const [index, edit] of edits.entries()) {
    if (!edit || typeof edit !== 'object' || Array.isArray(edit)) throw new Error(`Edit ${index + 1} must be an object.`);
    if (!['space.js', 'tests.js'].includes(edit.path)) throw new Error('Only space.js and tests.js are editable.');
    if (typeof edit.search !== 'string' || !edit.search || typeof edit.replace !== 'string') throw new Error(`Edit ${index + 1} requires nonempty search text and replacement text.`);
    if (Buffer.byteLength(edit.search) > 80_000 || Buffer.byteLength(edit.replace) > 80_000) throw new Error('An edit exceeds the 80,000-byte source limit.');
    const key = edit.path === 'space.js' ? 'source' : 'tests';
    const at = next[key].indexOf(edit.search);
    if (at < 0) throw new Error(`Edit ${index + 1} did not match ${edit.path}. Copy exact text from the current workspace.`);
    if (next[key].indexOf(edit.search, at + 1) >= 0) throw new Error(`Edit ${index + 1} matches more than once in ${edit.path}. Include enough surrounding text for one exact match.`);
    next[key] = next[key].slice(0, at) + edit.replace + next[key].slice(at + edit.search.length);
    if (Buffer.byteLength(next[key]) > 80_000) throw new Error(`${edit.path} exceeds the 80,000-byte source limit.`);
  }
  return next;
}
