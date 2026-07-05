# AUMARA Visual Production Pipeline

This folder turns the AUMARA image workflow into a versioned, reviewable production system.

GitHub does not generate images by itself. It stores the prompts, scripts, workflow history and reviewable outputs. Image generation is performed by the OpenAI API when the manual GitHub Action runs.

## What this pipeline is for

- website concept mockups;
- day / dawn / sunset / night edits of real AUMARA photographs;
- retreat and private-gathering storyboard frames;
- social and ad concept variants;
- reproducible prompt and output manifests.

## Source-of-truth rule

Generated-from-scratch images are concept art only and must never be presented as documentary photography of the existing property.

Customer-facing property imagery should start from an approved real photograph and use `mode: edit` prompts that explicitly preserve:

- architecture;
- house count and location;
- paths and terrain;
- vegetation and objects;
- camera angle and crop.

## Folder layout

```text
aumara-site/
  creative/
    prompts.json
    input_images/
      hero_base.jpg
    output_images/
      manifest.json
      *.png
  scripts/
    generate_visual_pack.py
```

Large originals and video masters should remain in the controlled Drive content library. Only approved web derivatives or temporary Action artifacts should be used in GitHub.

## Local use

```bash
python -m pip install openai
export OPENAI_API_KEY="..."
python aumara-site/scripts/generate_visual_pack.py --pack concept
python aumara-site/scripts/generate_visual_pack.py --pack dayparts --quality high
```

Run one prompt only:

```bash
python aumara-site/scripts/generate_visual_pack.py \
  --pack dayparts \
  --only hero_dawn_edit
```

## GitHub Actions use

1. In repository settings, create an Actions secret named `OPENAI_API_KEY`.
2. Open **Actions → AUMARA Visual Pack**.
3. Choose **Run workflow**.
4. Select a pack and quality.
5. Download the generated `aumara-visual-pack` artifact.
6. Review outputs manually before moving any asset into the live site.

The workflow is manual only. It does not run on every commit and does not automatically publish generated assets.

## Packs

- `concept` — interface and narrative concepts; no factual property claim.
- `dayparts` — surgical edits of `creative/input_images/hero_base.jpg`.
- `marketing` — editorial concepts for social, private gatherings and campaign ideation.
- `all` — every configured job.

## Prompt standard

Every prompt follows the production structure:

1. purpose;
2. scene or requested change;
3. exact elements to preserve;
4. style / quality cues;
5. exclusions and factual guardrails.

Use small single-change iterations rather than rewriting the entire image direction after every result.

## Review gate

No generated asset goes live until it passes:

- factual-property review;
- brand review;
- visible-text review;
- geometry and object-placement review;
- mobile crop review;
- Google Ads policy review when used in advertising.
