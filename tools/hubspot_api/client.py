"""
HubSpot API Client
Core HTTP client for HubSpot REST API operations with error handling, 
rate limiting, and pagination support
"""

import time
import logging
import requests
from typing import Dict, List, Optional, Any, Union
from datetime import datetime

from .config import get_config, HubSpotConfig

logger = logging.getLogger(__name__)

class HubSpotAPIError(Exception):
    """Base exception for HubSpot API errors"""
    pass

class HubSpotRateLimitError(HubSpotAPIError):
    """Exception for rate limit errors"""
    pass

class HubSpotAuthenticationError(HubSpotAPIError):
    """Exception for authentication errors"""
    pass

class HubSpotClient:
    """
    HubSpot API client with automatic retry, rate limiting, and pagination support
    """
    
    def __init__(self, config: Optional[HubSpotConfig] = None):
        """Initialize HubSpot client with configuration"""
        self.config = config or get_config()
        self.session = requests.Session()
        self.session.headers.update(self.config.headers)
        
        # Rate limiting tracking
        self._last_request_time = 0
        self._request_count = 0
        
        logger.info(f"HubSpot API client initialized for {self.config.environment} environment")
    
    def _handle_rate_limiting(self):
        """Handle rate limiting with automatic delays"""
        current_time = time.time()
        time_since_last = current_time - self._last_request_time
        
        if time_since_last < self.config.rate_limit_delay:
            sleep_time = self.config.rate_limit_delay - time_since_last
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f} seconds")
            time.sleep(sleep_time)
        
        self._last_request_time = time.time()
        self._request_count += 1
    
    def _make_request(
        self, 
        method: str, 
        endpoint: str, 
        params: Optional[Dict] = None,
        json_data: Optional[Dict] = None,
        retry_count: int = 0
    ) -> Dict[str, Any]:
        """
        Make HTTP request to HubSpot API with retry logic
        """
        self._handle_rate_limiting()
        
        url = self.config.get_endpoint_url(endpoint)
        
        try:
            logger.debug(f"Making {method} request to {url}")
            
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=self.config.timeout
            )
            
            # Handle different response status codes
            if response.status_code == 200:
                return response.json()
            elif response.status_code == 429:  # Rate limited
                if retry_count < self.config.max_retries:
                    retry_after = int(response.headers.get('Retry-After', 1))
                    logger.warning(f"Rate limited. Retrying after {retry_after} seconds")
                    time.sleep(retry_after)
                    return self._make_request(method, endpoint, params, json_data, retry_count + 1)
                else:
                    raise HubSpotRateLimitError("Rate limit exceeded and max retries reached")
            elif response.status_code == 401:
                raise HubSpotAuthenticationError("Invalid API key or authentication failed")
            elif response.status_code == 404:
                logger.warning(f"Resource not found: {url}")
                return {"results": [], "total": 0}
            else:
                response.raise_for_status()
                
        except requests.RequestException as e:
            if retry_count < self.config.max_retries:
                logger.warning(f"Request failed, retrying ({retry_count + 1}/{self.config.max_retries}): {e}")
                time.sleep(2 ** retry_count)  # Exponential backoff
                return self._make_request(method, endpoint, params, json_data, retry_count + 1)
            else:
                raise HubSpotAPIError(f"Request failed after {self.config.max_retries} retries: {e}")
    
    def get(self, endpoint: str, params: Optional[Dict] = None) -> Dict[str, Any]:
        """Make GET request to HubSpot API"""
        return self._make_request("GET", endpoint, params=params)
    
    def post(self, endpoint: str, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """Make POST request to HubSpot API"""
        return self._make_request("POST", endpoint, json_data=json_data)
    
    def patch(self, endpoint: str, json_data: Dict[str, Any]) -> Dict[str, Any]:
        """Make PATCH request to HubSpot API"""
        return self._make_request("PATCH", endpoint, json_data=json_data)
    
    def delete(self, endpoint: str) -> Dict[str, Any]:
        """Make DELETE request to HubSpot API"""
        return self._make_request("DELETE", endpoint)
    
    def search_objects(
        self,
        object_type: str,
        filter_groups: Optional[List[Dict]] = None,
        properties: Optional[List[str]] = None,
        sorts: Optional[List[Dict]] = None,
        query: Optional[str] = None,
        limit: Optional[int] = None,
        after: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search HubSpot objects with filters
        
        Args:
            object_type: Type of object (deals, companies, contacts, etc.)
            filter_groups: List of filter groups for complex filtering
            properties: List of properties to return
            sorts: List of sort criteria
            query: Text query for searching
            limit: Maximum number of results
            after: Pagination cursor
        
        Returns:
            API response with results and pagination info
        """
        endpoint = f"crm/v3/objects/{object_type}/search"
        
        payload = {
            "limit": limit or self.config.default_limit
        }
        
        if filter_groups:
            payload["filterGroups"] = filter_groups
        
        if properties:
            payload["properties"] = properties
        
        if sorts:
            payload["sorts"] = sorts
        
        if query:
            payload["query"] = query
        
        if after:
            payload["after"] = after
        
        return self.post(endpoint, payload)
    
    def get_all_objects(
        self,
        object_type: str,
        filter_groups: Optional[List[Dict]] = None,
        properties: Optional[List[str]] = None,
        sorts: Optional[List[Dict]] = None,
        query: Optional[str] = None,
        max_results: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all objects with automatic pagination
        
        Args:
            object_type: Type of object to retrieve
            filter_groups: Filters to apply
            properties: Properties to include
            sorts: Sort criteria
            query: Search query
            max_results: Maximum total results to return
        
        Returns:
            List of all objects matching criteria
        """
        all_results = []
        after = None
        total_fetched = 0
        
        while True:
            response = self.search_objects(
                object_type=object_type,
                filter_groups=filter_groups,
                properties=properties,
                sorts=sorts,
                query=query,
                after=after
            )
            
            results = response.get("results", [])
            all_results.extend(results)
            total_fetched += len(results)
            
            logger.info(f"Fetched {len(results)} {object_type}, total: {total_fetched}")
            
            # Check pagination
            paging = response.get("paging", {})
            next_page = paging.get("next", {})
            after = next_page.get("after")
            
            # Stop if no more pages or max results reached
            if not after or (max_results and total_fetched >= max_results):
                break
        
        if max_results and len(all_results) > max_results:
            all_results = all_results[:max_results]
        
        logger.info(f"Retrieved {len(all_results)} total {object_type}")
        return all_results
    
    def get_object_by_id(self, object_type: str, object_id: str, properties: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        """Get a single object by ID"""
        endpoint = f"crm/v3/objects/{object_type}/{object_id}"
        params = {}
        
        if properties:
            params["properties"] = ",".join(properties)
        
        try:
            return self.get(endpoint, params)
        except HubSpotAPIError:
            return None
    
    def test_connection(self) -> bool:
        """Test HubSpot API connection"""
        try:
            response = self.get("crm/v3/owners")
            logger.info("HubSpot API connection test successful")
            return True
        except Exception as e:
            logger.error(f"HubSpot API connection test failed: {e}")
            return False
    
    def get_associations(self, object_id: str, from_object_type: str, to_object_type: str) -> Dict[str, Any]:
        """
        Get associations between objects
        
        Args:
            object_id: ID of the source object
            from_object_type: Type of source object (e.g., 'deals', 'companies', 'contacts')
            to_object_type: Type of target object (e.g., 'deals', 'companies', 'contacts')
            
        Returns:
            Dictionary containing associations
        """
        endpoint = f"crm/v4/objects/{from_object_type}/{object_id}/associations/{to_object_type}"
        return self.get(endpoint)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get client usage statistics"""
        return {
            "total_requests": self._request_count,
            "environment": self.config.environment,
            "rate_limit_delay": self.config.rate_limit_delay
        }

# Global client instance
_client = None

def get_hubspot_client() -> HubSpotClient:
    """Get the global HubSpot client instance"""
    global _client
    if _client is None:
        _client = HubSpotClient()
    return _client