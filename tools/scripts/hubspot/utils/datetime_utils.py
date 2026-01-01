"""
Datetime utilities for HubSpot analysis
Common datetime parsing and formatting functions
"""

from datetime import datetime, timedelta
from typing import Optional, Tuple


def parse_datetime(date_str: Optional[str]) -> Optional[datetime]:
    """
    Parse HubSpot datetime string to datetime object.
    
    Handles multiple formats:
    - ISO format with 'T': "2025-11-15T10:30:00.000Z"
    - Date-only: "2025-11-15"
    - Returns None for empty/invalid strings
    
    Args:
        date_str: HubSpot datetime string or None
        
    Returns:
        datetime object or None if parsing fails
    """
    if not date_str or date_str == '' or date_str == 'null':
        return None
    
    try:
        # HubSpot datetime format: "2025-11-15T10:30:00.000Z"
        if 'T' in date_str:
            # Replace Z with +00:00 for timezone-aware parsing
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        # fecha_activo is just a date: "2025-11-07"
        else:
            return datetime.fromisoformat(date_str + "T00:00:00+00:00")
    except (ValueError, AttributeError):
        return None


def format_date_for_hubspot(date: datetime) -> str:
    """
    Format datetime for HubSpot API.
    
    Format: YYYY-MM-DDTHH:MM:SS.000Z
    
    Args:
        date: datetime object
        
    Returns:
        Formatted string for HubSpot API
    """
    if date.tzinfo is None:
        date = date.replace(tzinfo=datetime.now().astimezone().tzinfo)
    
    return date.strftime('%Y-%m-%dT%H:%M:%S.000Z')


def get_month_dates(month_str: str) -> Tuple[str, str]:
    """
    Convert YYYY-MM format to start/end dates of the month.
    
    Args:
        month_str: Month in YYYY-MM format (e.g., "2025-11")
        
    Returns:
        Tuple of (start_date, end_date) as YYYY-MM-DD strings
    """
    year, month = map(int, month_str.split('-'))
    start_date = datetime(year, month, 1)
    
    # Get last day of month
    if month == 12:
        end_date = datetime(year + 1, 1, 1) - timedelta(days=1)
    else:
        end_date = datetime(year, month + 1, 1) - timedelta(days=1)
    
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')


def get_current_month_to_date() -> Tuple[str, str]:
    """
    Get current month start date to today.
    
    Returns:
        Tuple of (start_date, end_date) as YYYY-MM-DD strings
    """
    today = datetime.now()
    start_date = datetime(today.year, today.month, 1)
    return start_date.strftime('%Y-%m-%d'), today.strftime('%Y-%m-%d')


def format_date_display(date_str: Optional[str]) -> str:
    """
    Format date string for display purposes.
    
    Args:
        date_str: ISO date string or None
        
    Returns:
        Formatted string for display or "N/A"
    """
    if not date_str:
        return "N/A"
    
    dt = parse_datetime(date_str)
    if dt:
        return dt.strftime("%Y-%m-%d %H:%M")
    return date_str











