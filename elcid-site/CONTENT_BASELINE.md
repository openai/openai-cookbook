# EL CID Country Club — website content baseline v0.1

Status: review-only. Do not deploy or merge to production without Ilya's explicit approval.

## Product separation

- EL CID Country Club is the country hotel / restaurant / shared-facility product.
- AUMARA is a separate private-house accommodation product at `/aumara/`.
- The root page must not use AUMARA houses, AUMARA brand images or AUMARA copy as the main EL CID identity.

## Working public inventory

- 4 terrace double rooms.
- 1 triple room.
- 1 separate studio with kitchen.

This matches the current operating brief and the simplified live-site structure. Booking.com currently exposes additional or duplicated room labels; the channel inventory must be reconciled before production copy is locked.

## Public facilities supported by current sources

- Seasonal outdoor pool.
- Restaurant and bar.
- Continental breakfast.
- Terraces and outdoor dining.
- Tennis and nearby walking/cycling.
- Address: Carrer Rincón del Silencio, 3, 03759 Benidoleig, Alicante.
- Tourism licence displayed by Booking.com: `CV H01453 A`.

## Wabi-Sabi positioning

Use the working formula: Mediterranean produce + fire + time/fermentation + slow hospitality.

Do not publish fixed opening hours, guaranteed menus, event capacity or fixed meal inclusions until operations confirms them.

## Asset policy

The review page temporarily uses the property's current Booking.com image CDN references to ensure EL CID-specific imagery rather than AUMARA imagery. Before production:

1. locate the original property-owned files;
2. copy approved originals to an owned Drive/CDN folder;
3. create responsive WebP/AVIF variants;
4. record source, owner approval and alt text;
5. remove all Booking CDN hotlinks.

The header uses a typographic monogram, not a fabricated official logo. Replace it only after the official EL CID logo asset is confirmed.

## Booking and conversion

- Review CTA: current Booking.com property page plus direct email and telephone.
- Do not claim a working direct Beds24 hotel booking route until the EL CID Beds24/Booking mapping and a complete reservation → modification → cancellation test pass.

## Production blockers

- [ ] Official logo and brandbook located and approved.
- [ ] EL CID image originals moved to owned hosting.
- [ ] Booking/Beds24 room mapping reconciled.
- [ ] Direct booking CTA tested end to end.
- [ ] ES/EN copy reviewed against current operations.
- [ ] Restaurant service wording confirmed.
- [ ] Legal/privacy/cookie text reviewed by the responsible professional.
- [ ] Mobile and desktop screenshots approved by Ilya.
- [ ] `robots` changed from `noindex,nofollow` only at approved production release.
