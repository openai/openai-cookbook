import { writeFileSync } from 'node:fs';

const [action, path] = process.argv.slice(2);
if (!['probe', 'preview', 'apply', 'restore', 'resume_auth', 'cancel_initial'].includes(action) || !path) {
  throw new Error('Usage: node aws/event.mjs probe|preview|apply|restore|resume_auth|cancel_initial OUTPUT.json');
}
writeFileSync(path, `${JSON.stringify({ version: 1, action, scheduledAt: new Date().toISOString() })}\n`,
  { mode: 0o600 });
console.log(`Wrote ${action} event. No AWS request was made.`);
