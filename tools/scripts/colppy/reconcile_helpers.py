"""
Shared helpers for Colppy ↔ HubSpot reconciliation.
"""
HUBSPOT_PORTAL_ID = "19877595"


def hubspot_deal_url(hubspot_id: str) -> str:
    """Build clickable HubSpot deal URL."""
    if not hubspot_id:
        return ""
    return f"https://app.hubspot.com/contacts/{HUBSPOT_PORTAL_ID}/deal/{hubspot_id}"


def norm_date(s: str) -> str:
    """Normalize to YYYY-MM-DD for comparison."""
    if not s:
        return ""
    return (str(s).strip()[:10]).replace("/", "-")


def dates_match(colppy_fecha: str, hubspot_close: str) -> bool:
    """True if Colppy fechaPago date equals HubSpot close_date date."""
    return norm_date(colppy_fecha) == norm_date(hubspot_close)


def plan_mismatch(colppy_id_plan: str | int | None, hubspot_id_plan: str | None) -> bool:
    """True if both are non-blank and differ. Blank on either side => not a mismatch."""
    c = str(colppy_id_plan or "").strip()
    h = str(hubspot_id_plan or "").strip()
    if not c or not h:
        return False
    return c != h


def fmt_amt(x, decimals: int = 2) -> str:
    """Format amount for Argentina: $ and comma as decimal separator."""
    try:
        fmt = f"${{:,.{decimals}f}}"
        return fmt.format(float(x)).replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return str(x)


def sort_key_id_empresa(x) -> tuple:
    """Sort key for id_empresa: numeric first by value, then non-numeric by string."""
    s = str(x) if x is not None else ""
    return (0 if s.isdigit() else 1, int(s) if s.isdigit() else s)
