---
name: smb-accountant-comparison
description: Compare SMB funnel WITH vs WITHOUT accountant involvement. Deal→Won conversion, revenue, ICP breakdown. Requires date range.
---

# /smb-accountant-comparison

Compare SMB deals **with accountant involvement** (type 8) vs **without** (direct sale to SMB). Shows Deal→Won conversion rates, revenue, and ICP breakdown for both cohorts.

## Usage

```
/colppy-ceo-assistant:smb-accountant-comparison 2025-10-01 to 2026-02-01
/colppy-ceo-assistant:smb-accountant-comparison last 3 months
/colppy-ceo-assistant:smb-accountant-comparison 2025-12
```

---

## What I Need From You

- **Date range**: Start and end dates (YYYY-MM-DD)
  - Single month: e.g. `2025-12` → 2025-12-01 to 2026-01-01
  - Custom range: e.g. `2025-10-01 to 2026-02-01`
  - Relative: e.g. "last 3 months" → compute from today

---

## Execution

### Single Script Run

Run **one** script. It performs both analyses internally and outputs the comparison:

```bash
cd /Users/virulana/openai-cookbook
python tools/scripts/hubspot/analyze_smb_accountant_involved_funnel.py --start-date {START_DATE} --end-date {END_DATE}
```

For fastest run (~5 min for 4 months), add `--minimal` to skip contact filter and ICP coverage:

```bash
python tools/scripts/hubspot/analyze_smb_accountant_involved_funnel.py --start-date {START_DATE} --end-date {END_DATE} --minimal
```

**Note:** The script runs both "WITH accountant" and "WITHOUT accountant" funnels in a single invocation. No need to run twice.

### Date Parameter Rules

- `--start-date`: First day of period (inclusive), format YYYY-MM-DD
- `--end-date`: First day after period (exclusive), format YYYY-MM-DD
  - Example: Oct 2025–Jan 2026 → `--start-date 2025-10-01 --end-date 2026-02-01`
  - Example: December 2025 only → `--start-date 2025-12-01 --end-date 2026-01-01`

---

## Output

### 1. Terminal Output

The script prints:
- **WITH Accountant** (accountant involvement): SMB deal closed + accountant company (association type 8) on the deal. We bill to the SMB. NOT the same as ICP Operador (we bill to the accountant).
- **WITHOUT Accountant**: Deals with `tiene_cuenta_contador = 0` or null, no type 8
- **Comparison table**: Side-by-side metrics

### 2. CSV Output

- **Comparison**: `tools/outputs/smb_accountant_funnel_comparison_{START}_{END}.csv`
- **Single funnel (WITH)**: `tools/outputs/smb_accountant_involved_funnel_{START}_{END}.csv`

### 3. Present to User

Show the comparison table in markdown:

```
| Metric              | WITH Accountant | WITHOUT Accountant | Difference   |
|---------------------|----------------|--------------------|--------------|
| Deal Created        | {n}            | {n}                | {diff}       |
| Deal Closed Won     | {n}            | {n}                | {diff}       |
| Deal→Won Rate       | {x}%           | {x}%               | +{pp} pp     |
| Total Revenue       | ${x}           | ${x}               | ${diff}      |
| ICP Operador Count  | {n}            | {n}                | -            |
| ICP PYME Count      | {n}            | {n}                | -            |
```

Include the key insight: **Deal→Won rate WITH accountant vs WITHOUT accountant** (typically ~80% vs ~30%).

---

## Funnel Definitions

### WITH Accountant
- `tiene_cuenta_contador > 0` (default, fast). Use `--dual-criteria` to also check association type 8 per deal.
- At least one associated contact
- SMB contacts (explicit SMB rol_wizard or no rol_wizard treated as SMB)

### WITHOUT Accountant (Direct Sale to SMB)
- `tiene_cuenta_contador = 0` or null (default, fast)
- Use `--dual-criteria` to also exclude deals with association type 8
- Same contact rules (must have contacts)

---

## Important Notes

- **HUBSPOT_API_KEY** must be set in `.env`
- Script: ~5 min with `--minimal` (fastest), ~14 min default, ~5–10 min with `--dual-criteria`
- Closed Won = `dealstage = closedwon`, both createdate and closedate in period
- ICP = PRIMARY company type (Cuenta Contador types = Operador, else = PYME)
