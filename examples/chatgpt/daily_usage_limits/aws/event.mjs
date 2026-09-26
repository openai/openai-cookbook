import { writeFileSync } from 'node:fs';

const [action, path, identity, ...extra] = process.argv.slice(2);
const identityField = action === 'cancel_run' ? 'runId' : action === 'check_connection' ? 'workspaceId' : null;
if (!['probe', 'check_connection', 'preview', 'apply', 'restore', 'resume_auth', 'cancel_initial', 'cancel_run'].includes(action) || !path ||
    extra.length || (action === 'cancel_run' && !/^[a-f0-9]{64}$/.test(identity ?? '')) ||
    (action === 'check_connection' && !/^[A-Za-z0-9_-]{1,160}$/.test(identity ?? '')) ||
    (!identityField && identity !== undefined)) {
  throw new Error('Usage: node aws/event.mjs probe|preview|apply|restore|resume_auth|cancel_initial OUTPUT.json; check_connection OUTPUT.json WORKSPACE_ID; cancel_run OUTPUT.json RUN_ID');
}
writeFileSync(path, `${JSON.stringify({ version: 1, action, scheduledAt: new Date().toISOString(), ...(identityField ? { [identityField]: identity } : {}) })}\n`,
  { mode: 0o600 });
console.log(`Wrote ${action} event. No AWS request was made.`);
