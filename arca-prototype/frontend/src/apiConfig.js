// ── Runtime backend URL config ──────────────────────────────
// Separate module to avoid circular imports (App → components → App)
const DEFAULT_BACKEND = "http://localhost:8000";

export function getApiBase() {
  // Build-time env var takes priority, then localStorage, then default
  const envUrl = import.meta.env.VITE_API_URL;
  if (envUrl) return envUrl;
  // In dev mode (Vite proxy), use empty string so /api goes to same origin
  if (import.meta.env.DEV) return "";
  return localStorage.getItem("arca_backend_url") || DEFAULT_BACKEND;
}

export { DEFAULT_BACKEND };
