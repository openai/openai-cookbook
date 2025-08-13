"""
HubSpot Query Builder
Fluent interface for building complex HubSpot API queries with filters, sorts, and pagination
"""

import logging
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from .client import get_hubspot_client, HubSpotClient

logger = logging.getLogger(__name__)

class HubSpotQueryBuilder:
    """
    Fluent query builder for HubSpot API searches
    Provides a database-like query interface for HubSpot objects
    """
    
    def __init__(self, object_type: str, client: Optional[HubSpotClient] = None):
        """Initialize query builder for specific object type"""
        self.object_type = object_type
        self.client = client or get_hubspot_client()
        
        # Query components
        self._filter_groups = []
        self._current_filters = []
        self._properties = []
        self._sorts = []
        self._query_text = None
        self._limit = None
        self._after = None
        
        logger.debug(f"Created HubSpot query builder for {object_type}")
    
    def select(self, *properties: str) -> 'HubSpotQueryBuilder':
        """Select specific properties to return"""
        self._properties.extend(properties)
        return self
    
    def where(self, property_name: str, operator: str, value: Union[str, int, float, List]) -> 'HubSpotQueryBuilder':
        """Add a filter condition"""
        filter_condition = {
            "propertyName": property_name,
            "operator": operator
        }
        
        if isinstance(value, list):
            filter_condition["values"] = [str(v) for v in value]
        else:
            filter_condition["value"] = str(value)
        
        self._current_filters.append(filter_condition)
        return self
    
    def where_equal(self, property_name: str, value: Union[str, int, float]) -> 'HubSpotQueryBuilder':
        """Add equality filter (shorthand)"""
        return self.where(property_name, "EQ", value)
    
    def where_not_equal(self, property_name: str, value: Union[str, int, float]) -> 'HubSpotQueryBuilder':
        """Add not equal filter (shorthand)"""
        return self.where(property_name, "NEQ", value)
    
    def where_in(self, property_name: str, values: List[Union[str, int, float]]) -> 'HubSpotQueryBuilder':
        """Add IN filter (shorthand)"""
        return self.where(property_name, "IN", values)
    
    def where_greater_than(self, property_name: str, value: Union[str, int, float]) -> 'HubSpotQueryBuilder':
        """Add greater than filter (shorthand)"""
        return self.where(property_name, "GT", value)
    
    def where_greater_than_or_equal(self, property_name: str, value: Union[str, int, float]) -> 'HubSpotQueryBuilder':
        """Add greater than or equal filter (shorthand)"""
        return self.where(property_name, "GTE", value)
    
    def where_less_than(self, property_name: str, value: Union[str, int, float]) -> 'HubSpotQueryBuilder':
        """Add less than filter (shorthand)"""
        return self.where(property_name, "LT", value)
    
    def where_less_than_or_equal(self, property_name: str, value: Union[str, int, float]) -> 'HubSpotQueryBuilder':
        """Add less than or equal filter (shorthand)"""
        return self.where(property_name, "LTE", value)
    
    def where_has_property(self, property_name: str) -> 'HubSpotQueryBuilder':
        """Add has property filter (shorthand)"""
        return self.where(property_name, "HAS_PROPERTY", "")
    
    def where_not_has_property(self, property_name: str) -> 'HubSpotQueryBuilder':
        """Add not has property filter (shorthand)"""
        return self.where(property_name, "NOT_HAS_PROPERTY", "")
    
    def where_contains(self, property_name: str, value: str) -> 'HubSpotQueryBuilder':
        """Add contains filter (shorthand)"""
        return self.where(property_name, "CONTAINS_TOKEN", value)
    
    def where_between(self, property_name: str, low_value: Union[str, int, float], high_value: Union[str, int, float]) -> 'HubSpotQueryBuilder':
        """Add between filter (shorthand)"""
        filter_condition = {
            "propertyName": property_name,
            "operator": "BETWEEN",
            "value": str(low_value),
            "highValue": str(high_value)
        }
        self._current_filters.append(filter_condition)
        return self
    
    def where_date_range(
        self, 
        property_name: str, 
        start_date: Union[str, datetime], 
        end_date: Union[str, datetime]
    ) -> 'HubSpotQueryBuilder':
        """Add date range filters (shorthand for common date filtering)"""
        # Convert datetime objects to ISO strings
        if isinstance(start_date, datetime):
            start_date = start_date.isoformat() + "Z"
        elif isinstance(start_date, str) and not start_date.endswith("Z"):
            start_date = start_date + "T00:00:00.000Z"
        
        if isinstance(end_date, datetime):
            end_date = end_date.isoformat() + "Z"
        elif isinstance(end_date, str) and not end_date.endswith("Z"):
            end_date = end_date + "T23:59:59.999Z"
        
        return self.where_greater_than_or_equal(property_name, start_date).where_less_than_or_equal(property_name, end_date)
    
    def or_where(self) -> 'HubSpotQueryBuilder':
        """Start a new filter group (OR condition)"""
        if self._current_filters:
            self._filter_groups.append({"filters": self._current_filters})
            self._current_filters = []
        return self
    
    def order_by(self, property_name: str, direction: str = "ASCENDING") -> 'HubSpotQueryBuilder':
        """Add sort criteria"""
        self._sorts.append({
            "propertyName": property_name,
            "direction": direction.upper()
        })
        return self
    
    def order_by_asc(self, property_name: str) -> 'HubSpotQueryBuilder':
        """Add ascending sort (shorthand)"""
        return self.order_by(property_name, "ASCENDING")
    
    def order_by_desc(self, property_name: str) -> 'HubSpotQueryBuilder':
        """Add descending sort (shorthand)"""
        return self.order_by(property_name, "DESCENDING")
    
    def search_text(self, query: str) -> 'HubSpotQueryBuilder':
        """Add text search query"""
        self._query_text = query
        return self
    
    def limit(self, count: int) -> 'HubSpotQueryBuilder':
        """Set result limit"""
        self._limit = min(count, 100)  # HubSpot max is 100
        return self
    
    def after(self, cursor: str) -> 'HubSpotQueryBuilder':
        """Set pagination cursor"""
        self._after = cursor
        return self
    
    def build_query(self) -> Dict[str, Any]:
        """Build the query payload"""
        # Finalize filter groups
        filter_groups = self._filter_groups.copy()
        if self._current_filters:
            filter_groups.append({"filters": self._current_filters})
        
        query = {}
        
        if filter_groups:
            query["filterGroups"] = filter_groups
        
        if self._properties:
            query["properties"] = list(set(self._properties))  # Remove duplicates
        
        if self._sorts:
            query["sorts"] = self._sorts
        
        if self._query_text:
            query["query"] = self._query_text
        
        if self._limit:
            query["limit"] = self._limit
        
        if self._after:
            query["after"] = self._after
        
        return query
    
    def execute(self) -> Dict[str, Any]:
        """Execute the query and return results"""
        query = self.build_query()
        
        logger.debug(f"Executing HubSpot query for {self.object_type}: {query}")
        
        return self.client.search_objects(
            object_type=self.object_type,
            filter_groups=query.get("filterGroups"),
            properties=query.get("properties"),
            sorts=query.get("sorts"),
            query=query.get("query"),
            limit=query.get("limit"),
            after=query.get("after")
        )
    
    def get_all(self, max_results: Optional[int] = None) -> List[Dict[str, Any]]:
        """Execute query and get all results with automatic pagination"""
        query = self.build_query()
        
        # Remove pagination parameters for get_all
        query.pop("after", None)
        query.pop("limit", None)
        
        return self.client.get_all_objects(
            object_type=self.object_type,
            filter_groups=query.get("filterGroups"),
            properties=query.get("properties"),
            sorts=query.get("sorts"),
            query=query.get("query"),
            max_results=max_results
        )
    
    def count(self) -> int:
        """Get count of matching records"""
        # Execute with limit 1 to get total count
        original_limit = self._limit
        self._limit = 1
        
        result = self.execute()
        
        # Restore original limit
        self._limit = original_limit
        
        return result.get("total", 0)
    
    def first(self) -> Optional[Dict[str, Any]]:
        """Get first matching result"""
        self._limit = 1
        result = self.execute()
        
        results = result.get("results", [])
        return results[0] if results else None

# Factory functions for common query patterns
def deals_query(client: Optional[HubSpotClient] = None) -> HubSpotQueryBuilder:
    """Create query builder for deals"""
    return HubSpotQueryBuilder("deals", client)

def companies_query(client: Optional[HubSpotClient] = None) -> HubSpotQueryBuilder:
    """Create query builder for companies"""
    return HubSpotQueryBuilder("companies", client)

def contacts_query(client: Optional[HubSpotClient] = None) -> HubSpotQueryBuilder:
    """Create query builder for contacts"""
    return HubSpotQueryBuilder("contacts", client)

# Common query builders
def closed_won_deals_in_july_2025(client: Optional[HubSpotClient] = None) -> HubSpotQueryBuilder:
    """Pre-built query for July 2025 closed won deals"""
    return (deals_query(client)
            .where_equal("dealstage", "closedwon")
            .where_date_range("createdate", "2025-07-01", "2025-07-31")
            .select("dealname", "amount", "id_empresa", "createdate", "dealstage")
            .order_by_desc("amount"))

def companies_with_cuit(client: Optional[HubSpotClient] = None) -> HubSpotQueryBuilder:
    """Pre-built query for companies with CUIT"""
    return (companies_query(client)
            .where_has_property("cuit")
            .select("name", "cuit", "colppy_id", "createdate"))

def companies_missing_cuit(client: Optional[HubSpotClient] = None) -> HubSpotQueryBuilder:
    """Pre-built query for companies missing CUIT"""
    return (companies_query(client)
            .where_not_has_property("cuit")
            .select("name", "colppy_id", "createdate"))