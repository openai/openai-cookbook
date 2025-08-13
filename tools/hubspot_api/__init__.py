"""
HubSpot API Package
Reusable RESTful API client for HubSpot CRM integration

This package provides a clean, database-like interface for HubSpot API operations,
mirroring the structure of the database package for consistency.
"""

from .config import HubSpotConfig
from .client import HubSpotClient, get_hubspot_client
from .models import HubSpotObject, Deal, Company, Contact
from .query_builder import HubSpotQueryBuilder

# Global client instance (similar to database package pattern)
hubspot_client = None

def get_client():
    """Get the global HubSpot client instance"""
    global hubspot_client
    if hubspot_client is None:
        hubspot_client = HubSpotClient()
    return hubspot_client

# Export main classes for easy import
__all__ = [
    'HubSpotConfig',
    'HubSpotClient', 
    'get_hubspot_client',
    'HubSpotObject',
    'Deal',
    'Company', 
    'Contact',
    'HubSpotQueryBuilder',
    'get_client'
]