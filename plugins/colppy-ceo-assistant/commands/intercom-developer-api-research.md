---
name: intercom-developer-api-research
description: Find Intercom conversations about Colppy API integrations, developers, and technical integrations. Uses curated keywords and negative filters. Editable config for learning.
---

# Intercom Developer / API Research

Find conversations where developers or integrators are working with the Colppy API.

## Definition

**Developer/API conversations** are those where someone is integrating Colppy with another system: e‑commerce, ERP, Invoicing, logistics, payment gateways, manufacturing, debugging API calls, asking about endpoints, authentication, or webhooks.

## Data Source Restriction

**Use ONLY Intercom MCP tools.** Do NOT call Slack, Atlassian, HubSpot, or any other MCP.

## Steps

1. **Load keywords** from `skills/intercom-developer-api-research/keywords.json`:
   - Read the file and use `keywords` array
   - Use `exclude_if_only` for the negative filter

2. **Call** `scan_full_text` with:
   - `topic`: "Colppy API integration"
   - `keywords`: from config (all values from the keywords array)
   - `exclude_if_only`: `["colppy.com", "request", "rest"]` (or from config)
   - `from_date`, `to_date`: last 5–7 days if not specified
   - `confirm_large_scan`: true if range > 500 conversations

3. **Summarize results**:
   - Report `matches_found` and `matches_excluded_by_filter` (if present)
   - Highlight true developer/API conversations (Producteca, API-17, frontera, service.php, etc.)
   - Separate noise (email signatures, rating prompts) from signal

4. **Optional deep dive**: Use `get_conversation_feedback` for the most relevant conversation IDs.

## Output Rules

- Present results directly in the chat — do not create files
- Include clickable Intercom URLs for referenced conversations
- If zero matches, suggest adding keywords to `keywords.json` and retrying

## Learning: Edit keywords.json

To improve discovery over time:
- **Add** keywords when you find new terms developers use
- **Remove** keywords that cause too much noise
- **Update** `exclude_if_only` to filter more false positives

Restart Cursor to pick up config changes.

---

## Local Iteration (No API Calls)

To iterate on keywords without re-fetching Intercom:

1. **First scan** — Call `scan_full_text` with `save_cache`:
   - `save_cache`: `"skills/intercom-developer-api-research/cache/conversations_YYYY-MM-DD.json"`

2. **Edit** `keywords.json`, then run locally:
   ```bash
   cd plugins/colppy-ceo-assistant
   node scripts/local_scan.mjs --cache skills/intercom-developer-api-research/cache/conversations_YYYY-MM-DD.json
   ```
   Add `--output results.json` to save output to a file.
