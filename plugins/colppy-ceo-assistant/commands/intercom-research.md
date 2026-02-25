---
name: intercom-research
description: Search Intercom conversations for customer feedback on a specific feature, topic, or product area. Scans conversations by keywords/tags, then deep-dives into the most relevant ones to extract insights.
---

# Intercom Customer Research

Research what customers are saying about a specific feature or topic by scanning Intercom support conversations.

## Data Source Restriction

**Use ONLY Intercom MCP tools** (scan_customer_feedback, get_conversation_feedback). Do NOT call Slack, Atlassian, HubSpot, or any other MCP. Intercom is the only data source for this command.

## Steps

1. **Ask for the topic**: What feature, product area, or theme to research (e.g. "conciliacion bancaria", "factura electronica", "conecta tu banco")

2. **Ask for date range**: Default to last 14 days if not specified. Narrower ranges are faster.

3. **Quick scan** using `scan_customer_feedback`:
   - Set `topic` to the user's topic
   - Add specific `keywords` if the topic has synonyms or related terms (e.g. for "conciliacion bancaria" add ["conciliacion", "conciliación", "bancaria", "banco", "extracto", "CBU"])
   - Optionally filter by `tags` if the user wants a specific category
   - Review matches and match reasons

4. **Deep dive** using `get_conversation_feedback`:
   - Pick the 5-8 most relevant conversation IDs from the scan (prioritize conversations where match_reason includes the core topic keywords, not just tangential matches)
   - Set `excerpt_length` to 2000 for detailed reading
   - Read full conversation timelines

5. **Categorize findings** by issue type:
   - Group conversations into themes (e.g. "bugs", "feature requests", "UX confusion", "missing functionality")
   - For each group: count, representative quotes, severity

6. **Present results** in the chat:
   - Summary table: scan stats (conversations scanned, matches found)
   - Findings by category with clickable Intercom URLs
   - Key insights and patterns
   - Recommended actions with priority (P0/P1/P2)

## Output Rules

- Present ALL results directly in the chat — do not create files
- Use markdown tables with proper formatting (no ** inside table cells)
- Include clickable Intercom URLs for every referenced conversation
- If zero matches are found, explain what was searched and suggest alternative keywords
