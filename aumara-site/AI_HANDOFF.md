# AUMARA WEB — source of truth

Updated: 2026-07-14
Owner / final approval: Ilya Doroshenko
Repository: `elcidspain/openai-cookbook`

## Reset decision

The compressed v3 landing-page direction is dismissed.

Return to the original AUMARA foundation as the visual and structural baseline:

- Production baseline file: `aumara-site/index.html`
- Production baseline preview: `https://elcidspain.github.io/openai-cookbook/`
- Reconciled review file: `aumara-site/direct-v3-preview.html`
- Reconciled preview URL after merge: `https://elcidspain.github.io/openai-cookbook/direct-v3-preview.html`
- Verified copy and facts: `aumara-site/CONTENT_BASELINE.md`
- Recovery snapshot of the current live page: `aumara-site/snapshots/live-2026-07-14/`
- Production is not switched automatically.

The first interactive map prototype remains useful only as a feature source:

- Map prototype: `aumara-site/prototype-v01.html`

Do not replace the original site with the map prototype. Integrate the map and route logic into the original visual system.

## Core product idea

The website is not a short brochure with one clipped video.

It is an interactive digital visit to AUMARA:

1. Emotional full-screen arrival.
2. Clear facts and two house types.
3. Interactive territory map.
4. Tap a location or house.
5. Open the real view, short route clip, house facts and booking path.
6. Move point-to-point through the property.
7. Expand from exterior route into each house, terrace, interior and view.

The uploaded full walkthrough is source material for route nodes, not a single decorative hero video.

## Visual baseline

Keep the original version's direction:

- immersive full-screen hero
- large editorial typography
- dark forest / warm gold / cream palette
- real AUMARA imagery
- Dawn / Day / Sunset / Night logic
- rich page depth, not a compressed brochure
- booking visible but not allowed to flatten the experience

The screenshot approved by Ilya is the visual reference for the opening experience: atmospheric hero, strong editorial hierarchy, rounded controls, warm cream cards and a premium mobile rhythm.

## Approved wording to integrate into the original structure

English:

> Some places give you more.  
> AUMARA gives you back to yourself.

Spanish:

> Hay lugares que te dan más.  
> En AUMARA, vuelves a encontrarte contigo mismo.

## Verified factual baseline

- 6 physical houses on site
- 5 currently bookable
- 3 Chalet
- 2 Superior Chalet
- Direct booking CTA: `https://beds24.com/booking2.php?propid=324882`
- Do not guess which exact numbered unit is unavailable when that fact is not verified.
- Use real AUMARA media.
- Production deployment workflow refreshed after FTP account verification.

## Build order

### Stage 1 — Preserve and restore the original page

Work from `aumara-site/index.html`. Do not redesign from scratch and do not shorten it into v3.

### Stage 2 — Territory map

Take the interaction model from `prototype-v01.html`, replace abstract geometry with the cleaned real site plan, and embed it into the original page.

Map points:

- arrival
- parking
- 3 Chalet locations
- 2 Superior Chalet locations
- sixth physical house / non-bookable status only if factually clear
- pool
- EL CID / restaurant
- viewpoint / nature route

Each point opens a real image or clip, factual text and the next action.

### Stage 3 — Route nodes from the full walkthrough

Cut the full video into route-specific clips:

- arrival / first reveal
- upper path
- red house approach
- green house approach
- central crossing
- valley viewpoint
- lower route
- final house / end of route

Each node has:

- poster frame
- short clip
- previous / next controls
- return to map
- linked house or place section

### Stage 4 — House layers

For each house type:

- exterior
- entrance
- interior sequence
- terrace / view
- layout / dimensions where verified
- capacity and factual description
- availability / Beds24

### Stage 5 — Expanded virtual visit

Create a point-to-point tour that feels like moving through the property. Do not claim true 360° until actual 360° source material exists.

## Roles

### ChatGPT / AI Ops

- Maintain GitHub implementation.
- Preserve the original visual baseline.
- Build map, hotspots, route nodes and media integration.
- Keep changes reversible.
- Verify facts and links.

### Claude

Parallel redesign work is paused. Claude may review only after the restored original plus map module is visible.

### Ilya

Approves visual direction and production switch.
