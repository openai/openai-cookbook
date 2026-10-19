import os
from urllib.parse import urlsplit

from fastmcp import FastMCP
from pydantic import BaseModel, Field

mcp = FastMCP("BLS evaluation fixture")


class IndicatorQuery(BaseModel):
    indicator: str = Field(description="Economic indicator to resolve.")


# These observations are deterministic fixture data, not current official BLS values.
SERIES = {
    "LNS14000000": {
        "title": "Unemployment Rate - Seasonally Adjusted",
        "data": [
            {"year": "2026", "period": "M01", "value": "4.0"},
            {"year": "2026", "period": "M02", "value": "4.1"},
        ],
    },
    "LNU04000000": {
        "title": "Unemployment Rate - Not Seasonally Adjusted",
        "data": [
            {"year": "2026", "period": "M01", "value": "4.3"},
            {"year": "2026", "period": "M02", "value": "3.9"},
        ],
    },
    "LNS12000000": {
        "title": "Employment Level - Seasonally Adjusted",
        "data": [
            {"year": "2026", "period": "M01", "value": "163000"},
            {"year": "2026", "period": "M02", "value": "163200"},
        ],
    },
    "LNS11300000": {
        "title": "Labor Force Participation Rate - Seasonally Adjusted",
        "data": [
            {"year": "2026", "period": "M01", "value": "62.5"},
            {"year": "2026", "period": "M02", "value": "62.6"},
        ],
    },
    "CES0000000001": {
        "title": "All Employees, Total Nonfarm - Seasonally Adjusted",
        "data": [
            {"year": "2026", "period": "M01", "value": "159100"},
            {"year": "2026", "period": "M02", "value": "159250"},
        ],
    },
}


def series_for(indicator: str) -> list[tuple[str, float]]:
    normalized = indicator.lower()
    if "unemploy" in normalized:
        return [("LNS14000000", 1.0), ("LNU04000000", 0.6)]
    if "participation" in normalized:
        return [("LNS11300000", 1.0)]
    if "nonfarm" in normalized or "payroll" in normalized:
        return [("CES0000000001", 1.0)]
    if "employ" in normalized:
        return [("LNS12000000", 0.5), ("CES0000000001", 0.5)]
    return []


@mcp.tool
def resolve(indicators: list[IndicatorQuery]) -> dict:
    """Resolve economic indicators to ranked candidate BLS series. Call before fetch_bls_data."""
    results = []
    for query in indicators:
        candidates = [
            {"series_id": series_id, "title": SERIES[series_id]["title"], "confidence": confidence}
            for series_id, confidence in series_for(query.indicator)
        ]
        entry = {"indicator": query.indicator, "candidates": candidates}
        if not candidates:
            # An empty list on its own is indistinguishable from a transient failure, and a
            # model that cannot tell the difference retries instead of reporting the gap.
            entry["note"] = (
                "No series in this catalog covers that indicator. "
                "This is a definitive answer, not a transient failure."
            )
        results.append(entry)
    return {"results": results}


@mcp.tool
def fetch_bls_data(series_ids: list[str]) -> dict:
    """Fetch observations for validated BLS series IDs."""
    data = []
    for series_id in series_ids:
        record = SERIES.get(series_id)
        if not record:
            data.append({"series_id": series_id, "error": "unknown series"})
            continue
        data.append(
            {
                "series_id": series_id,
                "title": record["title"],
                "data": record["data"],
            }
        )
    return {"data": data}


if __name__ == "__main__":
    url = urlsplit(os.environ.get("MCP_URL", "http://127.0.0.1:8000/mcp"))
    mcp.run(transport="http", host=url.hostname, port=url.port)
