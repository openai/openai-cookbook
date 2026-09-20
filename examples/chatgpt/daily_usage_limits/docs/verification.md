# Verify the example and its execution paths

The local checks below were run on macOS with Node.js **24.13.0 and 26.5.1**. The complete suite passes **126 tests**, including 32 combinations of policy, interval, cohort, and unit and the full 2,000-credit weekly release sequence. They use fictional data, simulated API responses, and injected AWS or credential transports. They do not contact a ChatGPT workspace or deploy AWS resources.

Run these commands from `examples/chatgpt/daily_usage_limits`:

| Check | Reproduce it | What it establishes |
| --- | --- | --- |
| Complete automated suite | `npm test` | Policy arithmetic, native credit/USD handling, cadence and period guards, cohort review, API parsing, durable state, retries, recovery, and restore behavior against test inputs. |
| Guided demonstration | `npm run demo` | Three fictional members with a 2,000-credit monthly target and 500-credit weekly releases: preview, partial success, reconciliation, the next slot, manual-edit conflict, and exact restoration. |
| AWS runtime tests | `node --test test/aws*.test.mjs` | The handler, lease fencing, and shared controller work with injected service responses. This is not acceptance by AWS. |
| Credential runner tests | `node --test test/credential-runner.test.mjs` | Provider argument validation, scoped child execution, recovery-command forwarding, and secret-output handling with simulated credentials. No real Keychain or systemd secret is read. |
| Local walkthrough | Follow [the Codex rehearsal](codex.md#1-i-rehearse-without-a-key) and [the local rehearsal](local.md#1-i-rehearse-the-all-members-workflow) in fresh private directories. | Separate CLI processes preserve state through snapshot, review, preview, synthetic apply, duplicate detection, and restore. The credit rehearsals use a 2,000-credit monthly target with 500-credit weekly releases; selected USD headroom is a separate native-USD example. |
| Generated local scripts | After the local rehearsal, run `sh -n .private/local-rehearsal/run-preview.sh` and `sh .private/local-rehearsal/run-preview.sh`. | Shell syntax and manual invocation of the synthetic preview work. No scheduler is installed by these commands. |
| macOS job syntax | `plutil -lint .private/local-rehearsal/launchd.plist.disabled` | The generated property list parses. This does not prove launchd invocation or locked-Keychain access. |
| Cloud package preparation | `npm run package --prefix aws` | Creates a local ZIP, digest, and source manifest using pinned dependencies. Inspect the manifest before any upload. Packaging uses the package registry; it makes no AWS deployment request. |
| CloudFormation schema | `cfn-lint -t aws/template.yaml` using version 1.40.4 | The disabled template passes local schema checks. AWS has not accepted a deployment for this contribution. |

The generated ZIP was extracted, its shared modules and four AWS SDK packages imported under Node.js 24.13.0, and its handler probe run with injected dependencies. That smoke check made zero AWS requests and read no credential.

The SVG assets have valid XML. The interactive illustration has valid JavaScript syntax, linked form labels, unique element IDs, and no remote assets. Local Markdown links and anchors were checked, and the repository's `docs-editor` checklist was applied to the guides.

## Complete live acceptance for the chosen path

Cloud acceptance has **not** been run for this contribution. Local rehearsal also does not establish any of the following:

- The real Admin key has the intended workspace scope and works under the unattended service identity.
- Live API responses match the selected workspace's unit, effective-limit source, and confirmed usage period.
- A bounded, approved cap change is independently read back and the exact original settings are restored.
- Codex, launchd, systemd, or EventBridge Scheduler fires at the intended time and recovers correctly after a missed run.
- AWS accepts the template, retrieves the real secret, delivers retries, or reaches the configured alert recipient.
- A real monthly boundary, billing-unit transition, or model-side limit is handled as expected in that workspace.
- Installed services, cloud resources, and credentials are removed or disabled and their final state is verified.

Use the [Codex](codex.md), [local](local.md), or [AWS](aws.md) walkthrough to perform only the separately authorized live steps. Keep a reviewable record of the actual target, trigger, API readback, failure recovery, restoration, and cleanup. A passing local test, manually invoked process, or saved alarm definition is evidence only for the action it exercised.
