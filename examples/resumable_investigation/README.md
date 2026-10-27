# Resume a voice investigation without starting twice

Draft Cookbook contribution by Sophia Cole / ColeWorld. MIT licensed; see LICENSE.
This contribution has not been accepted or endorsed by OpenAI.

A voice connection can disappear while an investigation keeps running. This
recipe puts the investigation's identity and progress in application storage,
not in the lifetime of a voice connection. Reconnect attaches to the same
read-only investigation; it is not a new start command.

The notebook is entirely offline. Its investigator and transport are fictional
test doubles. It does not use an OpenAI SDK, model, API key, microphone, paid
service, network connection, or real user data. Local SQLite writes are the
only persistent effects. Notebook examples use a temporary directory.

## Start here

Requires Python 3.11 or later. The module and tests use the standard library.

```sh
cd resumable_investigation
python -m unittest -v test_continuity
python validate_notebook.py
```

The second command compiles and sequentially runs every notebook code cell in a
shared Python namespace. It does not start a Jupyter kernel. It also validates
the complete notebook schema when `nbformat` is installed:

```sh
# Optional setup, performed before taking the example offline:
python -m pip install -r requirements.txt
python validate_notebook.py --require-schema
```

Open `resume_voice_investigation.ipynb` with your existing Jupyter installation
and run its cells in order. No installation or network activity is hidden in
the notebook. Full Jupyter-kernel execution is a separate verification step.

## Files

- `resume_voice_investigation.ipynb`: guided start, interrupted update, process
  restart, same-job attach, reconciliation, and continued polling.
- `continuity.py`: local SQLite state machine and fictional worker/transport.
- `test_continuity.py`: failure-oriented, offline `unittest` suite.
- `validate_notebook.py`: schema validation plus sequential-cell smoke test,
  with Python socket creation blocked during cell execution.
- `requirements.txt`: optional schema-validator dependency only.

## The application contract

1. A deliberate start gets one client intent key. Persist that key before
   sending the start. If its response is lost, retry the *same key and prompt*.
   A new key means new work. This example rejects key reuse with a new prompt.
2. SQLite maps `(authenticated tenant, intent key)` to one investigation ID.
   Reconnect presents that ID to a read-only `attach` operation. It never calls
   the investigator or creates a replacement job if the ID is missing.
3. A fictional worker ingests immutable, contiguous per-job events. Replaying
   identical events is harmless. Changed content, gaps, and new events after
   completion are rejected. Failed batches roll back.
4. A leased owner reserves one update at a time. The reservation and consumed
   cursor commit atomically *before* external emission. The durable delivery ID
   is `investigation_id:sequence`, independent of connection IDs.
5. A receipt is stored as `acknowledged`. It means the application sink replied,
   not that the user heard or understood an utterance.
6. Disconnect or owner takeover makes an unresolved attempt `unknown`. Recovery
   shows the affected sequences and does not automatically repeat their audio.
   Newer updates can continue. The user can separately ask for a summary, but
   this example does not silently issue one or replay an ambiguous utterance.

Job status and delivery status are independent. An investigation can be
`completed` while the outcome of its last voice update remains `unknown`.

## Why checkpoint before emission?

There is no transaction encompassing this database and a person's speaker.

| Interruption | Persisted result | Recovery |
|---|---|---|
| Before reserving an event | Cursor unchanged | Reserve it normally later |
| After reservation, before emission | Cursor advanced; pending attempt | Unknown after recovery; do not replay automatically |
| After emission, before stored receipt | Same persisted state as above | Same unknown result; delivery cannot be inferred |
| After stored receipt | Acknowledged attempt | Continue after this cursor |

This policy favors not repeating an ambiguous voice update over guaranteed
delivery. It can omit an update that was never emitted. The explicit unknown
status is intentional, not an error hidden behind an “exactly once” label.

## What the tests establish

- Duplicate and concurrent starts with one intent key reuse one local job.
- Read-only reconnect never creates work or advances a cursor.
- Job identity, cursor, and receipts survive a separately launched Python
  process opening the same SQLite file.
- Identical source replay is deduplicated; out-of-order/gapped/changed events
  fail without partially committing a batch.
- Tenant-scoped access is enforced at every job-facing store method.
- SQLite accepts only one current polling owner; expired owner tokens cannot
  mutate cursor, receipt, lease, or disconnect state.
- Before-emission and after-emission disconnects both remain unknown; process
  death between emission and stored receipt is not mistaken for non-delivery.
- A late external emission is still possible after lease loss. The test suite
  deliberately demonstrates this limitation.

## Production boundaries and integration checklist

This is a local state-machine teaching example, **not a distributed reliability
guarantee** or a general Realtime reconnection tutorial.

- **External job creation:** Here the database insert is the complete mock start.
  A real queue or provider needs its own verified idempotent start contract or
  a transactional dispatch/outbox plus reconciliation. A SQLite intent key does
  not by itself deduplicate an external model/API request. If a provider-start
  response is lost and cannot be reconciled, preserve an unknown start outcome;
  do not create another paid job merely because the voice channel reconnected.
- **Identity:** `Scope` is a test seam, not authentication. Derive it server-side
  from verified identity. Do not accept an arbitrary client tenant string.
- **Storage:** SQLite transactions exercise the local invariants. This recipe
  does not cover database replication, schema migration, failover, multi-region
  leases, retained-event expiration, backup recovery, or disk/power failure.
- **Clock and leases:** All owners must use an authoritative comparable clock.
  The tests inject time deterministically. Set lease duration and renewal for
  real latency, pause, and deployment behavior. Expiry uses `now >= lease_until`.
  Non-finite clock values and nonpositive/non-finite TTLs are rejected, as are
  TTLs too small to advance the deadline at the chosen numeric precision.
- **Fencing:** A token fences database operations, not an already-started send.
  An external dispatcher/sink must enforce fencing or deduplicate stable IDs
  if that guarantee is needed. A pre-send lease check cannot eliminate the
  check/send race. Even a deduplicated application receipt cannot prove speech
  was actually heard.
- **Acknowledgments:** A real adapter must define exactly which application
  event counts as receipt. An HTTP success, socket write, or audio queue event
  must not be relabeled as confirmed human delivery.
- **Retention and security:** Bound job/event retention, redact sensitive data,
  protect storage, and define deletion and authorization policy before using
  real investigations. This example intentionally contains no personal data.
- **Retries:** Connection retries and backoff belong in the transport adapter;
  they must preserve investigation identity and cannot turn reconnect into start.

No provider adapter is included, so there are no invented SDK methods or API
event names. Add an adapter only against the provider's current documented
contract and test its actual acknowledgment and replay semantics separately.

## Distinct teaching contribution

The focus is *application-job continuity across a voice-session boundary*:
intent key → investigation ID → source sequence → reservation cursor → explicit
delivery uncertainty. It is not a mobile connection setup, a generic stream
cursor tutorial, a live MCP integration, or a durable approval protocol.

Full-kernel execution and final author review remain pending before marking this
draft ready. Running these examples creates no deployment or external service.
