# Run the controller on a computer or server

Use your computer to rehearse the approach or test it with a small group. For ongoing workspace credit management, use a virtual machine or server operated by your organization, with monitoring and a team responsible for keeping it available. Choose the macOS or Linux scheduler procedure below.

This guide's commands run on macOS or Linux. From Windows, start with the [PowerShell demonstration](get-started.md#run-with-nodejs), then use your organization's managed Linux host or the [AWS setup path](aws.md#choose-your-setup-environment) for a live pilot.

Use a local scheduler to invoke the same controller without a model in the execution path. The host needs Node.js 24 or later, durable private storage on its local filesystem, and a credential provider that works under the scheduled service's identity. A sleeping or unavailable host can delay execution; the fixed policy catches up to the current interval when the host returns.

Prepare a fictional rehearsal and **uninstalled preview templates**. Review service installation and real changes in step 3. Run them from the extracted starter folder, or from `examples/chatgpt/daily_usage_limits` in the full repository.

## 1. Rehearse the all-members workflow

```bash
node src/cli.mjs init --dir .private/local-rehearsal --pattern fixed_release --cohort all --unit credit --interval-hours 168 --synthetic --allow-initial-reduction
node src/cli.mjs snapshot --config .private/local-rehearsal/config.json --out .private/local-rehearsal/enrollment.json --synthetic
```

Review the three fictional members: each has a 2,000-credit monthly target and will receive 500 credits each week. `--allow-initial-reduction` permits the first reviewed change from the original 2,000-credit limit to the first 500-credit portion. The membership snapshot fixes the enrolled users. The controller reports new members; include them through a fresh enrollment review. Removed or ineligible members produce attention receipts.

Replace `REVIEWED_SHA256` with the printed snapshot hash, then run:

```bash
node src/cli.mjs approve --enrollment .private/local-rehearsal/enrollment.json --hash REVIEWED_SHA256
node src/cli.mjs run --config .private/local-rehearsal/config.json --enrollment .private/local-rehearsal/enrollment.json --state .private/local-rehearsal/state --synthetic
node src/cli.mjs run --config .private/local-rehearsal/config.json --enrollment .private/local-rehearsal/enrollment.json --state .private/local-rehearsal/state --synthetic --apply
node src/cli.mjs run --config .private/local-rehearsal/config.json --enrollment .private/local-rehearsal/enrollment.json --state .private/local-rehearsal/state --synthetic --apply
node src/cli.mjs inspect --state .private/local-rehearsal/state
```

Expect preview receipts, then simulator changes, then `duplicate_slot` for all three members. The configured increment is per week in this rehearsal. This rehearsal uses the default 15-minute review window, measured from capture start. The first apply must also stay in the same interval slot. Set `initialReviewMaxAgeMinutes` before a live capture to cover the reviewed workflow.

To rehearse observed headroom, initialize a separate directory using `--pattern observed_headroom --cohort selected --unit usd --interval-hours 24 --synthetic`, then repeat the snapshot, approval, preview, apply, duplicate, and restore steps with that directory. Review `lookbackDays`, `coverageHours`, and `multiplierBps` in its configuration. Native USD calculations use USD throughout.

To try [individual starting limits](operations.md#individual-starting-limits) for a midmonth rollout, initialize another private rehearsal:

```bash
node src/cli.mjs init --dir .private/individual-rehearsal --pattern individual_staircase --cohort all --unit credit --interval-hours 24 --synthetic --allow-initial-reduction
```

Review `initialHeadroom`, `minimumInitialHeadroom`, `increment`, and `ceiling` in its configuration, then repeat the snapshot, approval, preview, apply, duplicate, and restore steps with `.private/individual-rehearsal`. The snapshot records a separate starting cap for each fictional person based on their observed monthly usage.

## 2. Generate and inspect the scheduler files

Find the runtime's absolute path with `command -v node`. Substitute that path for `/ABSOLUTE/PATH/TO/node`:

```bash
node src/cli.mjs render-local --dir .private/local-rehearsal --node /ABSOLUTE/PATH/TO/node --interval-minutes 60 --synthetic
```

The generated files are:

| File | Purpose |
| --- | --- |
| `run-preview.sh` | Invokes the controller without `--apply`. Inspect its paths and mode before running. |
| `launchd.plist.disabled` | macOS job definition, left uninstalled. |
| `usage-limit.service` | Linux systemd service definition. |
| `usage-limit.timer.disabled` | Linux systemd timer definition, left uninstalled. |

The check interval in these templates is 60 minutes. The policy's release interval remains 168 hours. Cap targets advance on the 168-hour policy interval.

For the credential-free rehearsal, confirm the generated runner contains `--synthetic` and omits `--apply`. Run the preview script and inspect its receipt:

```bash
sh .private/local-rehearsal/run-preview.sh
node src/cli.mjs inspect --state .private/local-rehearsal/state
```

Check the macOS syntax with `plutil -lint .private/local-rehearsal/launchd.plist.disabled`. On Linux, review the generated service and timer with your installed systemd tooling. After installation, verify a receipt produced by a timed trigger.

## 3. Prepare a live service for review

1. Create a separate live pilot directory and complete the [enrollment steps](operations.md#prepare-a-reviewed-enrollment). Use a disk local to the host. Keep the state directory outside shared or synchronized filesystems. Keep its state available across runs and restrict access to the service account. Do not reuse synthetic state for live calls.
2. Integrate your organization's protected credential provider so the scheduled process receives `CHATGPT_ADMIN_API_KEY`. Verify secret access under the scheduled identity with a read-only snapshot. Keep the credential out of logs. Do not store the key in a plist, service file, script, or plaintext environment file.
3. Generate templates for the live directory. Review absolute paths, runtime, service identity, cadence, logs, and attention handling. Run the preview script under that identity. Expect preview receipts with the approved workspace and members.
4. Authorize and complete one bounded live apply/readback/restore trial before recurring writes. Live application requires both `liveWrites: true` and `--apply`. Generated commands omit `--apply`. After restoring, create a new reviewed enrollment in a new private directory for continuing operation.
5. Choose one of the host-specific procedures below. The credential setup and service installation are separate, explicitly authorized steps. Verify a receipt from a timed invocation. Test reboot or sleep recovery, private-state access, and credential access in the intended unattended environment.

Complete the credential, scheduler, and recovery checks for the chosen host before enabling unattended live changes.

### macOS: Keychain and a user launchd job

These steps use the live configuration in `.private/pilot/config.json`. Complete its workspace, period, and policy review first. Run the commands from the example directory. The service and account names below select a dedicated pilot credential.

1. After credential storage is authorized, open **Keychain Access**, select the intended user's login keychain, and create a new password item with **Command-N**. Use `chatgpt-usage-limits` as the item name and `daily-limit` as the account. Enter the dedicated Admin key in the password field and save. Search for the saved item and confirm its name and account without revealing its password. [Apple's Keychain Access shortcuts](https://support.apple.com/en-ca/guide/keychain-access/kyca699a9058/mac) document the new-item shortcut.
2. Read the live enrollment through the credential runner. It reads the Keychain item into memory and passes it to the controller through a temporary environment variable. Command arguments and output exclude the key:

   ```bash
   pilot_dir="$PWD/.private/pilot"
   node_path="$(command -v node)"
   node src/credential-runner.mjs snapshot --provider keychain --service chatgpt-usage-limits --account daily-limit --config "$pilot_dir/config.json" --out "$pilot_dir/enrollment.json"
   ```

   Review the snapshot and approve its printed hash with `node src/cli.mjs approve --enrollment "$pilot_dir/enrollment.json" --hash REVIEWED_SHA256`. If Keychain requests access, review the exact program and item. Test credential access while the login keychain is locked. Do not broaden Keychain access for all applications.
3. Generate and manually run the Keychain-backed preview. The renderer refuses to overwrite existing files; use a fresh pilot directory if templates were already created there:

   ```bash
   node src/cli.mjs render-local --dir "$pilot_dir" --node "$node_path" --interval-minutes 60 --credential-provider keychain --keychain-service chatgpt-usage-limits --keychain-account daily-limit
   sh "$pilot_dir/run-preview.sh"
   plutil -lint "$pilot_dir/launchd.plist.disabled"
   ```

4. After approving installation of a recurring **preview**, check that no pilot with the same label is already installed. Run the following only if `launchctl print` reports that the service is absent. These commands use a fixed pilot label, so do not reuse it for a second job:

   ```bash
   agent_label="com.example.chatgpt-usage-limits"
   agent_domain="gui/$(id -u)"
   agent_file="$HOME/Library/LaunchAgents/$agent_label.plist"
   launchctl print "$agent_domain/$agent_label"
   ```

   Install the reviewed copy, enable it, and load it:

   ```bash
   set -eu
   test ! -e "$agent_file"
   mkdir -p "$HOME/Library/LaunchAgents"
   install -m 600 "$pilot_dir/launchd.plist.disabled" "$agent_file"
   plutil -replace Disabled -bool false "$agent_file"
   launchctl enable "$agent_domain/$agent_label"
   launchctl bootstrap "$agent_domain" "$agent_file"
   launchctl print "$agent_domain/$agent_label"
   ```

   The source template stays disabled. Verify the loaded service's arguments and interval, then inspect a receipt after its first timed fire. This user job depends on the user's login session and Keychain access.
5. To allow real changes later, pause and unload the preview job using the commands below. Complete the bounded live trial, first with a fresh approved snapshot, the scheduler paused, and `liveWrites: true`. This command changes the reviewed users' real caps:

   ```bash
   node src/credential-runner.mjs run --provider keychain --service chatgpt-usage-limits --account daily-limit --config "$pilot_dir/config.json" --enrollment "$pilot_dir/enrollment.json" --state "$pilot_dir/state" --apply
   ```

   Inspect independent readback and complete the restore procedure below. After restoration, prepare a fresh reviewed pilot. In its generated script, append `--apply` to the final controller invocation only after reviewing the exact command. Reinstall that pilot and verify independent readback from a real scheduled run.

To stop the macOS job, disable future loading and inspect whether a process is still running:

```bash
launchctl disable "$agent_domain/$agent_label"
launchctl print "$agent_domain/$agent_label"
```

Wait for the active run to finish and set `liveWrites: false`. Then unload the job and verify its disabled state:

```bash
launchctl bootout "$agent_domain/$agent_label"
launchctl print-disabled "$agent_domain"
```

Follow the reviewed restore procedure. The credential-runner invocation for its preview is:

```bash
node src/credential-runner.mjs restore --provider keychain --service chatgpt-usage-limits --account daily-limit --config "$pilot_dir/config.json" --enrollment "$pilot_dir/enrollment.json" --state "$pilot_dir/state"
```

After authorized restore/readback and with the gate off again, move the installed plist into the private pilot archive. Confirm `retired-launchd.plist` does not already exist before the move:

```bash
set -eu
test ! -e "$pilot_dir/retired-launchd.plist"
mv "$agent_file" "$pilot_dir/retired-launchd.plist"
launchctl print "$agent_domain/$agent_label"
```

Confirm that the final command reports the service as absent. Revoke the dedicated Admin key and remove its Keychain item only after confirming nothing else uses it. The `launchctl` commands above follow the host's `man launchctl`; check that manual for your macOS version.

### Linux: an encrypted credential and a user systemd timer

This path requires systemd 256 or later with working user-scoped encrypted credentials. Confirm `systemd-creds --version` and the host's supported credential configuration. User credentials use `--user`, and `LoadCredentialEncrypted` makes the decrypted value available only to the service at runtime. See the [systemd credential tool reference](https://github.com/systemd/systemd/blob/main/man/systemd-creds.xml). Do not fall back to null-key encryption or a plaintext environment file if the host cannot decrypt the credential.

The service also uses `PrivateTmp`, which requires user-namespace support for a user service. Verify both features under the service identity with the manual preview in step 4 before enabling its timer.

1. After credential storage is authorized, run this in Bash as the intended service user. Enter the dedicated key at the hidden prompt. The pipeline writes an encrypted credential file:

   ```bash
   set -eu
   set -o pipefail
   umask 077
   pilot_dir="$PWD/.private/pilot"
   node_path="$(command -v node)"
   test ! -e "$pilot_dir/chatgpt-admin-key.cred"
   systemd-ask-password -n 'ChatGPT Admin key:' | systemd-creds encrypt --user --name=chatgpt-admin-key - "$pilot_dir/chatgpt-admin-key.cred"
   ```

2. Run a read-only enrollment snapshot as a temporary user service, so credential access is tested in the service context:

   ```bash
   systemd-run --user --wait --pipe --collect -p "LoadCredentialEncrypted=chatgpt-admin-key:$pilot_dir/chatgpt-admin-key.cred" "$node_path" "$PWD/src/credential-runner.mjs" snapshot --provider systemd --config "$pilot_dir/config.json" --out "$pilot_dir/enrollment.json"
   ```

   Review the snapshot and approve its printed hash using the same local `approve` command as above. This temporary process reads the enrollment and exits.
3. Generate the preview service with its encrypted credential reference, then inspect the files:

   ```bash
   node src/cli.mjs render-local --dir "$pilot_dir" --node "$node_path" --interval-minutes 60 --credential-provider systemd --encrypted-credential "$pilot_dir/chatgpt-admin-key.cred"
   ```

   Confirm `LoadCredentialEncrypted=chatgpt-admin-key:…` names the intended encrypted file. The runner reads the fixed `chatgpt-admin-key` file from systemd's `CREDENTIALS_DIRECTORY`. Keep the credential path in the service definition.
4. After approving installation, confirm `usage-limit.service` and `usage-limit.timer` are absent from the user's service manager and unit directory. Install this pilot only; these fixed names must not replace another service:

   ```bash
   systemctl --user status usage-limit.service usage-limit.timer
   ```

   If both units are absent, install the preview definitions and start one manual service run:

   ```bash
   set -eu
   unit_dir="$HOME/.config/systemd/user"
   test ! -e "$unit_dir/usage-limit.service"
   test ! -e "$unit_dir/usage-limit.timer"
   mkdir -p "$unit_dir"
   install -m 600 "$pilot_dir/usage-limit.service" "$unit_dir/usage-limit.service"
   install -m 600 "$pilot_dir/usage-limit.timer.disabled" "$unit_dir/usage-limit.timer"
   systemd-analyze --user verify "$unit_dir/usage-limit.service" "$unit_dir/usage-limit.timer"
   systemctl --user daemon-reload
   systemctl --user start usage-limit.service
   journalctl --user -u usage-limit.service -n 50 --no-pager
   ```

   Confirm a successful preview receipt. Then, when recurring preview is authorized, enable the timer and inspect its next run:

   ```bash
   systemctl --user enable --now usage-limit.timer
   systemctl --user list-timers usage-limit.timer --all
   ```

   Verify a timed receipt. A user timer can stop when the user's session ends. Have the host administrator review unattended service ownership and any login-persistence change. Lingering requires a separate configuration decision.
5. Before applying changes on schedule, stop the timer, complete the bounded live trial, and create a fresh reviewed pilot after restoration. Only then add `--apply` to its generated controller invocation and enable `liveWrites`. Review the updated unit paths and reload them before resuming. Keep a single scheduler for the enrolled users.

To stop, disable the timer and inspect the running service:

```bash
systemctl --user disable --now usage-limit.timer
systemctl --user status usage-limit.service
```

Wait for the service to finish, set `liveWrites: false`, and preview restoration through a temporary service using the same encrypted credential:

```bash
systemd-run --user --wait --pipe --collect -p "LoadCredentialEncrypted=chatgpt-admin-key:$pilot_dir/chatgpt-admin-key.cred" "$node_path" "$PWD/src/credential-runner.mjs" restore --provider systemd --config "$pilot_dir/config.json" --enrollment "$pilot_dir/enrollment.json" --state "$pilot_dir/state"
```

After review, temporarily enable the write gate and repeat that exact command with `--apply`. Verify the original cap and source, then turn the gate off again.

After retention review, archive the two installed unit files into this pilot directory and reload the user manager. Confirm the archive filenames do not already exist:

```bash
set -eu
test ! -e "$pilot_dir/retired-usage-limit.service"
test ! -e "$pilot_dir/retired-usage-limit.timer"
mv "$unit_dir/usage-limit.service" "$pilot_dir/retired-usage-limit.service"
mv "$unit_dir/usage-limit.timer" "$pilot_dir/retired-usage-limit.timer"
systemctl --user daemon-reload
systemctl --user list-timers usage-limit.timer --all
systemctl --user is-enabled usage-limit.timer
```

Expect no scheduled timer and `not-found` from the final command. Revoke the dedicated key and remove its encrypted credential only when no retained process or other service needs it.

## 4. Handle attention receipts

| Condition | Action |
| --- | --- |
| Duplicate slot | No additional budget was released. Keep the same state directory. |
| Email or group selection changed | Pause new grants. Review the resolved membership and prepare a new enrollment after reconciling or restoring the existing one. Restoration uses the original enrolled IDs. |
| Conflicting manual edit or policy/enrollment mismatch | Pause the scheduler. Compare live settings, enrollment, and journal before approving another action. |
| Pending or ambiguous write | Rerun the same operation only after inspecting the saved absolute target and current state. Use readback to check whether the saved target was applied. |
| Initial review expired | Initial reductions and first writes for individual starting limits cannot be retried after their configured review window or interval slot ends. Inspect whether the saved target took effect; reconcile an applied change, or cancel an untouched initial operation using the procedure below. |
| Insufficient initial headroom | Compare current usage, the reviewed starting cap, and the ceiling. If an initial intent was saved, reconcile or cancel it before preparing a new review. |
| Authentication or authorization failure | Repair the dedicated credential or permissions through the approved process. Use `resume-auth` below to read current state and clear the halt, then preview the same pending operation. |
| Rate limit | Respect the recorded retry time. Do not shorten it by changing the scheduler. |
| Stale lock, incomplete journal, or corrupted journal | Stop all writers and reconcile saved intent against the API. Preserve evidence; deleting state can lose the original settings or repeat an operation. |
| Period ended, counter decreased, or unit changed | Stop and review the actual period and billing unit. Do not infer a new month or convert values. |

Configure the operator's attention route separately. Test delivery and agree what counts as a missed receipt.

After repairing authentication, clear an authorization halt with a read-only reconciliation. With the approved secret provider supplying the key, run:

```bash
node src/cli.mjs resume-auth --config .private/pilot/config.json --enrollment .private/pilot/enrollment.json --state .private/pilot/state
```

The command checks the saved pending operation against current API state and clears the halt only when they agree. It preserves the cap and updates the local recovery record. For Keychain or systemd, use `src/credential-runner.mjs resume-auth` with the same provider and path flags shown above. Preview before retrying an authorized apply; keep the existing journal. Initial reductions and first writes for individual starting limits retain their original configured review deadline and policy slot after authentication recovery. A previously saved exact increase for fixed releases or observed headroom can be retried after that window; its target is preserved.

### Cancel an unapplied initial operation

A failed API request can leave a saved initial operation. Initial reductions and first writes for individual starting limits cannot be retried after their review expires. Use `cancel-initial` to close that member's untouched initial operation while preserving the cohort's journal.

1. Pause the scheduler, confirm no run is active, and set `liveWrites: false`. Inspect receipts and the saved pending target. Complete any required authentication recovery first. These commands require the same confirmed, still-current usage period.
2. Run the following with the approved credential provider supplying the key. Do not add `--apply`:

   ```bash
   node src/cli.mjs cancel-initial --config .private/pilot/config.json --enrollment .private/pilot/enrollment.json --state .private/pilot/state
   node src/cli.mjs inspect --state .private/pilot/state
   ```

   The command reads the current cap and source, and checks that they still match the saved before-state. It sends no cap changes. A matching untouched member receives `initial_intent_cancelled`, and its enrollment is closed locally. Other members receive `no_unapplied_initial_intent` when there is nothing eligible to cancel. Keychain and systemd users can invoke `src/credential-runner.mjs cancel-initial` with their usual provider and path flags.
3. Review every member's result. Successful changes for the rest of the cohort remain in place. Preserve their original settings and pending records. Complete their reviewed reconciliation or restoration separately before creating a replacement pilot. Do not delete the state directory or overwrite the enrollment to bypass this review.

If the current cap differs from the saved before-state, cancellation stops with `CANCEL_REQUIRES_UNCHANGED_BEFORE_STATE`. Inspect whether the saved request committed or another administrator edited the cap, then use the matching reconciliation procedure. A timeout leaves the write outcome unresolved until readback. A new pilot needs a new snapshot, approval, and state directory.

## 5. Stop and restore

For the synthetic rehearsal:

```bash
node src/cli.mjs restore --config .private/local-rehearsal/config.json --enrollment .private/local-rehearsal/enrollment.json --state .private/local-rehearsal/state --synthetic
node src/cli.mjs restore --config .private/local-rehearsal/config.json --enrollment .private/local-rehearsal/enrollment.json --state .private/local-rehearsal/state --synthetic --apply
node src/cli.mjs inspect --state .private/local-rehearsal/state
```

Expect `restored` for each fictional member. The rehearsal leaves scheduler templates uninstalled.

For an installed live service, first disable and unload that exact job or timer, confirm no run is active, and set `liveWrites: false`. Follow the [reviewed restore procedure](operations.md#stop-restore-and-renew) while the period is current, verify the original cap and source by API readback, and turn the write gate off again. Verify that the job is absent or disabled in the host scheduler. Retain private receipts and remove only owned pilot files after the retention decision.

For a plan running on AWS, use [guided renewal on the same deployment](aws.md#7-renew-the-next-period). The AWS helper preserves the cloud state and carries the policy forward for the next period review.
