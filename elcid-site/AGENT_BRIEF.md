# EL CID Country Club — review-site recovery brief

Read first:

`aumara-control-tower/work-orders/2026-07-16-access-site-distribution.md`

## Objective

Recover a full, separate EL CID Country Club review website without changing AUMARA production or replacing AUMARA branding.

## Non-negotiable guardrails

- Work only on branch `agent/elcid-country-club-recovery`.
- Do not deploy to Nominalia or change DNS.
- Do not overwrite `/aumara/`.
- Do not use placeholder logos when an official asset exists.
- Do not commit guest data, access codes, API tokens or credentials.
- Keep a working booking CTA in review; switch to direct Beds24 only after the target passes an end-to-end test.

## Deliverables

1. Audit current `elcid-site/` source and recover the last complete approved structure.
2. Create an asset inventory with source IDs/paths and licensing/approval status.
3. Build a mobile-first review page for:
   - country hotel;
   - room types;
   - Wabi-Sabi restaurant;
   - pool, territory and location;
   - contact and map actions;
   - booking conversion.
4. Produce desktop and mobile screenshots.
5. Add automated checks for internal links, required assets, booking CTA and no regression to AUMARA.
6. Record unresolved content or asset gaps explicitly; do not invent facts.

## Review gate

No production deployment until Ilya approves the visual review and the direct-booking test passes.
