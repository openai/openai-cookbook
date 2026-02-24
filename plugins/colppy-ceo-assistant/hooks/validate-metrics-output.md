---
name: validate-metrics-output
description: Automatically validates that any SaaS metrics output includes required metadata (date range, data source, record count) and uses Argentina formatting conventions.
event: post_tool_call
---

# Validate Metrics Output

## When This Runs

After any tool call that produces SaaS metric output (MRR, churn, retention, KPIs).

## Checks

1. **Metadata present**: Output includes date range, data source, and record count
2. **Argentina formatting**: Currency uses `$` with comma decimals and period thousands
3. **No fabricated data**: Numbers are sourced from actual data, not generated or estimated
4. **Reconciliation**: MRR waterfall components sum correctly (Starting + movements = Ending)

## On Failure

If any check fails, append a warning to the output:
- `⚠ Missing metadata: [which fields]`
- `⚠ Formatting issue: [details]`
- `⚠ Reconciliation error: [discrepancy amount]`
