# AI Ops response — AUMARA v3 reconciliation

Date: 2026-07-14  
Status: preview only; production remains unchanged.

## What was reconciled

- Captured the current public AUMARA page as a recovery snapshot before changing the review branch.
- Preserved the live interactive plan and all eight route-video points.
- Rebuilt `direct-v3-preview.html` from the current live experience instead of from the stale compressed v3 branch.
- Kept the first commercial page focused on stays: houses, capacities, plan, pool, practical rules and direct booking.
- Removed the deeper Retreats / Gatherings / Safe depth material from the first sales page.
- Replaced the old Gmail contact with `reservas@elcidspain.com`.
- Added the verified inventory baseline: 6 physical houses, 5 bookable; 3 Chalet up to 4 guests and 2 Superior Chalet up to 6 guests.
- Clarified that the pool is shared exclusively by staying AUMARA guests.
- Clarified pets and meals without inventing availability or inclusions.
- Kept access instructions private and avoided promising fully automated personal TTLock codes.
- Added date pass-through to Beds24 using `checkin` and `checkout`.

## Validation completed

- Preview JavaScript and internal anchors checked: 2 scripts, 27 IDs, no unresolved target.
- Beds24 direct-booking URL tested with selected dates; the booking form received check-in and check-out and calculated the matching number of nights.
- Production file `aumara-site/index.html` was not modified.
- Work was moved to a fresh branch from current `main`; the stale review branch is not a merge source.

## Sources of truth

- Copy and operational facts: `aumara-site/CONTENT_BASELINE.md`
- Product and implementation direction: `aumara-site/AI_HANDOFF.md`
- Recovery copy of the public page: `aumara-site/snapshots/live-2026-07-14/`

## Next gates

1. Review the reconciled preview on iPhone and desktop.
2. Integrate the approved Spanish and English copy into the visual rhythm.
3. Complete a Beds24 end-to-end test: booking, inventory block, payment state, confirmation, cancellation and release.
4. Audit public Beds24 amenities and remove unsupported claims.
5. Move production media from fragile external delivery to stable repository or CDN assets.
6. Switch production only after Ilya explicitly approves it.

Claude can review the reconciled preview and this response. AI Ops remains responsible for fact-checking and implementation; Ilya remains the final production gate.


## Scope guard for the next review

- `aumara_walk_12s.mp4` is a media asset and fallback loop, not approval to replace the established opening experience or redesign the homepage around one clip.
- The website must preserve the original immersive visual baseline and the interactive territory route with eight real video points.
- “AI talent workation” is a separate B2B campaign hypothesis. It does not belong in the first guest-booking page unless Ilya explicitly opens that workstream.
- Do not restart information discovery in Drive. Review the implementation and verified baseline in this branch.
