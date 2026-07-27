# Policy Registry

This directory is the versioned policy boundary for the separate AUMARA and
EL CID guest products.

- `registry.yaml` pins one policy version and the three registry files.
- `shared.yaml` contains only cross-product safety and governance rules.
- `elcid.yaml` contains EL CID policy placeholders and source references.
- `aumara.yaml` contains AUMARA policy placeholders and source references.
- `schema.json` is the shared machine-readable schema.

The `.yaml` files use JSON-compatible YAML so validation requires only the
Python standard library. Private operational values, guest data, credentials,
property identifiers, inventory identifiers, fees, and contact details must
not be committed. Store only approved source references or `PENDING`
placeholders, then resolve values in the authorized runtime.

`pending` and `conflict` entries must keep both automation fields disabled.
Policy and template identifiers must remain inside their property namespace.

Validate locally:

```bash
python aumara-control-tower/scripts/validate_policy_registry.py
python -m unittest discover \
  -s aumara-control-tower/tests \
  -p 'test_policy_registry_schema.py'
```

To update the registry, change all affected files to one new
`policy_version`, record the change in `CHANGELOG.md`, and keep unresolved or
conflicting facts fail-closed.
