"""
Banco Galicia scraper service using Playwright.
Handles login and savings account statement extraction.

Follows the same pattern as arca_scraper.py for consistency.

## Key DOM findings (validated Feb 2026):
- Login form uses React controlled inputs: fill() doesn't trigger JS validators,
  must use type() with delays or evaluate() to dispatch input events.
- Transactions are rendered as div.table-row.cursor-p (role="button"), NOT <button>.
- Date appears in a child div.detalle-movimiento matching DD/MM/YYYY.
- Amount is embedded in tooltip or sibling text matching -?$[\\d.,]+
- Navigation: Home → "Cuentas" sidebar link → click specific account row.

Environment variables:
    GALICIA_DNI: DNI number (numeric)
    GALICIA_USER: Galicia username
    GALICIA_PASS: Galicia password
    GALICIA_HEADLESS: "true"/"false" (default: "true")
    GALICIA_TIMEOUT_MS: timeout in ms (default: 30000)
"""

import asyncio
import csv
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass, asdict

from playwright.async_api import (  # type: ignore[import-untyped]
    async_playwright,
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeout,
)

# Configuration via environment
GALICIA_LOGIN_URL = "https://onlinebanking.bancogalicia.com.ar/login"
HEADLESS = os.getenv("GALICIA_HEADLESS", "true").lower() == "true"
TIMEOUT_MS = int(os.getenv("GALICIA_TIMEOUT_MS", "30000"))


@dataclass
class BankTransaction:
    """A single bank account transaction."""
    date: str
    description: str
    amount: float
    balance: Optional[float] = None
    reference: Optional[str] = None


@dataclass
class AccountStatement:
    """Extracted bank account statement."""
    account_number: str
    account_type: str  # e.g. "Caja de Ahorro en Pesos"
    currency: str
    balance: Optional[float]
    transactions: list
    extracted_at: str
    period: Optional[str] = None


def _get_credentials() -> tuple[str, str, str]:
    """Read credentials from environment variables."""
    dni = os.getenv("GALICIA_DNI", "")
    user = os.getenv("GALICIA_USER", "")
    password = os.getenv("GALICIA_PASS", "")

    if not all([dni, user, password]):
        raise ValueError(
            "Missing Banco Galicia credentials. Set environment variables:\n"
            "  export GALICIA_DNI='your_dni'\n"
            "  export GALICIA_USER='your_username'\n"
            "  export GALICIA_PASS='your_password'"
        )

    return dni, user, password


def parse_ar_amount(raw: str) -> float:
    """Parse an Argentine-formatted currency amount.

    Examples:
        "$100.000,00"  → 100000.00
        "-$242.300,75" → -242300.75
        "$17,31"       → 17.31
    """
    negative = raw.startswith("-")
    digits = raw.replace("$", "").replace("-", "").strip()
    # Argentine: dots are thousands separators, comma is decimal
    digits = digits.replace(".", "").replace(",", ".")
    value = float(digits)
    return -value if negative else value


async def _create_browser_context(playwright) -> tuple[Browser, BrowserContext, Page]:
    """Create a browser context with standard settings."""
    browser = await playwright.chromium.launch(headless=HEADLESS)
    context = await browser.new_context(
        viewport={"width": 1280, "height": 720},
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
    )
    page = await context.new_page()
    page.set_default_timeout(TIMEOUT_MS)
    return browser, context, page


async def _fill_input_with_events(page: Page, selector: str, value: str):
    """Fill an input triggering React's synthetic event system.

    Galicia's React app uses controlled components. Plain fill() sets the
    DOM value but doesn't fire the onChange handlers React listens for,
    leaving the submit button disabled. This helper:
    1. Focuses the field
    2. Clears existing content
    3. Types character by character with a small delay
    This fires keydown/keypress/input/keyup per character, which React picks up.
    """
    el = page.locator(selector).first
    await el.click()
    await el.fill("")  # clear first
    await el.type(value, delay=50)
    await asyncio.sleep(0.3)


async def _login(page: Page, dni: str, user: str, password: str) -> dict[str, Any]:
    """
    Perform login to Banco Galicia Online Banking.

    Uses type() instead of fill() because Galicia's React form requires
    proper keyboard events to enable the submit button.

    Returns dict with success status and any error message.
    """
    await page.goto(GALICIA_LOGIN_URL, wait_until="networkidle")
    await asyncio.sleep(2)

    # Type into each field with delays to trigger React validators
    await _fill_input_with_events(
        page,
        'input[aria-label="Tu DNI"], input[placeholder*="DNI"]',
        dni,
    )
    await _fill_input_with_events(
        page,
        'input[aria-label="Tu usuario Galicia"], input[placeholder*="usuario"]',
        user,
    )
    await _fill_input_with_events(
        page,
        'input[aria-label="Tu clave Galicia"], input[placeholder*="clave"]',
        password,
    )

    await asyncio.sleep(1)

    # Click login button — should now be enabled after type() fired events
    login_btn = page.get_by_role("button", name="iniciar sesión")
    if await login_btn.is_disabled():
        # Fallback: tab out of password field to trigger final validation
        pass_input = page.locator('input[aria-label="Tu clave Galicia"]').first
        await pass_input.press("Tab")
        await asyncio.sleep(1)

    await login_btn.click()
    await asyncio.sleep(5)

    # Check for errors or successful navigation
    current_url = page.url
    if "login" in current_url.lower():
        error_el = page.locator(
            '[class*="error"], [class*="alert"], [role="alert"]'
        ).first
        if await error_el.count() > 0:
            error_text = await error_el.text_content()
            return {"success": False, "message": f"Login error: {error_text}"}
        return {"success": False, "message": "Login failed — still on login page"}

    return {"success": True, "message": "Login successful", "url": current_url}


async def login_test() -> dict[str, Any]:
    """
    Test login to Banco Galicia and return the post-login page state.
    Does NOT navigate further — just verifies credentials work.
    """
    dni, user, password = _get_credentials()

    async with async_playwright() as p:
        browser, context, page = await _create_browser_context(p)

        try:
            result = await _login(page, dni, user, password)

            if not result["success"]:
                await browser.close()
                return result

            # Capture post-login state
            title = await page.title()
            body_text = await page.locator("body").inner_text()

            await browser.close()

            return {
                "success": True,
                "message": "Login exitoso",
                "data": {
                    "page_title": title,
                    "current_url": result["url"],
                    "body_preview": body_text[:2000].strip(),
                },
            }

        except PlaywrightTimeout as e:
            await browser.close()
            return {"success": False, "message": f"Timeout: {e}", "data": None}
        except Exception as e:
            await browser.close()
            return {"success": False, "message": str(e), "data": None}


async def _navigate_to_account(page: Page, account_fragment: str = "CA$") -> bool:
    """Navigate from home page to a specific account's detail/statement view.

    After login, the home page shows account cards. We:
    1. Click "Cuentas" in the sidebar to open the accounts section
    2. Click the row matching `account_fragment` (e.g. "CA$" for Caja de Ahorro Pesos)

    Returns True if navigation succeeded.
    """
    # Step 1: Click "Cuentas" in the nav sidebar
    cuentas_link = page.get_by_text("Cuentas", exact=True).first
    if await cuentas_link.count() == 0:
        cuentas_link = page.locator('a[href*="cuentas"], a[href*="accounts"]').first
    await cuentas_link.click()
    await asyncio.sleep(3)

    # Step 2: Click the specific account row
    account_row = page.get_by_text(account_fragment, exact=False).first
    if await account_row.count() == 0:
        return False
    await account_row.click()
    await asyncio.sleep(3)

    return True


async def _extract_transactions_from_dom(page: Page) -> list[BankTransaction]:
    """Extract transactions from the account detail page via DOM traversal.

    Galicia renders transactions as div.table-row.cursor-p elements (role="button")
    inside a div.table-container.table-capitalize. Each row contains child divs
    for date, description, and amount.

    This runs a JS snippet inside the page context for reliable extraction.
    """
    raw_transactions = await page.evaluate("""
        () => {
            const rows = document.querySelectorAll('div.table-row.cursor-p');
            const results = [];
            const dateRe = /^\\d{2}\\/\\d{2}\\/\\d{4}$/;
            const amountRe = /^-?\\$[\\d.,]+$/;

            // Use leaf-node text to avoid parent divs concatenating child text.
            // Positive amounts get duplicated as "$100.000,00100.000,00" when
            // reading textContent from a parent that has both the value div
            // and an accessibility tooltip div as children.
            function leafTexts(el) {
                const out = [];
                for (const child of el.querySelectorAll('*')) {
                    if (child.children.length === 0 && child.textContent.trim()) {
                        out.push(child.textContent.trim());
                    }
                }
                return out;
            }

            for (const row of rows) {
                const texts = leafTexts(row);

                let date = '';
                let amount = '';
                const descParts = [];

                for (const t of texts) {
                    if (!date && dateRe.test(t)) {
                        date = t;
                    } else if (!amount && amountRe.test(t)) {
                        amount = t;
                    } else if (date && !amount && t.length > 2
                               && !dateRe.test(t) && !t.endsWith('Pesos')) {
                        descParts.push(t);
                    }
                }

                if (date && amount) {
                    const desc = [...new Set(descParts)]
                        .filter(p => !dateRe.test(p) && !amountRe.test(p))
                        .join(' ')
                        .trim();
                    results.push({ date, description: desc, amount });
                }
            }
            return results;
        }
    """)

    transactions = []
    for row in raw_transactions:
        try:
            transactions.append(BankTransaction(
                date=row["date"],
                description=row["description"],
                amount=parse_ar_amount(row["amount"]),
            ))
        except (ValueError, KeyError):
            continue

    return transactions


async def get_savings_account_statements(
    account_fragment: str = "CA$",
    export_csv: bool = True,
) -> dict[str, Any]:
    """Login, navigate to savings account, and extract transactions.

    Args:
        account_fragment: Text fragment to identify the account row (default: "CA$"
            which matches Caja de Ahorro Pesos).
        export_csv: If True, save transactions to arca-prototype/data/ as CSV.

    Returns structured transaction data.
    """
    dni, user, password = _get_credentials()

    async with async_playwright() as p:
        browser, context, page = await _create_browser_context(p)

        try:
            login_result = await _login(page, dni, user, password)
            if not login_result["success"]:
                await browser.close()
                return login_result

            await asyncio.sleep(3)

            # Navigate: Home → Cuentas → specific account
            nav_ok = await _navigate_to_account(page, account_fragment)
            if not nav_ok:
                body_text = await page.locator("body").inner_text()
                await browser.close()
                return {
                    "success": False,
                    "message": f"Could not find account matching '{account_fragment}'",
                    "data": {"page_preview": body_text[:2000]},
                }

            # Extract transactions from the DOM
            transactions = await _extract_transactions_from_dom(page)

            await browser.close()

            result = {
                "success": True,
                "message": f"Extracted {len(transactions)} transactions",
                "data": {
                    "transactions": [asdict(t) for t in transactions],
                    "transaction_count": len(transactions),
                },
            }

            # Optionally export to CSV
            if export_csv and transactions:
                csv_path = _export_to_csv(transactions)
                result["data"]["csv_path"] = str(csv_path)

            return result

        except PlaywrightTimeout as e:
            await browser.close()
            return {"success": False, "message": f"Timeout: {e}", "data": None}
        except Exception as e:
            await browser.close()
            return {"success": False, "message": str(e), "data": None}


def _export_to_csv(transactions: list[BankTransaction]) -> Path:
    """Write transactions to a dated CSV in arca-prototype/data/."""
    data_dir = Path(__file__).resolve().parent.parent.parent / "data"
    data_dir.mkdir(exist_ok=True)

    today = datetime.now().strftime("%Y%m%d")
    csv_path = data_dir / f"banco_galicia_statements_{today}.csv"

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "description", "amount"])
        for t in transactions:
            # Write in Argentine display format for readability
            sign = "-" if t.amount < 0 else ""
            abs_val = abs(t.amount)
            formatted = f'{sign}${abs_val:,.2f}'.replace(",", "X").replace(".", ",").replace("X", ".")
            writer.writerow([t.date, t.description, formatted])

    return csv_path


async def explore_post_login_structure() -> dict[str, Any]:
    """
    Login and return the full page structure for manual exploration.
    Use this to understand navigation before automating specific paths.
    """
    dni, user, password = _get_credentials()

    async with async_playwright() as p:
        browser, context, page = await _create_browser_context(p)

        try:
            login_result = await _login(page, dni, user, password)
            if not login_result["success"]:
                await browser.close()
                return login_result

            await asyncio.sleep(3)

            # Collect all visible links and buttons
            links = []
            for link in await page.locator("a[href]").all():
                text = await link.text_content()
                href = await link.get_attribute("href")
                if text and text.strip():
                    links.append({"text": text.strip()[:100], "href": href})

            buttons = []
            for btn in await page.locator("button").all():
                text = await btn.text_content()
                if text and text.strip():
                    buttons.append(text.strip()[:100])

            # Get full body text
            body = await page.locator("body").inner_text()
            title = await page.title()

            await browser.close()

            return {
                "success": True,
                "message": "Post-login structure extracted",
                "data": {
                    "page_title": title,
                    "current_url": login_result["url"],
                    "links": links[:50],
                    "buttons": buttons[:30],
                    "body_text": body[:5000],
                },
            }

        except Exception as e:
            await browser.close()
            return {"success": False, "message": str(e), "data": None}


# --- CLI entry point ---

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Banco Galicia Statement Scraper")
    parser.add_argument(
        "--action",
        choices=["test-login", "statements", "explore"],
        default="test-login",
        help="Action to perform",
    )
    parser.add_argument(
        "--account",
        default="CA$",
        help="Account identifier fragment (default: 'CA$' = Caja de Ahorro Pesos)",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Skip CSV export",
    )
    args = parser.parse_args()

    if args.action == "test-login":
        result = asyncio.run(login_test())
    elif args.action == "statements":
        result = asyncio.run(get_savings_account_statements(
            account_fragment=args.account,
            export_csv=not args.no_csv,
        ))
    elif args.action == "explore":
        result = asyncio.run(explore_post_login_structure())

    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
