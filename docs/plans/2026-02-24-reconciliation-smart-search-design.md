# Reconciliation Smart Search — Design Doc

**Date:** 2026-02-24
**Status:** Approved

## Overview

Add three features to ReconciliacionPage:

1. **Infinite scroll + sticky table headers** — no pagination, column names stay visible while scrolling
2. **Matched invoices table** — show all ~2,650 matched ARCA↔Colppy pairs (currently hidden), with scope toggle
3. **Chat-style LLM search** — natural language search powered by Claude Haiku with conversation follow-ups

## Architecture

```
ReconciliacionPage.jsx
├── Summary cards (existing)
├── Discrepancies section (existing, infinite scroll)
├── Matched invoices section (NEW, collapsible, infinite scroll)
└── Chat search panel (NEW, collapsible drawer at bottom)
        │
        ▼
POST /api/arca/reconcile/search
        │
        ├── Load invoices from SQLite (ARCA cache + Colppy)
        ├── Build Claude Haiku prompt (schema + data + conversation)
        └── Stream response via SSE
              │
              ▼
        { answer: str, matched_caes: str[], scope: str }
```

## Feature 1: Infinite Scroll + Sticky Headers

### Changes
- Add `position: sticky; top: 0; z-index: 2` to all `<thead>` elements
- Background color on sticky headers to prevent content showing through
- No virtualization needed — ~2,650 rows is well within browser performance limits

### Rationale
Reconciliation is a review workflow (scan everything, acknowledge discrepancies). Page breaks interrupt this flow. Sticky headers solve the main UX issue of losing column context while scrolling.

## Feature 2: Matched Invoices Table

### Backend Change: Return matched pairs
Modify `reconciliacion_emitidos.py` to collect matched pairs during the CAE cross-match loop and include them in the response:

```python
# In reconcile_emitidos():
matched_pairs = []
# ... in the matching loop:
if abs(arca_amount - colppy_amt) < 0.02:
    matched += 1
    matched_pairs.append({
        "arca": _arca_record_summary(arca_rec),
        "colppy": _colppy_record_summary(colppy_by_cae[cae]),
    })

# In return dict:
"matched_pairs": matched_pairs,
```

### Frontend: Collapsible section
- New section below discrepancies: "Comprobantes matcheados (N)"
- Collapsed by default, click to expand
- Table columns: CAE | Numero | Fecha | Contraparte | ARCA $ | Colppy $ | Estado
- Scope toggle at top: Discrepancias / Todos — affects both table visibility and chat search scope
- Rows highlighted by chat search get a blue left border

## Feature 3: Chat-Style Smart Search

### Backend

**New endpoint:** `POST /api/arca/reconcile/search`

```python
class SearchRequest(BaseModel):
    query: str
    cuit: str
    fecha_desde: str
    fecha_hasta: str
    scope: str = "discrepancies"  # "discrepancies" | "all"
    conversation: list[dict] = []  # [{role, content}]

# Response: SSE stream
# Each SSE event contains partial JSON:
# data: {"type": "text", "content": "Encontré 3 facturas..."}
# data: {"type": "matches", "caes": ["12345...", "67890..."]}
# data: {"type": "done"}
```

**LLM Integration:**
- Model: Claude Haiku (claude-haiku-4-5-20251001) — fast, cheap
- System prompt: Invoice schema + reconciliation context + instructions to return structured JSON
- Input: Compact JSON of invoices (only relevant fields, ~15-20K tokens for 2,650 invoices)
- API key: `ANTHROPIC_API_KEY` in `.env`
- Dependency: `anthropic` Python SDK

**Data budget per query:**
- ~15-20K input tokens (invoice data + system prompt + conversation)
- ~200-500 output tokens (answer + CAE list)
- Cost: ~$0.005 per query at Haiku pricing

### System Prompt Design

```
You are a reconciliation search assistant for Argentine tax invoices.
You help users find and analyze invoices from two sources:
- ARCA (Argentina's tax authority, formerly AFIP)
- Colppy (accounting ERP)

The data contains {N} invoices from {fecha_desde} to {fecha_hasta}.
Statuses: matched, only_arca, only_colppy, amount_mismatch, currency_mismatch

Always respond in Spanish. Be concise. When listing invoices, show key details.
Return a JSON block at the end with matched CAE numbers for highlighting.

Schema:
- ARCA fields: numero, fecha_emision, tipo_comprobante, cuit_contraparte,
  denominacion_contraparte, moneda, importe_total, cod_autorizacion (CAE)
- Colppy fields: nroFactura, fechaFactura, idTipoComprobante, RazonSocial,
  totalFactura_pesos, cae, idEstadoFactura
```

### Frontend: Chat Panel

**Layout:**
- Collapsible drawer anchored at the bottom of the reconciliation section
- Collapsed state: search bar with magnifying glass icon
- Expanded state: message history + input bar
- Scope indicator (Discrepancias / Todos) in the header

**Components:**
- `ChatPanel` — container with message list, input bar, scope toggle
- Messages: user bubbles (right-aligned, blue) and assistant bubbles (left-aligned, dark)
- Streaming: assistant messages render progressively as SSE events arrive
- Row highlighting: when `matched_caes` received, those rows in the tables above get highlighted

**State:**
- `chatMessages: [{role, content, caes?}]` — conversation history
- `chatLoading: boolean` — streaming in progress
- `highlightedCaes: Set<string>` — CAEs to highlight in tables
- `chatScope: "discrepancies" | "all"` — search scope

**UX details:**
- Enter key sends message
- "Limpiar" button clears conversation + highlights
- Auto-scroll to latest message
- Highlighted rows: `borderLeft: 3px solid rgba(59,130,246,0.7)`, subtle blue glow
- Chat panel remembers state across scope toggles (conversation persists)

## Data Flow

1. User runs reconciliation → results load (existing)
2. User types in chat: "facturas de ACME sin match"
3. Frontend sends POST /search with query + scope + conversation history
4. Backend loads invoices from SQLite, builds Claude prompt
5. Claude streams response with answer text + matched CAEs
6. Frontend renders chat message + highlights matching rows in tables
7. User asks follow-up: "cuánto suman?" → conversation continues with context

## Dependencies

- `anthropic` Python SDK (new backend dependency)
- `ANTHROPIC_API_KEY` environment variable

## Non-Goals

- No client-side text filtering (everything goes through LLM for consistency)
- No pagination — infinite scroll only
- No export/download of search results
- No persistent chat history (resets on page reload)
