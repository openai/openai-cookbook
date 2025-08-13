"""
HubSpot Object Models
Object-oriented interfaces for HubSpot CRM objects (Deals, Companies, Contacts, etc.)
Provides database-like methods for querying and manipulating HubSpot data
"""

import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from .client import get_hubspot_client, HubSpotClient

logger = logging.getLogger(__name__)

class HubSpotObject:
    """
    Base class for HubSpot CRM objects
    Provides common functionality similar to database models
    """
    
    object_type = None  # Override in subclasses
    default_properties = []  # Override in subclasses
    
    def __init__(self, client: Optional[HubSpotClient] = None):
        """Initialize with HubSpot client"""
        self.client = client or get_hubspot_client()
        
        if not self.object_type:
            raise ValueError("object_type must be defined in subclass")
    
    @classmethod
    def find_all(
        cls, 
        filters: Optional[List[Dict]] = None, 
        properties: Optional[List[str]] = None,
        limit: Optional[int] = None,
        client: Optional[HubSpotClient] = None
    ) -> List[Dict[str, Any]]:
        """Find all objects matching criteria"""
        instance = cls(client)
        
        filter_groups = [{"filters": filters}] if filters else None
        props = properties or cls.default_properties
        
        if limit:
            return instance.client.search_objects(
                object_type=cls.object_type,
                filter_groups=filter_groups,
                properties=props,
                limit=limit
            ).get("results", [])
        else:
            return instance.client.get_all_objects(
                object_type=cls.object_type,
                filter_groups=filter_groups,
                properties=props
            )
    
    @classmethod
    def find_by_id(cls, object_id: str, properties: Optional[List[str]] = None, client: Optional[HubSpotClient] = None) -> Optional[Dict[str, Any]]:
        """Find object by ID"""
        instance = cls(client)
        props = properties or cls.default_properties
        
        return instance.client.get_object_by_id(
            object_type=cls.object_type,
            object_id=object_id,
            properties=props
        )
    
    @classmethod
    def search(
        cls,
        filters: Optional[List[Dict]] = None,
        properties: Optional[List[str]] = None,
        sorts: Optional[List[Dict]] = None,
        query: Optional[str] = None,
        limit: Optional[int] = None,
        client: Optional[HubSpotClient] = None
    ) -> Dict[str, Any]:
        """Search objects with advanced options"""
        instance = cls(client)
        
        filter_groups = [{"filters": filters}] if filters else None
        props = properties or cls.default_properties
        
        return instance.client.search_objects(
            object_type=cls.object_type,
            filter_groups=filter_groups,
            properties=props,
            sorts=sorts,
            query=query,
            limit=limit
        )
    
    @classmethod
    def count(cls, filters: Optional[List[Dict]] = None, client: Optional[HubSpotClient] = None) -> int:
        """Count objects matching criteria"""
        response = cls.search(filters=filters, limit=1, client=client)
        return response.get("total", 0)
    
    @classmethod
    def find_by_property(
        cls, 
        property_name: str, 
        value: str, 
        operator: str = "EQ",
        properties: Optional[List[str]] = None,
        client: Optional[HubSpotClient] = None
    ) -> List[Dict[str, Any]]:
        """Find objects by a specific property value"""
        filters = [{"propertyName": property_name, "operator": operator, "value": value}]
        return cls.find_all(filters=filters, properties=properties, client=client)

class Deal(HubSpotObject):
    """HubSpot Deals object model"""
    
    object_type = "deals"
    default_properties = [
        "dealname", "amount", "dealstage", "pipeline", "closedate", "createdate",
        "hubspot_owner_id", "dealtype", "deal_currency_code", "id_empresa"
    ]
    
    @classmethod
    def find_closed_won(
        cls,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        date_property: str = "closedate",
        properties: Optional[List[str]] = None,
        client: Optional[HubSpotClient] = None
    ) -> List[Dict[str, Any]]:
        """Find closed won deals in date range"""
        filters = [{"propertyName": "dealstage", "operator": "EQ", "value": "closedwon"}]
        
        if start_date:
            filters.append({
                "propertyName": date_property,
                "operator": "GTE", 
                "value": start_date
            })
        
        if end_date:
            filters.append({
                "propertyName": date_property,
                "operator": "LTE",
                "value": end_date
            })
        
        return cls.find_all(filters=filters, properties=properties, client=client)
    
    @classmethod
    def find_by_empresa_id(cls, empresa_id: str, properties: Optional[List[str]] = None, client: Optional[HubSpotClient] = None) -> List[Dict[str, Any]]:
        """Find deals by empresa ID"""
        return cls.find_by_property("id_empresa", empresa_id, properties=properties, client=client)
    
    @classmethod
    def find_by_stage(cls, stage: str, properties: Optional[List[str]] = None, client: Optional[HubSpotClient] = None) -> List[Dict[str, Any]]:
        """Find deals by stage"""
        return cls.find_by_property("dealstage", stage, properties=properties, client=client)
    
    @classmethod
    def find_by_amount_range(
        cls, 
        min_amount: Optional[float] = None,
        max_amount: Optional[float] = None,
        properties: Optional[List[str]] = None,
        client: Optional[HubSpotClient] = None
    ) -> List[Dict[str, Any]]:
        """Find deals by amount range"""
        filters = []
        
        if min_amount is not None:
            filters.append({"propertyName": "amount", "operator": "GTE", "value": str(min_amount)})
        
        if max_amount is not None:
            filters.append({"propertyName": "amount", "operator": "LTE", "value": str(max_amount)})
        
        return cls.find_all(filters=filters, properties=properties, client=client)

class Company(HubSpotObject):
    """HubSpot Companies object model"""
    
    object_type = "companies" 
    default_properties = [
        "name", "domain", "website", "industry", "city", "country", "state",
        "createdate", "hubspot_owner_id", "cuit", "colppy_id", "external_id"
    ]
    
    @classmethod
    def find_by_cuit(cls, cuit: str, properties: Optional[List[str]] = None, client: Optional[HubSpotClient] = None) -> List[Dict[str, Any]]:
        """Find companies by CUIT"""
        return cls.find_by_property("cuit", cuit, properties=properties, client=client)
    
    @classmethod
    def find_by_colppy_id(cls, colppy_id: str, properties: Optional[List[str]] = None, client: Optional[HubSpotClient] = None) -> List[Dict[str, Any]]:
        """Find companies by Colppy ID"""
        return cls.find_by_property("colppy_id", colppy_id, properties=properties, client=client)
    
    @classmethod
    def find_with_cuit(cls, properties: Optional[List[str]] = None, client: Optional[HubSpotClient] = None) -> List[Dict[str, Any]]:
        """Find all companies that have a CUIT"""
        filters = [{"propertyName": "cuit", "operator": "HAS_PROPERTY"}]
        return cls.find_all(filters=filters, properties=properties, client=client)
    
    @classmethod
    def find_missing_cuit(cls, properties: Optional[List[str]] = None, client: Optional[HubSpotClient] = None) -> List[Dict[str, Any]]:
        """Find companies missing CUIT"""
        filters = [{"propertyName": "cuit", "operator": "NOT_HAS_PROPERTY"}]
        return cls.find_all(filters=filters, properties=properties, client=client)

class Contact(HubSpotObject):
    """HubSpot Contacts object model"""
    
    object_type = "contacts"
    default_properties = [
        "email", "firstname", "lastname", "phone", "company", "jobtitle",
        "createdate", "lastmodifieddate", "hubspot_owner_id", "lifecyclestage"
    ]
    
    @classmethod
    def find_by_email(cls, email: str, properties: Optional[List[str]] = None, client: Optional[HubSpotClient] = None) -> Optional[Dict[str, Any]]:
        """Find contact by email"""
        results = cls.find_by_property("email", email, properties=properties, client=client)
        return results[0] if results else None
    
    @classmethod
    def find_by_lifecycle_stage(cls, stage: str, properties: Optional[List[str]] = None, client: Optional[HubSpotClient] = None) -> List[Dict[str, Any]]:
        """Find contacts by lifecycle stage"""
        return cls.find_by_property("lifecyclestage", stage, properties=properties, client=client)
    
    @classmethod
    def find_leads(cls, properties: Optional[List[str]] = None, client: Optional[HubSpotClient] = None) -> List[Dict[str, Any]]:
        """Find all leads"""
        return cls.find_by_lifecycle_stage("lead", properties=properties, client=client)
    
    @classmethod
    def find_customers(cls, properties: Optional[List[str]] = None, client: Optional[HubSpotClient] = None) -> List[Dict[str, Any]]:
        """Find all customers"""
        return cls.find_by_lifecycle_stage("customer", properties=properties, client=client)

# Utility functions for common operations
def get_all_cuits_from_hubspot(client: Optional[HubSpotClient] = None) -> List[str]:
    """Get all CUITs currently in HubSpot"""
    companies = Company.find_with_cuit(properties=["cuit"], client=client)
    cuits = []
    
    for company in companies:
        cuit = company.get("properties", {}).get("cuit")
        if cuit:
            # Clean CUIT (remove dashes, spaces)
            clean_cuit = "".join(filter(str.isdigit, cuit))
            if len(clean_cuit) >= 10:
                cuits.append(clean_cuit)
    
    return list(set(cuits))  # Remove duplicates

def test_hubspot_connection(client: Optional[HubSpotClient] = None) -> bool:
    """Test HubSpot API connection"""
    test_client = client or get_hubspot_client()
    return test_client.test_connection()