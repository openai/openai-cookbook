import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { encodeControl } from './control.mjs';
import { validateEnrollment } from '../src/enrollment.mjs';
import { requireThat } from '../src/policy.mjs';

// Only creates private local items. Upload is a separate, explicit AWS CLI operation.
// Windows requires an ACL-aware writer for the private enrollment document.
requireThat(process.platform !== 'win32', 'MACOS_OR_LINUX_REQUIRED_FOR_PRIVATE_STATE');
const [configPath, enrollmentPath, deploymentId, outputPath] = process.argv.slice(2);
if (!configPath || !enrollmentPath || !outputPath ||
    !/^[a-z][a-z0-9-]{2,39}$/.test(deploymentId ?? '')) {
  throw new Error('Usage: node aws/prepare-control.mjs CONFIG ENROLLMENT DEPLOYMENT_ID OUTPUT_DIRECTORY');
}
const config = JSON.parse(readFileSync(configPath, 'utf8'));
const enrollment = JSON.parse(readFileSync(enrollmentPath, 'utf8'));
validateEnrollment(config, enrollment, new Date().toISOString(), true);
const prepared = encodeControl(config, enrollment);
// Exclusive directory creation prevents overwriting another reviewed artifact.
mkdirSync(outputPath, { mode: 0o700 });
function write(name, key, document) {
  const item = { PK: { S: `CONTROL#${deploymentId}` }, SK: { S: key }, document: { S: document } };
  writeFileSync(join(outputPath, name), `${JSON.stringify(item)}\n`, { mode: 0o600, flag: 'wx' });
}
for (const part of prepared.parts) write(`part-${String(part.index).padStart(8, '0')}.json`, `PART#${part.hash}`, part.document);
write('manifest.json', 'REVIEWED', prepared.document);
console.log(`ControlSha256=${prepared.hash}\nMembers=${enrollment.members.length}\nParts=${prepared.parts.length}\nPrivate controls: ${resolve(outputPath)}\nUpload every part before manifest.json. No AWS request was made.`);
