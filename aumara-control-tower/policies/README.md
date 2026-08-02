# Policy Registry

This directory is the versioned policy boundary for the separate AUMARA and
EL CID guest products.

- `registry.yaml` pins the compatibility policy version and the three registry files.
- `shared.yaml` contains only cross-product safety and governance rules.
- `elcid.yaml` contains EL CID facts, reply fragments, action policy and source references.
- `aumara.yaml` contains AUMARA policy placeholders and source references.
- `guest_reply_runtime.json` pins the independently deployable EL CID guest-reply snapshot.
- `schema.json` is the shared machine-readable schema.
- `../scripts/guest_reply_policy_runtime.py` loads only snapshot-approved EL CID reply fragments and fails closed on registry or snapshot drift.

The `.yaml` files use JSON-compatible YAML so validation requires only the
Python standard library. Private operational values, guest data, credentials,
property identifiers, inventory identifiers, fees, and contact details must
not be committed. Store only approved source references or `PENDING`
placeholders, then resolve private values in the authorized runtime.

`pending` and `conflict` entries must keep both automation fields disabled.
Policy and template identifiers must remain inside their property namespace.
A reply template may be used only when its policy is `verified`,
`allowed_auto_reply` is true, and the runtime snapshot explicitly lists the
policy ID.

The global `policy_version` remains compatible with live Beds24 workers. Guest
reply wording is deployed through the separate `snapshot_version`, so a reply
change cannot silently disable a working cot or note writer. The ChatGPT
automation prompt must declare the same guest-reply snapshot version. A
delivery failure changes only delivery state; it must not rewrite the approved
reply or restore a stale generic template.

Validate locally:

```bash
python aumara-control-tower/scripts/validate_policy_registry.py
python -m unittest discover \
  -s aumara-control-tower/tests \
  -p 'test_policy_registry_schema.py'
python -m unittest discover \
  -s aumara-control-tower/tests \
  -p 'test_guest_reply_policy_runtime.py'
```

For a reply-only change, update `guest_reply_runtime.json`, the approved EL CID
reply policies, the automation snapshot version, and `CHANGELOG.md`. Change the
global `policy_version` only when all registry consumers are migrated together.
