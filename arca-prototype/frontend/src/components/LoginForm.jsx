import { useState } from "react";
import { getApiBase } from "../App";

const API_BASE = getApiBase();

async function callApi(endpoint, body, onResult) {
  try {
    const res = await fetch(`${API_BASE}${endpoint}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      onResult({
        success: false,
        message: data.detail || "Error de conexión",
        data: null,
      });
      return;
    }
    onResult(data);
  } catch (err) {
    onResult({
      success: false,
      message: err.message || "No se pudo conectar al backend",
      data: null,
    });
  }
}

function LoginForm({ onResult }) {
  const [cuit, setCuit] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [loadingDfe, setLoadingDfe] = useState(false);
  const [loadingNotif, setLoadingNotif] = useState(false);

  const handleLogin = async (e) => {
    e.preventDefault();
    setLoading(true);
    onResult(null);
    await callApi("/api/arca/login", { cuit: cuit.trim(), password }, onResult);
    setLoading(false);
  };

  const handleDfe = async (e) => {
    e.preventDefault();
    if (!cuit.trim() || !password) {
      onResult({ success: false, message: "Ingrese CUIT y Clave Fiscal primero", data: null });
      return;
    }
    setLoadingDfe(true);
    onResult(null);
    await callApi(
      "/api/arca/domicilio-fiscal-electronico",
      { cuit: cuit.trim(), password },
      onResult
    );
    setLoadingDfe(false);
  };

  const handleNotif = async (e) => {
    e.preventDefault();
    if (!cuit.trim() || !password) {
      onResult({ success: false, message: "Ingrese CUIT y Clave Fiscal primero", data: null });
      return;
    }
    setLoadingNotif(true);
    onResult(null);
    await callApi("/api/arca/notificaciones", { cuit: cuit.trim(), password }, onResult);
    setLoadingNotif(false);
  };

  const loadingAny = loading || loadingDfe || loadingNotif;

  return (
    <form onSubmit={handleLogin} style={styles.form}>
      <div style={styles.field}>
        <label htmlFor="cuit" style={styles.label}>
          CUIT / CUIL
        </label>
        <input
          id="cuit"
          type="text"
          value={cuit}
          onChange={(e) => setCuit(e.target.value)}
          placeholder="20-12345678-9"
          required
          maxLength={15}
          style={styles.input}
          disabled={loadingAny}
        />
      </div>

      <div style={styles.field}>
        <label htmlFor="password" style={styles.label}>
          Clave Fiscal
        </label>
        <input
          id="password"
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          required
          style={styles.input}
          disabled={loadingAny}
        />
      </div>

      <div style={styles.buttons}>
        <button type="submit" disabled={loadingAny} style={styles.button}>
          {loading ? "Conectando..." : "Ingresar a ARCA"}
        </button>
        <button
          type="button"
          onClick={handleDfe}
          disabled={loadingAny}
          style={styles.buttonSecondary}
        >
          {loadingDfe ? "Cargando..." : "Ver Domicilio Fiscal Electrónico"}
        </button>
        <button
          type="button"
          onClick={handleNotif}
          disabled={loadingAny}
          style={styles.buttonSecondary}
        >
          {loadingNotif ? "Leyendo..." : "Leer todas las notificaciones"}
        </button>
      </div>
    </form>
  );
}

const styles = {
  form: {
    display: "flex",
    flexDirection: "column",
    gap: "1rem",
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
  buttons: {
    marginTop: "0.5rem",
    display: "flex",
    flexDirection: "column",
    gap: "0.5rem",
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
  buttonSecondary: {
    padding: "0.85rem 1.25rem",
    fontSize: "0.95rem",
    fontWeight: 600,
    borderRadius: "8px",
    border: "1px solid #475569",
    background: "transparent",
    color: "#94a3b8",
    cursor: "pointer",
  },
};

export default LoginForm;
