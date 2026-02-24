# ARCA Prototype — Deployment Guide

## Architecture Split

The ARCA prototype is split into two deployable parts:

| Part | Where | Why |
|------|-------|-----|
| **Frontend** (React) | GitHub Pages | Static files, no server needed |
| **Backend** (FastAPI) | Local machine + tunnel | Playwright requires a browser; Colppy/ARCA credentials stay local |

---

## Frontend — GitHub Pages

### How It Works

Vite builds the React app into `docs/arca-app/` in the repo root. A GitHub Actions workflow deploys the entire `docs/` directory to GitHub Pages.

### Build

```bash
cd arca-prototype/frontend
npm run build
# Output → ../../docs/arca-app/
```

The Vite config (`vite.config.js`) sets:
- `base: "/openai-cookbook/arca-app/"` in production (correct asset paths on GitHub Pages)
- `outDir: "../../docs/arca-app"` (2 levels up from `frontend/` = repo root's `docs/`)

### Deploy

Push to `main` — the GitHub Actions workflow (`.github/workflows/deploy-pages.yml`) triggers automatically on changes to `docs/**`.

Manual trigger: Go to **Actions → Deploy to GitHub Pages → Run workflow**.

### GitHub Pages Settings

In the repo's **Settings → Pages**:
- **Source:** GitHub Actions (not "Deploy from a branch")
- The `.nojekyll` file in `docs/` prevents Jekyll processing

### Backend URL Configuration

The frontend needs to know where the backend is running. Priority order:
1. Build-time `VITE_API_URL` env var
2. In Vite dev mode: empty string (proxied to `localhost:8000`)
3. `localStorage.getItem("arca_backend_url")`
4. Default: `http://localhost:8000`

Users can click the green/red status dot in the header to change the backend URL at runtime. The URL is saved to localStorage and persists across refreshes.

---

## Backend — Local Setup

### Prerequisites

- Python 3.11+
- Playwright browsers installed

### Install

```bash
cd arca-prototype
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### Configure

Create `.env` in `arca-prototype/`:

```env
ARCA_CUIT=20268448536
ARCA_PASSWORD=your_clave_fiscal
ARCA_HEADLESS=true

COLPPY_USER=your_colppy_user
COLPPY_PASSWORD=your_colppy_password
COLPPY_ID_EMPRESA=your_empresa_id

# Optional
GALICIA_DNI=your_dni
GALICIA_USER=your_user
GALICIA_PASS=your_pass
```

### Run

```bash
cd arca-prototype
.venv/bin/uvicorn backend.main:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs` (Swagger UI).

---

## Remote Access — Cloudflare Tunnel

To let remote users (e.g., accounting team) access the backend running on your local machine:

### Install cloudflared

```bash
brew install cloudflared
```

No signup or authentication required.

### Start Tunnel

```bash
cloudflared tunnel --url http://localhost:8000
```

This outputs a random URL like:
```
https://expressed-atlas-metro-adjustment.trycloudflare.com
```

### Share with Users

1. Send the `*.trycloudflare.com` URL to users
2. Users go to the GitHub Pages frontend
3. Click the status dot (top-right) → paste the tunnel URL → Save
4. The frontend now routes all API calls through the tunnel

### Notes

- The tunnel URL changes every time you restart `cloudflared`
- The backend must be running on `localhost:8000` at the same time
- CORS is set to `allow_origins=["*"]` to support tunnel URLs
- The tunnel is **public** — anyone with the URL can access the API while the tunnel is running

---

## Development Mode

For local development, the frontend Vite dev server proxies API calls to the backend:

```bash
# Terminal 1 — Backend
cd arca-prototype && .venv/bin/uvicorn backend.main:app --reload --port 8000

# Terminal 2 — Frontend
cd arca-prototype/frontend && npm run dev
# → http://localhost:5173 (auto-proxies /api → localhost:8000)
```

In dev mode, `getApiBase()` returns an empty string, so `/api/arca/...` goes to the same origin and Vite's proxy handles the rest.
