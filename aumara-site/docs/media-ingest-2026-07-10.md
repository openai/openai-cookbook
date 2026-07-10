# AUMARA media ingest — 2026-07-10

## Source
Google Drive folder: `AUMARA Web/00_INBOX_RAW`

## Current inventory
24 uploaded files representing 9 unique filenames:

- IMG_7694.MOV
- IMG_7695.MOV
- IMG_7696.MOV
- IMG_7697.MOV
- IMG_7698.MOV
- IMG_7699.MOV
- IMG_7700.MOV
- IMG_7701.MOV
- 2958d80ec1dcc1666b5170f5a2595c7f.mp4

The MOV uploads are exact triplicates by filename and byte size. Source files are preserved. The working inventory will use one canonical copy of each unique filename.

## First visual review

### IMG_7694.MOV
- Vertical 1080×1920
- ~60 fps
- ~14.0 s
- Exterior guided movement along paths and steps
- Useful for arrival/circulation continuity
- Strong sun flare in several moments

### IMG_7695.MOV
- Vertical 1080×1920
- ~60 fps
- ~8.9 s
- Clearest current house-scale reveal
- Shows façade, panoramic glazing, landscaping and adjacent units
- Strong candidate for a mobile hero cut or house-introduction sequence

### IMG_7697.MOV
- Vertical 1080×1920
- ~60 fps
- ~23.2 s
- Useful for spatial orientation and movement between houses
- Strong backlight in parts
- Better suited to a guided territory sequence than a clean hero

## Next production steps

1. Review one canonical copy of every unique file.
2. Build a media manifest with duration, orientation, technical quality, subject, usable timecodes and recommended placement.
3. Define the first site sequence: arrival → territory → house reveal → movement between units → booking CTA.
4. Identify missing material: interiors, bedrooms, bathrooms, terraces, panoramic windows, pool, EL CID/food, evening/night, human scale and 360 capture points.
5. Replace the current static-first hero in `aumara-site/index.html` with a mobile-safe video hero and poster fallback.
6. Add an interactive property map and house-specific media slots.
7. Keep Booking.com as fallback until Beds24 direct booking passes the complete test flow.

## Constraints

- Production URL remains `https://elcidspain.com/aumara/`.
- Public claims must be backed by real footage and verified operating data.
- Preserve canonical metadata, structured data, legal operator identity and mobile performance.
- Do not delete source files without explicit approval.
