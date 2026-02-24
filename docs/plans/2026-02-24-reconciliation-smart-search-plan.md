# Reconciliation Smart Search — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add infinite scroll with sticky headers, matched invoices table, and chat-style LLM search to ReconciliacionPage.

**Architecture:** Backend search endpoint calls Claude Haiku with invoice data from SQLite, streams response via SSE. Frontend renders a chat panel with conversation history and highlights matching rows in the invoice tables.

**Tech Stack:** FastAPI + Anthropic Python SDK (backend), React 18 + SSE via EventSource (frontend), Claude Haiku for LLM search.

**Design doc:** `docs/plans/2026-02-24-reconciliation-smart-search-design.md`

---

### Task 1: Add `anthropic` SDK dependency

**Files:**
- Modify: `arca-prototype/requirements.txt`

**Step 1: Add anthropic to requirements.txt**

Add `anthropic>=0.42.0` to the end of `arca-prototype/requirements.txt`:

```
anthropic>=0.42.0
```

**Step 2: Install the dependency**

Run: `cd /Users/virulana/openai-cookbook/arca-prototype && .venv/bin/pip install anthropic>=0.42.0`

**Step 3: Verify import works**

Run: `.venv/bin/python -c "import anthropic; print(anthropic.__version__)"`
Expected: version number printed, no errors.

**Step 4: Add ANTHROPIC_API_KEY to .env**

Add to `arca-prototype/.env`:
```
ANTHROPIC_API_KEY=sk-ant-...
```

(User must provide their own key.)

**Step 5: Commit**

```bash
git add arca-prototype/requirements.txt
git commit -m "chore: add anthropic SDK dependency for reconciliation search"
```

---

### Task 2: Sticky table headers

**Files:**
- Modify: `arca-prototype/frontend/src/components/ReconciliacionPage.jsx` (styles at ~line 970)

**Step 1: Update the `th` style**

In the `s` styles object at ~line 973, update the `th` style to add sticky positioning:

```javascript
th: {
  textAlign: "left", padding: "0.4rem 0.5rem", color: "#64748b",
  borderBottom: "1px solid #334155", fontSize: "0.75rem", fontWeight: 500,
  position: "sticky", top: 0, zIndex: 2,
  background: "#1e293b",
},
```

**Step 2: Verify in browser**

Run the dev server, navigate to reconciliation, run a reconciliation, and scroll. Column headers should remain visible.

**Step 3: Commit**

```bash
git add arca-prototype/frontend/src/components/ReconciliacionPage.jsx
git commit -m "feat: add sticky table headers to reconciliation tables"
```

---

### Task 3: Return matched pairs from reconciliation engine

**Files:**
- Modify: `arca-prototype/backend/services/reconciliacion_emitidos.py:262-345`

**Step 1: Add matched_pairs collection**

After line 262 (`matched = 0`), add:

```python
matched_pairs = []
```

**Step 2: Collect matched pairs in the loop**

At line 295-296, change:

```python
elif abs(arca_amount - colppy_amt) < 0.02:
    matched += 1
```

to:

```python
elif abs(arca_amount - colppy_amt) < 0.02:
    matched += 1
    matched_pairs.append({
        "arca": _arca_record_summary(arca_rec),
        "colppy": _colppy_record_summary(colppy_by_cae[cae]),
    })
```

**Step 3: Include matched_pairs in the return dict**

At line 344, after `"discrepancies": discrepancies,` add:

```python
"matched_pairs": matched_pairs,
```

**Step 4: Verify via API**

Run: `curl -s "http://localhost:8000/api/arca/reconcile/emitidos?cuit=20239151730&fecha_desde=2026-01-01&fecha_hasta=2026-01-31" | python3 -m json.tool | head -5`

Check that `matched_pairs` key exists in the response.

**Step 5: Commit**

```bash
git add arca-prototype/backend/services/reconciliacion_emitidos.py
git commit -m "feat: return matched invoice pairs from reconciliation engine"
```

---

### Task 4: Matched invoices collapsible section in frontend

**Files:**
- Modify: `arca-prototype/frontend/src/components/ReconciliacionPage.jsx`

**Step 1: Add state for matched invoices visibility**

In `EmitidosReconciliation`, after the `ackOpen` state (line ~82), add:

```javascript
const [showMatched, setShowMatched] = useState(false);
const [chatScope, setChatScope] = useState("discrepancies"); // "discrepancies" | "all"
```

**Step 2: Add matched invoices section**

After the discrepancies section (after line ~538, before the "All matched" success banner), add:

```jsx
{/* Matched invoices (collapsible) */}
{result?.matched_pairs?.length > 0 && (
  <div style={s.discSection}>
    <div
      style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer", marginBottom: showMatched ? "0.75rem" : 0 }}
      onClick={() => setShowMatched((p) => !p)}
    >
      <h3 style={{ color: "#f8fafc", margin: 0 }}>
        <span style={{ color: "#64748b", marginRight: "0.5rem" }}>{showMatched ? "▾" : "▸"}</span>
        Comprobantes matcheados ({result.matched_pairs.length})
      </h3>
      <span style={{ ...s.badge, ...s.badgeMatched }}>CAE + monto OK</span>
    </div>

    {showMatched && (
      <div style={{ maxHeight: "500px", overflowY: "auto" }}>
        <table style={s.table}>
          <thead>
            <tr>
              <th style={s.th}>CAE</th>
              <th style={s.th}>Número</th>
              <th style={s.th}>Fecha</th>
              <th style={s.th}>Contraparte</th>
              <th style={{ ...s.th, textAlign: "right" }}>ARCA $</th>
              <th style={{ ...s.th, textAlign: "right" }}>Colppy $</th>
            </tr>
          </thead>
          <tbody>
            {result.matched_pairs.map((pair, i) => {
              const cae = pair.arca?.cod_autorizacion || "";
              const isHighlighted = highlightedCaes.has(cae);
              return (
                <tr key={i} style={isHighlighted ? { borderLeft: "3px solid rgba(59,130,246,0.7)", background: "rgba(59,130,246,0.05)" } : {}}>
                  <td style={{ ...s.td, fontSize: "0.75rem", fontFamily: "monospace" }}>{cae}</td>
                  <td style={s.td}>{pair.arca?.numero}</td>
                  <td style={s.td}>{pair.arca?.fecha_emision}</td>
                  <td style={s.td}>{pair.arca?.denominacion_contraparte}</td>
                  <td style={{ ...s.td, textAlign: "right" }}>{fmtMoney(pair.arca?.importe_total)}</td>
                  <td style={{ ...s.td, textAlign: "right" }}>{fmtMoney(pair.colppy?.totalFactura_pesos)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    )}
  </div>
)}
```

Note: `highlightedCaes` state will be added in Task 6. For now, initialize it as:
```javascript
const [highlightedCaes, setHighlightedCaes] = useState(new Set());
```

**Step 3: Also add highlight support to discrepancy rows**

In the discrepancy row rendering (line ~442), update the `rowStyle` logic to include chat highlights:

```javascript
const dKey = computeDiscrepancyKey(d);
const ack = acks.get(dKey);
const isAcked = !!ack;
const cae = d.arca?.cod_autorizacion || d.colppy?.cae || "";
const isHighlighted = highlightedCaes.has(cae);
const rowStyle = {
  ...(isAcked ? { opacity: 0.55, borderLeft: "3px solid rgba(34,197,94,0.5)" } : {}),
  ...(isHighlighted && !isAcked ? { borderLeft: "3px solid rgba(59,130,246,0.7)", background: "rgba(59,130,246,0.05)" } : {}),
};
```

**Step 4: Verify in browser**

Run reconciliation, verify the collapsible matched section appears and expands on click.

**Step 5: Commit**

```bash
git add arca-prototype/frontend/src/components/ReconciliacionPage.jsx
git commit -m "feat: add matched invoices collapsible section with highlight support"
```

---

### Task 5: Backend search endpoint with Claude Haiku + SSE

**Files:**
- Create: `arca-prototype/backend/services/reconciliation_search.py`
- Modify: `arca-prototype/backend/routers/arca.py`

**Step 1: Create the search service**

Create `arca-prototype/backend/services/reconciliation_search.py`:

```python
"""
LLM-powered search over reconciliation data.

Uses Claude Haiku to interpret natural-language queries against
ARCA + Colppy invoice data and return structured results.
"""

import json
import logging
import os
from typing import Any, AsyncIterator

import anthropic

from backend.services import arca_db, colppy_api
from backend.services.reconciliacion_emitidos import (
    _arca_record_summary,
    _colppy_record_summary,
    _safe_float,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
Sos un asistente de búsqueda para reconciliación de facturas argentinas.
Ayudás a encontrar y analizar comprobantes de dos fuentes:
- ARCA (autoridad fiscal argentina, ex-AFIP)
- Colppy (ERP contable)

Los datos contienen {n_total} comprobantes del {fecha_desde} al {fecha_hasta}.
- {n_matched} matcheados (CAE + monto coinciden)
- {n_discrepancies} con discrepancias (only_arca, only_colppy, amount_mismatch, currency_mismatch, etc.)

Campos ARCA: numero, fecha_emision, tipo_comprobante, cuit_contraparte, \
denominacion_contraparte, moneda, importe_total, cod_autorizacion (CAE)
Campos Colppy: nroFactura, fechaFactura, idTipoComprobante, RazonSocial, \
totalFactura_pesos, cae, idEstadoFactura

Respondé siempre en español. Sé conciso pero informativo.
Cuando listés facturas, mostrá los datos clave (número, contraparte, monto, estado).

IMPORTANTE: Al final de tu respuesta, incluí un bloque JSON con los CAEs de las \
facturas que mencionaste, así:

```json
{"matched_caes": ["12345678901234", "98765432109876"]}
```

Si no mencionás facturas específicas, usá `{"matched_caes": []}`.
"""


def _build_invoice_context(
    discrepancies: list[dict],
    matched_pairs: list[dict],
    scope: str,
) -> str:
    """Build compact text representation of invoices for the LLM context."""
    lines = []

    # Always include discrepancies
    if discrepancies:
        lines.append("=== DISCREPANCIAS ===")
        for d in discrepancies:
            status = d["status"]
            if d.get("arca"):
                a = d["arca"]
                lines.append(
                    f"[{status}] CAE:{a.get('cod_autorizacion','')} "
                    f"N:{a.get('numero','')} {a.get('fecha_emision','')} "
                    f"{a.get('denominacion_contraparte','')} "
                    f"ARCA:${a.get('importe_total',0)}"
                )
            if d.get("colppy"):
                c = d["colppy"]
                src = "  Colppy:" if d.get("arca") else f"[{status}] "
                lines.append(
                    f"{src}CAE:{c.get('cae','')} "
                    f"N:{c.get('nroFactura','')} {c.get('fechaFactura','')} "
                    f"{c.get('RazonSocial','')} "
                    f"Colppy:${c.get('totalFactura_pesos',0)}"
                )
            if d.get("diff_pesos"):
                lines.append(f"  Diferencia: ${d['diff_pesos']}")

    # Include matched pairs only if scope is "all"
    if scope == "all" and matched_pairs:
        lines.append(f"\n=== MATCHEADOS ({len(matched_pairs)}) ===")
        for p in matched_pairs:
            a = p["arca"]
            c = p["colppy"]
            lines.append(
                f"[matched] CAE:{a.get('cod_autorizacion','')} "
                f"N:{a.get('numero','')} {a.get('fecha_emision','')} "
                f"{a.get('denominacion_contraparte','')} "
                f"${a.get('importe_total',0)}"
            )

    return "\n".join(lines)


async def search_invoices_stream(
    query: str,
    cuit: str,
    fecha_desde: str,
    fecha_hasta: str,
    scope: str,
    conversation: list[dict],
    discrepancies: list[dict],
    matched_pairs: list[dict],
) -> AsyncIterator[str]:
    """
    Stream search results from Claude Haiku.

    Yields SSE-formatted lines: `data: {...}\n\n`
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        yield f'data: {json.dumps({"type": "error", "content": "ANTHROPIC_API_KEY no configurada en .env"})}\n\n'
        return

    n_disc = len(discrepancies)
    n_matched = len(matched_pairs)
    n_total = n_disc + n_matched

    system = SYSTEM_PROMPT.format(
        n_total=n_total,
        n_matched=n_matched,
        n_discrepancies=n_disc,
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
    )

    invoice_context = _build_invoice_context(discrepancies, matched_pairs, scope)

    # Build messages: system context + conversation history + current query
    messages = []

    # First message always includes the invoice data as context
    context_msg = f"Datos de facturas para buscar:\n\n{invoice_context}"
    messages.append({"role": "user", "content": context_msg})
    messages.append({"role": "assistant", "content": "Entendido. Tengo los datos de facturas cargados. ¿Qué querés buscar?"})

    # Add conversation history
    for msg in conversation:
        messages.append({"role": msg["role"], "content": msg["content"]})

    # Add current query
    messages.append({"role": "user", "content": query})

    client = anthropic.AsyncAnthropic(api_key=api_key)

    try:
        full_text = ""
        async with client.messages.stream(
            model="claude-haiku-4-5-20251001",
            max_tokens=1024,
            system=system,
            messages=messages,
        ) as stream:
            async for text in stream.text_stream:
                full_text += text
                yield f'data: {json.dumps({"type": "text", "content": text})}\n\n'

        # Extract matched CAEs from the response
        caes = []
        try:
            # Look for JSON block in the response
            json_start = full_text.rfind("```json")
            json_end = full_text.rfind("```", json_start + 7)
            if json_start >= 0 and json_end > json_start:
                json_str = full_text[json_start + 7:json_end].strip()
                parsed = json.loads(json_str)
                caes = parsed.get("matched_caes", [])
        except (json.JSONDecodeError, ValueError):
            pass

        yield f'data: {json.dumps({"type": "matches", "caes": caes})}\n\n'
        yield f'data: {json.dumps({"type": "done"})}\n\n'

    except anthropic.APIError as e:
        logger.error("Claude API error: %s", e)
        yield f'data: {json.dumps({"type": "error", "content": f"Error de API Claude: {e}"})}\n\n'
    except Exception as e:
        logger.error("Search error: %s", e)
        yield f'data: {json.dumps({"type": "error", "content": f"Error: {e}"})}\n\n'
```

**Step 2: Add the search endpoint to arca.py**

At the top of `arca-prototype/backend/routers/arca.py`, add to imports:

```python
from fastapi.responses import StreamingResponse
```

Add after the existing `AcknowledgmentCreate` model (around line 1058):

```python
class ReconcileSearchRequest(BaseModel):
    query: str
    cuit: str
    fecha_desde: str
    fecha_hasta: str
    scope: str = "discrepancies"
    conversation: list[dict] = []
    discrepancies: list[dict] = []
    matched_pairs: list[dict] = []
```

Add after the last acknowledgment endpoint (after line 1091):

```python
@router.post("/reconcile/search")
async def reconcile_search(body: ReconcileSearchRequest):
    """Stream LLM-powered search over reconciliation data."""
    from backend.services.reconciliation_search import search_invoices_stream

    return StreamingResponse(
        search_invoices_stream(
            query=body.query,
            cuit=body.cuit,
            fecha_desde=body.fecha_desde,
            fecha_hasta=body.fecha_hasta,
            scope=body.scope,
            conversation=body.conversation,
            discrepancies=body.discrepancies,
            matched_pairs=body.matched_pairs,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
```

**Step 3: Verify the endpoint loads**

Run: `curl -s -X POST http://localhost:8000/api/arca/reconcile/search -H "Content-Type: application/json" -d '{"query":"test","cuit":"20239151730","fecha_desde":"2026-01-01","fecha_hasta":"2026-01-31","discrepancies":[],"matched_pairs":[]}' --no-buffer`

Expected: SSE events stream back (or an error about missing API key — both prove the endpoint works).

**Step 4: Commit**

```bash
git add arca-prototype/backend/services/reconciliation_search.py arca-prototype/backend/routers/arca.py
git commit -m "feat: add LLM-powered reconciliation search endpoint with SSE streaming"
```

---

### Task 6: Frontend chat panel

**Files:**
- Modify: `arca-prototype/frontend/src/components/ReconciliacionPage.jsx`

**Step 1: Add chat state to EmitidosReconciliation**

After the `highlightedCaes` state (added in Task 4), add:

```javascript
const [chatMessages, setChatMessages] = useState([]); // [{role, content, caes?}]
const [chatInput, setChatInput] = useState("");
const [chatLoading, setChatLoading] = useState(false);
const [chatOpen, setChatOpen] = useState(false);
```

**Step 2: Add the sendMessage function**

Add this async function inside `EmitidosReconciliation`:

```javascript
const sendChatMessage = async () => {
  const query = chatInput.trim();
  if (!query || chatLoading || !result) return;

  const userMsg = { role: "user", content: query };
  setChatMessages((prev) => [...prev, userMsg]);
  setChatInput("");
  setChatLoading(true);
  setChatOpen(true);

  // Build conversation history (exclude the data-loading preamble)
  const history = chatMessages.filter((m) => m.role === "user" || m.role === "assistant");

  let assistantText = "";
  const assistantMsg = { role: "assistant", content: "", caes: [] };
  setChatMessages((prev) => [...prev, { ...assistantMsg }]);

  try {
    const res = await fetch(`${API_BASE}/api/arca/reconcile/search`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query,
        cuit: selectedRep.cuit,
        fecha_desde: fechaDesde,
        fecha_hasta: fechaHasta,
        scope: chatScope,
        conversation: history.map(({ role, content }) => ({ role, content })),
        discrepancies: result.discrepancies || [],
        matched_pairs: result.matched_pairs || [],
      }),
    });

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          const evt = JSON.parse(line.slice(6));
          if (evt.type === "text") {
            assistantText += evt.content;
            setChatMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = { role: "assistant", content: assistantText };
              return updated;
            });
          } else if (evt.type === "matches") {
            const caes = evt.caes || [];
            setHighlightedCaes(new Set(caes));
            setChatMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = { ...updated[updated.length - 1], caes };
              return updated;
            });
          } else if (evt.type === "error") {
            assistantText += `\n⚠️ ${evt.content}`;
            setChatMessages((prev) => {
              const updated = [...prev];
              updated[updated.length - 1] = { role: "assistant", content: assistantText };
              return updated;
            });
          }
        } catch { /* skip malformed SSE lines */ }
      }
    }
  } catch (err) {
    setChatMessages((prev) => {
      const updated = [...prev];
      updated[updated.length - 1] = { role: "assistant", content: `⚠️ Error: ${err.message}` };
      return updated;
    });
  } finally {
    setChatLoading(false);
  }
};

const clearChat = () => {
  setChatMessages([]);
  setChatInput("");
  setHighlightedCaes(new Set());
};
```

**Step 3: Add the ChatPanel component**

Add this as a new function component (before the `AckDropdown` component):

```jsx
function ChatPanel({ messages, input, onInputChange, onSend, onClear, loading, open, onToggle, scope, onScopeChange }) {
  const messagesEndRef = { current: null };

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  return (
    <div style={s.chatPanel}>
      {/* Header bar — always visible */}
      <div style={s.chatHeader} onClick={onToggle}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{ fontSize: "1rem" }}>🔍</span>
          <span style={{ color: "#f8fafc", fontWeight: 500, fontSize: "0.9rem" }}>
            Buscar con IA
          </span>
          {messages.length > 0 && (
            <span style={{ ...s.badge, background: "rgba(59,130,246,0.2)", color: "#93c5fd" }}>
              {messages.filter((m) => m.role === "user").length} consultas
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <div style={{ display: "flex", gap: "0.25rem" }} onClick={(e) => e.stopPropagation()}>
            {["discrepancies", "all"].map((s_) => (
              <button
                key={s_}
                type="button"
                onClick={() => onScopeChange(s_)}
                style={{
                  ...s.modeBtn, fontSize: "0.7rem", padding: "0.15rem 0.5rem",
                  ...(scope === s_ ? s.modeBtnActive : {}),
                }}
              >
                {s_ === "discrepancies" ? "Discrepancias" : "Todos"}
              </button>
            ))}
          </div>
          <span style={{ color: "#64748b", fontSize: "0.8rem" }}>{open ? "▾" : "▸"}</span>
        </div>
      </div>

      {/* Expanded: message history + input */}
      {open && (
        <>
          {messages.length > 0 && (
            <div style={s.chatMessages}>
              {messages.map((msg, i) => (
                <div
                  key={i}
                  style={{
                    ...s.chatBubble,
                    ...(msg.role === "user" ? s.chatBubbleUser : s.chatBubbleAssistant),
                  }}
                >
                  <div style={{ whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
                    {msg.content || (loading && i === messages.length - 1 ? "..." : "")}
                  </div>
                  {msg.caes?.length > 0 && (
                    <div style={{ fontSize: "0.7rem", color: "#64748b", marginTop: "0.3rem" }}>
                      {msg.caes.length} factura(s) resaltada(s) en la tabla ↑
                    </div>
                  )}
                </div>
              ))}
              <div ref={(el) => { messagesEndRef.current = el; }} />
            </div>
          )}

          <div style={s.chatInputRow}>
            <input
              type="text"
              value={input}
              onChange={(e) => onInputChange(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); onSend(); } }}
              placeholder="ej: facturas de ACME sin match, montos > $100.000 ..."
              style={{ ...s.input, flex: 1, padding: "0.5rem 0.75rem", fontSize: "0.85rem" }}
              disabled={loading}
            />
            <button
              type="button"
              onClick={onSend}
              disabled={loading || !input.trim()}
              style={{ ...s.button, padding: "0.5rem 1rem", fontSize: "0.85rem", opacity: loading || !input.trim() ? 0.5 : 1 }}
            >
              {loading ? "..." : "Enviar"}
            </button>
            {messages.length > 0 && (
              <button
                type="button"
                onClick={onClear}
                style={{ ...s.ackBtn, padding: "0.5rem 0.75rem", color: "#64748b" }}
              >
                Limpiar
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
```

**Step 4: Render ChatPanel in EmitidosReconciliation**

Add after the data freshness footer (after line ~553), but still inside the `<>` fragment:

```jsx
{/* Chat search — only show after reconciliation */}
{result && (
  <ChatPanel
    messages={chatMessages}
    input={chatInput}
    onInputChange={setChatInput}
    onSend={sendChatMessage}
    onClear={clearChat}
    loading={chatLoading}
    open={chatOpen}
    onToggle={() => setChatOpen((p) => !p)}
    scope={chatScope}
    onScopeChange={setChatScope}
  />
)}
```

**Step 5: Add chat styles**

Add these to the `s` styles object:

```javascript
chatPanel: {
  marginTop: "1.5rem", borderRadius: "8px",
  background: "rgba(30,41,59,0.6)", border: "1px solid #334155",
  overflow: "hidden",
},
chatHeader: {
  display: "flex", justifyContent: "space-between", alignItems: "center",
  padding: "0.6rem 1rem", cursor: "pointer",
  background: "rgba(30,41,59,0.8)", borderBottom: "1px solid #334155",
},
chatMessages: {
  maxHeight: "300px", overflowY: "auto", padding: "0.75rem",
  display: "flex", flexDirection: "column", gap: "0.5rem",
},
chatBubble: {
  padding: "0.5rem 0.75rem", borderRadius: "8px", maxWidth: "85%",
},
chatBubbleUser: {
  alignSelf: "flex-end", background: "rgba(59,130,246,0.2)",
  color: "#93c5fd", borderBottomRightRadius: "2px",
},
chatBubbleAssistant: {
  alignSelf: "flex-start", background: "rgba(30,41,59,0.8)",
  color: "#cbd5e1", borderBottomLeftRadius: "2px",
},
chatInputRow: {
  display: "flex", gap: "0.5rem", padding: "0.75rem",
  borderTop: "1px solid #334155",
},
```

**Step 6: Strip the JSON block from displayed assistant messages**

In the `ChatPanel` component, update the message rendering to hide the `matched_caes` JSON block from the display. Replace the content rendering line:

```jsx
{msg.content || (loading && i === messages.length - 1 ? "..." : "")}
```

with:

```jsx
{(msg.content || (loading && i === messages.length - 1 ? "..." : "")).replace(/```json\s*\{[^}]*"matched_caes"[^}]*\}\s*```/s, "").trim()}
```

**Step 7: Verify build**

Run: `cd /Users/virulana/openai-cookbook/arca-prototype/frontend && npx vite build`
Expected: Clean build, no errors.

**Step 8: Commit**

```bash
git add arca-prototype/frontend/src/components/ReconciliacionPage.jsx
git commit -m "feat: add chat-style LLM search panel with SSE streaming"
```

---

### Task 7: End-to-end testing

**Step 1: Start backend and frontend**

```bash
cd /Users/virulana/openai-cookbook/arca-prototype
.venv/bin/uvicorn backend.main:app --reload --port 8000 &
cd frontend && npx vite --port 5173 &
```

**Step 2: Run reconciliation**

Navigate to http://localhost:5173, go to Reconciliación page, select a representado, run Jan 2026 reconciliation. Verify:
- Sticky headers: scroll the page — column headers remain visible
- Matched invoices section appears (collapsed), click to expand
- Discrepancy tables render normally

**Step 3: Test chat search**

In the chat panel:
1. Type "facturas de febrero" → should get LLM response + highlighted rows
2. Follow-up: "cuáles tienen diferencia?" → conversation continues with context
3. Toggle scope to "Todos" → search covers matched invoices too
4. Click "Limpiar" → conversation clears, highlights removed

**Step 4: Test edge cases**

- Empty query → button disabled, no request sent
- Missing ANTHROPIC_API_KEY → error message in chat
- Large result set → SSE streams progressively

**Step 5: Final commit**

If any fixes were needed, commit them:
```bash
git add -A
git commit -m "fix: polish chat search UX after e2e testing"
```
