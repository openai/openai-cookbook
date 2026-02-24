/**
 * NotificationsPage — Choose representado and view notifications from cache.
 * Uses credentials from .env (no login needed). Cache-first loading.
 */
import { useState, useEffect } from "react";
import { getApiBase } from "../App";

const API_BASE = getApiBase();

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

function NotificationCard({ n, onViewPdf }) {
  const hasPdf = n.tiene_adjunto;
  const msg = n.mensaje_completo || n.mensaje_preview || "";
  const preview = msg.length > 120 ? msg.slice(0, 120) + "…" : msg;

  return (
    <article style={styles.card}>
      <div style={styles.cardHeader}>
        <span style={styles.badge}>{n.clasificacion || "Otros"}</span>
        {hasPdf && (
          <span style={styles.pdfBadge} onClick={() => onViewPdf(n)}>
            PDF
          </span>
        )}
      </div>
      <div style={styles.organismo}>{n.organismo || "-"}</div>
      <div style={styles.date}>
        Publicado: {formatDate(n.fecha_publicacion)}
      </div>
      <p style={styles.preview}>{preview}</p>
    </article>
  );
}

export default function NotificationsPage() {
  const [representados, setRepresentados] = useState([]);
  const [selectedRep, setSelectedRep] = useState(null);
  const [loadingRep, setLoadingRep] = useState(true);
  const [loading, setLoading] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [selectedPdf, setSelectedPdf] = useState(null);
  const [refreshing, setRefreshing] = useState(false);
  const [downloadingPdf, setDownloadingPdf] = useState(false);

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

  const loadFromCache = async (e) => {
    e.preventDefault();
    if (!selectedRep) {
      setError("Seleccione un representado");
      return;
    }
    const cuitClean = selectedRep.cuit;
    if (cuitClean.length !== 11) {
      setError("CUIT debe tener 11 dígitos o seleccione un representado");
      return;
    }
    setError(null);
    setData(null);
    setLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/arca/notificaciones-contenido?cuit=${encodeURIComponent(cuitClean)}`
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

  const refreshFromArca = async () => {
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
    setRefreshing(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/arca/notificaciones-contenido/refresh?cuit_representado=${encodeURIComponent(cuit)}`
      );
      const json = await res.json();
      if (!res.ok || !json.success) {
        setError(json.error || json.detail || "Error al actualizar desde ARCA");
        return;
      }
      setData(json);
    } catch (err) {
      setError(err.message || "No se pudo conectar al backend");
    } finally {
      setRefreshing(false);
    }
  };

  const getCuitClean = () => (data?.cuit || selectedRep?.cuit || "").replace(/\D/g, "");

  const handleViewPdf = async (n) => {
    const cuitClean = getCuitClean();
    const base = API_BASE || "";
    const url = `${base}/api/arca/notificaciones/${n.id}/pdf?cuit=${encodeURIComponent(cuitClean)}`;
    const res = await fetch(url);
    if (!res.ok) {
      setSelectedPdf({ ...n, url: null, notCached: true, error: null });
      return;
    }
    setSelectedPdf({ ...n, url, notCached: false, error: null });
  };

  const handleDownloadPdf = async () => {
    if (!selectedPdf) return;
    const cuitClean = getCuitClean();
    const base = API_BASE || "";
    setDownloadingPdf(true);
    setSelectedPdf((prev) => ({ ...prev, error: null }));
    try {
      const url = `${base}/api/arca/notificaciones/${selectedPdf.id}/pdf/download?cuit=${encodeURIComponent(cuitClean)}`;
      const res = await fetch(url);
      const contentType = res.headers.get("content-type") || "";
      if (contentType.includes("application/pdf")) {
        // Success — PDF returned directly. Build blob URL for iframe.
        const blob = await res.blob();
        const blobUrl = URL.createObjectURL(blob);
        setSelectedPdf((prev) => ({ ...prev, url: blobUrl, notCached: false, error: null }));
      } else {
        // JSON error response
        const json = await res.json();
        setSelectedPdf((prev) => ({ ...prev, error: json.error || "Error al descargar PDF desde ARCA" }));
      }
    } catch (err) {
      setSelectedPdf((prev) => ({ ...prev, error: err.message || "Error de conexión" }));
    } finally {
      setDownloadingPdf(false);
    }
  };

  const closePdf = () => {
    // Revoke blob URL if we created one
    if (selectedPdf?.url?.startsWith("blob:")) {
      URL.revokeObjectURL(selectedPdf.url);
    }
    setSelectedPdf(null);
  };

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <h1 style={styles.title}>Notificaciones DFE</h1>
        <p style={styles.subtitle}>
          Comunicaciones de mis representados. Seleccione y cargue desde caché.
        </p>
      </header>

      <form onSubmit={loadFromCache} style={styles.form}>
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
              <option value="">Cargando representados…</option>
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

        <div style={styles.buttonRow}>
          <button type="submit" disabled={loading || refreshing || loadingRep || !selectedRep} style={styles.button}>
            {loading ? "Cargando…" : "Cargar desde caché"}
          </button>
          <button
            type="button"
            onClick={refreshFromArca}
            disabled={loading || refreshing || loadingRep || !selectedRep}
            style={styles.buttonSecondary}
          >
            {refreshing ? "Descargando de ARCA…" : "Actualizar desde ARCA"}
          </button>
        </div>
      </form>

      {error && (
        <div style={styles.error}>{error}</div>
      )}

      {data && data.notifications?.length === 0 && (
        <div style={styles.empty}>
          No hay notificaciones en caché para este representado.
          <br />
          <button
            type="button"
            onClick={refreshFromArca}
            disabled={refreshing || !selectedRep}
            style={{ ...styles.buttonSecondary, marginTop: "1rem" }}
          >
            {refreshing ? "Descargando…" : "Descargar desde ARCA"}
          </button>
        </div>
      )}

      {data && data.notifications?.length > 0 && (
        <section style={styles.section}>
          <p style={styles.meta}>
            {data.total} notificaciones · Cargado desde caché
            {data.fetched_at && ` · ${formatDate(data.fetched_at)}`}
          </p>
          <div style={styles.grid}>
            {data.notifications.map((n) => (
              <NotificationCard
                key={n.id}
                n={n}
                onViewPdf={handleViewPdf}
              />
            ))}
          </div>
        </section>
      )}

      {selectedPdf && (
        <div style={styles.modal} onClick={closePdf}>
          <div style={styles.modalContent} onClick={(e) => e.stopPropagation()}>
            <div style={styles.modalHeader}>
              <h3>PDF — {selectedPdf.organismo || selectedPdf.id}</h3>
              <button type="button" onClick={closePdf} style={styles.closeBtn}>
                ✕
              </button>
            </div>
            {selectedPdf.notCached && !selectedPdf.url ? (
              <div style={styles.pdfError}>
                {selectedPdf.error ? (
                  <p style={{ color: "#fca5a5" }}>{selectedPdf.error}</p>
                ) : (
                  <p>PDF no disponible en caché local.</p>
                )}
                <button
                  type="button"
                  onClick={handleDownloadPdf}
                  disabled={downloadingPdf}
                  style={{ ...styles.button, marginTop: "1rem", maxWidth: "300px" }}
                >
                  {downloadingPdf ? "Descargando de ARCA... (~30s)" : "Descargar desde ARCA"}
                </button>
              </div>
            ) : selectedPdf.url ? (
              <iframe
                src={selectedPdf.url}
                title={`PDF ${selectedPdf.id}`}
                style={styles.pdfFrame}
              />
            ) : (
              <div style={styles.pdfError}>{selectedPdf.error || "PDF no disponible"}</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

const styles = {
  page: {
    padding: "1.5rem",
    maxWidth: "900px",
    margin: "0 auto",
  },
  header: {
    marginBottom: "1.5rem",
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
  input: {
    padding: "0.75rem 1rem",
    fontSize: "1rem",
    borderRadius: "8px",
    border: "1px solid #334155",
    background: "#1e293b",
    color: "#f8fafc",
    outline: "none",
  },
  buttonRow: {
    display: "flex",
    gap: "0.75rem",
  },
  button: {
    flex: 1,
    padding: "0.85rem 1.25rem",
    fontSize: "1rem",
    fontWeight: 600,
    borderRadius: "8px",
    border: "none",
    background: "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
    color: "white",
    cursor: "pointer",
  },
  buttonSecondary: {
    padding: "0.6rem 1rem",
    fontSize: "0.9rem",
    borderRadius: "8px",
    border: "1px solid #475569",
    background: "transparent",
    color: "#94a3b8",
    cursor: "pointer",
  },
  repSection: {
    padding: "1rem",
    background: "rgba(0,0,0,0.2)",
    borderRadius: "8px",
    marginBottom: "0.5rem",
  },
  repTitle: {
    margin: "0 0 0.75rem",
    fontSize: "1rem",
    color: "#e2e8f0",
  },
  repRow: {
    display: "flex",
    gap: "0.5rem",
    flexWrap: "wrap",
    marginBottom: "0.75rem",
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
  grid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))",
    gap: "1rem",
  },
  card: {
    padding: "1rem",
    background: "rgba(30, 41, 59, 0.8)",
    border: "1px solid #334155",
    borderRadius: "8px",
    display: "flex",
    flexDirection: "column",
    gap: "0.5rem",
  },
  cardHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
  },
  badge: {
    fontSize: "0.7rem",
    padding: "0.2rem 0.5rem",
    background: "rgba(59, 130, 246, 0.3)",
    borderRadius: "4px",
    color: "#93c5fd",
  },
  pdfBadge: {
    fontSize: "0.7rem",
    padding: "0.2rem 0.5rem",
    background: "rgba(34, 197, 94, 0.3)",
    borderRadius: "4px",
    color: "#86efac",
    cursor: "pointer",
  },
  organismo: {
    fontSize: "0.9rem",
    fontWeight: 600,
    color: "#e2e8f0",
  },
  date: {
    fontSize: "0.75rem",
    color: "#64748b",
  },
  preview: {
    margin: 0,
    fontSize: "0.85rem",
    color: "#94a3b8",
    lineHeight: 1.4,
  },
  modal: {
    position: "fixed",
    inset: 0,
    background: "rgba(0,0,0,0.7)",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    zIndex: 1000,
    padding: "1rem",
  },
  modalContent: {
    background: "#1e293b",
    borderRadius: "12px",
    width: "100%",
    maxWidth: "800px",
    maxHeight: "90vh",
    display: "flex",
    flexDirection: "column",
    overflow: "hidden",
  },
  modalHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "1rem",
    borderBottom: "1px solid #334155",
  },
  closeBtn: {
    background: "none",
    border: "none",
    color: "#94a3b8",
    fontSize: "1.25rem",
    cursor: "pointer",
  },
  pdfError: {
    padding: "2rem",
    textAlign: "center",
    color: "#94a3b8",
  },
  pdfFrame: {
    flex: 1,
    minHeight: "400px",
    border: "none",
  },
};
