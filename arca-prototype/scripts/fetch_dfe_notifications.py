"""
Fetch Domicilio Fiscal Electrónico notifications using credentials from .env.
Run from arca-prototype/: python scripts/fetch_dfe_notifications.py

Requires ARCA_CUIT and ARCA_PASSWORD in .env (copy from .env.example).
"""
import asyncio
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

from backend.services.arca_scraper import open_domicilio_fiscal_electronico


async def main():
    cuit = os.getenv("ARCA_CUIT", "").strip()
    password = os.getenv("ARCA_PASSWORD", "").strip()

    if not cuit or not password:
        print("Error: Set ARCA_CUIT and ARCA_PASSWORD in .env")
        print("Copy .env.example to .env and fill in your credentials.")
        sys.exit(1)

    result = await open_domicilio_fiscal_electronico(cuit, password)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
