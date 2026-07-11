import re
from datetime import UTC, datetime

from dateutil.parser import parse


def parse_date_str(value: str | datetime | None) -> datetime | None:
    """Parse a date string into a datetime object.

    If the value is a 4-digit year, it returns January 1 of that year in UTC.
    Otherwise, it attempts to parse the date string using dateutil.parser.parse.
    If the resulting datetime has no timezone, it defaults to UTC.
    """
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    try:
        # Year Handling
        if re.fullmatch(r"\d{4}", value.strip()):
            year = int(value.strip())
            return datetime(year, 1, 1, tzinfo=UTC)

        #  General Handing
        dt: datetime = parse(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt

    except Exception:
        return None


def safe_iso(dt: datetime | None) -> str | None:
    """Return the ISO format of a datetime object.

    If the datetime is None, it returns None.
    """
    if isinstance(dt, str):
        dt = parse_date_str(dt)

    if isinstance(dt, datetime):
        return dt.isoformat()

    return None
