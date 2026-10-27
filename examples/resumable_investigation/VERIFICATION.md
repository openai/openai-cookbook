# Local verification

Verification date: 2026-10-23. No external API execution.

## Passed

1. `python -m unittest -v test_continuity`
   - 26 tests passed.
   - Includes simultaneous starts/owner claims using separate SQLite connections,
     reopening persistence in a separate Python process, tenant boundaries,
     stale fencing tokens, duplicate/reordered/gapped events, and interrupted
     delivery before and after emission.
   - Includes regression checks rejecting boolean/float event sequences and
     non-finite clocks/TTLs across every ownership path.
2. `python validate_notebook.py`
   - All 8 code cells compiled and ran sequentially in a shared Python namespace.
   - Python socket creation was blocked during execution.
   - Notebook outputs and execution counts remain cleared in the saved file.
3. `python validate_notebook.py --require-schema`
   - Full notebook schema validation passed using the existing validation
     environment with `nbformat` installed.
   - All 8 sequential code cells passed again.
4. `python -m compileall -q continuity.py test_continuity.py validate_notebook.py`
   - Passed.

## Not run or not claimed

- Full Jupyter-kernel execution: not run. The available runtime is known to
  restrict kernel socket use. Sequential execution is useful evidence but not
  a substitute for kernel/UI validation.
- Live model, voice, transport, or provider integration: not included and not
  tested. No SDK or provider event name is invented by this recipe.
- Exactly-once spoken delivery: not guaranteed. The late-sink test deliberately
  demonstrates the limit of database fencing.
- Production distributed behavior, database failover, or audio usability:
  not tested. These are outside the local teaching example's scope.

## Acceptance map

| Requirement | Evidence |
|---|---|
| Stable application job, no duplicate reconnect start | Duplicate/concurrent start and read-only attach tests |
| Persistent cursor and identity | Separate-process SQLite reopening test |
| Ordered, replay-safe source events | Replay, changed content, order, gap, and rollback tests |
| Tenant separation | Cross-tenant rejection for every job-facing method |
| Single accepted polling owner | Concurrent claims and expiry/fencing/renewal tests |
| Honest interrupted-delivery outcome | Before/after emission and crash-window tests plus notebook demonstration |
| Offline runnable teaching artifact | Sequential cells with sockets blocked, schema validation, compilation |

Use the README's commands to reproduce the checks in your own environment.
