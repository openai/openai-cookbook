/**
 * LibroIVAPage — Generate Libro IVA from Mis Comprobantes, reconcile, then download.
 * Flow: Select CUIT + period → Load comprobantes with IVA breakdown → Verify nothing missing → Generate file.
 * Also supports manual CSV upload for edge cases.
 */
import { useState, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "";

function formatDate(iso) {
  if (!iso) return "-";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString("es-AR", { day: "2-digit", month: "2-digit", year: "numeric" });
  } catch {
    return iso;
  }
}

function formatCurrency(n) {
  if (n == null || isNaN(n)) return "-";
  return n.toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function LibroIVAPage() {
  const [representados, setRepresentados] = useState([]);
  const [selectedRep, setSelectedRep] = useState(null);
  const [loadingRep, setLoadingRep] = useState(true);
  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");
  const [tipo, setTipo] = useState("ventas");
  const [loading, setLoading] = useState(false);
  const [reconcileData, setReconcileData] = useState(null);
  const [error, setError] = useState(null);
  const [generating, setGenerating] = useState(false);

  // CSV upload state
  const [file, setFile] = useState(null);
  const [csvResult, setCsvResult] = useState(null);

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
          const rj = await refresh.json();
          if (cancelled) return;
          if (rj.success && rj.representados?.length > 0) {
            setRepresentados(rj.representados);
            setSelectedRep(rj.representados[0]);
          } else if (rj.error) setError(rj.error);
        }
      } catch (err) {
        if (!cancelled) setError(err.message || "No se pudo conectar");
      } finally {
        if (!cancelled) setLoadingRep(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  const handleReconcile = async (e) => {
    e.preventDefault();
    if (!selectedRep || !fechaDesde || !fechaHasta) {
      setError("Seleccione representado y rango de fechas");
      return;
    }
    setError(null);
    setReconcileData(null);
    setLoading(true);
    try {
      const url = `${API_BASE}/api/arca/libro-iva/reconcile-data?cuit=${encodeURIComponent(selectedRep.cuit)}&fecha_desde=${fechaDesde}&fecha_hasta=${fechaHasta}&tipo=${tipo}`;
      const res = await fetch(url);
      const json = await res.json();
      if (!json.success) throw new Error(json.error || "Error al cargar");
      setReconcileData(json);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async () => {
    if (!selectedRep || !fechaDesde || !fechaHasta) return;
    setGenerating(true);
    setError(null);
    try {
      const url = `${API_BASE}/api/arca/libro-iva/generate?cuit=${encodeURIComponent(selectedRep.cuit)}&fecha_desde=${fechaDesde}&fecha_hasta=${fechaHasta}&tipo=${tipo}`;
      const res = await fetch(url);
      if (!res.ok) {
        const json = await res.json().catch(() => ({}));
        throw new Error(json.error || res.statusText);
      }
      const blob = await res.blob();
      const fn = res.headers.get("Content-Disposition")?.match(/filename="?([^";]+)"?/)?.[1] || `libro_iva_${tipo}.zip`;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = fn;
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (err) {
      setError(err.message);
    } finally {
      setGenerating(false);
    }
  };

  const handleCsvConvert = async (e) => {
    e.preventDefault();
    if (!file) {
      setError("Seleccione un archivo CSV");
      return;
    }
    setLoading(true);
    setError(null);
    setCsvResult(null);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("tipo", tipo);
      const res = await fetch(`${API_BASE}/api/arca/libro-iva/convert`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const json = await res.json().catch(() => ({}));
        throw new Error(json.error || "Error al convertir");
      }
      const blob = await res.blob();
      const fn = res.headers.get("Content-Disposition")?.match(/filename="?([^";]+)"?/)?.[1] || `libro_iva_${tipo}_afip.zip`;
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = fn;
      a.click();
      URL.revokeObjectURL(a.href);
      const rows = res.headers.get("X-Converted-Rows");
      setCsvResult({ success: true, rows: rows ? parseInt(rows, 10) : null });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <h1 style={styles.title}>Libro IVA Digital</h1>
        <p style={styles.subtitle}>
          Genere el Libro IVA desde Mis Comprobantes. Concilie y verifique que no falte nada antes de descargar.
        </p>
      </header>

      {/* ─── Generar desde Mis Comprobantes (reconciliación) ─── */}
      <section style={styles.section}>
        <h2 style={styles.sectionTitle}>1. Generar desde Mis Comprobantes</h2>
        <form onSubmit={handleReconcile} style={styles.form}>
          <div style={styles.row}>
            <div style={styles.field}>
              <label style={styles.label}>Representado</label>
              <select
                value={selectedRep?.cuit ?? ""}
                onChange={(e) => setSelectedRep(representados.find((r) => r.cuit === e.target.value) || null)}
                style={styles.select}
                disabled={loading || loadingRep}
              >
                {loadingRep ? (
                  <option value="">Cargando…</option>
                ) : representados.length === 0 ? (
                  <option value="">No hay representados</option>
                ) : (
                  representados.map((r) => (
                    <option key={r.cuit} value={r.cuit}>{r.nombre} — {r.cuit}</option>
                  ))
                )}
              </select>
            </div>
            <div style={styles.field}>
              <label style={styles.label}>Tipo</label>
              <select value={tipo} onChange={(e) => setTipo(e.target.value)} style={styles.select} disabled={loading}>
                <option value="ventas">Ventas (emitidos)</option>
                <option value="compras">Compras (recibidos)</option>
              </select>
            </div>
          </div>
          <div style={styles.row}>
            <div style={styles.field}>
              <label style={styles.label}>Desde</label>
              <input
                type="date"
                value={fechaDesde}
                onChange={(e) => setFechaDesde(e.target.value)}
                style={styles.input}
                required
              />
            </div>
            <div style={styles.field}>
              <label style={styles.label}>Hasta</label>
              <input
                type="date"
                value={fechaHasta}
                onChange={(e) => setFechaHasta(e.target.value)}
                style={styles.input}
                required
              />
            </div>
          </div>
          <button type="submit" disabled={loading || loadingRep || !selectedRep} style={styles.button}>
            {loading ? "Cargando…" : "Cargar y conciliar"}
          </button>
        </form>

        {error && <div style={styles.error}>{error}</div>}

        {reconcileData && reconcileData.comprobantes?.length > 0 && (
          <div style={styles.reconcile}>
            <h3 style={styles.reconcileTitle}>Conciliación — Mis Comprobantes ↔ IVA {tipo === "ventas" ? "Ventas" : "Compras"}</h3>
            <p style={styles.reconcileMeta}>
              {reconcileData.total_comprobantes} comprobantes · Neto: $ {formatCurrency(reconcileData.total_neto)} · IVA: $ {formatCurrency(reconcileData.total_iva)}
            </p>
            <p style={styles.reconcileNote}>
              Todos los comprobantes de Mis Comprobantes se incluirán en el archivo Libro IVA. Verifique que la lista esté completa.
            </p>
            <div style={styles.tableWrap}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    <th style={styles.th}>Fecha</th>
                    <th style={styles.th}>Tipo</th>
                    <th style={styles.th}>PV</th>
                    <th style={styles.th}>Número</th>
                    <th style={styles.th}>Contraparte</th>
                    <th style={styles.th}>Total</th>
                    <th style={styles.th}>Neto</th>
                    <th style={styles.th}>IVA</th>
                  </tr>
                </thead>
                <tbody>
                  {reconcileData.comprobantes.slice(0, 50).map((c, i) => (
                    <tr key={i}>
                      <td style={styles.td}>{formatDate(c.fecha_emision)}</td>
                      <td style={styles.td}>{c.tipo_comprobante || "-"}</td>
                      <td style={styles.td}>{c.punto_venta}</td>
                      <td style={styles.td}>{c.numero || `${c.numero_desde}`}</td>
                      <td style={styles.td}>{c.denominacion_contraparte?.slice(0, 20) || "-"}</td>
                      <td style={styles.tdRight}>$ {formatCurrency(c.importe_total)}</td>
                      <td style={styles.tdRight}>$ {formatCurrency(c.importe_neto_calc)}</td>
                      <td style={styles.tdRight}>$ {formatCurrency(c.importe_iva_calc)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {reconcileData.comprobantes.length > 50 && (
                <p style={styles.more}>… y {reconcileData.comprobantes.length - 50} más</p>
              )}
            </div>
            <button
              type="button"
              onClick={handleGenerate}
              disabled={generating}
              style={styles.button}
            >
              {generating ? "Generando…" : "Generar archivo Libro IVA"}
            </button>
          </div>
        )}

        {reconcileData && reconcileData.comprobantes?.length === 0 && (
          <div style={styles.empty}>
            No hay comprobantes en caché para este período. Ejecute primero la descarga desde ARCA (Comprobantes).
          </div>
        )}
      </section>

      {/* ─── CSV manual (alternativa) ─── */}
      <section style={styles.section}>
        <h2 style={styles.sectionTitle}>2. Subir CSV manual</h2>
        <p style={styles.sectionNote}>Si tiene comprobantes fuera de Mis Comprobantes, suba un CSV.</p>
        <form onSubmit={handleCsvConvert} style={styles.form}>
          <div style={styles.field}>
            <input
              type="file"
              accept=".csv"
              onChange={(e) => { setFile(e.target.files?.[0] || null); setCsvResult(null); }}
              style={styles.fileInput}
            />
          </div>
          <button type="submit" disabled={loading || !file} style={styles.buttonSecondary}>
            Convertir CSV y descargar
          </button>
        </form>
        {csvResult?.success && <p style={styles.success}>Archivo descargado ({csvResult.rows} filas).</p>}
      </section>
    </div>
  );
}

const styles = {
  page: { padding: "1.5rem", maxWidth: "900px", margin: "0 auto" },
  header: { marginBottom: "1.5rem", textAlign: "center" },
  title: { margin: 0, fontSize: "1.5rem", fontWeight: 600, color: "#f8fafc" },
  subtitle: { margin: "0.5rem 0 0", fontSize: "0.9rem", color: "#94a3b8" },
  section: { marginBottom: "2rem" },
  sectionTitle: { margin: "0 0 0.75rem", fontSize: "1.1rem", color: "#e2e8f0" },
  sectionNote: { margin: "0 0 0.75rem", fontSize: "0.85rem", color: "#64748b" },
  form: { display: "flex", flexDirection: "column", gap: "1rem", marginBottom: "1rem" },
  row: { display: "flex", gap: "1rem", flexWrap: "wrap" },
  field: { flex: 1, minWidth: "140px" },
  label: { display: "block", fontSize: "0.85rem", color: "#cbd5e1", marginBottom: "0.25rem" },
  select: {
    width: "100%", padding: "0.6rem 0.8rem", borderRadius: "6px",
    border: "1px solid #334155", background: "#1e293b", color: "#f8fafc",
  },
  input: {
    width: "100%", padding: "0.6rem 0.8rem", borderRadius: "6px",
    border: "1px solid #334155", background: "#1e293b", color: "#f8fafc",
  },
  button: {
    padding: "0.75rem 1.25rem", fontSize: "1rem", fontWeight: 600, borderRadius: "8px",
    border: "none", background: "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
    color: "white", cursor: "pointer", alignSelf: "flex-start",
  },
  buttonSecondary: {
    padding: "0.6rem 1rem", fontSize: "0.9rem", borderRadius: "8px",
    border: "1px solid #475569", background: "transparent", color: "#94a3b8", cursor: "pointer", alignSelf: "flex-start",
  },
  error: {
    padding: "1rem", borderRadius: "8px", background: "rgba(239,68,68,0.15)",
    border: "1px solid rgba(239,68,68,0.4)", color: "#fca5a5", marginTop: "0.5rem",
  },
  success: { color: "#86efac", fontSize: "0.9rem", marginTop: "0.5rem" },
  reconcile: { marginTop: "1.5rem", padding: "1rem", background: "rgba(0,0,0,0.2)", borderRadius: "8px" },
  reconcileTitle: { margin: "0 0 0.5rem", fontSize: "1rem", color: "#e2e8f0" },
  reconcileMeta: { margin: "0 0 0.25rem", fontSize: "0.9rem", color: "#94a3b8" },
  reconcileNote: { margin: "0 0 0.75rem", fontSize: "0.85rem", color: "#64748b" },
  tableWrap: { overflowX: "auto", marginBottom: "1rem" },
  table: { width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" },
  th: { textAlign: "left", padding: "0.5rem", borderBottom: "1px solid #334155", color: "#94a3b8" },
  td: { padding: "0.5rem", borderBottom: "1px solid #334155", color: "#e2e8f0" },
  tdRight: { padding: "0.5rem", borderBottom: "1px solid #334155", color: "#e2e8f0", textAlign: "right" },
  more: { margin: "0.5rem 0", fontSize: "0.85rem", color: "#64748b" },
  empty: { padding: "1.5rem", textAlign: "center", color: "#94a3b8", background: "rgba(255,255,255,0.03)", borderRadius: "8px" },
  fileInput: { marginBottom: "0.5rem", color: "#94a3b8" },
};
