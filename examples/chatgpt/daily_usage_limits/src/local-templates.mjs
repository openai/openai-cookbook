import { mkdir, writeFile } from 'node:fs/promises';
import { resolve, join, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { requireThat } from './policy.mjs';

export async function renderLocal({ directory, nodePath, intervalMinutes = 60, synthetic = false,
  credentialProvider, keychainService, keychainAccount, encryptedCredential }) {
  const dir = resolve(directory);
  const root = fileURLToPath(new URL('../', import.meta.url)).replace(/\/$/, '');
  requireThat(isAbsolute(nodePath) && !/[\r\n]/.test(nodePath + dir + root), 'ABSOLUTE_NODE_PATH_REQUIRED');
  requireThat(Number.isInteger(intervalMinutes) && intervalMinutes >= 1 && intervalMinutes <= 1440, 'POLL_INTERVAL_INVALID');
  requireThat(!credentialProvider || ['keychain','systemd'].includes(credentialProvider), 'CREDENTIAL_PROVIDER_INVALID');
  requireThat(!synthetic || !credentialProvider, 'SYNTHETIC_CREDENTIALS_FORBIDDEN');
  if(credentialProvider==='keychain') requireThat(keychainService && keychainAccount && !/[\r\n]/.test(keychainService+keychainAccount), 'KEYCHAIN_IDENTITY_REQUIRED');
  if(credentialProvider==='systemd') requireThat(encryptedCredential && isAbsolute(encryptedCredential) && !/[\r\n]/.test(encryptedCredential), 'ENCRYPTED_CREDENTIAL_PATH_REQUIRED');
  await mkdir(dir, { recursive: true, mode: 0o700 });
  const quote = value => `'${value.replaceAll("'", "'\\''")}'`;
  const command = [nodePath, join(root, credentialProvider ? 'src/credential-runner.mjs':'src/cli.mjs'), 'run',
    ...(credentialProvider ? ['--provider',credentialProvider] : []),
    ...(credentialProvider==='keychain' ? ['--service',keychainService,'--account',keychainAccount] : []),
    '--config', join(dir,'config.json'), '--enrollment',join(dir,'enrollment.json'), '--state',join(dir,'state'), ...(synthetic?['--synthetic']:[])].map(quote).join(' ');
  // Preview is the only generated command. Activation and apply are separate reviews.
  const script = `#!/bin/sh\nset -eu\numask 077\n# Supply CHATGPT_ADMIN_API_KEY through the host's approved secret store.\n# Never paste the key into this script or the scheduler template.\nexec ${command}\n`;
  const xml = value => value.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  const plist = `<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n<plist version="1.0"><dict>\n<key>Label</key><string>com.example.chatgpt-usage-limits</string>\n<key>Disabled</key><true/>\n<key>ProgramArguments</key><array><string>/bin/sh</string><string>${xml(join(dir,'run-preview.sh'))}</string></array>\n<key>StartInterval</key><integer>${intervalMinutes * 60}</integer>\n<key>StandardOutPath</key><string>${xml(join(dir,'scheduler.log'))}</string>\n<key>StandardErrorPath</key><string>${xml(join(dir,'scheduler-error.log'))}</string>\n</dict></plist>\n`;
  // systemd's quoting and percent escaping differ from POSIX shell quoting.
  const systemdPath = `"${join(dir,'run-preview.sh').replaceAll('\\','\\\\').replaceAll('"','\\"').replaceAll('%','%%')}"`;
  const encryptedDirective = credentialProvider==='systemd' ? `LoadCredentialEncrypted="chatgpt-admin-key:${encryptedCredential.replaceAll('\\','\\\\').replaceAll('"','\\"').replaceAll('%','%%')}"\n` : '';
  const files = {
    'run-preview.sh':script,
    'launchd.plist.disabled':plist,
    'usage-limit.service':`[Unit]\nDescription=Preview reviewed ChatGPT usage limits\n[Service]\nType=oneshot\nUMask=0077\n${encryptedDirective}ExecStart=/bin/sh ${systemdPath}\nNoNewPrivileges=true\nPrivateTmp=true\n`,
    'usage-limit.timer.disabled':`[Unit]\nDescription=Poll ChatGPT usage-limit policy slots\n[Timer]\nOnBootSec=5min\nOnUnitActiveSec=${intervalMinutes}min\nUnit=usage-limit.service\n[Install]\nWantedBy=timers.target\n`,
  };
  for (const [name, body] of Object.entries(files)) await writeFile(join(dir,name),body,{flag:'wx',mode:0o600});
  return Object.keys(files).map(name=>join(dir,name));
}
