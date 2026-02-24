/**
 * ComprobantesPage — Browse comprobantes recibidos/emitidos from SQLite cache.
 * Choose representado (CUIT), toggle direction, view table, click for details.
 */
import { useState, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "";

function formatDate(iso) {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("es-AR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  } catch {
    return iso;
  }
}

function formatCurrency(amount, moneda) {
  if (amount == null) return "-";
  const num = typeof amount === "string" ? parseFloat(amount) : amount;
  if (isNaN(num)) return amount;
  const symbol = moneda === "USD" ? "US$" : "$";
  return `${symbol} ${num.toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/* ── Detail View ──────────────────────────────────────────────────────── */

function ComprobanteDetail({ comprobante, onBack }) {
  const c = comprobante;
  const rows = [
    ["Fecha Emisión", c.fecha_emision_display || formatDate(c.fecha_emision)],
    ["Tipo Comprobante", c.tipo_comprobante || "-"],
    ["Código Tipo", c.tipo_comprobante_codigo],
    ["Punto de Venta", c.punto_venta],
    ["Número Desde", c.numero_desde],
    ["Número Hasta", c.numero_hasta],
    ["Número", c.numero],
    ["CAE", c.cod_autorizacion || "-"],
    ["Tipo Doc. Contraparte", c.tipo_doc_contraparte],
    ["CUIT Contraparte", c.cuit_contraparte],
    ["Denominación Contraparte", c.denominacion_contraparte],
    ["Moneda", c.moneda],
    ["Importe Total", c.importe_total_display || formatCurrency(c.importe_total, c.moneda)],
  ];

  return (
    <div style={styles.detail}>
      <button type="button" onClick={onBack} style={styles.backBtn}>
        ← Volver a la lista
      </button>
      <h3 style={styles.detailTitle}>
        {c.tipo_comprobante} — {c.numero}
      </h3>
      <table style={styles.detailTable}>
        <tbody>
          {rows.map(([label, value]) => (
            <tr key={label}>
              <td style={styles.detailLabel}>{label}</td>
              <td style={styles.detailValue}>{value ?? "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── Main Page ────────────────────────────────────────────────────────── */

export default function ComprobantesPage() {
  const [representados, setRepresentados] = useState([]);
  const [selectedRep, setSelectedRep] = useState(null);
  const [loadingRep, setLoadingRep] = useState(true);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [direccion, setDireccion] = useState("R"); // R = recibidos, E = emitidos
  const [selected, setSelected] = useState(null); // selected comprobante for detail

  // Load representados on mount (same pattern as NotificationsPage)
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
        } else {
          const refresh = await fetch(`${API_BASE}/api/arca/representados/refresh`);
          const refreshJson = await refresh.json();
          if (cancelled) return;
          if (refreshJson.success && refreshJson.representados?.length > 0) {
            setRepresentados(refreshJson.representados);
            setSelectedRep(refreshJson.representados[0]);
          } else if (refreshJson.error) {
            setError(refreshJson.error);
          }
        }
      } catch (err) {
        if (!cancelled) setError(err.message || "No se pudo conectar al backend");
      } finally {
        if (!cancelled) setLoadingRep(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  // Clear data when direction changes
  useEffect(() => {
    setData(null);
    setSelected(null);
    setError(null);
  }, [direccion]);

  const loadComprobantes = async (e) => {
    e.preventDefault();
    if (!selectedRep) {
      setError("Seleccione un representado");
      return;
    }
    const cuit = selectedRep.cuit;
    if (cuit.length !== 11) {
      setError("CUIT debe tener 11 dígitos");
      return;
    }
    setError(null);
    setData(null);
    setSelected(null);
    setLoading(true);
    try {
      const endpoint = direccion === "R" ? "comprobantes-recibidos" : "comprobantes-emitidos";
      const res = await fetch(
        `${API_BASE}/api/arca/${endpoint}?cuit=${encodeURIComponent(cuit)}`
      );
      const json = await res.json();
      if (!res.ok) {
        setError(json.error || json.detail || "Error al cargar");
        return;
      }
      setData(json);
    } catch (err) {
      setError(err.message || "No se pudo conectar al backend");
    } finally {
      setLoading(false);
    }
  };

  // If a comprobante is selected, show detail view
  if (selected) {
    return (
      <div style={styles.page}>
        <ComprobanteDetail comprobante={selected} onBack={() => setSelected(null)} />
      </div>
    );
  }

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <h1 style={styles.title}>Comprobantes</h1>
        <p style={styles.subtitle}>
          Comprobantes recibidos y emitidos desde caché SQLite.
        </p>
      </header>

      {/* Direction toggle */}
      <div style={styles.dirToggle}>
        <button
          type="button"
          onClick={() => setDireccion("R")}
          style={{ ...styles.dirBtn, ...(direccion === "R" ? styles.dirBtnActive : {}) }}
        >
          Recibidos
        </button>
        <button
          type="button"
          onClick={() => setDireccion("E")}
          style={{ ...styles.dirBtn, ...(direccion === "E" ? styles.dirBtnActive : {}) }}
        >
          Emitidos
        </button>
      </div>

      <form onSubmit={loadComprobantes} style={styles.form}>
        <div style={styles.field}>
          <label style={styles.label}>Selecciona tu representado</label>
          <select
            value={selectedRep ? selectedRep.cuit : ""}
            onChange={(e) => {
              const c = e.target.value;
              setSelectedRep(representados.find((r) => r.cuit === c) || null);
            }}
            style={styles.select}
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

        <button type="submit" disabled={loading || loadingRep || !selectedRep} style={styles.button}>
          {loading ? "Cargando..." : "Cargar comprobantes"}
        </button>
      </form>

      {error && <div style={styles.error}>{error}</div>}

      {data && data.comprobantes?.length === 0 && (
        <div style={styles.empty}>
          No hay comprobantes {direccion === "R" ? "recibidos" : "emitidos"} en caché.
          Ejecute primero la descarga desde ARCA (backend POST).
        </div>
      )}

      {data && data.comprobantes?.length > 0 && (
        <section style={styles.section}>
          <p style={styles.meta}>
            {data.total} comprobantes {direccion === "R" ? "recibidos" : "emitidos"} · Desde caché
            {data.fetched_at && ` · ${formatDate(data.fetched_at)}`}
          </p>
          <div style={styles.tableWrap}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Fecha</th>
                  <th style={styles.th}>Tipo</th>
                  <th style={styles.th}>PV - Número</th>
                  <th style={styles.th}>Contraparte</th>
                  <th style={{ ...styles.th, textAlign: "right" }}>Importe</th>
                </tr>
              </thead>
              <tbody>
                {data.comprobantes.map((c, i) => (
                  <tr
                    key={`${c.tipo_comprobante_codigo}-${c.punto_venta}-${c.numero}-${i}`}
                    style={styles.tr}
                    onClick={() => setSelected(c)}
                  >
                    <td style={styles.td}>
                      {c.fecha_emision_display || formatDate(c.fecha_emision)}
                    </td>
                    <td style={styles.td}>
                      <span style={styles.tipoBadge}>{c.tipo_comprobante || "-"}</span>
                    </td>
                    <td style={styles.td}>
                      {c.punto_venta}-{c.numero}
                    </td>
                    <td style={styles.td}>
                      <div style={styles.contraparte}>{c.denominacion_contraparte || "-"}</div>
                      <div style={styles.contraparteCuit}>{c.cuit_contraparte || ""}</div>
                    </td>
                    <td style={{ ...styles.td, textAlign: "right", fontVariantNumeric: "tabular-nums" }}>
                      {c.importe_total_display || formatCurrency(c.importe_total, c.moneda)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

/* ── Styles ───────────────────────────────────────────────────────────── */

const styles = {
  page: {
    padding: "1.5rem",
    maxWidth: "960px",
    margin: "0 auto",
  },
  header: {
    marginBottom: "1rem",
    textAlign: "center",
  },
  title: {
    margin: 0,
    fontSize: "1.5rem",
    fontWeight: 600,
    color: "#f8fafc",
  },
  subtitle: {
    margin: "0.5rem 0 0",
    fontSize: "0.9rem",
    color: "#94a3b8",
  },

  /* Direction toggle */
  dirToggle: {
    display: "flex",
    gap: "0.5rem",
    justifyContent: "center",
    marginBottom: "1rem",
  },
  dirBtn: {
    padding: "0.5rem 1.25rem",
    fontSize: "0.9rem",
    borderRadius: "6px",
    border: "1px solid #334155",
    background: "transparent",
    color: "#94a3b8",
    cursor: "pointer",
  },
  dirBtnActive: {
    background: "rgba(59, 130, 246, 0.2)",
    borderColor: "#3b82f6",
    color: "#93c5fd",
  },

  /* Form */
  form: {
    display: "flex",
    flexDirection: "column",
    gap: "1rem",
    marginBottom: "1.5rem",
  },
  field: {
    display: "flex",
    flexDirection: "column",
    gap: "0.35rem",
  },
  label: {
    fontSize: "0.85rem",
    fontWeight: 500,
    color: "#cbd5e1",
  },
  select: {
    padding: "0.75rem 1rem",
    fontSize: "1rem",
    borderRadius: "8px",
    border: "1px solid #334155",
    background: "#1e293b",
    color: "#f8fafc",
    outline: "none",
    width: "100%",
  },
  button: {
    padding: "0.85rem 1.25rem",
    fontSize: "1rem",
    fontWeight: 600,
    borderRadius: "8px",
    border: "none",
    background: "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
    color: "white",
    cursor: "pointer",
  },

  /* Feedback */
  error: {
    padding: "1rem",
    borderRadius: "8px",
    background: "rgba(239, 68, 68, 0.15)",
    border: "1px solid rgba(239, 68, 68, 0.4)",
    color: "#fca5a5",
    marginBottom: "1rem",
  },
  empty: {
    padding: "2rem",
    textAlign: "center",
    color: "#94a3b8",
    background: "rgba(255,255,255,0.03)",
    borderRadius: "8px",
  },
  section: {
    marginTop: "1rem",
  },
  meta: {
    fontSize: "0.85rem",
    color: "#94a3b8",
    marginBottom: "1rem",
  },

  /* Table */
  tableWrap: {
    overflowX: "auto",
    borderRadius: "8px",
    border: "1px solid #334155",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: "0.9rem",
  },
  th: {
    padding: "0.75rem 1rem",
    textAlign: "left",
    fontWeight: 600,
    fontSize: "0.8rem",
    color: "#94a3b8",
    background: "rgba(15, 23, 42, 0.6)",
    borderBottom: "1px solid #334155",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  },
  tr: {
    cursor: "pointer",
    borderBottom: "1px solid rgba(51, 65, 85, 0.5)",
  },
  td: {
    padding: "0.65rem 1rem",
    color: "#e2e8f0",
    verticalAlign: "top",
  },
  tipoBadge: {
    fontSize: "0.75rem",
    padding: "0.15rem 0.5rem",
    background: "rgba(59, 130, 246, 0.2)",
    borderRadius: "4px",
    color: "#93c5fd",
    whiteSpace: "nowrap",
  },
  contraparte: {
    fontSize: "0.85rem",
    color: "#e2e8f0",
  },
  contraparteCuit: {
    fontSize: "0.75rem",
    color: "#64748b",
  },

  /* Detail view */
  detail: {
    padding: "1rem",
  },
  backBtn: {
    padding: "0.5rem 1rem",
    fontSize: "0.9rem",
    borderRadius: "6px",
    border: "1px solid #334155",
    background: "transparent",
    color: "#93c5fd",
    cursor: "pointer",
    marginBottom: "1.5rem",
  },
  detailTitle: {
    margin: "0 0 1.25rem",
    fontSize: "1.25rem",
    fontWeight: 600,
    color: "#f8fafc",
  },
  detailTable: {
    width: "100%",
    borderCollapse: "collapse",
  },
  detailLabel: {
    padding: "0.6rem 1rem",
    fontWeight: 500,
    fontSize: "0.85rem",
    color: "#94a3b8",
    borderBottom: "1px solid rgba(51, 65, 85, 0.4)",
    width: "40%",
  },
  detailValue: {
    padding: "0.6rem 1rem",
    fontSize: "0.9rem",
    color: "#e2e8f0",
    borderBottom: "1px solid rgba(51, 65, 85, 0.4)",
  },
};
