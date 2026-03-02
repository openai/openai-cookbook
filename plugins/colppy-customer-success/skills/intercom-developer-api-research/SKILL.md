---
name: intercom-developer-api-research
description: Find Intercom conversations about Colppy API integrations, developers, and technical integrations. Use when the user asks about developer feedback, API usage, integrations (e‑commerce, ERP, payment gateways), or technical support conversations.
---

# Intercom Developer / API Research

Find and analyze Intercom conversations where developers or integrators are working with the Colppy API.

## Definition

**Developer/API conversations** are those where someone is integrating Colppy with another system: e‑commerce, ERP, Invoicing, logistics, payment gateways, manufacturing, debugging API calls, asking about endpoints, authentication, or webhooks.

---

## Keyword Config (Editable)

Keywords are loaded from `keywords.json` in this skill folder. **Add or remove keywords** to improve discovery over time.

| Category | Examples |
|----------|----------|
| **Spanish** | conectar, conexión, integrador, programar, código, endpoint, webhook, token, autenticación, documentación API, Frontera, restfull |
| **Technical** | POST, GET, JSON, XML, API key, error 500, timeout, request, response |
| **Roles** | desarrollador, programador, integrador, developer |
| **Tools** | Producteca, Tiendanube, WooCommerce, Mercado Pago, Mercado Libre |

**Negative filter:** Matches that *only* contain `colppy.com`, `request`, or `rest` are excluded (email signatures, rating prompts, false positives like "resto").

---

## Workflow

1. **Load keywords** from `keywords.json` (or use the default set in this skill).
2. **Call** `scan_full_text` with:
   - `topic`: "Colppy API integration"
   - `keywords`: from config
   - `exclude_if_only`: `["colppy.com", "request", "rest"]`
   - `from_date`, `to_date`: user-specified or last 5–7 days
   - `confirm_large_scan`: true if range > 500 conversations
3. **Filter results** — exclude matches where the only matched keywords are in exclude_if_only (tool does this when parameter is passed).
4. **Summarize** — highlight true developer/API conversations vs. noise.

---

## Example Prompts

- "Find developer/API conversations in Intercom from the last 5 days"
- "Search for Colppy integration requests in the last 2 weeks"
- "What are developers asking about the Colppy API?"
- "Find Producteca or Tiendanube integration issues in Intercom"

---

## Improving the Model (Feedback Loop)

The keyword matching improves over time through a feedback loop:

| Step | Action |
|------|--------|
| 1 | Run scan with `--report` → get `scan_report.md` with full context |
| 2 | Review each conversation, mark true vs false in `scan_feedback.json` or tell the AI in chat |
| 3 | Run `node scripts/suggest_keyword_changes.mjs` → get suggested `exclude_if_only` additions |
| 4 | Apply changes to `keywords.json`, re-run scan |
| 5 | Repeat until precision is satisfactory |

The suggestion script analyzes which keywords appear only in false positives (safe to exclude) vs in both (needs manual review).

---

## Learning: Add or Remove Keywords

Edit `keywords.json`:

- **Add** when you discover new terms developers use (e.g. "Zapier", "n8n", "error 404")
- **Remove** when a keyword causes too much noise
- **Update exclude_if_only** to filter more false positives

Restart Cursor or reload the skill to pick up changes.

---

## Local Iteration (No API Calls)

To iterate on keywords without re-fetching from Intercom:

1. **Create cache** (one-time) — Either:
   - **Option A:** Call `scan_full_text` with `save_cache`: `"skills/intercom-developer-api-research/cache/conversations_2025-01-21_2025-01-28.json"` (restart Cursor if MCP hasn't picked up save_cache)
   - **Option B:** Run the export script from workspace root:
     ```bash
     node tools/scripts/intercom/export_cache_for_local_scan.mjs --from 2025-01-21 --to 2025-01-28
     ```

2. **Edit** `keywords.json` — Add/remove keywords, update `exclude_if_only`.

3. **Re-run locally** — From the plugin root:
   ```bash
   node scripts/local_scan.mjs --cache skills/.../cache/conversations_YYYY-MM-DD_YYYY-MM-DD.json [--output results.json]
   ```
   - `--output <path>` — Save JSON results to file
   - `--full-context` — Include full message bodies and `conversation_thread` in JSON (for deeper inspection)
   - `--report <path>` — Write a Markdown report with **full conversation context** per match (recommended before editing keywords)

4. **Review context** — Before editing keywords, run with `--report` to see full conversations and where keywords matched:
   ```bash
   node scripts/local_scan.mjs --cache skills/.../cache/conversations_2025-01-21_2025-02-05.json --output results.json --report skills/.../cache/scan_report.md
   ```
   Open `scan_report.md` to see each match with the complete thread.

5. **Give feedback** — Tell the AI which conversations are true vs false:
   - **In chat:** "Conversations X, Y, Z are false positives" — the AI will suggest keyword changes
   - **Edit file:** Update `cache/scan_feedback.json` with `true_positives` and `false_positives` arrays (conversation IDs)

6. **Improve the model** — Run the suggestion script to learn from feedback:
   ```bash
   node scripts/suggest_keyword_changes.mjs
   ```
   It reads `scan_feedback.json` + `local_scan_results.json` and outputs:
   - Keywords in FPs but not TPs (safe to add to `exclude_if_only`)
   - Keywords in both (review manually)
   - Per-FP analysis: which keywords to add, and whether it's safe

7. **Apply & repeat** — Edit `keywords.json`, re-run scan, update feedback, repeat until precision is satisfactory.
