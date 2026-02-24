/**
 * RetencionesPage — View retenciones/percepciones from SQLite cache.
 * "Ver caché" loads from DB (fast). "Descargar de ARCA" fetches fresh data via Playwright.
 * Uses representado selector (same pattern as Notifications/Comprobantes).
 */
import { useState, useEffect } from "react";
import { getApiBase } from "../App";

const API_BASE = getApiBase();

const IMPUESTOS = [
  { code: "767", label: "767 - SICORE Ret y Perc" },
  { code: "216", label: "216 - SIRE IVA" },
  { code: "217", label: "217 - Ganancias" },
  { code: "219", label: "219 - Bienes Personales" },
  { code: "353", label: "353 - Seg. Social" },
];

function fmtDate(iso) {
  if (!iso) return "-";
  const d = iso.slice(0, 10);
  const [y, m, day] = d.split("-");
  return `${day}/${m}/${y}`;
}

function fmtMoney(n) {
  if (n == null) return "-";
  return `$${Number(n).toLocaleString("es-AR", { minimumFractionDigits: 2 })}`;
}

export default function RetencionesPage() {
  const [representados, setRepresentados] = useState([]);
  const [selectedRep, setSelectedRep] = useState(null);
  const [loadingRep, setLoadingRep] = useState(true);

  // Download form state (for ARCA refresh)
  const [impuesto, setImpuesto] = useState("217");
  const [tipoOp, setTipoOp] = useState("percepcion");
  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");

  const [loading, setLoading] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [data, setData] = useState(null);    // cached retenciones from GET
  const [dlResult, setDlResult] = useState(null); // download result from POST
  const [error, setError] = useState(null);

  // Default dates: current month DD/MM/YYYY (for ARCA download)
  const now = new Date();
  const firstDay = new Date(now.getFullYear(), now.getMonth(), 1);
  const lastDay = new Date(now.getFullYear(), now.getMonth() + 1, 0);
  const fmtDMY = (d) => d.toISOString().slice(0, 10).split("-").reverse().join("/");

  // Load representados on mount
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

  // Load cached retenciones from SQLite
  const loadCache = async () => {
    if (!selectedRep) return;
    setLoading(true);
    setError(null);
    setData(null);
    setDlResult(null);
    try {
      const params = new URLSearchParams({ cuit: selectedRep.cuit });
      const res = await fetch(`${API_BASE}/api/arca/retenciones?${params}`);
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err.message || "Error de conexión");
    } finally {
      setLoading(false);
    }
  };

  // Download fresh from ARCA (Playwright) and save to SQLite
  const handleDownload = async (e) => {
    e.preventDefault();
    if (!selectedRep) return;
    setDownloading(true);
    setError(null);
    setDlResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/arca/retenciones/download`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          cuit_representado: selectedRep.cuit,
          fecha_desde: fechaDesde || fmtDMY(firstDay),
          fecha_hasta: fechaHasta || fmtDMY(lastDay),
          impuesto,
          tipo_operacion: tipoOp,
        }),
      });
      const json = await res.json();
      if (json.success) {
        setDlResult(json);
        // Reload cache to show updated data
        await loadCache();
      } else {
        setError(json.error || json.message || "Error al descargar");
      }
    } catch (err) {
      setError(err.message || "Error de conexión");
    } finally {
      setDownloading(false);
    }
  };

  const retenciones = data?.retenciones || [];
  const totalImporte = retenciones.reduce((s, r) => s + (r.importeRetenido || 0), 0);

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <h1 style={styles.title}>Mis Retenciones</h1>
        <p style={styles.subtitle}>
          Retenciones y percepciones desde caché SQLite.
          Use "Descargar de ARCA" para actualizar datos.
        </p>
      </header>

      {/* Representado + Load cache */}
      <div style={styles.form}>
        <div style={styles.field}>
          <label style={styles.label}>Representado</label>
          <select
            value={selectedRep ? selectedRep.cuit : ""}
            onChange={(e) => {
              const c = e.target.value;
              setSelectedRep(representados.find((r) => r.cuit === c) || null);
              setData(null);
            }}
            style={styles.select}
            disabled={loading || downloading || loadingRep}
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

        <button
          type="button"
          onClick={loadCache}
          disabled={loading || downloading || loadingRep || !selectedRep}
          style={styles.button}
        >
          {loading ? "Cargando..." : "Ver caché"}
        </button>
      </div>

      {/* Cache info */}
      {data?.fetched_at && (
        <div style={styles.cacheInfo}>
          Última actualización: {new Date(data.fetched_at).toLocaleString("es-AR")}
          {" · "}{data.total} registros en caché
        </div>
      )}
      {data && !data.retenciones?.length && (
        <div style={styles.warning}>
          No hay retenciones en caché para este representado.
          Use el formulario de descarga de ARCA para obtener datos.
        </div>
      )}

      {/* Retenciones table */}
      {retenciones.length > 0 && (
        <div style={styles.tableWrap}>
          <div style={styles.tableSummary}>
            <strong>{retenciones.length}</strong> retenciones/percepciones
            {" · "}Total: <strong style={{ color: "#86efac" }}>{fmtMoney(totalImporte)}</strong>
          </div>
          <table style={styles.table}>
            <thead>
              <tr>
                <th style={styles.th}>Fecha</th>
                <th style={styles.th}>CUIT Agente</th>
                <th style={styles.th}>Operación</th>
                <th style={styles.th}>Régimen</th>
                <th style={styles.th}>Certificado</th>
                <th style={{ ...styles.th, textAlign: "right" }}>Importe</th>
              </tr>
            </thead>
            <tbody>
              {retenciones.map((r, i) => (
                <tr key={i}>
                  <td style={styles.td}>{fmtDate(r.fechaRetencion)}</td>
                  <td style={styles.td}>{r.cuitAgenteRetencion}</td>
                  <td style={styles.td}>{r.descripcionOperacion}</td>
                  <td style={styles.td}>{r.codigoRegimen}</td>
                  <td style={styles.td}>{r.numeroCertificado}</td>
                  <td style={{
                    ...styles.td,
                    textAlign: "right",
                    color: r.importeRetenido < 0 ? "#fb923c" : "#86efac",
                  }}>
                    {fmtMoney(r.importeRetenido)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ARCA Download section */}
      <details style={styles.downloadSection}>
        <summary style={styles.downloadSummary}>
          Descargar de ARCA (actualizar caché)
        </summary>
        <form onSubmit={handleDownload} style={styles.dlForm}>
          <div style={styles.dirToggle}>
            <button type="button" onClick={() => setTipoOp("retencion")}
              style={{ ...styles.dirBtn, ...(tipoOp === "retencion" ? styles.dirBtnActive : {}) }}>
              Retención
            </button>
            <button type="button" onClick={() => setTipoOp("percepcion")}
              style={{ ...styles.dirBtn, ...(tipoOp === "percepcion" ? styles.dirBtnActive : {}) }}>
              Percepción
            </button>
          </div>

          <div style={styles.field}>
            <label style={styles.label}>Impuesto</label>
            <select value={impuesto} onChange={(e) => setImpuesto(e.target.value)}
              style={styles.select} disabled={downloading}>
              {IMPUESTOS.map((imp) => (
                <option key={imp.code} value={imp.code}>{imp.label}</option>
              ))}
            </select>
          </div>

          <div style={styles.dateRow}>
            <div style={styles.field}>
              <label style={styles.label}>Fecha desde (DD/MM/YYYY)</label>
              <input type="text" value={fechaDesde}
                onChange={(e) => setFechaDesde(e.target.value)}
                placeholder={fmtDMY(firstDay)} style={styles.input} />
            </div>
            <div style={styles.field}>
              <label style={styles.label}>Fecha hasta (DD/MM/YYYY)</label>
              <input type="text" value={fechaHasta}
                onChange={(e) => setFechaHasta(e.target.value)}
                placeholder={fmtDMY(lastDay)} style={styles.input} />
            </div>
          </div>

          <button type="submit" disabled={downloading || !selectedRep}
            style={{ ...styles.button, background: downloading ? "#475569" : "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)" }}>
            {downloading ? "Descargando de ARCA..." : "Descargar de ARCA"}
          </button>
        </form>

        {dlResult?.success && (
          <div style={styles.success}>
            Descarga exitosa: {dlResult.row_count || dlResult.saved_to_db} registros guardados en caché.
            {dlResult.filename && (
              <>
                {" "}
                <a href={`${API_BASE}/api/arca/retenciones/file/${dlResult.filename}`}
                  target="_blank" rel="noopener noreferrer" style={styles.downloadLink}>
                  Descargar CSV
                </a>
              </>
            )}
          </div>
        )}
      </details>

      {error && (
        <div style={styles.error}>
          <strong>Error:</strong> {error}
        </div>
      )}
    </div>
  );
}

/* ── Styles ───────────────────────────────────────────────────────────── */

const styles = {
  page: { padding: "1.5rem", maxWidth: "800px", margin: "0 auto" },
  header: { marginBottom: "1rem", textAlign: "center" },
  title: { margin: 0, fontSize: "1.5rem", fontWeight: 600, color: "#f8fafc" },
  subtitle: { margin: "0.5rem 0 0", fontSize: "0.9rem", color: "#94a3b8" },

  form: { display: "flex", flexDirection: "column", gap: "1rem", marginBottom: "1rem" },
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

  dirToggle: { display: "flex", gap: "0.5rem", justifyContent: "center", marginBottom: "0.75rem" },
  dirBtn: {
    padding: "0.5rem 1.25rem", fontSize: "0.9rem", borderRadius: "6px",
    border: "1px solid #334155", background: "transparent", color: "#94a3b8", cursor: "pointer",
  },
  dirBtnActive: {
    background: "rgba(59, 130, 246, 0.2)", borderColor: "#3b82f6", color: "#93c5fd",
  },

  cacheInfo: {
    fontSize: "0.8rem", color: "#64748b", marginBottom: "1rem", textAlign: "center",
  },
  warning: {
    padding: "1rem", borderRadius: "8px",
    background: "rgba(251,146,60,0.12)", border: "1px solid rgba(251,146,60,0.35)",
    color: "#fed7aa", marginBottom: "1rem", fontSize: "0.9rem",
  },

  tableWrap: { marginBottom: "1.5rem" },
  tableSummary: {
    fontSize: "0.9rem", color: "#cbd5e1", marginBottom: "0.5rem",
  },
  table: { width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" },
  th: {
    textAlign: "left", padding: "0.5rem", color: "#64748b",
    borderBottom: "1px solid #334155", fontSize: "0.75rem", fontWeight: 500,
  },
  td: {
    padding: "0.5rem", color: "#cbd5e1",
    borderBottom: "1px solid rgba(51,65,85,0.4)",
  },

  downloadSection: {
    marginTop: "1rem", padding: "1rem", borderRadius: "8px",
    background: "rgba(30,41,59,0.4)", border: "1px solid #334155",
  },
  downloadSummary: {
    cursor: "pointer", color: "#f59e0b", fontWeight: 500, fontSize: "0.95rem",
  },
  dlForm: {
    display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "1rem",
  },

  error: {
    padding: "1rem", borderRadius: "8px",
    background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.4)",
    color: "#fca5a5", marginTop: "1rem",
  },
  success: {
    padding: "1rem", borderRadius: "8px",
    background: "rgba(34,197,94,0.15)", border: "1px solid rgba(34,197,94,0.4)",
    color: "#86efac", marginTop: "1rem",
  },
  downloadLink: { color: "#93c5fd", marginLeft: "0.5rem" },
};
