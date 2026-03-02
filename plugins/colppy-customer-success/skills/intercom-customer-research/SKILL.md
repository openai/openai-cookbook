---
name: intercom-customer-research
description: Research customer feedback in Intercom conversations for a specific feature or topic. Use when the user asks about customer sentiment, feature feedback, support pain points, or wants to understand what customers are saying about a particular area of the product.
---

# Intercom Customer Research

Search and analyze Intercom support conversations to understand customer feedback on specific features, topics, or product areas.

## Data Source Restriction (Critical)

**When doing customer feedback research, use ONLY Intercom tools.** Do NOT use Slack, Atlassian, HubSpot, or any other data source. Intercom is the single source of truth for support conversations and customer feedback.

---

## Prerequisites & Setup

Connect the built-in **Intercom integration** in Claude Desktop:

1. Open Claude Desktop
2. Go to **Settings → Integrations**
3. Find **Intercom** and click **Connect**
4. Log in with your Intercom account credentials
5. Authorize access

That's it. No tokens, no config files, no local server needed.

---

## Team Inbox Filtering (Cycle-Time Focus)

**Use `team_assignee_id`** to filter by a specific team inbox. Inboxes align with user lifecycle (e.g. onboarding, first 90 days), so filtering by inbox focuses conversations on that cycle time and speeds up exports.

| Team ID | Inbox Name | Purpose |
|---------|------------|---------|
| 2334166 | Primeros 90 días | New customer onboarding, first 90 days lifecycle |

Pass `team_assignee_id: "2334166"` when you want conversations from the Primeros 90 días inbox only. Get more IDs from Intercom: inbox → team → URL shows `inbox/team/TEAM_ID`.

---

## Research Workflow

### Step 1: Scan for relevant conversations

**Two scan options:**

| Tool | Scope | When to use |
|------|-------|-------------|
| `scan_customer_feedback` | First message only | Fast. Topic likely in the opening message. |
| `scan_full_text` | All messages (including replies) | Slower. Topic may appear in support replies (e.g. Mercado Pago, integrations). |

Search conversations by date range, filtering by topic keywords, Intercom tags, and optionally **team inbox** (`team_assignee_id`). Start narrow (7–14 days) and widen if you get too few results.

Ask for example:
- *"Search Intercom conversations from the last 14 days about conciliacion bancaria"*
- *"Find Primeros 90 días conversations about onboarding in the last 7 days"* (use `team_assignee_id: "2334166"`)
- *"Find conversations where Mercado Pago was mentioned in the last 5 days"* (use `scan_full_text`)
- *"Find conversations tagged 'Bug' about factura electronica since January 2026"*

### Step 2: Deep-dive into specific conversations

Once you have a list of relevant conversation IDs or previews, read the full conversation thread to extract the actual customer feedback.

Ask for example:
- *"Read the full conversation [ID] and summarize the customer's pain point"*
- *"Show me what the customer and support agent said in conversation [ID]"*

---

## Example Prompts

- "What feedback have customers given about conciliacion bancaria in the last 30 days?"
- "Search Intercom for conversations about factura electronica issues since January 2026"
- "Find customer complaints about importacion de items tagged with Bug"
- "What are customers saying about the new eSueldos module?"
- "What pain points do customers report about conecta tu banco?"
- "Find conversations where customers asked about carga masiva de facturas"
- "In which conversations did Mercado Pago appear in the last 5 days?" (use `scan_full_text`)
- "How many Intercom conversations were there last week?"

---

## Tips for Best Results

- **Filter by team inbox** (`team_assignee_id`) when analyzing a specific lifecycle stage (e.g. Primeros 90 días). Faster and more focused.
- **Narrow date ranges** are faster. Start with 7–14 days; widen if needed.
- **Combine tags + keywords** for precision: e.g. tag "Bug" + keyword "factura" finds bug reports about invoicing.
- **Scan first, then read**: get a list of matching conversations first, then pick the 3–5 most relevant to read in full.
- **Specify keywords explicitly** if the topic is multi-word: e.g. "conciliacion", "banco", "CBU" separately gives better matches than the full phrase.
- **Use `scan_full_text`** when the topic may appear in replies (e.g. Mercado Pago, integrations). It fetches full conversations so uses more API calls; keep date ranges narrow (5–7 days) and `max_scan` at 200 unless needed.

---

## Scan result limits

**`scan_full_text` returns all matches** — no cap. The cost is in fetching conversations; once fetched, all matches are returned. The `limit` parameter is deprecated and no longer used.
