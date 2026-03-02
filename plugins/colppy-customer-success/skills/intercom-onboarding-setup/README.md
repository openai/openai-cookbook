# Setup / Onboarding Intercom Research

Classify Intercom conversations about setup and onboarding topics to identify the most typical issues during user onboarding, segmented by user type (accountant vs SMB).

## Topic configs

| File | Purpose | Categories |
|------|---------|------------|
| `topic.json` | Broad onboarding/setup classification | account_registration, company_setup, iva_afip_config, first_configuration, how_to_get_started, plan_selection, invite_users, first_bank_connection, navigation_help, trial_questions, other |
| `topic_first_invoice.json` | First-time-to-value (first invoice) | factura_electronica_config, talonario_punto_venta, no_puedo_facturar, emitir_primera_factura, delegacion_afip, other |

## Run classification

### Option 1: Segmented analysis with `analyze_onboarding.py` (recommended)

Segments by user type (accountant/smb) and runs LLM classification:

```bash
# First invoice analysis — accountant vs SMB
python tools/scripts/intercom/analyze_onboarding.py \
  --cache plugins/colppy-customer-success/skills/intercom-developer-api-research/cache/conversations_YYYY-MM-DD_YYYY-MM-DD_team2334166.json \
  --user-type accountant --llm

python tools/scripts/intercom/analyze_onboarding.py \
  --cache plugins/colppy-customer-success/skills/intercom-developer-api-research/cache/conversations_YYYY-MM-DD_YYYY-MM-DD_team2334166.json \
  --user-type smb --llm

# Broader onboarding topics — accountant vs SMB
python tools/scripts/intercom/analyze_onboarding.py \
  --cache plugins/colppy-customer-success/skills/intercom-developer-api-research/cache/conversations_YYYY-MM-DD_YYYY-MM-DD_team2334166.json \
  --user-type accountant --llm \
  --topic plugins/colppy-customer-success/skills/intercom-onboarding-setup/topic.json

python tools/scripts/intercom/analyze_onboarding.py \
  --cache plugins/colppy-customer-success/skills/intercom-developer-api-research/cache/conversations_YYYY-MM-DD_YYYY-MM-DD_team2334166.json \
  --user-type smb --llm \
  --topic plugins/colppy-customer-success/skills/intercom-onboarding-setup/topic.json
```

### Option 2: Direct `llm_classify.mjs` (no user type segmentation)

```bash
cd plugins/colppy-customer-success

node scripts/llm_classify.mjs \
  --cache skills/intercom-developer-api-research/cache/conversations_YYYY-MM-DD_YYYY-MM-DD.json \
  --topic skills/intercom-onboarding-setup/topic.json \
  --all \
  --output skills/intercom-onboarding-setup/cache/llm_onboarding_classified.json \
  --report skills/intercom-onboarding-setup/cache/onboarding_report.md
```

Use a smaller cache (e.g. 1-week range) to avoid OpenAI rate limits. Concurrency is 10 by default.

## MCP tool

The `analyze_onboarding_first_invoice` MCP tool wraps `analyze_onboarding.py`. Parameters:
- `cache_path` (required): path to Intercom cache JSON
- `user_type`: `accountant`, `smb`, or `all` (default: `accountant`)
- `use_llm`: run LLM classifier (default: false)
- `topic`: topic config JSON path (default: `topic_first_invoice.json`)

## Exporting cache data

```bash
# Export Primeros 90 días inbox conversations with contact details
cd tools/scripts/intercom
node export_cache_for_local_scan.mjs --from YYYY-MM-DD --to YYYY-MM-DD --team 2334166
```

This fetches `contact_es_contador` and `contact_rol_wizard` from Intercom contact custom attributes (synced from HubSpot). When cache lacks this data, `analyze_onboarding.py` falls back to HubSpot API lookup by email.

## Improving classification accuracy (review & training loop)

The classifier uses few-shot examples stored in topic config JSON files (`topic.json`, `topic_first_invoice.json`). You can improve accuracy over time by reviewing results, correcting mistakes, and promoting good examples back into the config.

### Step 1: Run classification with `--review`

Generate a review JSON file alongside the normal classification:

```bash
cd plugins/colppy-customer-success

node scripts/llm_classify.mjs \
  --cache skills/intercom-developer-api-research/cache/conversations_2026-01-01_2026-01-31_team2334166.json \
  --topic skills/intercom-onboarding-setup/topic_first_invoice.json \
  --all \
  --review /tmp/review_smb_ftv.json
```

The review file contains one entry per conversation with:

- `conversation_id` — Intercom conversation ID
- `snippet` — first 500 characters of the conversation
- `llm_result` — the LLM's classification (`is_first_invoice`, `category`, `confidence`, `reasoning`)
- `correct` — `null` (pending review)
- `override_category` — `null` (set this if the LLM picked the wrong category)
- `override_match` — `null` (optional boolean to override the match field when `correct=false`)
- `promote_to_example` — `false` (set to `true` to use as a few-shot example)

### Step 2: Review and correct

Open the review JSON and for each entry:

1. **Set `correct`** to `true` or `false` — does the LLM classification agree with your judgment?
2. **Set `override_category`** (optional) — if the LLM got the category wrong, set the right one
3. **Set `override_match`** (optional) — use this when a corrected example should explicitly switch match true/false
4. **Set `promote_to_example: true`** (optional) — for conversations that are good teaching examples, especially:
   - False negatives the model should learn to catch
   - Tricky edge cases (e.g. conversation starts with scheduling but is actually about FCE setup)
   - Clear false positives the model should learn to reject

### Step 3: Apply corrections

Feed the reviewed file back to update the topic config:

```bash
node scripts/llm_classify.mjs \
  --apply-review /tmp/review_smb_ftv.json \
  --topic skills/intercom-onboarding-setup/topic_first_invoice.json
```

This will:

- Append promoted conversations to the `few_shot_examples` array in the topic config
- Report accuracy metrics: agreement rate, correction rate by category

### Step 4: Re-run and compare

Run the same classification again. The updated few-shot examples are now part of the prompt, so the model should handle similar cases better:

```bash
# Same command as Step 1 — the topic config now includes the new examples
node scripts/llm_classify.mjs \
  --cache skills/intercom-developer-api-research/cache/conversations_2026-01-01_2026-01-31_team2334166.json \
  --topic skills/intercom-onboarding-setup/topic_first_invoice.json \
  --all
```

### How few-shot examples work

The topic config JSON has a `few_shot_examples` array. Each example contains:

- `conversation_snippet` — a representative excerpt from the conversation
- `classification` — the correct classification with reasoning

When `llm_classify.mjs` builds the prompt, it injects these examples between the topic definition and the actual conversation to classify. This gives the LLM concrete reference points for ambiguous cases.

**Guidelines for good few-shot examples:**

- Include at least 1 false positive (teaches the model what to reject)
- Include edge cases where the snippet alone is misleading (e.g. scheduling → FCE setup)
- Keep snippets concise — capture the signal, not the full conversation
- 4-6 examples per topic is a good range; more can dilute the signal

## Filtering by first login (future)

To restrict to users in their first days/weeks in Colppy:

1. Export from Mixpanel: users with first "Login" event in date range.
2. Join by email with Intercom contact/conversation.
3. Filter the conversation cache to only those contacts before running classification.

The Intercom cache does not include Colppy first-login dates; that data lives in Mixpanel.
