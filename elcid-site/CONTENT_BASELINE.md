# EL CID Country Club — website content baseline v0.2

Status: review-only. Do not deploy or merge to production without Ilya's explicit approval.

## Product separation

- EL CID Country Club is the country hotel / restaurant / shared-facility product.
- AUMARA is a separate private-house accommodation product at `/aumara/`.
- The root page must not use AUMARA houses, AUMARA brand images or AUMARA copy as the main EL CID identity.

## Working public inventory

- 4 terrace double/twin rooms.
- 1 triple room.
- 1 separate studio with kitchen.

This matches the current operating brief and simplified live-site structure. Booking.com currently exposes additional or duplicated room labels; channel inventory must be reconciled before production copy is locked.

## Public facilities supported by the current Booking listing

- Seasonal outdoor pool.
- Restaurant and bar.
- Continental breakfast.
- Terraces / outdoor dining.
- Tennis, darts and nearby walking/cycling.
- Address: C/Rincón del Silencio, 3, 03759 Benidoleig, Alicante.
- Tourism licence displayed by Booking.com: CV H01453 A.

## Wabi-Sabi positioning

Use the working formula: Mediterranean produce + fire + time/fermentation + slow hospitality.
Do not publish fixed opening hours, guaranteed menus, event capacity or fixed meal inclusions until operations confirms them.

## Assets

- The official green EL CID Country Club logo supplied by Ilya is used in the review header and footer. The review embeds a transparent optimized WebP derivative of the supplied PNG.
- Property-owned EL CID originals were recovered from Google Drive as `File_000.png`–`File_012.png`.
- Booking CDN image hotlinks have been removed from the review build.
- The review references the recovered Drive originals. Before production, copy approved optimized WebP/AVIF variants to the final owned hosting or CDN path.

### Recovered image mapping

- Hero / pool / façade: Drive `File_000.png`.
- Double room: Drive `File_006.png`.
- Larger / triple room working image: Drive `File_011.png`.
- Studio context card: Drive `File_005.png` — terrace only; the copy does not claim the image shows the kitchen.
- Breakfast / dining by pool: Drive `File_010.png`.
- Dedicated studio kitchen photograph: not present in the recovered series and remains an optional content gap.

## Booking and conversion

- Review CTA: current Booking.com property page plus direct email and telephone.
- Do not claim a working direct Beds24 hotel booking route until the EL CID Beds24/Booking mapping and a complete reservation–modification–cancellation test pass.

## Production blockers

- [x] Official logo supplied and integrated.
- [x] EL CID image originals recovered from Drive.
- [x] Booking CDN image hotlinks removed from the review build.
- [ ] Final production image/CDN path selected and optimized variants uploaded.
- [ ] Booking/Beds24 room mapping reconciled.
- [ ] Direct booking CTA tested end to end.
- [ ] ES/EN copy reviewed against current operations.
- [ ] Restaurant service wording confirmed.
- [ ] Legal/privacy/cookie text reviewed by the responsible professional.
- [ ] Mobile and desktop screenshots approved by Ilya.
- [ ] `robots` changed from `noindex,nofollow` only at approved production release.
