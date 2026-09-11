# Checkout API: Redis connection-pool exhaustion

Sample runbook for the bundled `checkout-api` incident.

## Mitigation

Roll back to the last healthy deployment after incident commander approval.
The example records approval but does not execute the rollback.

## Verification

After a responder performs the rollback, confirm the error rate drops below 1%
and p95 latency falls below 400 ms. Use fresh evidence before declaring recovery.
