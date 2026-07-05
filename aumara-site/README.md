# AUMARA Landing

Public, mobile-first landing page for the AUMARA accommodation project in Benidoleig, Costa Blanca.

## Business identity

- Public brand: **AUMARA**
- Legal operator: **EL CID VENTURES BENIDOLEIG S.L.**
- CIF: **B53816989**
- External booking and payment channel: **Booking.com**

The landing must keep the brand, legal operator and booking channel separate and visible.

## Current inventory

- 6 physical houses on site
- 5 currently bookable for short stays
- 3 Chalet
- 2 Superior Chalet
- 1 house temporarily outside the short-stay inventory

## Source

`index.html` is a self-contained static page with inline CSS and JavaScript.

Current source images are served from the approved AUMARA Google Drive photo library through public Googleusercontent URLs.

## Production target

`https://elcidspain.com/aumara`

Do not use the production URL in Google Ads until it returns HTTP 200 and all release checks pass.

## Release checklist

- [ ] GitHub Pages or the production host serves the latest `index.html`.
- [ ] The owned AUMARA route returns HTTP 200 without a redirect loop.
- [ ] Mobile and desktop rendering are checked.
- [ ] Every image loads.
- [ ] Booking.com direct CTA opens the AUMARA listing.
- [ ] Date search passes check-in, check-out, adults and children.
- [ ] Email and telephone links work.
- [ ] No login, bot challenge or geo-block blocks the page.
- [ ] Search and ads crawlers can access the rendered content.
- [ ] AUMARA, the legal operator, CIF and contact details are visible.
- [ ] Google Ads Final URL is changed only after QA.
- [ ] Spend stays paused until the repaired ad is Eligible and a test budget is approved.

## Tracking events

The static page pushes these events into `window.dataLayer`:

- `booking_click`
- `booking_search`
- `email_click`
- `phone_click`

A Google tag can be connected later without changing the event names.
