/**
 * ReconciliacionPage — Two reconciliation modes:
 *   1. Retenciones vs Comprobantes Recibidos (existing)
 *   2. ARCA Emitidos vs Colppy Ventas (new)
 */
import { useState, useEffect, Fragment } from "react";
import { getApiBase } from "../apiConfig";

const API_BASE = getApiBase();

export default function ReconciliacionPage() {
  const [mode, setMode] = useState("emitidos"); // "emitidos" | "recibidos" | "retenciones"

  return (
    <div style={s.page}>
      <header style={s.header}>
        <h1 style={s.title}>Reconciliación</h1>
        <div style={s.modeToggle}>
          <button
            type="button"
            onClick={() => setMode("emitidos")}
            style={{ ...s.modeBtn, ...(mode === "emitidos" ? s.modeBtnActive : {}) }}
          >
            Emitidos
          </button>
          <button
            type="button"
            onClick={() => setMode("recibidos")}
            style={{ ...s.modeBtn, ...(mode === "recibidos" ? s.modeBtnActive : {}) }}
          >
            Recibidos
          </button>
          <button
            type="button"
            onClick={() => setMode("retenciones")}
            style={{ ...s.modeBtn, ...(mode === "retenciones" ? s.modeBtnActive : {}) }}
          >
            Retenciones
          </button>
        </div>
      </header>

      {mode === "emitidos" && <EmitidosReconciliation />}
      {mode === "recibidos" && <RecibidosReconciliation />}
      {mode === "retenciones" && <RetencionesReconciliation />}
    </div>
  );
}


/* ═══════════════════════════════════════════════════════════════════════════
   ARCA Emitidos ↔ Colppy Ventas
   ═══════════════════════════════════════════════════════════════════════════ */

/* ── Acknowledgment helpers ─────────────────────────────────────────── */

const CATEGORY_META = {
  revisado:    { label: "Revisado",    bg: "rgba(100,116,139,0.2)", color: "#94a3b8" },
  esperado:    { label: "Esperado",    bg: "rgba(34,197,94,0.2)",   color: "#86efac" },
  a_corregir:  { label: "A corregir",  bg: "rgba(251,146,60,0.2)",  color: "#fb923c" },
  no_corregir: { label: "No se corrige", bg: "rgba(100,116,139,0.15)", color: "#64748b" },
};

function computeDiscrepancyKey(d) {
  const status = d.status;
  const cae = d.arca?.cod_autorizacion || d.colppy?.cae || "";
  if (cae) return `${status}:${cae}`;
  const source = d.source || "";
  const rec = d.arca || d.colppy || {};
  const numero = rec.numero || rec.nroFactura || "";
  const fecha = rec.fecha_emision || rec.fechaFactura || "";
  return `${status}:${source}:${numero}:${fecha}`;
}


function EmitidosReconciliation() {
  const [representados, setRepresentados] = useState([]);
  const [selectedRep, setSelectedRep] = useState(null);
  const [loadingRep, setLoadingRep] = useState(true);

  const [fechaDesde, setFechaDesde] = useState("2026-01-01");
  const [fechaHasta, setFechaHasta] = useState("2026-01-31");

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState(null); // {pct, message, step, total}

  // Acknowledgments
  const [acks, setAcks] = useState(new Map());
  const [ackFilter, setAckFilter] = useState("all"); // "all" | "pending" | "acked"
  const [ackOpen, setAckOpen] = useState(null); // discrepancy_key of open dropdown

  // Matched invoices & search
  const [showMatched, setShowMatched] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState(new Set()); // collapsed discrepancy group statuses
  const [highlightedCaes, setHighlightedCaes] = useState(new Set());
  const [expandedRow, setExpandedRow] = useState(null); // discrepancy_key of expanded detail row
  const [chatScope, setChatScope] = useState("discrepancies"); // "discrepancies" | "all"

  // Chat
  const [chatMessages, setChatMessages] = useState([]); // [{role, content, caes?}]
  const [chatInput, setChatInput] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);

  const fetchAcknowledgments = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/arca/reconcile/acknowledgments`);
      const json = await res.json();
      if (json.success) {
        const map = new Map();
        for (const a of json.acknowledgments) map.set(a.discrepancy_key, a);
        setAcks(map);
      }
    } catch { /* silent */ }
  };

  const handleAcknowledge = async (key, status, category, reason, context) => {
    try {
      await fetch(`${API_BASE}/api/arca/reconcile/acknowledgments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          discrepancy_key: key, status, category, reason,
          acknowledged_by: "", context_json: context,
        }),
      });
      await fetchAcknowledgments();
      setAckOpen(null);
    } catch { /* silent */ }
  };

  const handleUnacknowledge = async (key) => {
    try {
      await fetch(`${API_BASE}/api/arca/reconcile/acknowledgments/${encodeURIComponent(key)}`, {
        method: "DELETE",
      });
      await fetchAcknowledgments();
    } catch { /* silent */ }
  };

  // ── Chat search ──
  const sendChatMessage = async () => {
    const query = chatInput.trim();
    if (!query || chatLoading || !result) return;

    const userMsg = { role: "user", content: query };
    setChatMessages((prev) => [...prev, userMsg]);
    setChatInput("");
    setChatLoading(true);
    setChatOpen(true);

    const history = chatMessages.filter((m) => m.role === "user" || m.role === "assistant");

    let assistantText = "";
    setChatMessages((prev) => [...prev, { role: "assistant", content: "" }]);

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
              assistantText += evt.content;
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
        updated[updated.length - 1] = { role: "assistant", content: `Error: ${err.message}` };
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

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch(`${API_BASE}/api/arca/representados`);
        const json = await res.json();
        if (cancelled) return;
        if (json.success && json.representados?.length > 0) {
          setRepresentados(json.representados);
          setSelectedRep(json.representados[0]);
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoadingRep(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedRep) return;
    setLoading(true);
    setResult(null);
    setError(null);
    setProgress({ pct: 5, message: "Iniciando reconciliación...", step: 0, total: 5 });

    try {
      const params = new URLSearchParams({
        cuit: selectedRep.cuit,
        fecha_desde: fechaDesde,
        fecha_hasta: fechaHasta,
      });
      const res = await fetch(`${API_BASE}/api/arca/reconcile/emitidos/stream?${params}`, {
        signal: AbortSignal.timeout(180_000),
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        const lines = buf.split("\n\n");
        buf = lines.pop(); // keep incomplete chunk

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.type === "progress") {
              setProgress({ pct: evt.pct, message: evt.message, step: evt.step, total: evt.total });
            } else if (evt.type === "result") {
              const json = evt.data;
              if (json.success) {
                setResult(json);
                fetchAcknowledgments();
              } else {
                setError(json.message || "Error en reconciliación");
              }
            } else if (evt.type === "error") {
              setError(evt.message);
            }
          } catch (_) { /* skip malformed */ }
        }
      }
    } catch (err) {
      if (err.name === "TimeoutError") {
        setError("La operación tardó más de 3 minutos. Intente de nuevo.");
      } else {
        setError(err.message || "Error de conexión");
      }
    } finally {
      setLoading(false);
      setProgress(null);
    }
  };

  const summary = result?.summary;

  // Compute ack stats for summary card
  const totalDisc = summary
    ? summary.amount_mismatch + summary.only_arca + summary.only_colppy
    : 0;
  const ackedCount = result?.discrepancies
    ? result.discrepancies.filter(
        (d) => ["only_arca", "only_colppy", "amount_mismatch"].includes(d.status)
          && acks.has(computeDiscrepancyKey(d))
      ).length
    : 0;
  const pendingCount = totalDisc - ackedCount;

  return (
    <>
      <p style={s.subtitle}>
        Comparar comprobantes emitidos en ARCA contra facturas de venta en Colppy (por CAE).
      </p>

      <form onSubmit={handleSubmit} style={s.form}>
        <div style={s.field}>
          <label style={s.label}>Representado</label>
          <select
            value={selectedRep ? selectedRep.cuit : ""}
            onChange={(e) => {
              setSelectedRep(representados.find((r) => r.cuit === e.target.value) || null);
            }}
            style={s.select}
            disabled={loading || loadingRep}
          >
            {loadingRep ? (
              <option value="">Cargando representados...</option>
            ) : representados.length === 0 ? (
              <option value="">No hay representados en caché</option>
            ) : (
              representados.map((r) => (
                <option key={r.cuit} value={r.cuit}>
                  {r.nombre} - {r.cuit}
                </option>
              ))
            )}
          </select>
        </div>

        <div style={s.dateRow}>
          <div style={s.field}>
            <label style={s.label}>Desde</label>
            <input type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} style={s.input} />
          </div>
          <div style={s.field}>
            <label style={s.label}>Hasta</label>
            <input type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} style={s.input} />
          </div>
        </div>

        <button type="submit" disabled={loading || !selectedRep} style={s.button}>
          {loading ? `Reconciliando${progress ? ` (${progress.pct}%)` : "..."}` : "Reconciliar"}
        </button>
      </form>

      {loading && progress && (
        <div style={{
          margin: "16px 0", padding: "16px 20px",
          background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.3)",
          borderRadius: 10,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, fontSize: 13 }}>
            <span style={{ color: "#c4b5fd" }}>{progress.message}</span>
            <span style={{ color: "#94a3b8" }}>Paso {progress.step}/{progress.total}</span>
          </div>
          <div style={{
            height: 6, borderRadius: 3, background: "rgba(99,102,241,0.15)", overflow: "hidden",
          }}>
            <div style={{
              height: "100%", borderRadius: 3,
              background: "linear-gradient(90deg, #6366f1, #818cf8)",
              width: `${progress.pct}%`,
              transition: "width 0.4s ease",
            }} />
          </div>
        </div>
      )}

      {error && <div style={s.error}><strong>Error:</strong> {error}</div>}

      {/* Auto-fetch notice */}
      {result?.arca_auto_fetched && (
        <div style={s.autoFetchNotice}>
          Los datos de ARCA fueron descargados automáticamente para este período y guardados en caché.
        </div>
      )}

      {/* Summary cards */}
      {summary && (
        <>
          <div style={s.summaryGrid}>
            <div style={s.card}>
              <div style={s.cardValue}>{summary.arca_total}</div>
              <div style={s.cardLabel}>ARCA Emitidos</div>
            </div>
            <div style={s.card}>
              <div style={s.cardValue}>{summary.colppy_total}</div>
              <div style={s.cardLabel}>Colppy Ventas</div>
            </div>
            <div style={{ ...s.card, borderColor: "rgba(34,197,94,0.4)" }}>
              <div style={{ ...s.cardValue, color: "#86efac" }}>
                {summary.matched}
              </div>
              <div style={s.cardLabel}>Matched (CAE + monto)</div>
            </div>
            <div style={{
              ...s.card,
              borderColor: pendingCount > 0
                ? "rgba(251,146,60,0.4)"
                : totalDisc > 0 ? "rgba(34,197,94,0.4)" : "rgba(34,197,94,0.4)",
            }}>
              <div style={{
                ...s.cardValue,
                color: pendingCount > 0 ? "#fb923c" : "#86efac",
              }}>
                {totalDisc}
              </div>
              <div style={s.cardLabel}>Discrepancias reales</div>
              {totalDisc > 0 && (
                <div style={{ fontSize: "0.75rem", color: "#64748b", marginTop: "0.2rem" }}>
                  {pendingCount > 0 && <span style={{ color: "#fb923c" }}>{pendingCount} pendientes</span>}
                  {pendingCount > 0 && ackedCount > 0 && " · "}
                  {ackedCount > 0 && <span style={{ color: "#86efac" }}>{ackedCount} confirmadas</span>}
                </div>
              )}
            </div>
            {summary.currency_mismatch > 0 && (
              <div style={{ ...s.card, borderColor: "rgba(147,130,220,0.4)" }}>
                <div style={{ ...s.cardValue, color: "#c4b5fd" }}>
                  {summary.currency_mismatch}
                </div>
                <div style={s.cardLabel}>Moneda distinta</div>
              </div>
            )}
          </div>

          {/* Totals */}
          <div style={{ ...s.summaryGrid, gridTemplateColumns: "1fr 1fr" }}>
            <div style={s.card}>
              <div style={s.cardValue}>{fmtMoney(summary.arca_importe_total)}</div>
              <div style={s.cardLabel}>Total ARCA (pesos)</div>
            </div>
            <div style={s.card}>
              <div style={s.cardValue}>{fmtMoney(summary.colppy_importe_total)}</div>
              <div style={s.cardLabel}>Total Colppy (pesos)</div>
            </div>
          </div>

          {/* Data quality warnings */}
          {((summary.arca_no_cae || 0) + (summary.colppy_no_cae || 0) +
            (summary.arca_duplicate_cae || 0) + (summary.colppy_duplicate_cae || 0)) > 0 && (
            <div style={s.warning}>
              <strong>Alertas de calidad de datos:</strong>
              {(summary.arca_no_cae || 0) > 0 && (
                <span> {summary.arca_no_cae} ARCA sin CAE.</span>
              )}
              {(summary.colppy_no_cae || 0) > 0 && (
                <span> {summary.colppy_no_cae} Colppy sin CAE.</span>
              )}
              {(summary.arca_duplicate_cae || 0) > 0 && (
                <span> {summary.arca_duplicate_cae} ARCA con CAE duplicado.</span>
              )}
              {(summary.colppy_duplicate_cae || 0) > 0 && (
                <span> {summary.colppy_duplicate_cae} Colppy con CAE duplicado.</span>
              )}
              <span> Estos registros aparecen en la tabla de discrepancias abajo.</span>
            </div>
          )}
        </>
      )}

      {/* Chat search — above discrepancies */}
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

      {/* Discrepancies breakdown */}
      {result?.discrepancies?.length > 0 && (
        <div style={s.discSection}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
            <h3 style={{ color: "#f8fafc", margin: 0 }}>
              Discrepancias ({result.discrepancies.length})
            </h3>
            <div style={s.modeToggle}>
              {[
                { key: "all", label: "Todas" },
                { key: "pending", label: "Pendientes" },
                { key: "acked", label: "Confirmadas" },
              ].map((f) => (
                <button
                  key={f.key}
                  type="button"
                  onClick={() => setAckFilter(f.key)}
                  style={{ ...s.modeBtn, fontSize: "0.75rem", padding: "0.25rem 0.6rem", ...(ackFilter === f.key ? s.modeBtnActive : {}) }}
                >
                  {f.label}
                </button>
              ))}
            </div>
          </div>

          {/* Group by status */}
          {["only_arca", "only_colppy", "amount_mismatch", "currency_mismatch", "missing_cae", "duplicate_cae"].map((status) => {
            const allItems = result.discrepancies.filter((d) => d.status === status);
            // Apply ack filter
            const items = allItems.filter((d) => {
              if (ackFilter === "all") return true;
              const isAcked = acks.has(computeDiscrepancyKey(d));
              return ackFilter === "acked" ? isAcked : !isAcked;
            });
            if (items.length === 0) return null;

            const statusLabels = {
              only_arca: `Solo en ARCA (${items.length})`,
              only_colppy: `Solo en Colppy (${items.length})`,
              amount_mismatch: `Diferencia de monto (${items.length})`,
              currency_mismatch: `Moneda distinta (${items.length})`,
              missing_cae: `Sin CAE (${items.length})`,
              duplicate_cae: `CAE duplicado (${items.length})`,
            };
            const statusStyles = {
              only_arca: s.badgeOnlyArca,
              only_colppy: s.badgeOnlyColppy,
              amount_mismatch: s.badgeMismatch,
              currency_mismatch: s.badgeCurrency,
              missing_cae: s.badgeNoData,
              duplicate_cae: s.badgeMismatch,
            };

            const isCollapsed = collapsedGroups.has(status);
            const toggleGroup = () => setCollapsedGroups((prev) => {
              const next = new Set(prev);
              next.has(status) ? next.delete(status) : next.add(status);
              return next;
            });

            return (
              <div key={status} style={{ marginBottom: "1rem" }}>
                <div
                  onClick={toggleGroup}
                  style={{
                    ...s.badge, ...statusStyles[status],
                    display: "inline-flex", alignItems: "center", gap: 6,
                    marginBottom: "0.5rem", cursor: "pointer", userSelect: "none",
                  }}
                >
                  <span style={{ fontSize: 10, transition: "transform 0.2s", transform: isCollapsed ? "rotate(-90deg)" : "rotate(0deg)" }}>▼</span>
                  {statusLabels[status]}
                </div>

                {!isCollapsed && <table style={s.table}>
                  <thead>
                    <tr>
                      {status === "amount_mismatch" ? (
                        <>
                          <th style={s.th}>CAE</th>
                          <th style={s.th}>Número</th>
                          <th style={s.th}>Fecha</th>
                          <th style={s.th}>Tipo</th>
                          <th style={s.th}>Estado</th>
                          <th style={{ ...s.th, textAlign: "right" }}>ARCA $</th>
                          <th style={{ ...s.th, textAlign: "right" }}>Colppy $</th>
                          <th style={{ ...s.th, textAlign: "right" }}>Diff $</th>
                          <th style={{ ...s.th, textAlign: "center", width: "90px" }}>Acción</th>
                        </>
                      ) : status === "currency_mismatch" ? (
                        <>
                          <th style={s.th}>CAE</th>
                          <th style={s.th}>Número</th>
                          <th style={s.th}>Fecha</th>
                          <th style={s.th}>Tipo</th>
                          <th style={s.th}>Estado</th>
                          <th style={{ ...s.th, textAlign: "right" }}>ARCA (orig.)</th>
                          <th style={{ ...s.th, textAlign: "right" }}>Colppy (ARS)</th>
                          <th style={{ ...s.th, textAlign: "center", width: "90px" }}>Acción</th>
                        </>
                      ) : (
                        <>
                          <th style={s.th}>Origen</th>
                          <th style={s.th}>Número</th>
                          <th style={s.th}>Fecha</th>
                          <th style={s.th}>Tipo</th>
                          <th style={s.th}>Estado</th>
                          <th style={s.th}>Contraparte</th>
                          <th style={{ ...s.th, textAlign: "right" }}>Importe</th>
                          <th style={{ ...s.th, textAlign: "center", width: "90px" }}>Acción</th>
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((d, i) => {
                      const dKey = computeDiscrepancyKey(d);
                      const ack = acks.get(dKey);
                      const isAcked = !!ack;
                      const cae = d.arca?.cod_autorizacion || d.colppy?.cae || "";
                      const isHighlighted = highlightedCaes.has(cae);
                      const isExpanded = expandedRow === dKey;
                      const rowStyle = {
                        cursor: "pointer",
                        ...(isAcked ? { opacity: 0.55, borderLeft: "3px solid rgba(34,197,94,0.5)" } : {}),
                        ...(isHighlighted && !isAcked ? { borderLeft: "3px solid rgba(59,130,246,0.7)", background: "rgba(59,130,246,0.05)" } : {}),
                        ...(isExpanded ? { background: "rgba(99,102,241,0.06)" } : {}),
                      };
                      const toggleExpand = () => setExpandedRow(isExpanded ? null : dKey);
                      const colCount = status === "amount_mismatch" ? 9 : 8;

                      const detailRow = isExpanded ? (
                        <tr key={`${i}-detail`}>
                          <td colSpan={colCount} style={{ padding: "8px 4px", border: "none" }}>
                            <InvoiceDetail arca={d.arca} colppy={d.colppy} />
                          </td>
                        </tr>
                      ) : null;

                      const actionCell = (
                        <td style={{ ...s.td, textAlign: "center", position: "relative" }}>
                          {isAcked ? (
                            <span
                              style={{
                                ...s.badge, ...CATEGORY_META[ack.category] || CATEGORY_META.revisado,
                                cursor: "pointer",
                              }}
                              title={ack.reason || "Click para deshacer"}
                              onClick={() => handleUnacknowledge(dKey)}
                            >
                              {(CATEGORY_META[ack.category] || CATEGORY_META.revisado).label} ✕
                            </span>
                          ) : ackOpen === dKey ? (
                            <AckDropdown
                              onConfirm={(cat, reason) =>
                                handleAcknowledge(dKey, d.status, cat, reason, { arca: d.arca, colppy: d.colppy })
                              }
                              onCancel={() => setAckOpen(null)}
                            />
                          ) : (
                            <button
                              type="button"
                              style={s.ackBtn}
                              onClick={() => setAckOpen(dKey)}
                            >
                              Confirmar
                            </button>
                          )}
                        </td>
                      );

                      if (status === "amount_mismatch") {
                        const estadoColppy = d.colppy?.estadoFactura || "";
                        return (
                          <Fragment key={i}>
                            <tr style={rowStyle} onClick={toggleExpand}>
                              <td style={{ ...s.td, fontSize: "0.75rem", fontFamily: "monospace" }}>
                                {d.arca?.cod_autorizacion}
                              </td>
                              <td style={s.td}>{d.arca?.numero || d.colppy?.nroFactura}</td>
                              <td style={s.td}>{d.arca?.fecha_emision || d.colppy?.fechaFactura}</td>
                              <td style={{ ...s.td, fontSize: "0.8rem" }}>{tipoLetter(d.arca?.tipo_comprobante)}</td>
                              <td style={{ ...s.td, fontSize: "0.8rem", ...(ESTADO_COLORS[estadoColppy] || {}) }}>{estadoColppy || "—"}</td>
                              <td style={{ ...s.td, textAlign: "right" }}>{fmtMoney(d.arca?.importe_total)}</td>
                              <td style={{ ...s.td, textAlign: "right" }}>{fmtMoney(d.colppy?.totalFactura_pesos)}</td>
                              <td style={{ ...s.td, textAlign: "right", color: d.diff_pesos > 0 ? "#fb923c" : "#93c5fd" }}>
                                {d.diff_pesos > 0 ? "+" : ""}{fmtMoney(d.diff_pesos)}
                              </td>
                              {actionCell}
                            </tr>
                            {detailRow}
                          </Fragment>
                        );
                      }
                      if (status === "currency_mismatch") {
                        const moneda = d.arca?.moneda || "???";
                        const estadoCurr = d.colppy?.estadoFactura || "";
                        return (
                          <Fragment key={i}>
                            <tr style={rowStyle} onClick={toggleExpand}>
                              <td style={{ ...s.td, fontSize: "0.75rem", fontFamily: "monospace" }}>
                                {d.arca?.cod_autorizacion}
                              </td>
                              <td style={s.td}>{d.arca?.numero}</td>
                              <td style={s.td}>{d.arca?.fecha_emision}</td>
                              <td style={{ ...s.td, fontSize: "0.8rem" }}>{tipoLetter(d.arca?.tipo_comprobante)}</td>
                              <td style={{ ...s.td, fontSize: "0.8rem", ...(ESTADO_COLORS[estadoCurr] || {}) }}>{estadoCurr || "—"}</td>
                              <td style={{ ...s.td, textAlign: "right" }}>
                                {moneda} {d.arca?.importe_total?.toLocaleString("es-AR", { minimumFractionDigits: 2 })}
                              </td>
                              <td style={{ ...s.td, textAlign: "right" }}>{fmtMoney(d.colppy?.totalFactura_pesos)}</td>
                              {actionCell}
                            </tr>
                            {detailRow}
                          </Fragment>
                        );
                      }
                      const rec = d.arca || d.colppy;
                      const isArca = !!d.arca;
                      const estadoOther = d.colppy?.estadoFactura || "";
                      return (
                        <Fragment key={i}>
                          <tr style={rowStyle} onClick={toggleExpand}>
                            <td style={{ ...s.td, fontSize: "0.75rem" }}>{d.source || (isArca ? "ARCA" : "Colppy")}</td>
                            <td style={s.td}>{isArca ? rec.numero : rec.nroFactura}</td>
                            <td style={s.td}>{isArca ? rec.fecha_emision : rec.fechaFactura}</td>
                            <td style={{ ...s.td, fontSize: "0.8rem" }}>{tipoLetter(rec.tipo_comprobante)}</td>
                            <td style={{ ...s.td, fontSize: "0.8rem", ...(ESTADO_COLORS[estadoOther] || {}) }}>{estadoOther || "—"}</td>
                            <td style={s.td}>
                              {isArca ? rec.denominacion_contraparte : rec.RazonSocial}
                            </td>
                            <td style={{ ...s.td, textAlign: "right" }}>
                              {fmtMoney(isArca ? rec.importe_total : rec.totalFactura_pesos)}
                            </td>
                            {actionCell}
                          </tr>
                          {detailRow}
                        </Fragment>
                      );
                    })}
                  </tbody>
                </table>}
              </div>
            );
          })}
        </div>
      )}

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
                    <th style={s.th}>Tipo</th>
                    <th style={s.th}>Estado</th>
                    <th style={s.th}>Contraparte</th>
                    <th style={{ ...s.th, textAlign: "right" }}>ARCA $</th>
                    <th style={{ ...s.th, textAlign: "right" }}>Colppy $</th>
                  </tr>
                </thead>
                <tbody>
                  {result.matched_pairs.map((pair, i) => {
                    const cae = pair.arca?.cod_autorizacion || "";
                    const isHL = highlightedCaes.has(cae);
                    const estadoMatched = pair.colppy?.estadoFactura || "";
                    return (
                      <tr key={i} style={isHL ? { borderLeft: "3px solid rgba(59,130,246,0.7)", background: "rgba(59,130,246,0.05)" } : {}}>
                        <td style={{ ...s.td, fontSize: "0.75rem", fontFamily: "monospace" }}>{cae}</td>
                        <td style={s.td}>{pair.arca?.numero}</td>
                        <td style={s.td}>{pair.arca?.fecha_emision}</td>
                        <td style={{ ...s.td, fontSize: "0.8rem" }}>{tipoLetter(pair.arca?.tipo_comprobante)}</td>
                        <td style={{ ...s.td, fontSize: "0.8rem", ...(ESTADO_COLORS[estadoMatched] || {}) }}>{estadoMatched || "—"}</td>
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

      {/* All matched */}
      {result && result.discrepancies?.length === 0 && (
        <div style={s.successBanner}>
          Todos los comprobantes coinciden entre ARCA y Colppy.
        </div>
      )}

      {/* Data freshness */}
      {result && (
        <div style={s.freshness}>
          {result.reconciled_at && (
            <span>Reconciliado: <strong>{result.reconciled_at}</strong></span>
          )}
          {result.arca_fetched_at && (
            <span style={{ marginLeft: 16 }}>ARCA cache: {result.arca_fetched_at}</span>
          )}
          <span style={{ marginLeft: 16 }}>Colppy: en vivo</span>
          {(summary?.colppy_anuladas || 0) > 0 && (
            <span style={{ marginLeft: 16, color: "#f87171" }}>
              {summary.colppy_anuladas} factura(s) anulada(s) en Colppy
            </span>
          )}
        </div>
      )}
    </>
  );
}


/* ═══════════════════════════════════════════════════════════════════════════
   ARCA Recibidos ↔ Colppy Compras + Retenciones/Percepciones Overlay
   ═══════════════════════════════════════════════════════════════════════════ */

function RecibidosReconciliation() {
  const [representados, setRepresentados] = useState([]);
  const [selectedRep, setSelectedRep] = useState(null);
  const [loadingRep, setLoadingRep] = useState(true);

  const [fechaDesde, setFechaDesde] = useState("2026-01-01");
  const [fechaHasta, setFechaHasta] = useState("2026-01-31");

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [progress, setProgress] = useState(null);

  const [collapsedGroups, setCollapsedGroups] = useState(new Set());
  const [expandedRow, setExpandedRow] = useState(null);
  const [showMatched, setShowMatched] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch(`${API_BASE}/api/arca/representados`);
        const json = await res.json();
        if (cancelled) return;
        if (json.success && json.representados?.length > 0) {
          setRepresentados(json.representados);
          setSelectedRep(json.representados[0]);
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoadingRep(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedRep) return;
    setLoading(true);
    setResult(null);
    setError(null);
    setProgress({ pct: 5, message: "Iniciando reconciliación de recibidos...", step: 0, total: 6 });

    try {
      const params = new URLSearchParams({
        cuit: selectedRep.cuit,
        fecha_desde: fechaDesde,
        fecha_hasta: fechaHasta,
      });
      const res = await fetch(`${API_BASE}/api/arca/reconcile/recibidos/stream?${params}`, {
        signal: AbortSignal.timeout(180_000),
      });

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        const lines = buf.split("\n\n");
        buf = lines.pop();

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          try {
            const evt = JSON.parse(line.slice(6));
            if (evt.type === "progress") {
              setProgress({ pct: evt.pct, message: evt.message, step: evt.step, total: evt.total });
            } else if (evt.type === "result") {
              if (evt.data.success) {
                setResult(evt.data);
              } else {
                setError(evt.data.message || "Error en reconciliación");
              }
            } else if (evt.type === "error") {
              setError(evt.message);
            }
          } catch (_) { /* skip malformed */ }
        }
      }
    } catch (err) {
      if (err.name === "TimeoutError") {
        setError("La operación tardó más de 3 minutos. Intente de nuevo.");
      } else {
        setError(err.message || "Error de conexión");
      }
    } finally {
      setLoading(false);
      setProgress(null);
    }
  };

  const summary = result?.summary;
  const totalDisc = summary
    ? summary.amount_mismatch + summary.only_arca + summary.only_colppy
    : 0;

  const toggleGroup = (status) =>
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      next.has(status) ? next.delete(status) : next.add(status);
      return next;
    });

  const discKey = (d) => {
    const nro = d.arca?.numero || d.colppy?.nroFactura || "";
    const fecha = d.arca?.fecha_emision || d.colppy?.fechaFactura || "";
    return `${d.status}:${nro}:${fecha}`;
  };

  // Group discrepancies by status
  const grouped = {};
  for (const d of result?.discrepancies || []) {
    (grouped[d.status] = grouped[d.status] || []).push(d);
  }

  const STATUS_LABELS = {
    amount_mismatch: { label: "Diferencia de monto", badge: s.badgeMismatch },
    only_arca: { label: "Solo en ARCA", badge: s.badgeOnlyArca },
    only_colppy: { label: "Solo en Colppy", badge: s.badgeOnlyColppy },
    missing_number: { label: "Sin número", badge: s.badgeNoData },
    duplicate_number: { label: "Nro factura duplicado", badge: s.badgeMismatch },
  };

  return (
    <>
      <p style={s.subtitle}>
        Comparar comprobantes recibidos en ARCA contra facturas de compra en Colppy (por número de factura).
      </p>

      <form onSubmit={handleSubmit} style={s.form}>
        <div style={s.field}>
          <label style={s.label}>Representado</label>
          <select
            value={selectedRep ? selectedRep.cuit : ""}
            onChange={(e) => setSelectedRep(representados.find((r) => r.cuit === e.target.value) || null)}
            style={s.select}
            disabled={loading || loadingRep}
          >
            {loadingRep ? (
              <option value="">Cargando representados...</option>
            ) : representados.length === 0 ? (
              <option value="">No hay representados en caché</option>
            ) : (
              representados.map((r) => (
                <option key={r.cuit} value={r.cuit}>{r.nombre} - {r.cuit}</option>
              ))
            )}
          </select>
        </div>

        <div style={s.dateRow}>
          <div style={s.field}>
            <label style={s.label}>Desde</label>
            <input type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} style={s.input} />
          </div>
          <div style={s.field}>
            <label style={s.label}>Hasta</label>
            <input type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} style={s.input} />
          </div>
        </div>

        <button type="submit" disabled={loading || !selectedRep} style={s.button}>
          {loading ? `Reconciliando${progress ? ` (${progress.pct}%)` : "..."}` : "Reconciliar Recibidos"}
        </button>
      </form>

      {/* Progress bar */}
      {loading && progress && (
        <div style={{
          margin: "16px 0", padding: "16px 20px",
          background: "rgba(99,102,241,0.08)", border: "1px solid rgba(99,102,241,0.3)",
          borderRadius: 10,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 8, fontSize: 13 }}>
            <span style={{ color: "#c4b5fd" }}>{progress.message}</span>
            <span style={{ color: "#94a3b8" }}>Paso {progress.step}/{progress.total}</span>
          </div>
          <div style={{ height: 6, borderRadius: 3, background: "rgba(99,102,241,0.15)", overflow: "hidden" }}>
            <div style={{
              height: "100%", borderRadius: 3,
              background: "linear-gradient(90deg, #6366f1, #818cf8)",
              width: `${progress.pct}%`,
              transition: "width 0.4s ease",
            }} />
          </div>
        </div>
      )}

      {error && <div style={s.error}><strong>Error:</strong> {error}</div>}

      {result?.arca_auto_fetched && (
        <div style={s.autoFetchNotice}>
          Los datos de ARCA fueron descargados automáticamente para este período y guardados en caché.
        </div>
      )}

      {/* Summary cards */}
      {summary && (
        <>
          <div style={s.summaryGrid}>
            <div style={s.card}>
              <div style={s.cardValue}>{summary.arca_total}</div>
              <div style={s.cardLabel}>ARCA Recibidos</div>
            </div>
            <div style={s.card}>
              <div style={s.cardValue}>{summary.colppy_total}</div>
              <div style={s.cardLabel}>Colppy Compras</div>
            </div>
            <div style={{ ...s.card, borderColor: "rgba(34,197,94,0.4)" }}>
              <div style={{ ...s.cardValue, color: "#86efac" }}>{summary.matched}</div>
              <div style={s.cardLabel}>Matched (nro + monto)</div>
            </div>
            <div style={{
              ...s.card,
              borderColor: totalDisc > 0 ? "rgba(251,146,60,0.4)" : "rgba(34,197,94,0.4)",
            }}>
              <div style={{ ...s.cardValue, color: totalDisc > 0 ? "#fb923c" : "#86efac" }}>
                {totalDisc}
              </div>
              <div style={s.cardLabel}>Discrepancias</div>
            </div>
          </div>

          {/* Totals row */}
          <div style={{ ...s.summaryGrid, gridTemplateColumns: "1fr 1fr" }}>
            <div style={s.card}>
              <div style={s.cardValue}>{fmtMoney(summary.arca_importe_total)}</div>
              <div style={s.cardLabel}>Total ARCA (pesos)</div>
            </div>
            <div style={s.card}>
              <div style={s.cardValue}>{fmtMoney(summary.colppy_importe_total)}</div>
              <div style={s.cardLabel}>Total Colppy (pesos)</div>
            </div>
          </div>

          {/* Retenciones info card */}
          {summary.retenciones_cached > 0 && (
            <div style={{
              ...s.card, borderColor: "rgba(147,130,220,0.4)",
              marginBottom: "1rem", textAlign: "left", padding: "0.75rem 1rem",
            }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <div>
                  <span style={{ color: "#c4b5fd", fontWeight: 600 }}>Retenciones vinculadas</span>
                  <span style={{ color: "#94a3b8", fontSize: "0.8rem", marginLeft: 8 }}>
                    {summary.retenciones_cached} certificados en caché
                  </span>
                </div>
                <div style={{ textAlign: "right" }}>
                  <div style={{ color: "#c4b5fd", fontWeight: 600 }}>{fmtMoney(summary.retenciones_total)}</div>
                  <div style={{ color: "#94a3b8", fontSize: "0.75rem" }}>
                    {summary.retenciones_linked} facturas con retenciones
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* Data quality warnings */}
          {((summary.arca_no_number || 0) + (summary.colppy_no_number || 0) +
            (summary.arca_duplicate_number || 0) + (summary.colppy_duplicate_number || 0)) > 0 && (
            <div style={s.warning}>
              <strong>Alertas de calidad de datos:</strong>
              {(summary.arca_no_number || 0) > 0 && <span> {summary.arca_no_number} ARCA sin número.</span>}
              {(summary.colppy_no_number || 0) > 0 && <span> {summary.colppy_no_number} Colppy sin número.</span>}
              {(summary.arca_duplicate_number || 0) > 0 && <span> {summary.arca_duplicate_number} facturas con nro repetido en ARCA (mismo nro aparece 2+ veces).</span>}
              {(summary.colppy_duplicate_number || 0) > 0 && <span> {summary.colppy_duplicate_number} facturas con nro repetido en Colppy (mismo nro aparece 2+ veces).</span>}
            </div>
          )}

          {/* Discrepancies by status group */}
          {Object.entries(grouped).map(([status, items]) => {
            const meta = STATUS_LABELS[status] || { label: status, badge: s.badgeNoData };
            const collapsed = collapsedGroups.has(status);
            return (
              <div key={status} style={s.discSection}>
                <div
                  onClick={() => toggleGroup(status)}
                  style={{ display: "flex", justifyContent: "space-between", alignItems: "center", cursor: "pointer", marginBottom: collapsed ? 0 : 8 }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <span style={{ color: "#64748b" }}>{collapsed ? "\u25b6" : "\u25bc"}</span>
                    <span style={{ ...s.badge, ...meta.badge }}>{meta.label}</span>
                    <span style={{ color: "#64748b", fontSize: "0.8rem" }}>{items.length} registros</span>
                  </div>
                </div>
                {!collapsed && (
                  <div style={{ overflowX: "auto" }}>
                    {status === "duplicate_number" && (
                      <div style={{ fontSize: "0.8rem", color: "#94a3b8", marginBottom: 8, padding: "8px 12px", background: "rgba(251,146,60,0.08)", borderRadius: 6 }}>
                        Estas facturas tienen el mismo número que otra factura ya existente en la misma fuente.
                        Solo la primera aparición se usa para el matching; las repetidas aparecen aquí.
                      </div>
                    )}
                    <table style={s.table}>
                      <thead>
                        <tr>
                          <th style={s.th}>Nro Factura</th>
                          <th style={s.th}>Tipo</th>
                          <th style={s.th}>Fecha</th>
                          <th style={s.th}>Proveedor</th>
                          <th style={s.th}>CUIT</th>
                          <th style={s.th}>Estado</th>
                          <th style={{ ...s.th, textAlign: "right" }}>ARCA</th>
                          <th style={{ ...s.th, textAlign: "right" }}>Colppy</th>
                          {status === "duplicate_number" ? (
                            <th style={s.th}>Duplicado en</th>
                          ) : (
                            <>
                              <th style={{ ...s.th, textAlign: "right" }}>Perc.</th>
                              <th style={{ ...s.th, textAlign: "center" }}>Ret.</th>
                            </>
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {items.map((d, i) => {
                          const key = discKey(d);
                          const isExpanded = expandedRow === key;
                          const nro = d.arca?.numero || d.colppy?.nroFactura || d.duplicate_number || "";
                          const tipo = tipoLetter(d.arca?.tipo_comprobante || d.colppy?.tipo_comprobante);
                          const fecha = d.arca?.fecha_emision || d.colppy?.fechaFactura || "";
                          const prov = d.arca?.denominacion_contraparte || d.colppy?.RazonSocial || "";
                          const cuit = d.arca?.cuit_contraparte || d.colppy?.cuit_proveedor || "";
                          const percTotal = d.colppy?.totalPercepciones || 0;
                          const retCount = d.retenciones?.length || 0;
                          const estadoRec = d.colppy?.estadoFactura || "";
                          return (
                            <Fragment key={key + i}>
                              <tr
                                onClick={() => setExpandedRow(isExpanded ? null : key)}
                                style={{ cursor: "pointer", background: isExpanded ? "rgba(99,102,241,0.08)" : "transparent" }}
                              >
                                <td style={s.td}>{nro}</td>
                                <td style={{ ...s.td, fontSize: "0.8rem" }}>{tipo}</td>
                                <td style={s.td}>{fmtDate(fecha)}</td>
                                <td style={{ ...s.td, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{prov}</td>
                                <td style={{ ...s.td, fontSize: "0.75rem", color: "#64748b" }}>{cuit}</td>
                                <td style={{ ...s.td, fontSize: "0.8rem", ...(ESTADO_COLORS[estadoRec] || {}) }}>{estadoRec || "—"}</td>
                                <td style={{ ...s.td, textAlign: "right" }}>{d.arca ? fmtMoney(d.arca.importe_total) : "—"}</td>
                                <td style={{ ...s.td, textAlign: "right" }}>
                                  {d.colppy ? fmtMoney(d.colppy.totalFactura_pesos) : "—"}
                                </td>
                                {status === "duplicate_number" ? (
                                  <td style={s.td}>
                                    <span style={{
                                      ...s.badge,
                                      background: d.source === "arca" ? "rgba(59,130,246,0.2)" : "rgba(168,85,247,0.2)",
                                      color: d.source === "arca" ? "#93c5fd" : "#c4b5fd",
                                    }}>
                                      {d.source === "arca" ? "ARCA" : "Colppy"}
                                    </span>
                                  </td>
                                ) : (
                                  <>
                                    <td style={{ ...s.td, textAlign: "right", color: percTotal > 0 ? "#c4b5fd" : "#475569" }}>
                                      {percTotal > 0 ? fmtMoney(percTotal) : "—"}
                                    </td>
                                    <td style={{ ...s.td, textAlign: "center" }}>
                                      {retCount > 0 ? (
                                        <span style={{ ...s.badge, background: "rgba(147,130,220,0.2)", color: "#c4b5fd" }}>{retCount}</span>
                                      ) : "—"}
                                    </td>
                                  </>
                                )}
                              </tr>
                              {isExpanded && (
                                <tr>
                                  <td colSpan={status === "duplicate_number" ? 9 : 10} style={{ padding: "8px 4px", background: "rgba(15,23,42,0.5)" }}>
                                    <RecibidoDetail arca={d.arca} colppy={d.colppy} retenciones={d.retenciones} percepcionesDiff={d.percepciones_diff} cuitMatch={d.cuit_match} />
                                  </td>
                                </tr>
                              )}
                            </Fragment>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}

          {/* Matched pairs toggle */}
          {result?.matched_pairs?.length > 0 && (
            <div style={{ marginTop: "1rem" }}>
              <button
                type="button"
                onClick={() => setShowMatched(!showMatched)}
                style={{ ...s.button, background: "#334155", fontSize: "0.85rem", padding: "0.5rem 1rem" }}
              >
                {showMatched ? "Ocultar" : "Mostrar"} {result.matched_pairs.length} facturas matcheadas
              </button>
              {showMatched && (
                <div style={{ ...s.discSection, marginTop: 8 }}>
                  <div style={{ overflowX: "auto", maxHeight: "400px", overflowY: "auto" }}>
                    <table style={s.table}>
                      <thead>
                        <tr>
                          <th style={s.th}>Nro Factura</th>
                          <th style={s.th}>Tipo</th>
                          <th style={s.th}>Fecha</th>
                          <th style={s.th}>Proveedor</th>
                          <th style={s.th}>CUIT</th>
                          <th style={s.th}>Estado</th>
                          <th style={{ ...s.th, textAlign: "right" }}>ARCA</th>
                          <th style={{ ...s.th, textAlign: "right" }}>Colppy</th>
                          <th style={{ ...s.th, textAlign: "right" }}>Perc.</th>
                          <th style={{ ...s.th, textAlign: "center" }}>Ret.</th>
                        </tr>
                      </thead>
                      <tbody>
                        {result.matched_pairs.map((pair, i) => {
                          const key = `matched:${pair.arca?.numero || i}`;
                          const isExpanded = expandedRow === key;
                          const percTotal = pair.colppy?.totalPercepciones || 0;
                          const retCount = pair.retenciones?.length || 0;
                          const estadoMatchedRec = pair.colppy?.estadoFactura || "";
                          return (
                            <Fragment key={key}>
                              <tr
                                onClick={() => setExpandedRow(isExpanded ? null : key)}
                                style={{ cursor: "pointer", background: isExpanded ? "rgba(99,102,241,0.08)" : "transparent" }}
                              >
                                <td style={s.td}>{pair.arca?.numero || pair.colppy?.nroFactura}</td>
                                <td style={{ ...s.td, fontSize: "0.8rem" }}>{tipoLetter(pair.arca?.tipo_comprobante)}</td>
                                <td style={s.td}>{fmtDate(pair.arca?.fecha_emision)}</td>
                                <td style={{ ...s.td, maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                  {pair.arca?.denominacion_contraparte || pair.colppy?.RazonSocial}
                                </td>
                                <td style={{ ...s.td, fontSize: "0.75rem", color: "#64748b" }}>
                                  {pair.arca?.cuit_contraparte || pair.colppy?.cuit_proveedor}
                                </td>
                                <td style={{ ...s.td, fontSize: "0.8rem", ...(ESTADO_COLORS[estadoMatchedRec] || {}) }}>{estadoMatchedRec || "—"}</td>
                                <td style={{ ...s.td, textAlign: "right" }}>{fmtMoney(pair.arca?.importe_total)}</td>
                                <td style={{ ...s.td, textAlign: "right" }}>{fmtMoney(pair.colppy?.totalFactura_pesos)}</td>
                                <td style={{ ...s.td, textAlign: "right", color: percTotal > 0 ? "#c4b5fd" : "#475569" }}>
                                  {percTotal > 0 ? fmtMoney(percTotal) : "—"}
                                </td>
                                <td style={{ ...s.td, textAlign: "center" }}>
                                  {retCount > 0 ? (
                                    <span style={{ ...s.badge, background: "rgba(147,130,220,0.2)", color: "#c4b5fd" }}>{retCount}</span>
                                  ) : "—"}
                                </td>
                              </tr>
                              {isExpanded && (
                                <tr>
                                  <td colSpan={10} style={{ padding: "8px 4px", background: "rgba(15,23,42,0.5)" }}>
                                    <RecibidoDetail arca={pair.arca} colppy={pair.colppy} retenciones={pair.retenciones} percepcionesDiff={pair.percepciones_diff} cuitMatch={pair.cuit_match} />
                                  </td>
                                </tr>
                              )}
                            </Fragment>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Footer */}
          {result && (
            <div style={s.freshness}>
              {result.reconciled_at && (
                <span>Reconciliado: <strong>{result.reconciled_at}</strong></span>
              )}
              {result.arca_fetched_at && (
                <span style={{ marginLeft: 16 }}>ARCA cache: {result.arca_fetched_at}</span>
              )}
              <span style={{ marginLeft: 16 }}>Colppy: en vivo</span>
              {result.proveedores_count > 0 && (
                <span style={{ marginLeft: 16 }}>{result.proveedores_count} proveedores</span>
              )}
              {(summary?.colppy_anuladas || 0) > 0 && (
                <span style={{ marginLeft: 16, color: "#f87171" }}>
                  {summary.colppy_anuladas} factura(s) anulada(s) en Colppy
                </span>
              )}
            </div>
          )}
        </>
      )}
    </>
  );
}


/* ── Recibido Detail Panel (expandable row) ──────────────────────────── */

function RecibidoDetail({ arca, colppy, retenciones, percepcionesDiff, cuitMatch }) {
  const detailStyle = {
    display: "flex", flexDirection: "column", gap: 12, padding: "12px 16px",
    background: "rgba(30,41,59,0.7)", borderRadius: 8, fontSize: "0.8rem",
  };
  const colsStyle = { display: "flex", gap: 24 };
  const colStyle = { flex: 1, minWidth: 0 };
  const headStyle = { color: "#94a3b8", fontWeight: 600, marginBottom: 6, fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: 0.5 };
  const rowS = { display: "flex", justifyContent: "space-between", padding: "2px 0", borderBottom: "1px solid rgba(148,163,184,0.08)" };
  const labelS = { color: "#94a3b8" };
  const valS = { color: "#e2e8f0", fontFamily: "monospace", fontSize: "0.78rem" };

  const DetailRow = ({ label, value, highlight, warn }) => (
    <div style={rowS}>
      <span style={labelS}>{label}</span>
      <span style={{ ...valS, ...(highlight ? { color: "#fbbf24" } : {}), ...(warn ? { color: "#fb923c" } : {}) }}>{value ?? "—"}</span>
    </div>
  );

  return (
    <div style={detailStyle}>
      {/* Side-by-side ARCA / Colppy */}
      <div style={colsStyle}>
        {arca && (
          <div style={colStyle}>
            <div style={headStyle}>ARCA (Fiscal)</div>
            <DetailRow label="CAE" value={arca.cod_autorizacion} />
            <DetailRow label="Número" value={arca.numero} />
            <DetailRow label="Fecha" value={arca.fecha_emision} />
            <DetailRow label="Tipo" value={arca.tipo_comprobante} />
            <DetailRow label="Punto Venta" value={arca.punto_venta} />
            <DetailRow label="CUIT contraparte" value={arca.cuit_contraparte} />
            <DetailRow label="Contraparte" value={arca.denominacion_contraparte} />
            <DetailRow label="Moneda" value={arca.moneda} />
            {arca.neto_gravado != null && arca.neto_gravado > 0 && <DetailRow label="Neto gravado" value={fmtMoney(arca.neto_gravado)} />}
            {arca.neto_no_gravado != null && arca.neto_no_gravado > 0 && <DetailRow label="Neto no gravado" value={fmtMoney(arca.neto_no_gravado)} />}
            {arca.exento != null && arca.exento > 0 && <DetailRow label="Exento" value={fmtMoney(arca.exento)} />}
            {arca.iva_total != null && arca.iva_total > 0 && <DetailRow label="IVA total" value={fmtMoney(arca.iva_total)} />}
            {arca.otros_tributos != null && arca.otros_tributos > 0 && <DetailRow label="Otros tributos" value={fmtMoney(arca.otros_tributos)} />}
            <DetailRow label="Importe total" value={fmtMoney(arca.importe_total)} highlight />
            {arca.tipo_cambio != null && arca.tipo_cambio > 0 && arca.tipo_cambio !== 1 && (
              <DetailRow label="Tipo cambio" value={arca.tipo_cambio.toFixed(4)} />
            )}
          </div>
        )}
        {colppy && (
          <div style={colStyle}>
            <div style={headStyle}>Colppy (ERP)</div>
            <DetailRow label="Número" value={colppy.nroFactura} />
            <DetailRow label="Fecha" value={colppy.fechaFactura} />
            <DetailRow label="Razón Social" value={colppy.RazonSocial} />
            <DetailRow label="CUIT proveedor" value={colppy.cuit_proveedor} />
            <DetailRow label="Estado" value={colppy.estadoFactura} />
            <DetailRow label="Neto gravado" value={fmtMoney(colppy.netoGravado)} />
            <DetailRow label="Neto no gravado" value={fmtMoney(colppy.netoNoGravado)} />
            {colppy.iva21 > 0 && <DetailRow label="IVA 21%" value={fmtMoney(colppy.iva21)} />}
            {colppy.iva105 > 0 && <DetailRow label="IVA 10.5%" value={fmtMoney(colppy.iva105)} />}
            {colppy.iva27 > 0 && <DetailRow label="IVA 27%" value={fmtMoney(colppy.iva27)} />}
            <DetailRow label="Total IVA" value={fmtMoney(colppy.totalIVA)} />
            {colppy.percepcionIVA > 0 && <DetailRow label="Percepción IVA" value={fmtMoney(colppy.percepcionIVA)} />}
            {colppy.percepcionIIBB > 0 && <DetailRow label="Percepción IIBB" value={fmtMoney(colppy.percepcionIIBB)} />}
            {colppy.percepcionIIBB1 > 0 && <DetailRow label="Percepción IIBB1" value={fmtMoney(colppy.percepcionIIBB1)} />}
            {colppy.percepcionIIBB2 > 0 && <DetailRow label="Percepción IIBB2" value={fmtMoney(colppy.percepcionIIBB2)} />}
            {colppy.IIBBLocal > 0 && <DetailRow label="IIBB Local" value={fmtMoney(colppy.IIBBLocal)} />}
            {colppy.IIBBOtro > 0 && <DetailRow label="IIBB Otro" value={fmtMoney(colppy.IIBBOtro)} />}
            {colppy.totalPercepciones > 0 && <DetailRow label="Total percepciones" value={fmtMoney(colppy.totalPercepciones)} />}
            <DetailRow label="Total factura" value={fmtMoney(colppy.totalFactura_pesos)} highlight />
            {colppy.valorCambio > 0 && colppy.valorCambio !== 1 && (
              <DetailRow label="Tipo cambio" value={colppy.valorCambio.toFixed(4)} />
            )}
            {colppy.fechaPago && <DetailRow label="Fecha pago" value={colppy.fechaPago} />}
          </div>
        )}
        {!arca && !colppy && <span style={{ color: "#64748b" }}>Sin datos de detalle</span>}
      </div>

      {/* Percepciones match indicator */}
      {percepcionesDiff != null && (
        <div style={{
          padding: "6px 12px", borderRadius: 6, fontSize: "0.78rem",
          background: Math.abs(percepcionesDiff) < 0.02
            ? "rgba(34,197,94,0.1)" : "rgba(251,146,60,0.1)",
          border: `1px solid ${Math.abs(percepcionesDiff) < 0.02
            ? "rgba(34,197,94,0.3)" : "rgba(251,146,60,0.3)"}`,
          color: Math.abs(percepcionesDiff) < 0.02 ? "#86efac" : "#fb923c",
        }}>
          {Math.abs(percepcionesDiff) < 0.02
            ? "Percepciones: ARCA otros_tributos = Colppy percepciones"
            : `Percepciones: diferencia de ${fmtMoney(Math.abs(percepcionesDiff))} (ARCA otros_tributos ${percepcionesDiff > 0 ? ">" : "<"} Colppy percepciones)`
          }
        </div>
      )}

      {/* CUIT match indicator */}
      {cuitMatch != null && !cuitMatch && (
        <div style={{
          padding: "6px 12px", borderRadius: 6, fontSize: "0.78rem",
          background: "rgba(251,146,60,0.1)", border: "1px solid rgba(251,146,60,0.3)",
          color: "#fb923c",
        }}>
          CUIT mismatch: ARCA {arca?.cuit_contraparte} vs Colppy {colppy?.cuit_proveedor}
        </div>
      )}

      {/* Linked retenciones */}
      {retenciones && retenciones.length > 0 && (
        <div style={{
          padding: "8px 12px", borderRadius: 6,
          background: "rgba(147,130,220,0.08)", border: "1px solid rgba(147,130,220,0.25)",
        }}>
          <div style={{ color: "#c4b5fd", fontWeight: 600, fontSize: "0.75rem", textTransform: "uppercase", marginBottom: 4 }}>
            Retenciones vinculadas ({retenciones.length})
          </div>
          {retenciones.map((r, i) => (
            <div key={i} style={{
              display: "flex", justifyContent: "space-between", padding: "3px 0",
              borderBottom: i < retenciones.length - 1 ? "1px solid rgba(148,163,184,0.08)" : "none",
              fontSize: "0.78rem",
            }}>
              <span style={{ color: "#94a3b8" }}>
                Cert #{r.numeroCertificado} — {r.descripcionOperacion || `Imp. ${r.impuestoRetenido}`} (Rég. {r.codigoRegimen})
              </span>
              <span style={{ color: "#c4b5fd", fontFamily: "monospace" }}>{fmtMoney(r.importeRetenido)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}


/* ═══════════════════════════════════════════════════════════════════════════
   Retenciones ↔ Comprobantes Recibidos (original)
   ═══════════════════════════════════════════════════════════════════════════ */

function RetencionesReconciliation() {
  const [representados, setRepresentados] = useState([]);
  const [selectedRep, setSelectedRep] = useState(null);
  const [loadingRep, setLoadingRep] = useState(true);

  const [fechaDesde, setFechaDesde] = useState("2025-01-01");
  const [fechaHasta, setFechaHasta] = useState("2025-12-31");

  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [expanded, setExpanded] = useState({});

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const res = await fetch(`${API_BASE}/api/arca/representados`);
        const json = await res.json();
        if (cancelled) return;
        if (json.success && json.representados?.length > 0) {
          setRepresentados(json.representados);
          setSelectedRep(json.representados[0]);
        }
      } catch (err) {
        if (!cancelled) setError(err.message);
      } finally {
        if (!cancelled) setLoadingRep(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!selectedRep) return;
    setLoading(true);
    setResult(null);
    setError(null);
    try {
      const params = new URLSearchParams({
        cuit: selectedRep.cuit,
        ...(fechaDesde && { fecha_desde: fechaDesde }),
        ...(fechaHasta && { fecha_hasta: fechaHasta }),
      });
      const res = await fetch(`${API_BASE}/api/arca/retenciones/reconcile?${params}`);
      const json = await res.json();
      if (json.success) {
        setResult(json);
      } else {
        setError(json.error || "Error en reconciliación");
      }
    } catch (err) {
      setError(err.message || "Error de conexión");
    } finally {
      setLoading(false);
    }
  };

  const togglePeriodo = (periodo) => {
    setExpanded((prev) => ({ ...prev, [periodo]: !prev[periodo] }));
  };

  const summary = result?.summary;
  const coverage = result?.comprobantes_data_coverage;

  return (
    <>
      <p style={s.subtitle}>
        Verificar retenciones/percepciones contra comprobantes recibidos (caché local).
      </p>

      <form onSubmit={handleSubmit} style={s.form}>
        <div style={s.field}>
          <label style={s.label}>Representado</label>
          <select
            value={selectedRep ? selectedRep.cuit : ""}
            onChange={(e) => {
              setSelectedRep(representados.find((r) => r.cuit === e.target.value) || null);
            }}
            style={s.select}
            disabled={loading || loadingRep}
          >
            {loadingRep ? (
              <option value="">Cargando representados...</option>
            ) : representados.length === 0 ? (
              <option value="">No hay representados en caché</option>
            ) : (
              representados.map((r) => (
                <option key={r.cuit} value={r.cuit}>
                  {r.nombre} - {r.cuit}
                </option>
              ))
            )}
          </select>
        </div>

        <div style={s.dateRow}>
          <div style={s.field}>
            <label style={s.label}>Desde</label>
            <input type="date" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} style={s.input} />
          </div>
          <div style={s.field}>
            <label style={s.label}>Hasta</label>
            <input type="date" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} style={s.input} />
          </div>
        </div>

        <button type="submit" disabled={loading || !selectedRep} style={s.button}>
          {loading ? "Verificando..." : "Verificar"}
        </button>
      </form>

      {error && <div style={s.error}><strong>Error:</strong> {error}</div>}

      {coverage && coverage.status === "none" && result && (
        <div style={s.warning}>
          No hay comprobantes recibidos en caché. Los estados mostrarán "Sin datos".
        </div>
      )}
      {coverage && coverage.status === "partial" && result && (
        <div style={s.warning}>
          Comprobantes en caché: <strong>{coverage.min}</strong> a <strong>{coverage.max}</strong>.
          Períodos fuera de este rango mostrarán "Sin datos".
        </div>
      )}

      {summary && (
        <div style={s.summaryGrid}>
          <div style={s.card}>
            <div style={s.cardValue}>{fmtMoney(summary.total_positivo)}</div>
            <div style={s.cardLabel}>Total Percepciones</div>
          </div>
          <div style={{ ...s.card, borderColor: "rgba(251,146,60,0.4)" }}>
            <div style={{ ...s.cardValue, color: "#fb923c" }}>{fmtMoney(summary.total_notas_credito)}</div>
            <div style={s.cardLabel}>Notas de Crédito</div>
          </div>
          <div style={{ ...s.card, borderColor: "rgba(34,197,94,0.4)" }}>
            <div style={{ ...s.cardValue, color: "#86efac" }}>{fmtMoney(summary.total_neto_para_ddjj)}</div>
            <div style={s.cardLabel}>Neto para DDJJ</div>
          </div>
          <div style={s.card}>
            <div style={s.cardValue}>{summary.total_retenciones} <span style={{ fontSize: "0.75rem", color: "#94a3b8" }}>registros</span></div>
            <div style={s.cardLabel}>
              {summary.grupos_matched > 0 && <span style={{ color: "#86efac" }}>{summary.grupos_matched} con datos</span>}
              {summary.grupos_orphan > 0 && <span style={{ color: "#fb923c" }}> {summary.grupos_orphan} sin match</span>}
              {summary.grupos_no_data > 0 && <span style={{ color: "#94a3b8" }}> {summary.grupos_no_data} sin datos</span>}
            </div>
          </div>
        </div>
      )}

      {result?.periodos?.map((p) => {
        const isOpen = expanded[p.periodo] !== false;
        const isNegative = p.total_retenido_mes < 0;
        return (
          <div key={p.periodo} style={s.periodoCard}>
            <div style={s.periodoHeader} onClick={() => togglePeriodo(p.periodo)}>
              <div style={s.periodoLeft}>
                <span style={s.periodoChevron}>{isOpen ? "▾" : "▸"}</span>
                <span style={s.periodoName}>{p.periodo}</span>
              </div>
              <div style={{ ...s.periodoTotal, color: isNegative ? "#fb923c" : "#86efac" }}>
                {fmtMoney(p.total_retenido_mes)}
              </div>
            </div>
            {isOpen && p.agentes.map((ag) => (
              <div key={ag.cuit_agente} style={s.agenteBlock}>
                <div style={s.agenteHeader}>
                  <div>
                    <strong style={{ color: "#f8fafc" }}>{ag.nombre_agente}</strong>
                    <span style={s.agenteCuit}> ({ag.cuit_agente})</span>
                  </div>
                  <span style={{
                    ...s.badge,
                    ...(ag.match_status === "matched" ? s.badgeMatched
                      : ag.match_status === "orphan" ? s.badgeOrphan : s.badgeNoData),
                  }}>
                    {ag.match_status === "matched" ? "Con comprobante"
                      : ag.match_status === "orphan" ? "Sin match agente" : "Sin datos"}
                  </span>
                </div>
                <table style={s.table}>
                  <thead>
                    <tr>
                      <th style={s.th}>Fecha</th>
                      <th style={s.th}>Certificado</th>
                      <th style={s.th}>Operación</th>
                      <th style={s.th}>Régimen</th>
                      <th style={{ ...s.th, textAlign: "right" }}>Importe</th>
                    </tr>
                  </thead>
                  <tbody>
                    {ag.retenciones.map((r, i) => (
                      <tr key={i}>
                        <td style={s.td}>{fmtDate(r.fechaRetencion)}</td>
                        <td style={s.td}>{r.numeroCertificado}</td>
                        <td style={s.td}>{r.descripcionOperacion}</td>
                        <td style={s.td}>{r.codigoRegimen}</td>
                        <td style={{ ...s.td, textAlign: "right", color: r.importeRetenido < 0 ? "#fb923c" : "#86efac" }}>
                          {fmtMoney(r.importeRetenido)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr>
                      <td colSpan={4} style={{ ...s.td, fontWeight: 600, color: "#f8fafc" }}>Total agente</td>
                      <td style={{ ...s.td, textAlign: "right", fontWeight: 600, color: ag.total_retenido < 0 ? "#fb923c" : "#86efac" }}>
                        {fmtMoney(ag.total_retenido)}
                      </td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            ))}
          </div>
        );
      })}

      {result?.success && (
        <div style={s.footer}>
          Régimen 594 / Impuesto 217 — Percepciones de Ganancias para DDJJ.
        </div>
      )}
    </>
  );
}


/* ── Invoice Detail Panel (expandable row) ────────────────────────── */

function InvoiceDetail({ arca, colppy }) {
  const detailStyle = {
    display: "flex", gap: 24, padding: "12px 16px",
    background: "rgba(30,41,59,0.7)", borderRadius: 8, fontSize: "0.8rem",
  };
  const colStyle = { flex: 1, minWidth: 0 };
  const headStyle = { color: "#94a3b8", fontWeight: 600, marginBottom: 6, fontSize: "0.75rem", textTransform: "uppercase", letterSpacing: 0.5 };
  const rowS = { display: "flex", justifyContent: "space-between", padding: "2px 0", borderBottom: "1px solid rgba(148,163,184,0.08)" };
  const label = { color: "#94a3b8" };
  const val = { color: "#e2e8f0", fontFamily: "monospace", fontSize: "0.78rem" };

  const DetailRow = ({ label: l, value: v, highlight }) => (
    <div style={rowS}>
      <span style={label}>{l}</span>
      <span style={{ ...val, ...(highlight ? { color: "#fbbf24" } : {}) }}>{v ?? "—"}</span>
    </div>
  );

  return (
    <div style={detailStyle}>
      {arca && (
        <div style={colStyle}>
          <div style={headStyle}>ARCA (Fiscal)</div>
          <DetailRow label="CAE" value={arca.cod_autorizacion} />
          <DetailRow label="Número" value={arca.numero} />
          <DetailRow label="Fecha" value={arca.fecha_emision} />
          <DetailRow label="Tipo" value={arca.tipo_comprobante} />
          <DetailRow label="Punto Venta" value={arca.punto_venta} />
          <DetailRow label="CUIT contraparte" value={arca.cuit_contraparte} />
          <DetailRow label="Tipo doc." value={arca.tipo_doc_contraparte} />
          <DetailRow label="Contraparte" value={arca.denominacion_contraparte} />
          <DetailRow label="Moneda" value={arca.moneda} />
          {arca.neto_gravado != null && arca.neto_gravado > 0 && (
            <DetailRow label="Neto gravado" value={fmtMoney(arca.neto_gravado)} />
          )}
          {arca.neto_no_gravado != null && arca.neto_no_gravado > 0 && (
            <DetailRow label="Neto no gravado" value={fmtMoney(arca.neto_no_gravado)} />
          )}
          {arca.exento != null && arca.exento > 0 && (
            <DetailRow label="Exento" value={fmtMoney(arca.exento)} />
          )}
          {arca.iva_total != null && arca.iva_total > 0 && (
            <DetailRow label="IVA total" value={fmtMoney(arca.iva_total)} />
          )}
          {arca.otros_tributos != null && arca.otros_tributos > 0 && (
            <DetailRow label="Otros tributos" value={fmtMoney(arca.otros_tributos)} />
          )}
          <DetailRow label="Importe total" value={fmtMoney(arca.importe_total)} highlight />
          {arca.tipo_cambio != null && arca.tipo_cambio > 0 && arca.tipo_cambio !== 1 && (
            <DetailRow label="Tipo cambio" value={arca.tipo_cambio.toFixed(4)} />
          )}
        </div>
      )}
      {colppy && (
        <div style={colStyle}>
          <div style={headStyle}>Colppy (ERP)</div>
          <DetailRow label="CAE" value={colppy.cae} />
          <DetailRow label="Número" value={colppy.nroFactura} />
          <DetailRow label="Fecha" value={colppy.fechaFactura} />
          <DetailRow label="Razón Social" value={colppy.RazonSocial} />
          <DetailRow label="Estado" value={colppy.estadoFactura} />
          <DetailRow label="Neto gravado" value={fmtMoney(colppy.netoGravado)} />
          <DetailRow label="Neto no gravado" value={fmtMoney(colppy.netoNoGravado)} />
          {colppy.iva21 > 0 && <DetailRow label="IVA 21%" value={fmtMoney(colppy.iva21)} />}
          {colppy.iva105 > 0 && <DetailRow label="IVA 10.5%" value={fmtMoney(colppy.iva105)} />}
          {colppy.iva27 > 0 && <DetailRow label="IVA 27%" value={fmtMoney(colppy.iva27)} />}
          <DetailRow label="Total IVA" value={fmtMoney(colppy.totalIVA)} />
          {colppy.percepcionIVA > 0 && <DetailRow label="Percepción IVA" value={fmtMoney(colppy.percepcionIVA)} />}
          {colppy.percepcionIIBB > 0 && <DetailRow label="Percepción IIBB" value={fmtMoney(colppy.percepcionIIBB)} />}
          <DetailRow label="Total factura" value={fmtMoney(colppy.totalFactura_pesos)} highlight />
          {colppy.valorCambio > 0 && colppy.valorCambio !== 1 && (
            <DetailRow label="Tipo cambio" value={colppy.valorCambio.toFixed(4)} />
          )}
          {colppy.fechaPago && <DetailRow label="Fecha pago" value={colppy.fechaPago} />}
        </div>
      )}
      {!arca && !colppy && <span style={{ color: "#64748b" }}>Sin datos de detalle</span>}
    </div>
  );
}


/* ── Chat Search Panel ──────────────────────────────────────────────── */

function ChatPanel({ messages, input, onInputChange, onSend, onClear, loading, open, onToggle, scope, onScopeChange }) {
  const messagesEndRef = { current: null };

  useEffect(() => {
    if (messagesEndRef.current) {
      messagesEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [messages]);

  // Strip the matched_caes JSON block from displayed text
  const cleanContent = (text) =>
    (text || "").replace(/```json\s*\{[\s\S]*?"matched_caes"[\s\S]*?\}\s*```/g, "").trim();

  return (
    <div style={s.chatPanel}>
      {/* Header — always visible */}
      <div style={s.chatHeader} onClick={onToggle}>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <span style={{ fontSize: "1rem", filter: "grayscale(1)" }}>&#128269;</span>
          <span style={{ color: "#f8fafc", fontWeight: 500, fontSize: "0.9rem" }}>
            Buscar con IA
          </span>
          {messages.length > 0 && (
            <span style={{ ...s.badge, background: "rgba(59,130,246,0.2)", color: "#93c5fd" }}>
              {messages.filter((m) => m.role === "user").length} consulta(s)
            </span>
          )}
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
          <div style={{ display: "flex", gap: "0.25rem" }} onClick={(e) => e.stopPropagation()}>
            {["discrepancies", "all"].map((sc) => (
              <button
                key={sc}
                type="button"
                onClick={() => onScopeChange(sc)}
                style={{
                  ...s.modeBtn, fontSize: "0.7rem", padding: "0.15rem 0.5rem",
                  ...(scope === sc ? s.modeBtnActive : {}),
                }}
              >
                {sc === "discrepancies" ? "Discrepancias" : "Todos"}
              </button>
            ))}
          </div>
          <span style={{ color: "#64748b", fontSize: "0.8rem" }}>{open ? "▾" : "▸"}</span>
        </div>
      </div>

      {/* Expanded: messages + input */}
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
                    {cleanContent(msg.content) || (loading && i === messages.length - 1 ? "..." : "")}
                  </div>
                  {msg.caes?.length > 0 && (
                    <div style={{ fontSize: "0.7rem", color: "#64748b", marginTop: "0.3rem" }}>
                      {msg.caes.length} factura(s) resaltada(s) en la tabla
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
              placeholder='ej: "facturas de ACME sin match", "montos > $100.000"'
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


/* ── Inline Acknowledge Dropdown ──────────────────────────────────────── */

function AckDropdown({ onConfirm, onCancel }) {
  const [category, setCategory] = useState("revisado");
  const [reason, setReason] = useState("");

  return (
    <div style={s.ackDropdown} onClick={(e) => e.stopPropagation()}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.3rem", marginBottom: "0.4rem" }}>
        {Object.entries(CATEGORY_META).map(([key, meta]) => (
          <button
            key={key}
            type="button"
            onClick={() => setCategory(key)}
            style={{
              ...s.badge,
              background: category === key ? meta.bg : "transparent",
              color: category === key ? meta.color : "#64748b",
              border: `1px solid ${category === key ? meta.color : "#334155"}`,
              cursor: "pointer",
              fontSize: "0.7rem",
            }}
          >
            {meta.label}
          </button>
        ))}
      </div>
      <input
        type="text"
        placeholder="Motivo (opcional)"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        style={{ ...s.input, padding: "0.3rem 0.5rem", fontSize: "0.75rem", marginBottom: "0.4rem" }}
        onKeyDown={(e) => { if (e.key === "Enter") onConfirm(category, reason); if (e.key === "Escape") onCancel(); }}
        autoFocus
      />
      <div style={{ display: "flex", gap: "0.3rem", justifyContent: "flex-end" }}>
        <button type="button" onClick={onCancel} style={{ ...s.ackBtn, color: "#64748b" }}>
          Cancelar
        </button>
        <button type="button" onClick={() => onConfirm(category, reason)} style={{ ...s.ackBtn, color: "#86efac" }}>
          Confirmar
        </button>
      </div>
    </div>
  );
}


/* ── Helpers ──────────────────────────────────────────────────────────── */

const fmtMoney = (n) =>
  n != null ? `$${Number(n).toLocaleString("es-AR", { minimumFractionDigits: 2 })}` : "-";

const fmtDate = (iso) => {
  if (!iso) return "-";
  const [y, m, d] = iso.slice(0, 10).split("-");
  return `${d}/${m}/${y}`;
};

/** Extract comprobante letter (A/B/C/E/M/T) from tipo_comprobante string.
 *  Matches a standalone single letter at the end: "Factura A" → "A", "NC B" → "B".
 *  Handles edge cases: "Tique" → "Tique", "Factura de Exportación" → "Exp" */
const tipoLetter = (tipo) => {
  if (!tipo) return "";
  // Match a standalone letter at the end (preceded by space)
  const m = tipo.trim().match(/\s([A-Z])\s*$/);
  if (m) return m[1];
  // Known non-letter types → short abbreviations
  if (/exportaci/i.test(tipo)) return "Exp";
  if (/^tique$/i.test(tipo.trim())) return "Tiq";
  return tipo;
};

const ESTADO_COLORS = {
  Activa: { color: "#86efac" },
  Anulada: { color: "#f87171" },
  "Aplicada parcial": { color: "#fbbf24" },
};


/* ── Styles ──────────────────────────────────────────────────────────── */

const s = {
  page: { padding: "1.5rem", maxWidth: "900px", margin: "0 auto" },
  header: { marginBottom: "1rem", textAlign: "center" },
  title: { margin: 0, fontSize: "1.5rem", fontWeight: 600, color: "#f8fafc" },
  subtitle: { margin: "0.5rem 0 0", fontSize: "0.9rem", color: "#94a3b8", textAlign: "center" },

  modeToggle: {
    display: "flex", gap: "0.5rem", justifyContent: "center", marginTop: "0.75rem",
  },
  modeBtn: {
    padding: "0.4rem 1rem", fontSize: "0.85rem", borderRadius: "6px",
    border: "1px solid #334155", background: "transparent",
    color: "#94a3b8", cursor: "pointer",
  },
  modeBtnActive: {
    background: "rgba(59,130,246,0.2)", borderColor: "#3b82f6", color: "#93c5fd",
  },

  form: { display: "flex", flexDirection: "column", gap: "1rem", marginBottom: "1.5rem" },
  field: { display: "flex", flexDirection: "column", gap: "0.35rem", flex: 1 },
  label: { fontSize: "0.85rem", fontWeight: 500, color: "#cbd5e1" },
  select: {
    padding: "0.75rem 1rem", fontSize: "1rem", borderRadius: "8px",
    border: "1px solid #334155", background: "#1e293b", color: "#f8fafc",
    outline: "none", width: "100%",
  },
  input: {
    padding: "0.75rem 1rem", fontSize: "1rem", borderRadius: "8px",
    border: "1px solid #334155", background: "#1e293b", color: "#f8fafc",
    outline: "none", width: "100%", boxSizing: "border-box",
  },
  dateRow: { display: "flex", gap: "1rem" },
  button: {
    padding: "0.85rem 1.25rem", fontSize: "1rem", fontWeight: 600,
    borderRadius: "8px", border: "none",
    background: "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
    color: "white", cursor: "pointer",
  },

  error: {
    padding: "1rem", borderRadius: "8px",
    background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.4)",
    color: "#fca5a5", marginBottom: "1rem",
  },
  warning: {
    padding: "1rem", borderRadius: "8px",
    background: "rgba(251,146,60,0.12)", border: "1px solid rgba(251,146,60,0.35)",
    color: "#fed7aa", marginBottom: "1rem", fontSize: "0.9rem",
  },
  autoFetchBanner: {
    padding: "1rem", borderRadius: "8px",
    background: "rgba(59,130,246,0.15)", border: "1px solid rgba(59,130,246,0.4)",
    color: "#93c5fd", marginBottom: "1rem", fontSize: "0.9rem", textAlign: "center",
  },
  autoFetchNotice: {
    padding: "0.75rem 1rem", borderRadius: "8px",
    background: "rgba(34,197,94,0.1)", border: "1px solid rgba(34,197,94,0.3)",
    color: "#86efac", marginBottom: "1rem", fontSize: "0.85rem", textAlign: "center",
  },
  successBanner: {
    padding: "1rem", borderRadius: "8px",
    background: "rgba(34,197,94,0.15)", border: "1px solid rgba(34,197,94,0.4)",
    color: "#86efac", textAlign: "center", fontWeight: 600,
  },

  summaryGrid: {
    display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))",
    gap: "0.75rem", marginBottom: "1rem",
  },
  card: {
    padding: "1rem", borderRadius: "8px",
    background: "rgba(30,41,59,0.6)", border: "1px solid #334155",
    textAlign: "center",
  },
  cardValue: { fontSize: "1.25rem", fontWeight: 600, color: "#f8fafc" },
  cardLabel: { fontSize: "0.8rem", color: "#94a3b8", marginTop: "0.25rem" },

  discSection: {
    marginTop: "1rem", padding: "1rem", borderRadius: "8px",
    background: "rgba(30,41,59,0.4)", border: "1px solid #334155",
  },

  periodoCard: {
    marginBottom: "1rem", borderRadius: "8px",
    background: "rgba(30,41,59,0.4)", border: "1px solid #334155",
    overflow: "hidden",
  },
  periodoHeader: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    padding: "0.75rem 1rem", cursor: "pointer", background: "rgba(30,41,59,0.6)",
  },
  periodoLeft: { display: "flex", alignItems: "center", gap: "0.5rem" },
  periodoChevron: { color: "#64748b", fontSize: "0.9rem" },
  periodoName: { fontWeight: 600, color: "#f8fafc", fontSize: "1rem" },
  periodoTotal: { fontWeight: 600, fontSize: "1rem" },

  agenteBlock: { padding: "0.75rem 1rem", borderTop: "1px solid #1e293b" },
  agenteHeader: {
    display: "flex", justifyContent: "space-between", alignItems: "center",
    marginBottom: "0.5rem",
  },
  agenteCuit: { fontSize: "0.8rem", color: "#64748b" },

  badge: {
    fontSize: "0.75rem", padding: "0.2rem 0.6rem", borderRadius: "12px", fontWeight: 500,
  },
  badgeMatched: { background: "rgba(34,197,94,0.2)", color: "#86efac" },
  badgeOrphan: { background: "rgba(251,146,60,0.2)", color: "#fb923c" },
  badgeNoData: { background: "rgba(100,116,139,0.2)", color: "#94a3b8" },
  badgeOnlyArca: { background: "rgba(239,68,68,0.2)", color: "#fca5a5" },
  badgeOnlyColppy: { background: "rgba(59,130,246,0.2)", color: "#93c5fd" },
  badgeMismatch: { background: "rgba(251,146,60,0.2)", color: "#fb923c" },
  badgeCurrency: { background: "rgba(147,130,220,0.2)", color: "#c4b5fd" },

  table: { width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" },
  th: {
    textAlign: "left", padding: "0.4rem 0.5rem", color: "#64748b",
    borderBottom: "1px solid #334155", fontSize: "0.75rem", fontWeight: 500,
    position: "sticky", top: 0, zIndex: 2, background: "#1e293b",
  },
  td: {
    padding: "0.4rem 0.5rem", color: "#cbd5e1",
    borderBottom: "1px solid rgba(51,65,85,0.4)",
  },

  ackBtn: {
    fontSize: "0.7rem", padding: "0.2rem 0.5rem", borderRadius: "4px",
    border: "1px solid #334155", background: "transparent",
    color: "#94a3b8", cursor: "pointer", whiteSpace: "nowrap",
  },
  ackDropdown: {
    position: "absolute", right: 0, top: "100%", zIndex: 10,
    background: "#1e293b", border: "1px solid #334155", borderRadius: "8px",
    padding: "0.5rem", minWidth: "220px", boxShadow: "0 4px 12px rgba(0,0,0,0.4)",
  },

  footer: {
    marginTop: "1.5rem", padding: "1rem", borderRadius: "8px",
    background: "rgba(30,41,59,0.3)", border: "1px solid #1e293b",
    fontSize: "0.8rem", color: "#64748b", textAlign: "center",
  },
  freshness: {
    marginTop: "1.5rem", padding: "0.75rem 1rem", borderRadius: "8px",
    background: "rgba(30,41,59,0.4)", border: "1px solid rgba(51,65,85,0.6)",
    fontSize: "0.8rem", color: "#94a3b8", display: "flex", flexWrap: "wrap",
    alignItems: "center", gap: "4px 0",
  },
  // Chat panel
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
};
