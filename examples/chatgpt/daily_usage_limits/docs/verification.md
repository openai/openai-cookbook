# Verify the example and its execution paths

The tests cover 32 combinations of policy, interval, cohort, and unit and the full 2,000-credit weekly release sequence. They use fictional data, simulated API responses, and injected AWS or credential transports. They make zero requests to ChatGPT workspaces or AWS services.

The repository's **Validate usage-budget example** workflow checks Windows, macOS, and Linux with Node.js 24. It runs the tests and demonstration from both the source and the extracted starter download, verifies that the download matches the source, and builds the AWS package. Windows runs the portable checks and verifies that unsupported private-storage operations stop before writing; macOS and Linux also run the local journal and scheduler-script tests.

Run these commands from the extracted starter folder, or from `examples/chatgpt/daily_usage_limits` in the full repository:

| Check | Reproduce it | What it establishes |
| --- | --- | --- |
| Complete automated suite | `npm test` | Policy arithmetic, native credit/USD handling, cadence and period guards, ID/email/group selection, cohort review, API parsing, durable state, retries, recovery, and restore behavior against test inputs. |
| Guided demonstration | `node src/demo.mjs` | Three fictional members with a 2,000-credit monthly target and 500-credit weekly releases: preview, partial success, reconciliation, the next slot, manual-edit conflict, and exact restoration. This simulation keeps its state in memory. |
| AWS runtime tests | `node --test test/aws*.test.mjs` | Connection checks, queued work, control-part integrity, progress records, lease fencing, and the shared controller work with injected service responses. |
| Credential runner tests | `node --test test/credential-runner.test.mjs` | Provider argument validation, scoped child execution, recovery-command forwarding, and secret-output handling with simulated credentials. |
| Local walkthrough on macOS or Linux | Follow [the Codex rehearsal](codex.md#1-run-the-fictional-rehearsal) and [the local rehearsal](local.md#1-rehearse-the-all-members-workflow) in fresh private directories. | Separate CLI processes preserve state through snapshot, review, preview, synthetic apply, duplicate detection, and restore. The credit rehearsals use a 2,000-credit monthly target with 500-credit weekly releases; selected USD headroom uses native USD. |
| Generated local scripts | After the local rehearsal, run `sh -n .private/local-rehearsal/run-preview.sh` and `sh .private/local-rehearsal/run-preview.sh`. | Shell syntax and manual invocation of the synthetic preview work. Scheduler installation is a separate step in the local walkthrough. |
| macOS job syntax | `plutil -lint .private/local-rehearsal/launchd.plist.disabled` | The generated property list parses. Verify launchd invocation and locked-Keychain access on the intended host. |
| Cloud package preparation | `npm run package --prefix aws` | Creates a local ZIP, digest, and source manifest using pinned dependencies from the package registry. Inspect the manifest before any upload. |
| CloudFormation schema | `cfn-lint -t aws/template.yaml` using version 1.40.4 | The disabled template passes local schema checks. |

After packaging, test the extracted ZIP as well as the source directory. Verify the shared-module and AWS SDK imports, then run the handler probe with injected dependencies. Record the Node.js version and source revision with the result.

The SVG assets have valid XML. The interactive illustration has valid JavaScript syntax, linked form labels, and unique element IDs. All illustration assets are bundled for offline use. Local Markdown links and anchors were checked.

## Verify the starter download

The starter ZIP contains this example's source, guides, illustrations, tests, and license, plus a file manifest. It excludes credentials, private state, installed dependencies, and cloud build output.

Record the source commit from the contribution or its workflow result. Before extraction, run this command in the folder containing the downloaded ZIP to record its SHA-256:

```bash
node -e 'console.log(require("node:crypto").createHash("sha256").update(require("node:fs").readFileSync(process.argv[1])).digest("hex"))' chatgpt-usage-budget-starter.zip
```

Extract that ZIP into a fresh directory. From the extracted starter's top-level folder, run `npm test` and `node src/demo.mjs`, then build the AWS package there. Keep the source commit, ZIP digest, Node.js version, and test results together. These identify the exact kit used for deployment.

Use the workflow results for the source revision you plan to deploy. The portable demonstration runs on Windows, macOS, and Linux. Live local storage and scheduling use macOS or Linux; the AWS runtime uses Lambda and DynamoDB.

When updating the example, rebuild the download after editing included files, then check that it matches the current source:

```bash
python3 scripts/package_starter.py
python3 scripts/package_starter.py --check
```

Run these packaging commands from `examples/chatgpt/daily_usage_limits` in the repository. Rebuilding the ZIP requires Python. The browser example requires a browser, and the downloaded controller requires Node.js.

## Complete live acceptance for the chosen path

The automated results above use simulated services. Complete and record live checks against the exact kit and workspace you intend to operate.

For AWS, keep these stages separate and perform them in order:

| Stage | Evidence |
| --- | --- |
| AWS delivery | A `probe` invocation and stored receipt, followed by a timed probe. The Admin API is not accessed. |
| Workspace connection | A successful `check_connection` from the deployed Lambda, with the intended workspace and unit, `usersRead: true`, and `capWrites: 0`. Complete this before configuring budgets or capturing enrollment. |
| Limit behavior | A reviewed enrollment, completed preview, bounded approved apply, independent readback, and exact restoration. |

Follow [the AWS walkthrough](aws.md) for these commands. A successful connection checks read access; a live change and restoration establish the write behavior for the reviewed members.

Complete the remaining checks for the chosen execution path:

- Verify the Admin key's workspace scope and access under the unattended service identity.
- Match live API responses to the selected workspace's unit, effective-limit source, and confirmed usage period.
- Apply a bounded, approved cap change, read it back independently, and restore the exact original settings.
- Verify that the chosen scheduler fires at the intended time and recovers after a missed run.
- For AWS, verify deployment, secret retrieval, queued-work completion, retries, and delivery to the configured alert recipient. Increase the enrollment gradually and measure completion time against the configured review window, API throughput, and period end.
- Record how the intended workspace handles a real monthly boundary, billing-unit transition, or model-side limit.
- Remove or disable installed services, cloud resources, and credentials, then verify their final state.

Use the [Codex](codex.md), [local](local.md), or [AWS](aws.md) walkthrough for the authorized live steps. Record the actual target, timed trigger, API readback, delivered alert, failure recovery, restoration, and cleanup. Record local tests and manual invocations separately so the evidence identifies exactly what ran.
