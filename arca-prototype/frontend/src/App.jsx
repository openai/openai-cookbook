import { useState, useEffect } from "react";
import LoginForm from "./components/LoginForm";
import NotificationsPage from "./components/NotificationsPage";
import ComprobantesPage from "./components/ComprobantesPage";
import RetencionesPage from "./components/RetencionesPage";
import ReconciliacionPage from "./components/ReconciliacionPage";
import BancoGaliciaPage from "./components/BancoGaliciaPage";
import LibroIVAPage from "./components/LibroIVAPage";

// ── Runtime backend URL config ──────────────────────────────
const DEFAULT_BACKEND = "http://localhost:8000";

export function getApiBase() {
  // Build-time env var takes priority, then localStorage, then default
  const envUrl = import.meta.env.VITE_API_URL;
  if (envUrl) return envUrl;
  // In dev mode (Vite proxy), use empty string so /api goes to same origin
  if (import.meta.env.DEV) return "";
  return localStorage.getItem("arca_backend_url") || DEFAULT_BACKEND;
}

function BackendStatus() {
  const [status, setStatus] = useState("checking"); // "checking" | "connected" | "disconnected"
  const [editing, setEditing] = useState(false);
  const [url, setUrl] = useState(localStorage.getItem("arca_backend_url") || DEFAULT_BACKEND);

  const checkConnection = async (targetUrl) => {
    setStatus("checking");
    try {
      const res = await fetch(`${targetUrl}/health`, { signal: AbortSignal.timeout(3000) });
      if (res.ok) { setStatus("connected"); return; }
    } catch {}
    setStatus("disconnected");
  };

  useEffect(() => { checkConnection(getApiBase()); }, []);

  const handleSave = () => {
    const clean = url.replace(/\/+$/, "");
    localStorage.setItem("arca_backend_url", clean);
    setUrl(clean);
    setEditing(false);
    checkConnection(clean);
    // Force reload so all components pick up new URL
    window.location.reload();
  };

  const dot = status === "connected" ? "#22c55e" : status === "disconnected" ? "#ef4444" : "#f59e0b";
  const label = status === "connected" ? "Backend conectado" : status === "disconnected" ? "Backend no disponible" : "Verificando...";

  return (
    <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", fontSize: "0.75rem", color: "#94a3b8" }}>
      <span style={{ width: 8, height: 8, borderRadius: "50%", background: dot, display: "inline-block" }} />
      {!editing ? (
        <>
          <span>{label}</span>
          <button onClick={() => setEditing(true)} style={{ background: "none", border: "none", color: "#64748b", cursor: "pointer", fontSize: "0.7rem", textDecoration: "underline" }}>
            {getApiBase() || "localhost"}
          </button>
        </>
      ) : (
        <>
          <input
            value={url}
            onChange={e => setUrl(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleSave()}
            style={{ background: "#1e293b", border: "1px solid #334155", borderRadius: 4, color: "#e2e8f0", padding: "2px 6px", fontSize: "0.75rem", width: 220 }}
            autoFocus
          />
          <button onClick={handleSave} style={{ background: "#3b82f6", border: "none", borderRadius: 4, color: "#fff", padding: "2px 8px", fontSize: "0.7rem", cursor: "pointer" }}>OK</button>
          <button onClick={() => setEditing(false)} style={{ background: "none", border: "none", color: "#64748b", cursor: "pointer", fontSize: "0.7rem" }}>Cancelar</button>
        </>
      )}
    </div>
  );
}

function App() {
  const [result, setResult] = useState(null);
  const [view, setView] = useState("login"); // "login" | "notifications" | "comprobantes" | "retenciones" | "reconciliacion" | "banco" | "libro-iva"

  const handleLoginResult = (data) => {
    setResult(data);
  };

  return (
    <div style={styles.container}>
      <header style={styles.header}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
          <h1 style={styles.title}>ARCA Prototype</h1>
          <BackendStatus />
        </div>
        <p style={styles.subtitle}>
          {view === "login"
            ? "Ingrese su CUIT y Clave Fiscal para iniciar"
            : view === "notifications"
            ? "Ver notificaciones desde caché SQLite"
            : view === "comprobantes"
            ? "Explorar comprobantes recibidos y emitidos"
            : view === "retenciones"
            ? "Descargar retenciones y percepciones (Exportar para Aplicativo)"
            : view === "reconciliacion"
            ? "Verificar retenciones contra comprobantes recibidos"
            : view === "banco"
            ? "Movimientos bancarios Banco Galicia"
            : "Convertir CSV a formato Libro IVA Digital AFIP"}
        </p>
        <nav style={styles.nav}>
          <button
            type="button"
            onClick={() => setView("login")}
            style={{ ...styles.navBtn, ...(view === "login" ? styles.navBtnActive : {}) }}
          >
            Login
          </button>
          <button
            type="button"
            onClick={() => setView("notifications")}
            style={{ ...styles.navBtn, ...(view === "notifications" ? styles.navBtnActive : {}) }}
          >
            Notificaciones
          </button>
          <button
            type="button"
            onClick={() => setView("comprobantes")}
            style={{ ...styles.navBtn, ...(view === "comprobantes" ? styles.navBtnActive : {}) }}
          >
            Comprobantes
          </button>
          <button
            type="button"
            onClick={() => setView("retenciones")}
            style={{ ...styles.navBtn, ...(view === "retenciones" ? styles.navBtnActive : {}) }}
          >
            Retenciones
          </button>
          <button
            type="button"
            onClick={() => setView("reconciliacion")}
            style={{ ...styles.navBtn, ...(view === "reconciliacion" ? styles.navBtnActive : {}) }}
          >
            Reconciliación
          </button>
          <button
            type="button"
            onClick={() => setView("banco")}
            style={{ ...styles.navBtn, ...(view === "banco" ? styles.navBtnActive : {}) }}
          >
            Banco
          </button>
          <button
            type="button"
            onClick={() => setView("libro-iva")}
            style={{ ...styles.navBtn, ...(view === "libro-iva" ? styles.navBtnActive : {}) }}
          >
            Libro IVA
          </button>
        </nav>
      </header>

      {view === "login" && (
        <>
          <LoginForm onResult={handleLoginResult} />
          {result && (
        <div
          style={{
            ...styles.result,
            ...(result.success ? styles.success : styles.error),
          }}
        >
          <strong>{result.success ? "Éxito" : "Error"}</strong>: {result.message}
          {result.data && (
            <div style={styles.dataSection}>
              {result.data.notifications?.length > 0 && (
                <section style={styles.section}>
                  <strong>Lista de notificaciones ({result.data.total})</strong>
                  <ul style={styles.notifList}>
                    {result.data.notifications.map((n, i) => (
                      <li key={i} style={styles.notifItem}>
                        {n.asunto} | {n.clasificacion || "-"} | {n.recibido || "-"}
                      </li>
                    ))}
                  </ul>
                </section>
              )}
              {result.data.notifications_found?.length > 0 && (
                <section style={styles.section}>
                  <strong>Notificaciones</strong>
                  <ul style={styles.list}>
                    {result.data.notifications_found.map((n, i) => (
                      <li key={i}>{n.text}</li>
                    ))}
                  </ul>
                </section>
              )}
              {result.data.comprobantes_found?.length > 0 && (
                <section style={styles.section}>
                  <strong>Comprobantes</strong>
                  <ul style={styles.list}>
                    {result.data.comprobantes_found.map((c, i) => (
                      <li key={i}>{c.text}</li>
                    ))}
                  </ul>
                </section>
              )}
              {result.data.alerts?.length > 0 && (
                <section style={styles.section}>
                  <strong>Alertas</strong>
                  <ul style={styles.list}>
                    {result.data.alerts.map((a, i) => (
                      <li key={i}>{a}</li>
                    ))}
                  </ul>
                </section>
              )}
              <section style={styles.section}>
                <strong>Contenido de la página</strong>
                <pre style={styles.pre}>
                  {result.data.body_preview || result.data.body_full || JSON.stringify(result.data)}
                </pre>
              </section>
            </div>
          )}
        </div>
          )}
        </>
      )}

      {view === "notifications" && <NotificationsPage />}

      {view === "comprobantes" && <ComprobantesPage />}

      {view === "retenciones" && <RetencionesPage />}

      {view === "reconciliacion" && <ReconciliacionPage />}

      {view === "banco" && <BancoGaliciaPage />}

      {view === "libro-iva" && <LibroIVAPage />}
    </div>
  );
}

const styles = {
  container: {
    padding: "2rem",
    background: "linear-gradient(180deg, #1e293b 0%, #0f172a 100%)",
    borderRadius: "12px",
    boxShadow: "0 4px 24px rgba(0,0,0,0.3)",
  },
  header: {
    marginBottom: "1.5rem",
    textAlign: "center",
  },
  title: {
    margin: 0,
    fontSize: "1.75rem",
    fontWeight: 600,
    color: "#f8fafc",
  },
  subtitle: {
    margin: "0.5rem 0 0",
    fontSize: "0.9rem",
    color: "#94a3b8",
  },
  nav: {
    display: "flex",
    gap: "0.5rem",
    justifyContent: "center",
    marginTop: "1rem",
  },
  navBtn: {
    padding: "0.5rem 1rem",
    fontSize: "0.9rem",
    borderRadius: "6px",
    border: "1px solid #334155",
    background: "transparent",
    color: "#94a3b8",
    cursor: "pointer",
  },
  navBtnActive: {
    background: "rgba(59, 130, 246, 0.2)",
    borderColor: "#3b82f6",
    color: "#93c5fd",
  },
  result: {
    marginTop: "1.5rem",
    padding: "1rem",
    borderRadius: "8px",
    fontSize: "0.9rem",
  },
  success: {
    background: "rgba(34, 197, 94, 0.15)",
    border: "1px solid rgba(34, 197, 94, 0.4)",
  },
  error: {
    background: "rgba(239, 68, 68, 0.15)",
    border: "1px solid rgba(239, 68, 68, 0.4)",
  },
  dataSection: {
    marginTop: "1rem",
  },
  section: {
    marginBottom: "1rem",
    fontSize: "0.9rem",
  },
  list: {
    margin: "0.25rem 0 0",
    paddingLeft: "1.25rem",
  },
  notifList: {
    margin: "0.25rem 0 0",
    paddingLeft: "1.25rem",
    listStyle: "none",
  },
  notifItem: {
    padding: "0.25rem 0",
    borderBottom: "1px solid rgba(255,255,255,0.1)",
  },
  pre: {
    margin: "0.5rem 0 0",
    padding: "0.75rem",
    background: "rgba(0,0,0,0.2)",
    borderRadius: "6px",
    fontSize: "0.8rem",
    overflow: "auto",
    maxHeight: "300px",
    whiteSpace: "pre-wrap",
  },
};

export default App;
