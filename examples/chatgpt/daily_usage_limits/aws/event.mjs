import { writeFileSync } from 'node:fs';

const [action, path, runId] = process.argv.slice(2);
if (!['probe', 'preview', 'apply', 'restore', 'resume_auth', 'cancel_initial', 'cancel_run'].includes(action) || !path ||
    (action === 'cancel_run' && !/^[a-f0-9]{64}$/.test(runId ?? ''))) {
  throw new Error('Usage: node aws/event.mjs probe|preview|apply|restore|resume_auth|cancel_initial|cancel_run OUTPUT.json [RUN_ID for cancel_run]');
}
writeFileSync(path, `${JSON.stringify({ version: 1, action, scheduledAt: new Date().toISOString(), ...(runId ? { runId } : {}) })}\n`,
  { mode: 0o600 });
console.log(`Wrote ${action} event. No AWS request was made.`);
