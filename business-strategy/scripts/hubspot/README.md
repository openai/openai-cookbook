# HubSpot setup scripts

Idempotent HubSpot CRM setup for the TPS intake architecture. Re-runnable, no third-party deps.

## Files

- `properties.py` — declarative source of truth for the four property groups and ~36 `tps_*` contact properties (mirrors `multi-domain-intake-architecture.md` §3).
- `create_properties.py` — applies the definitions to a HubSpot portal via the CRM v3 API.

## Prerequisites

1. **HubSpot Private App** with scopes:
   - `crm.schemas.contacts.read`
   - `crm.schemas.contacts.write`
2. Python 3.10+ (uses `from __future__ import annotations` and built-in `urllib`; no `pip install`).

## Run

```bash
export HUBSPOT_PRIVATE_APP_TOKEN=pat-na1-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

# Preview what would change
python create_properties.py --dry-run

# Apply
python create_properties.py
```

## Safety

- **Idempotent.** Re-runs PATCH existing properties to match `properties.py`; new ones are POSTed.
- **Never deletes.** Removing a property from `properties.py` does *not* delete it in HubSpot — do that manually after confirming no workflows depend on it.
- **PATCH limits.** HubSpot ignores changes to `name`, `type`, or `fieldType` on existing properties. To rename or change type, create a new property and migrate.
- **Rate limit.** A 100 ms sleep between property writes keeps you well under HubSpot's 100 req / 10 s limit.

## Editing the schema

1. Edit `properties.py` (groups, options, labels).
2. Run `--dry-run` to verify the diff.
3. Run without `--dry-run` to apply.
4. Commit `properties.py` to the same PR/branch so the spec stays in lockstep with the portal.

## What this does *not* do

- Create the HubSpot **form** (build in UI; reference `hubspot-intake-form-spec.md`).
- Create the HubSpot **meeting type** (build in UI: *Tax Problem Case Review*, 30 min).
- Create HubSpot **workflows** (build in UI; reference `multi-domain-intake-architecture.md` §4 and `n8n-routing-workflow.md`).

These are intentionally manual because HubSpot's form/workflow APIs require materially more code and the UI is faster for one-time setup.
