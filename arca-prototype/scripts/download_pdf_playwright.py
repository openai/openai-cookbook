#!/usr/bin/env python3
"""
Download PDF attachment for a specific DFE notification via Playwright.

Uses the DFE REST API through an authenticated browser session:
  1. Login to ARCA → navigate to DFE → capture auth token
  2. Fetch notification detail → get adjunto metadata (idArchivo, filename)
  3. Download PDF via GET /api/v1/communications/{idComunicacion}/{idArchivo}

Usage:
    python scripts/download_pdf_playwright.py [notification_id]
    # Default: 582958952 (SCT - Intimación)
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

load_dotenv()


async def main():
    nid = int(sys.argv[1]) if len(sys.argv) > 1 else 582958952
    cuit = os.getenv("ARCA_CUIT", "")
    password = os.getenv("ARCA_PASSWORD", "")

    if not cuit or not password:
        print("Set ARCA_CUIT and ARCA_PASSWORD in .env")
        sys.exit(1)

    print(f"Downloading PDF for notification {nid}...")
    from backend.services.attachment_download import download_attachment

    result = await download_attachment(
        cuit=cuit,
        password=password,
        notification_id=nid,
    )

    if result["success"]:
        print(f"SUCCESS: {result['path']}")
        print(f"  {result.get('message', '')}")
    else:
        print(f"FAILED: {result['error']}")
        if result.get("message"):
            print(f"  {result['message']}")


if __name__ == "__main__":
    asyncio.run(main())
