"""
ARCA Prototype - FastAPI backend.
Receives credentials from frontend and orchestrates ARCA scraping.
"""
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI

# Load .env from arca-prototype root
load_dotenv(Path(__file__).resolve().parents[1] / ".env")
from fastapi.middleware.cors import CORSMiddleware

from backend.routers import arca, colppy

app = FastAPI(
    title="ARCA Prototype API",
    description="Backend for ARCA scraping prototype",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(arca.router, prefix="/api/arca", tags=["arca"])
app.include_router(colppy.router, prefix="/api/colppy", tags=["colppy"])


@app.get("/health")
def health():
    """Health check for the API."""
    return {"status": "ok"}
