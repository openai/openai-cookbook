import { readFileSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { hash } from './store.mjs';
import { validateEnrollment } from '../src/enrollment.mjs';
import { requireThat } from '../src/policy.mjs';

// Only creates a private local item. Upload is a separate, explicit AWS CLI operation.
// Windows requires an ACL-aware writer for the private enrollment document.
requireThat(process.platform !== 'win32', 'MACOS_OR_LINUX_REQUIRED_FOR_PRIVATE_STATE');
const [configPath, enrollmentPath, deploymentId, outputPath] = process.argv.slice(2);
if (!configPath || !enrollmentPath || !outputPath ||
    !/^[a-z][a-z0-9-]{2,39}$/.test(deploymentId ?? '')) {
  throw new Error('Usage: node aws/prepare-control.mjs CONFIG ENROLLMENT DEPLOYMENT_ID OUTPUT');
}
const config = JSON.parse(readFileSync(configPath, 'utf8'));
const enrollment = JSON.parse(readFileSync(enrollmentPath, 'utf8'));
validateEnrollment(config, enrollment, new Date().toISOString(), true);
if (enrollment.members.length > 25) throw new Error('AWS pilot supports at most 25 reviewed members.');
const document = JSON.stringify({ config, enrollment });
if (Buffer.byteLength(document) > 300_000) throw new Error('Control document exceeds 300 KB; reduce the cohort.');
const item = { PK: { S: `CONTROL#${deploymentId}` }, SK: { S: 'REVIEWED' },
  document: { S: document }, documentSha256: { S: hash(document) } };
// Exclusive creation prevents silently overwriting another reviewed artifact.
writeFileSync(outputPath, `${JSON.stringify(item, null, 2)}\n`, { mode: 0o600, flag: 'wx' });
console.log(`ControlSha256=${hash(document)}\nPrivate control item: ${resolve(outputPath)}\nNo AWS request was made.`);
