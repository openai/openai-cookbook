/**
 * BancoGaliciaPage — View bank transactions from SQLite cache.
 * "Ver caché" loads instantly. "Descargar de Banco Galicia" fetches via Playwright.
 */
import { useState, useEffect } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "";

function fmtMoney(n) {
  if (n == null) return "-";
  const sign = n < 0 ? "-" : "";
  const abs = Math.abs(n);
  return `${sign}$${abs.toLocaleString("es-AR", { minimumFractionDigits: 2 })}`;
}

export default function BancoGaliciaPage() {
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  // Auto-load cache on mount
  useEffect(() => { loadCache(); }, []);

  const loadCache = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/arca/banco/transactions`);
      const json = await res.json();
      setData(json);
    } catch (err) {
      setError(err.message || "Error de conexión");
    } finally {
      setLoading(false);
    }
  };

  const handleRefresh = async () => {
    setRefreshing(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/arca/banco/refresh`, { method: "POST" });
      const json = await res.json();
      if (json.success) {
        await loadCache(); // reload from DB
      } else {
        setError(json.error || json.message || "Error al descargar");
      }
    } catch (err) {
      setError(err.message || "Error de conexión");
    } finally {
      setRefreshing(false);
    }
  };

  const transactions = data?.transactions || [];
  const summary = data?.summary;

  return (
    <div style={s.page}>
      <header style={s.header}>
        <h1 style={s.title}>Banco Galicia</h1>
        <p style={s.subtitle}>
          Movimientos de cuenta desde caché SQLite.
        </p>
      </header>

      {/* Actions */}
      <div style={s.actions}>
        <button type="button" onClick={loadCache}
          disabled={loading || refreshing} style={s.button}>
          {loading ? "Cargando..." : "Ver caché"}
        </button>
        <button type="button" onClick={handleRefresh}
          disabled={loading || refreshing}
          style={{ ...s.button, background: refreshing ? "#475569" : "linear-gradient(135deg, #f59e0b 0%, #d97706 100%)" }}>
          {refreshing ? "Descargando..." : "Descargar de Banco Galicia"}
        </button>
      </div>

      {/* Cache info */}
      {data?.fetched_at && (
        <div style={s.cacheInfo}>
          Última actualización: {new Date(data.fetched_at).toLocaleString("es-AR")}
          {" · "}{data.total} movimientos en caché
        </div>
      )}

      {error && (
        <div style={s.error}><strong>Error:</strong> {error}</div>
      )}

      {/* Summary cards */}
      {summary && (
        <div style={s.summaryGrid}>
          <div style={s.card}>
            <div style={{ ...s.cardValue, color: "#86efac" }}>{fmtMoney(summary.ingresos)}</div>
            <div style={s.cardLabel}>Ingresos</div>
          </div>
          <div style={s.card}>
            <div style={{ ...s.cardValue, color: "#fca5a5" }}>{fmtMoney(summary.egresos)}</div>
            <div style={s.cardLabel}>Egresos</div>
          </div>
          <div style={{ ...s.card, borderColor: summary.neto >= 0 ? "rgba(34,197,94,0.4)" : "rgba(239,68,68,0.4)" }}>
            <div style={{ ...s.cardValue, color: summary.neto >= 0 ? "#86efac" : "#fca5a5" }}>
              {fmtMoney(summary.neto)}
            </div>
            <div style={s.cardLabel}>Neto</div>
          </div>
          <div style={s.card}>
            <div style={s.cardValue}>{data?.total || 0}</div>
            <div style={s.cardLabel}>Movimientos</div>
          </div>
        </div>
      )}

      {/* Transactions table */}
      {transactions.length > 0 && (
        <div style={s.tableWrap}>
          <table style={s.table}>
            <thead>
              <tr>
                <th style={s.th}>Fecha</th>
                <th style={s.th}>Descripción</th>
                <th style={{ ...s.th, textAlign: "right" }}>Monto</th>
              </tr>
            </thead>
            <tbody>
              {transactions.map((t, i) => (
                <tr key={i}>
                  <td style={s.td}>{t.date}</td>
                  <td style={s.td}>{t.description}</td>
                  <td style={{
                    ...s.td,
                    textAlign: "right",
                    fontWeight: 500,
                    color: t.amount >= 0 ? "#86efac" : "#fca5a5",
                  }}>
                    {fmtMoney(t.amount)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {data && transactions.length === 0 && !loading && (
        <div style={s.warning}>
          No hay movimientos en caché.
          Use "Descargar de Banco Galicia" para obtener datos.
        </div>
      )}
    </div>
  );
}

/* ── Styles ───────────────────────────────────────────────────────────── */

const s = {
  page: { padding: "1.5rem", maxWidth: "800px", margin: "0 auto" },
  header: { marginBottom: "1rem", textAlign: "center" },
  title: { margin: 0, fontSize: "1.5rem", fontWeight: 600, color: "#f8fafc" },
  subtitle: { margin: "0.5rem 0 0", fontSize: "0.9rem", color: "#94a3b8" },

  actions: { display: "flex", gap: "0.75rem", marginBottom: "1rem" },
  button: {
    flex: 1, padding: "0.85rem 1.25rem", fontSize: "1rem", fontWeight: 600,
    borderRadius: "8px", border: "none",
    background: "linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)",
    color: "white", cursor: "pointer",
  },

  cacheInfo: {
    fontSize: "0.8rem", color: "#64748b", marginBottom: "1rem", textAlign: "center",
  },

  error: {
    padding: "1rem", borderRadius: "8px",
    background: "rgba(239,68,68,0.15)", border: "1px solid rgba(239,68,68,0.4)",
    color: "#fca5a5", marginBottom: "1rem",
  },
  warning: {
    padding: "1rem", borderRadius: "8px",
    background: "rgba(251,146,60,0.12)", border: "1px solid rgba(251,146,60,0.35)",
    color: "#fed7aa", fontSize: "0.9rem",
  },

  summaryGrid: {
    display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
    gap: "0.75rem", marginBottom: "1.5rem",
  },
  card: {
    padding: "1rem", borderRadius: "8px",
    background: "rgba(30,41,59,0.6)", border: "1px solid #334155",
    textAlign: "center",
  },
  cardValue: { fontSize: "1.15rem", fontWeight: 600, color: "#f8fafc" },
  cardLabel: { fontSize: "0.8rem", color: "#94a3b8", marginTop: "0.25rem" },

  tableWrap: { overflowX: "auto" },
  table: { width: "100%", borderCollapse: "collapse", fontSize: "0.85rem" },
  th: {
    textAlign: "left", padding: "0.5rem", color: "#64748b",
    borderBottom: "1px solid #334155", fontSize: "0.75rem", fontWeight: 500,
  },
  td: {
    padding: "0.5rem", color: "#cbd5e1",
    borderBottom: "1px solid rgba(51,65,85,0.4)",
  },
};
