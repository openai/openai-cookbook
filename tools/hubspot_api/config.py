"""
HubSpot API Configuration Management
Handles API keys, rate limiting, and environment settings
"""

import os
import logging
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from multiple possible locations
# tools/hubspot_api/config.py -> tools/ -> repo root
_tools_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_repo_root = os.path.dirname(_tools_dir)
tools_env = os.path.join(_tools_dir, '.env')
repo_env = os.path.join(_repo_root, '.env')

# Load from repo root first (HUBSPOT_API_KEY typically lives here)
if os.path.exists(repo_env):
    load_dotenv(repo_env)

# Then load from tools directory (supplements; tools/.env has Colppy DB, etc.)
if os.path.exists(tools_env):
    load_dotenv(tools_env)

logger = logging.getLogger(__name__)

class HubSpotConfig:
    """HubSpot API configuration management"""
    
    def __init__(self):
        """Initialize configuration from environment variables"""
        self.api_key = self._get_api_key()
        self.base_url = "https://api.hubapi.com"
        self.timeout = int(os.getenv("HUBSPOT_TIMEOUT", "30"))
        self.max_retries = int(os.getenv("HUBSPOT_MAX_RETRIES", "3"))
        self.rate_limit_delay = float(os.getenv("HUBSPOT_RATE_LIMIT_DELAY", "0.1"))
        self.default_limit = int(os.getenv("HUBSPOT_DEFAULT_LIMIT", "100"))
        self.environment = os.getenv("ENVIRONMENT", "development")
        
        # Validate configuration
        self.validate()
    
    def _get_api_key(self) -> str:
        """Get HubSpot API key from environment variables"""
        # Try multiple environment variable names
        api_key = (
            os.getenv("HUBSPOT_API_KEY") or 
            os.getenv("HUBSPOT_ACCESS_TOKEN") or
            os.getenv("HUBSPOT_TOKEN")
        )
        
        if not api_key:
            raise ValueError(
                "HubSpot API key not found. Please set one of: "
                "HUBSPOT_API_KEY, HUBSPOT_ACCESS_TOKEN, or HUBSPOT_TOKEN"
            )
        
        # Check for placeholder values
        placeholder_values = [
            "your_hubspot_api_key_here", 
            "your_api_key_here",
            "your_hubspot_token_here",
            "your_token_here",
            "replace_with_your_key"
        ]
        
        if api_key.lower() in [p.lower() for p in placeholder_values]:
            raise ValueError(
                f"HubSpot API key is set to placeholder value '{api_key}'. "
                "Please replace with your actual HubSpot API key from "
                "HubSpot Settings > Integrations > Private Apps"
            )
        
        return api_key
    
    @property
    def headers(self) -> dict:
        """Get standard HTTP headers for HubSpot API requests"""
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": f"Colppy-HubSpot-Client/1.0 ({self.environment})"
        }
    
    def validate(self) -> bool:
        """Validate configuration settings"""
        if not self.api_key:
            raise ValueError("HubSpot API key is required")
        
        if self.timeout <= 0:
            raise ValueError("Timeout must be positive")
        
        if self.max_retries < 0:
            raise ValueError("Max retries cannot be negative")
        
        if self.default_limit <= 0 or self.default_limit > 100:
            raise ValueError("Default limit must be between 1 and 100")
        
        logger.info(f"HubSpot API configuration validated for {self.environment} environment")
        return True
    
    def get_endpoint_url(self, endpoint: str) -> str:
        """Get full URL for a HubSpot API endpoint"""
        if endpoint.startswith("/"):
            endpoint = endpoint[1:]
        
        return f"{self.base_url}/{endpoint}"
    
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.environment.lower() == "production"
    
    def __repr__(self) -> str:
        """String representation of configuration (without exposing API key)"""
        return (
            f"HubSpotConfig(environment={self.environment}, "
            f"timeout={self.timeout}, "
            f"max_retries={self.max_retries}, "
            f"default_limit={self.default_limit})"
        )

# Global configuration instance
_config = None

def get_config() -> HubSpotConfig:
    """Get the global HubSpot configuration instance"""
    global _config
    if _config is None:
        _config = HubSpotConfig()
    return _config

# Configuration validation on import
try:
    get_config()
    logger.info("HubSpot API configuration loaded successfully")
except Exception as e:
    logger.warning(f"HubSpot API configuration not available: {e}")
    logger.info("Set HUBSPOT_API_KEY environment variable to enable HubSpot integration")