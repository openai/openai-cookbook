# AUMARA WEB — source of truth

Updated: 2026-07-12
Owner / final approval: Ilya Doroshenko
Repository: `elcidspain/openai-cookbook`

## Reset decision

The compressed v3 landing-page direction is dismissed.

Return to the first interactive concept:

- Source file: `aumara-site/prototype-v01.html`
- Preview URL: `https://elcidspain.github.io/openai-cookbook/prototype-v01.html`
- The old v3 preview URL now redirects to this file.
- Production is not switched automatically.

## Core product idea

The website is not a short brochure with one clipped video.

It is an interactive digital visit to AUMARA:

1. See the territory as a map.
2. Tap a point or house.
3. Open the real view, short route clip, house facts and booking path for that point.
4. Move point-to-point through the property.
5. Expand from the exterior route into each house, terrace, interior and view.

The uploaded full walkthrough is source material for route nodes, not a single decorative hero video.

## Visual baseline

Keep the first version's editorial direction:

- atmospheric full-screen opening
- large typography
- cream editorial sections
- dark forest / warm gold palette
- interactive territory as the main product feature
- category cards and booking as supporting layers

Do not reduce the site to a short generic hospitality landing page.

## Approved wording to preserve for later integration

English:

> Some places give you more.  
> AUMARA gives you back to yourself.

Spanish:

> Hay lugares que te dan más.  
> En AUMARA, vuelves a encontrarte contigo mismo.

The wording may be integrated into the first-version structure after the map and route logic are working.

## Verified factual baseline

- 6 physical houses on site
- 5 currently bookable
- 3 Chalet
- 2 Superior Chalet
- Direct booking CTA: `https://beds24.com/booking2.php?propid=324882`
- Do not guess which exact numbered unit is unavailable when that fact is not verified.
- Use real AUMARA media.

## Work order

### Stage 1 — Territory map

Replace abstract road geometry with the cleaned real site plan. Preserve six clickable locations and make the plan usable on iPhone.

### Stage 2 — Route nodes

Cut the full walkthrough into point-specific clips:

- arrival / first reveal
- upper path
- red house approach
- green house approach
- central crossing
- valley viewpoint
- lower route
- final house / end of route

Each node must have a still poster, a short clip, next/previous route controls and a link back to the map.

### Stage 3 — House layers

For each house or category:

- exterior
- entrance
- interior sequence
- terrace / view
- capacity and factual description
- availability / Beds24

### Stage 4 — Expanded virtual visit

Create a point-to-point tour interface. It can feel like moving through the property, but must not pretend to be a true 360° capture when the source is ordinary phone video.

## Roles

### ChatGPT / AI Ops

- Maintain the GitHub implementation.
- Build map, hotspots, route nodes and media integration.
- Keep changes reversible.
- Verify facts and links.

### Claude

Claude review work is paused for now. No parallel prototype work and no independent redesign.

### Ilya

Approves visual direction and production switch.
