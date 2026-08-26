# Bounded, owner-governed security supervisor

This local-only example reconciles **synthetic repositories only** for an explicitly finite number of cycles. It re-reads trusted configuration, inventory and named-human approvals each cycle; coalesces bounded local JSONL events; preserves signed owner-private state across service recreation; and stops on missing approvals, changed revisions, forged evidence or failed isolation. No hosted model, real Codex Security scan, customer repository, provider write, pull request, merge or deployment is implemented.

The supervisor and process-coordinated recipe require a Linux or macOS POSIX host and run Linux containers. Native Windows execution is unsupported; use an independently approved suitable Linux environment instead.

## Hardened daemon-free service boundary

Run the following from the root of the complete reference checkout or the self-contained Cookbook example. It creates a **new, separate** owner-private demo directory outside the checkout, copies the bundled synthetic fixtures, and creates an empty event stream. No event is required for the initial reconciliation. The example approvals describe fictional actors; copying them does not grant permission to scan real repositories.

Every input and state directory is `0700`; every input file is `0600`. Use the host owner's actual non-root UID/GID so the container can read these private bind mounts without weakening their permissions:

```sh
export GOVERNED_CHECKOUT="$(pwd -P)"
export GOVERNED_EXAMPLES="$GOVERNED_CHECKOUT/cookbook/security-review-pipeline"
export GOVERNED_DEMO_DIR="$(mktemp -d "${TMPDIR:-/tmp}/governed-security-demo.XXXXXX")"
export GOVERNED_PRIVATE_INPUTS="$GOVERNED_DEMO_DIR/inputs"
export GOVERNED_PRIVATE_STATE="$GOVERNED_DEMO_DIR/state"
export GOVERNED_UID="$(id -u)"
export GOVERNED_GID="$(id -g)"
export GOVERNED_COMPOSE_PROJECT="governed-security-review-$$"
export GOVERNED_MAX_CYCLES=2
export GOVERNED_INTERVAL_SECONDS=0

install -d -m 0700 "$GOVERNED_PRIVATE_INPUTS" "$GOVERNED_PRIVATE_STATE"
install -m 0600 "$GOVERNED_EXAMPLES/config.example.json" \
  "$GOVERNED_PRIVATE_INPUTS/configuration.json"
install -m 0600 "$GOVERNED_EXAMPLES/inventory.example.json" \
  "$GOVERNED_PRIVATE_INPUTS/inventory.json"
install -m 0600 "$GOVERNED_EXAMPLES/approvals.example.json" \
  "$GOVERNED_PRIVATE_INPUTS/approvals.json"
install -m 0600 /dev/null "$GOVERNED_PRIVATE_INPUTS/events.jsonl"

docker compose --project-name "$GOVERNED_COMPOSE_PROJECT" \
  -f local/docker-compose.governed.example.yml config
docker compose --project-name "$GOVERNED_COMPOSE_PROJECT" \
  -f local/docker-compose.governed.example.yml \
  run --rm --no-deps --pull never governed-security-supervisor
docker compose --project-name "$GOVERNED_COMPOSE_PROJECT" \
  -f local/docker-compose.governed.example.yml down --remove-orphans
```

Expected: the first run reports `attempted_repositories_per_cycle: [4, 0]`. With no transient failures, `scanner_invocations_per_cycle` is also `[4, 0]` and `retry_attempts_per_cycle` is `[0, 0]`. Repeating only the `docker compose ... run` command with the same inputs and state reports exactly zero jobs, attempts and retries. Re-running the whole setup block creates fresh state and therefore starts a new demonstration. The unique Compose project name keeps cleanup separate from other local projects. Compose cleanup does not delete the private input or state directories under `GOVERNED_DEMO_DIR`; retain them only while needed for this demonstration, and remove that disposable directory when finished.

The image must already be cached: automatic pulls and builds are prohibited. The mutable image tag is suitable only for this synthetic local lab; production requires an independently approved immutable image digest, signature and supply-chain policy. The service uses no network, a read-only root, four separately read-only allowlisted `src/`, `scripts/`, `fixtures/` and `contracts/` mounts, read-only private inputs, a writable owner-private state bind, a non-root identity, no capabilities, no-new-privileges, resource ceilings and no Docker socket. The checkout root, `.git` and root dotenv files are never mounted. Before reconciling, the supervisor verifies every approved bind, rejects visible Git/dotenv/credential material and refuses hidden secret entries or symbolic links within the approved source directories.

This service confines the trusted control plane **and** offline synthetic fixture inspection inside the same outer container. It does not provide a separate untrusted worker boundary; receipts truthfully report `outer_service_container_isolated` alongside the inner recipe's `synthetic_offline_not_sandboxed` mode.

## Separately isolated workers on the trusted host

Run the same bounded supervisor directly on a trusted host when separate restricted Docker workers are required:

If you already ran the Compose example, use fresh state for this worker-isolation demonstration. Reusing its state can correctly reuse prior evidence and produce no new worker receipts. The first command below creates a separate `0700` state directory under the disposable demo directory prepared above; it does not change or delete the Compose state.

```sh
export GOVERNED_PRIVATE_STATE="$(mktemp -d "$GOVERNED_DEMO_DIR/host-worker-state.XXXXXX")"

python3 -B scripts/run_bounded_security_supervisor.py \
  --config "$GOVERNED_PRIVATE_INPUTS/configuration.json" \
  --inventory "$GOVERNED_PRIVATE_INPUTS/inventory.json" \
  --approvals "$GOVERNED_PRIVATE_INPUTS/approvals.json" \
  --events "$GOVERNED_PRIVATE_INPUTS/events.jsonl" \
  --state-dir "$GOVERNED_PRIVATE_STATE" \
  --max-cycles 2 \
  --interval-seconds 0 \
  --max-events-per-cycle 128 \
  --max-pending-events 32 \
  --docker
```

Expected with fresh state: distinct attempted repositories `[4, 0]` and successful restricted worker receipts `[3, 0]`. Raw scan attempts are nominally `[4, 0]`; a recorded transient retry may increase the first count within the configured limit without adding a repository job. Inspect `retry_attempts_per_cycle`, `scanner_attempts_by_repository` and `transient_retry_events` in the cycle metrics; do not treat an unexplained extra attempt or exhausted failure as success. To demonstrate a restart, repeat only the Python command while retaining the same `GOVERNED_PRIVATE_STATE`; creating another fresh state directory starts a new demonstration. A true unchanged restart must report exactly zero jobs, attempts, retries and new isolation receipts.

Trusted configuration, human approvals, provider authority and signed state remain on the host. Each synthetic worker receives only read-only fixture source, protected acceptance tests and bounded writable scratch in a separate non-root, network-denied, read-only, capability-free container. Docker-in-Docker, daemon sockets in the service container and unsandboxed fallback are prohibited.

JSONL events are untrusted hints only. Each row must contain exactly `event_id`, `repository_id`, `revision` and `event_type`; permitted event types are `repository_changed`, `approval_changed` and `reconcile_requested`. The repository identity must be present in the trusted synthetic inventory and its revision must match exactly. Events never grant scope, finding disposition, patch, exception, merge, deployment or policy authority.

## Remaining production prerequisites

This local demonstration does **not** implement a real customer repository adapter, product scanner dispatcher, enterprise identity, scoped provider access, persistent scheduler/webhook service, operational monitoring, secret manager, approved model-network egress, product entitlement, independently approved spend/data routing, production persistence or deployment adapter. Each requires separate customer-owned implementation, named-human approval and evidence before any live execution.
