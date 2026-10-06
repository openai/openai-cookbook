# Space icon assets

[james-finance.webp](james-finance.webp) and [nora-town-square.webp](nora-town-square.webp) were generated with the app's image-generation pipeline and normalized to 256 × 256 WebP. James uses a rising financial chart; Nora uses a conversational composition. Both use a black background with green and violet dimensional artwork.

The shared generation prompt is `devDayIconInstructions` in [server/devday-theme.mjs](../../server/devday-theme.mjs), with persona context assembled by [server/space-icons.mjs](../../server/space-icons.mjs). The adapter in [server/space-icon-image.mjs](../../server/space-icon-image.mjs) requests one square image and normalizes it for circular presentation. The same direction applies to newly generated world icons.

Nora's icon is bundled with her editable message-board example so a fresh setup works without an image-generation call. James's icon is installed by `npm run prepare-arcade`, which requires the local server to be stopped. Existing saved icons are replaced only through explicit upload, regeneration, or installation.

The eight `light/*.webp` assets are alternate light-mode versions of the prepared demo icons. Each was generated using its corresponding dark icon as an edit reference, preserving the subject and dimensional green and purple materials while introducing a light studio background and lighting. The prompts are stored beside the assets as `light/*.prompt.txt`. Outputs were normalized to 256 × 256 WebP. The original dark reference icons for all eight variants are not bundled; most world icons are generated locally when a page is built.

The server advertises a light variant only when the current icon's image bytes match the corresponding original recorded in [server/demo-appearance.mjs](../../server/demo-appearance.mjs). An upload or new generation remains authoritative. Both variants load together and CSS selects the appropriate one in the login chooser, account controls, community graph, and person list. A theme toggle does not make an image-generation request.
