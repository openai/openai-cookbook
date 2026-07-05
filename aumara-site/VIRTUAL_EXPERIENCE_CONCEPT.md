# AUMARA + EL CID — Virtual Experience Concept

## Strategic decision

Do not buy Nominalia SiteBuilder, ShopBuilder, one-page design, VPS, SSL, email or social-media products for the current launch. The existing stack already covers domain, hosting, WordPress and the AUMARA static landing page. The useful Nominalia products are limited to compliance and security/maintenance, and only after the current package contents are verified.

## Experience architecture

Create two coordinated experiences on the same owned domain:

- `/aumara/` — nature, private chalets, dawn, sunset, night sky, birds, wind and silence.
- `/el-cid/` — country club, hotel, restaurant, pool, terraces, events and hospitality.

Each experience should remain fast, indexable and bookable. The sensory layer must enhance conversion rather than turn the site into a heavy game.

## AUMARA experience

### Hero mode

- Background automatically follows local Benidoleig time: dawn, day, sunset and night.
- Manual mode selector: `Dawn · Day · Sunset · Night`.
- Use real AUMARA photographs whenever available.
- Add gentle cross-fades instead of heavy 3D rendering.

### Ambient sound

- Sound is always off by default.
- A visible button enables an authentic 20–40 second loop of birds, wind and evening insects recorded on site.
- Never autoplay sound.
- Keep the file compressed and locally hosted.

### Lightweight movement

- Slow image parallax.
- Small changes in light and sky temperature.
- Optional short cinemagraph or 8–12 second silent loop.
- Respect `prefers-reduced-motion`.

### Conversion layer

The booking interface remains visible and simple during every mode:

- Check availability.
- View Chalet.
- View Superior Chalet.
- Open Booking.com.
- Call or email the property.

## EL CID experience

### Story sequence

- Arrival through the entrance.
- Hotel rooms and terraces.
- Pool and gardens.
- Wabi-Sabi restaurant.
- Sunset dinner / evening atmosphere.
- AUMARA as a separate accommodation experience within the destination.

### Dynamic modes

- Morning: breakfast and quiet property atmosphere.
- Afternoon: pool, mountain light, lunches and arrivals.
- Evening: restaurant, terrace and events.

## Technical implementation

### Phase 1 — now

- Static HTML/CSS/JS on the existing Nominalia hosting.
- Responsive images and WebP.
- Time-based hero image selection using JavaScript.
- Manual time-of-day selector.
- Optional audio button.
- No new CMS, no VPS, no SiteBuilder.

### Phase 2

- Local media library under `/assets/`.
- Two or three authentic ambient audio loops.
- Short real video loops.
- Analytics events for mode selection, audio activation and booking clicks.
- Spanish and English versions.

### Phase 3

- Interactive property map.
- House-level galleries and availability.
- Beds24 booking engine integration when stable.
- Event, retreat and restaurant modules.

## Asset status

Current Drive assets found:

- `AUMARA Fotos AI Edited` — approved edited photo folder.
- No AUMARA-titled video files were found in Drive at the time of review.
- No audio files were found in Drive at the time of review.

Therefore the first release should use photos and CSS transitions. Authentic audio and short video should be recorded on location rather than generated as fake ambience.

## Nominalia product decision

### Do not buy now

- WordPress Start / Managed WordPress Start — duplicate hosting until the current package is audited.
- Advanced Multidomain Hosting — unnecessary for two routes on one domain.
- SiteBuilder — locks the project into a second builder.
- ShopBuilder — not an e-commerce requirement.
- Website for €145 — weaker than the custom site already built.
- Extra email — existing domain mail must be audited first.
- Positive SSL — verify the SSL already bundled with the current Domain Pack.
- VPS and Server Management — excessive for the present traffic and architecture.
- Social Media Hub / Metricool offer — evaluate only after checking the current content workflow; do not duplicate existing Meta, Threads and Airtable workflows.

### Potentially useful after audit

- GDPR Essential / iubenda for cookie consent and privacy documents.
- WordPress Maintenance or Managed WordPress only if Nominalia can take over and clean the existing legacy installation under a clear SLA.
- Acronis backup only if the current hosting has no adequate daily backup and export path.

## Partner programme decision

The Nominalia Partner programme is not a benefit for buying our own services. It is a sales channel for recommending or reselling Nominalia products to third parties:

- Prescriber: referral code and commission.
- Affiliate: commission through tracked links, usually via Awin.
- Reseller: white-label panel and volume discounts.

For AUMARA/EL CID operations it is not strategically relevant now. It may become relevant later to AUMARA Feasibility Desk if the team packages domains, hosting and website delivery for external clients. Until that product exists, do not add Nominalia affiliate banners to hospitality websites.
