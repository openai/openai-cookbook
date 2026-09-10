---
name: expense-review-policy
description: Review invoices and contracts against accounts-payable policy before human approval.
---

# Expense review policy

Policy ID: `AP-104`.

Apply this policy to invoices, expense receipts, and service contracts.

## Invoices and expenses

- Read the entire invoice, including the vendor and every line item.
- Use Python to multiply quantities by unit prices and add every line total plus shipping.
- Strip currency separators, compare the result with `Total amount due`, and report the exact difference.
- Require a purchase order or another documented approval.
- Flag missing receipts, unsupported charges, and changed payment instructions.
- Escalate incorrect totals and unverified changes to bank details.

## Contracts

- Read every clause and report all matching risks, even when one already requires escalation.
- Flag automatic renewals and restrictive cancellation windows.
- Flag unilateral price increases and missing liability limits.
- Escalate customer-data sharing or subcontractor access without approval.
- Identify missing confidentiality, security, or termination terms.

## Review decision

- `needs_info`: Required documentation or supporting information is missing.
- `escalated`: Fraud indicators, financial discrepancies, or risky terms need review.
- `ready_for_approval`: No policy violations remain, but a human must still approve.

Write `/workspace/output/<document-stem>.json` with the following fields:

```json
{
  "document": "invoice.txt",
  "policy_id": "AP-104",
  "decision": "escalated",
  "vendor": "Cedar Office Supply",
  "amount": 6420,
  "issues": ["The claimed total exceeds the calculated total."],
  "recommendation": "Escalate for human review."
}
```

Every `issues` entry must be a plain-English string, not a nested object.

Never approve payments, sign contracts, or take external actions.
