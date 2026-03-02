# Colppy Customer Success — Instructions

## Tool Usage Hierarchy

This plugin bundles the `intercom-research` MCP server with curated tools. Always prefer higher-level tools over raw API calls.

### For customer feedback research

Use the **plugin's bundled MCP tools** — they handle pagination, filtering, and formatting:

| Tool | When to use |
|------|-------------|
| `scan_customer_feedback` | Scan conversations by topic keywords (first message only, fast) |
| `scan_full_text` | Scan all messages including replies (slower, for topics in agent responses) |
| `get_conversation_feedback` | Deep-dive into specific conversations by ID |
| `analyze_onboarding_first_invoice` | Onboarding analysis segmented by user type |

**Do NOT** use raw Intercom API tools (`search_conversations`, `get_conversation`, `list_conversations`) to manually fetch and analyze conversations. These are low-level building blocks — the plugin tools above already wrap them with proper filtering, team inbox support, and output formatting.

### For onboarding / classification analysis

Use the **scripts**, not manual conversation-by-conversation analysis:

```bash
# Segmented onboarding analysis (recommended)
python tools/scripts/intercom/analyze_onboarding.py \
  --cache <cache_path> --user-type smb --llm

# Direct LLM classification
cd plugins/colppy-customer-success
node scripts/llm_classify.mjs \
  --cache <cache_path> --topic <topic.json> --all
```

**Do NOT** manually read conversations one-by-one and classify them yourself. The LLM classifier (`llm_classify.mjs`) handles this at scale with few-shot learning.

### For exporting conversation data

Use the **export script** to create a local cache:

```bash
cd tools/scripts/intercom
node export_cache_for_local_scan.mjs --from YYYY-MM-DD --to YYYY-MM-DD --team 2334166
```

**Do NOT** export conversations by calling `export_intercom_conversations` or `search_conversations` repeatedly. The export script handles pagination, contact attribute enrichment (`es_contador`, `rol_wizard`), and saves to the correct cache location.

## Cached Data

Check for existing cached data before making API calls:

- `skills/intercom-developer-api-research/cache/conversations_*.json` — exported conversation caches by date range
- `skills/intercom-onboarding-setup/cache/` — classification reports and results

## Classification Improvement

To improve classification accuracy, use the review feedback loop — not manual re-classification:

1. Run with `--review /tmp/review.json` to generate a review file
2. Edit the review JSON (set `correct`, `override_category`, `promote_to_example`)
3. Run `--apply-review /tmp/review.json` to update the topic config's few-shot examples

See `skills/intercom-onboarding-setup/README.md` for the full workflow.

## Data Source Restrictions

- **Customer feedback**: Use ONLY Intercom. Do NOT pull from Slack, HubSpot, Atlassian, or other sources.
- **User segmentation**: The `contact_es_contador` field in cached data determines accountant vs SMB. Falls back to HubSpot API lookup by email if missing.
