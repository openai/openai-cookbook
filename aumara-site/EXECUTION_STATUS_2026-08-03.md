# AUMARA execution status — 2026-08-03

## Decision (this session)

**Path chosen: CONTENT / interactive presence.**  
Not domain split to aumaru.me first. Not Matterport / Kuula first.

Why:

1. Master ТЗ and AI_HANDOFF already lock production target as `https://elcidspain.com/aumara/`.
2. Separate domain without stronger presence content is empty work.
3. Drive `08_360_TOURS` is empty — no spherical source, so no true 360 product yet.
4. We already have a working interactive layer:
   - `aumara-site/explore.html` — site plan + house selection + route line
   - `aumara-site/index.html` — baseline immersive landing + 8-point walkthrough
   - `route-v01.json` + storyboard from real site video
   - web exports in Drive `10_EXPORTS_WEB`

## What is already true

| Asset | Status |
|---|---|
| Fixed guest PIN `1531` on upcoming AUMARA bookings | Live via Beds24 API |
| Guest access text check-in / check-out | **14:00 / 12:00** in Control Tower policy |
| Explore map page | Built, EN/ES, house markers, route |
| Live GitHub Pages baseline | https://elcidspain.github.io/openai-cookbook/ |
| 360 spherical tours | **Missing** (folder empty) |
| Interior sequences per house type | Gap |
| aumaru.me | Deferred until content + Ads readiness |

## Immediate build order (owned by Control Tower / Grok)

### Now
1. Keep interactive **map + house choice** as the product spine (not a brochure).
2. Primary booking CTA → Beds24 `propid=324882`.
3. Booking.com remains secondary / fallback only.
4. Align guest-facing times: check-in **14:00**, check-out **12:00**.

### Next content production (no AI-fantasy media)
1. Inventory remaining raw clips in Drive `00_INBOX_RAW` (dedupe IMG_7694–7701 copies).
2. Cut route nodes for mobile explore (poster + 6–12s clip each).
3. Fill missing house stills from real source only (Chalet vs Superior Chalet).
4. When 360 is shot later: drop into `08_360_TOURS` and attach to house panels — architecture already allows it.

### Explicitly NOT doing this week
- Buying Matterport / Kuula accounts
- Full 3D / Gaussian splat
- Domain cutover to aumaru.me
- Rewriting the whole site from scratch

## Commercial path on every screen

User must always be able to:
- pick a house type / unit orientation
- open live availability on Beds24
- fall back to Booking.com if needed
- contact operator

## Operator facts (verified baseline)

- Operator: EL CID VENTURES BENIDOLEIG S.L.
- Beds24 property: 324882
- Inventory public: 3 Chalet + 2 Superior Chalet (5 bookable)
- Place: Benidoleig, Marina Alta, Costa Blanca
