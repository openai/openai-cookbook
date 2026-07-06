# Nominalia Deployment

Date: 2026-07-06
Status: Execution

## Objective
Publish the approved AUMARA v03 static site on the owned domain after the Nominalia hosting payment.

## Release candidate
- Source: `aumara-site/index.html`
- Production target: `https://elcidspain.com/aumara/`
- Primary reservation route: Booking.com

## Sequence
1. Confirm the paid hosting service is active.
2. Identify the production web root and the `/aumara/` directory.
3. Preserve the current web files before replacement.
4. Upload the contents of `aumara-site` to the production directory.
5. Confirm HTTPS and the canonical production URL.
6. Test desktop and mobile rendering.
7. Test every image, navigation link, Booking button, email link and telephone link.
8. Confirm the page does not collect payment-card data.
9. Confirm title, description, canonical metadata and operator disclosure.
10. Record the production URL and test evidence in Airtable.

## Acceptance
- Production URL returns the AUMARA v03 page.
- No broken images or links.
- Booking.com remains the primary transactional channel.
- Mobile layout passes.
- GitHub remains the versioned source of truth.
