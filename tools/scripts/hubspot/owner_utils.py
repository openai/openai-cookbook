#!/usr/bin/env python3
"""
HubSpot Owner Utilities
=======================
Shared utility functions for fetching and caching HubSpot owner names.
This module ensures all scripts display actual owner names instead of "Unknown (ID)".
"""

import sys
import os
from typing import Optional, Dict

# Add tools directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from dotenv import load_dotenv
load_dotenv()

# Try to use HubSpot API client if available
try:
    from hubspot_api.client import HubSpotClient, HubSpotAPIError
    HUBSPOT_CLIENT_AVAILABLE = True
except ImportError:
    HUBSPOT_CLIENT_AVAILABLE = False

# Cache for owner names to avoid repeated API calls
_OWNER_CACHE: Dict[str, str] = {}

# Cache for owner status (active/inactive)
_OWNER_STATUS_CACHE: Dict[str, bool] = {}

# Static owner mapping for known owners (fallback)
_STATIC_OWNER_MAP = {
    "1571181342": "Rocio Luque",
    "79369461": "Mariano Alvarez Bor",
    "103406387": "Karina Lorena Russo",
    "81313123": "Tatiana Amaya",
    "78535701": "Estefania Sol Arregui",
    "80563180": "Sofia Celentano",
    "216511812": "Juan Ignacio Onetto",
    "1587023252": "Eliana Delpiero",
    "151388545": "Pamela Viarengo",
    "1718788346": "Ivo Salvador Gassner",
    "672724138": "Pablo Ezcurra",
    "213457436": "Antonella Pachas",
    "713598836": "Santiago Martinez",
    "416739362": "Claudia Cristi",
    "688875036": "Pablo Pereira Colman",
    "206527914": "Melina Costa",
    "82921632": "Jair Josue Calas",
    "82002684": "Colppy Sueldos",
    "80746866": "Camila Gisel Lagoa",
}

def fetch_owner_from_api(owner_id: str) -> Optional[Dict]:
    """
    Fetch owner details from HubSpot API
    
    Args:
        owner_id: HubSpot owner ID as string (or can be int/float, will be converted)
        
    Returns:
        Dictionary with owner details (name, archived status) if found, None otherwise
    """
    if not HUBSPOT_CLIENT_AVAILABLE:
        return None
    
    try:
        # Convert to int first to handle float IDs, then to string
        owner_id_clean = str(int(float(str(owner_id))))
        client = HubSpotClient()
        endpoint = f"crm/v3/owners/{owner_id_clean}"
        owner = client.get(endpoint)
        
        if owner:
            first_name = owner.get('firstName', '')
            last_name = owner.get('lastName', '')
            name = f"{first_name} {last_name}".strip()
            archived = owner.get('archived', True)  # Default to True (inactive) if not found
            
            return {
                'name': name if name else None,
                'archived': archived,
                'is_active': not archived
            }
    except Exception:
        # Silently fail and return None - will use fallback
        pass
    
    return None

def fetch_owner_name_from_api(owner_id: str) -> Optional[str]:
    """
    Fetch owner name from HubSpot API (backward compatibility)
    
    Args:
        owner_id: HubSpot owner ID as string
        
    Returns:
        Owner name if found, None otherwise
    """
    owner_data = fetch_owner_from_api(owner_id)
    if owner_data and owner_data.get('name'):
        return owner_data['name']
    return None

def get_owner_name(owner_id, use_cache: bool = True) -> str:
    """
    Get owner name from ID, with API fallback and caching
    
    Args:
        owner_id: HubSpot owner ID (can be string, int, or None)
        use_cache: Whether to use cached results (default: True)
        
    Returns:
        Owner name or "No Owner" if owner_id is None/empty
    """
    if not owner_id:
        return "No Owner"
    
    owner_id_str = str(owner_id)
    
    # Check cache first
    if use_cache and owner_id_str in _OWNER_CACHE:
        return _OWNER_CACHE[owner_id_str]
    
    # Check static map
    if owner_id_str in _STATIC_OWNER_MAP:
        name = _STATIC_OWNER_MAP[owner_id_str]
        if use_cache:
            _OWNER_CACHE[owner_id_str] = name
        return name
    
    # Try to fetch from API
    api_name = fetch_owner_name_from_api(owner_id_str)
    if api_name:
        if use_cache:
            _OWNER_CACHE[owner_id_str] = api_name
        return api_name
    
    # Fallback: return Unknown with ID
    return f"Unknown ({owner_id_str})"

def get_owner_status(owner_id, use_cache: bool = True) -> Optional[bool]:
    """
    Get owner active status from ID
    
    Args:
        owner_id: HubSpot owner ID (can be string, int, or None)
        use_cache: Whether to use cached results (default: True)
        
    Returns:
        True if active, False if inactive/archived, None if not found
    """
    if not owner_id:
        return None
    
    owner_id_str = str(owner_id)
    
    # Check cache first
    if use_cache and owner_id_str in _OWNER_STATUS_CACHE:
        return _OWNER_STATUS_CACHE[owner_id_str]
    
    # Try to fetch from API
    owner_data = fetch_owner_from_api(owner_id_str)
    if owner_data:
        is_active = owner_data.get('is_active', False)
        if use_cache:
            _OWNER_STATUS_CACHE[owner_id_str] = is_active
        return is_active
    
    # If not found in API, assume active (for backward compatibility)
    # This handles cases where static map owners don't have status
    return True

def get_owner_name_and_status(owner_id, use_cache: bool = True) -> tuple:
    """
    Get both owner name and status in one call
    
    Args:
        owner_id: HubSpot owner ID (can be string, int, or None)
        use_cache: Whether to use cached results (default: True)
        
    Returns:
        Tuple of (name, is_active) where is_active is True/False/None
    """
    name = get_owner_name(owner_id, use_cache)
    status = get_owner_status(owner_id, use_cache)
    return (name, status)

def get_owner_name_batch(owner_ids: list, use_cache: bool = True) -> Dict[str, str]:
    """
    Get owner names for multiple IDs in batch
    
    Args:
        owner_ids: List of owner IDs
        use_cache: Whether to use cached results (default: True)
        
    Returns:
        Dictionary mapping owner_id to owner_name
    """
    result = {}
    for owner_id in owner_ids:
        if owner_id:
            result[str(owner_id)] = get_owner_name(owner_id, use_cache=use_cache)
    return result

def clear_owner_cache():
    """Clear the owner name cache"""
    global _OWNER_CACHE
    _OWNER_CACHE.clear()



