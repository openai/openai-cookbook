#!/usr/bin/env python3
"""
Meta Ads MCP Server
===================

MCP (Model Context Protocol) server for Meta Ads API integration.
Provides tools for campaign analysis, performance metrics, and ad management.

Usage:
    python -m mcp_meta_ads

Author: Data Analytics Team - Colppy
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    Resource, Tool, TextContent, ImageContent, EmbeddedResource,
    LoggingLevel
)

# Meta Ads API imports
from facebook_business.api import FacebookAdsApi
from facebook_business.adobjects.adaccount import AdAccount
from facebook_business.adobjects.campaign import Campaign
from facebook_business.adobjects.adset import AdSet
from facebook_business.adobjects.ad import Ad
from facebook_business.adobjects.insights import Insights
from facebook_business.exceptions import FacebookRequestError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MetaAdsMCPServer:
    """Meta Ads MCP Server implementation"""
    
    def __init__(self):
        """Initialize the MCP server"""
        self.server = Server("meta-ads")
        self.api = None
        self.setup_handlers()
        self.load_environment()
        
    def load_environment(self):
        """Load environment variables"""
        # Try to load from multiple locations
        env_paths = [
            os.path.join(os.path.dirname(__file__), '.env'),
            os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'),
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
        ]
        
        for env_path in env_paths:
            if os.path.exists(env_path):
                load_dotenv(env_path)
                logger.info(f"Loaded environment from {env_path}")
                break
        
        # Initialize Meta Ads API
        self.initialize_api()
    
    def initialize_api(self):
        """Initialize Meta Ads API connection"""
        try:
            app_id = os.environ.get('META_ADS_APP_ID')
            app_secret = os.environ.get('META_ADS_APP_SECRET')
            access_token = os.environ.get('META_ADS_ACCESS_TOKEN')
            
            if not all([app_id, app_secret, access_token]):
                logger.warning("Meta Ads API credentials not fully configured")
                return
            
            FacebookAdsApi.init(app_id=app_id, app_secret=app_secret, access_token=access_token)
            self.api = FacebookAdsApi.get_default_api()
            logger.info("Meta Ads API initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize Meta Ads API: {e}")
    
    def setup_handlers(self):
        """Setup MCP server handlers"""
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available Meta Ads tools"""
            return [
                Tool(
                    name="meta_ads_list_accounts",
                    description="List all accessible Meta Ads accounts",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                Tool(
                    name="meta_ads_get_campaigns",
                    description="Get campaigns from a Meta Ads account",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "account_id": {
                                "type": "string",
                                "description": "Ad account ID (with or without 'act_' prefix)"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of campaigns to return",
                                "default": 50
                            }
                        },
                        "required": ["account_id"]
                    }
                ),
                Tool(
                    name="meta_ads_get_campaign_performance",
                    description="Get performance metrics for campaigns",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "account_id": {
                                "type": "string",
                                "description": "Ad account ID"
                            },
                            "campaign_ids": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "List of campaign IDs to analyze"
                            },
                            "start_date": {
                                "type": "string",
                                "description": "Start date (YYYY-MM-DD)",
                                "default": "30 days ago"
                            },
                            "end_date": {
                                "type": "string", 
                                "description": "End date (YYYY-MM-DD)",
                                "default": "today"
                            }
                        },
                        "required": ["account_id"]
                    }
                ),
                Tool(
                    name="meta_ads_get_ad_sets",
                    description="Get ad sets for campaigns",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "account_id": {
                                "type": "string",
                                "description": "Ad account ID"
                            },
                            "campaign_id": {
                                "type": "string",
                                "description": "Campaign ID"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of ad sets to return",
                                "default": 50
                            }
                        },
                        "required": ["account_id", "campaign_id"]
                    }
                ),
                Tool(
                    name="meta_ads_get_ads",
                    description="Get ads for ad sets",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "account_id": {
                                "type": "string",
                                "description": "Ad account ID"
                            },
                            "ad_set_id": {
                                "type": "string",
                                "description": "Ad set ID"
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of ads to return",
                                "default": 50
                            }
                        },
                        "required": ["account_id", "ad_set_id"]
                    }
                ),
                Tool(
                    name="meta_ads_get_insights",
                    description="Get detailed insights for campaigns, ad sets, or ads",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "account_id": {
                                "type": "string",
                                "description": "Ad account ID"
                            },
                            "object_type": {
                                "type": "string",
                                "enum": ["campaign", "adset", "ad"],
                                "description": "Type of object to get insights for"
                            },
                            "object_id": {
                                "type": "string",
                                "description": "ID of the object"
                            },
                            "start_date": {
                                "type": "string",
                                "description": "Start date (YYYY-MM-DD)",
                                "default": "30 days ago"
                            },
                            "end_date": {
                                "type": "string",
                                "description": "End date (YYYY-MM-DD)", 
                                "default": "today"
                            },
                            "breakdowns": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Breakdown dimensions (e.g., 'age', 'gender', 'country')"
                            }
                        },
                        "required": ["account_id", "object_type", "object_id"]
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> List[TextContent]:
            """Handle tool calls"""
            try:
                if name == "meta_ads_list_accounts":
                    return await self.list_accounts()
                elif name == "meta_ads_get_campaigns":
                    return await self.get_campaigns(arguments)
                elif name == "meta_ads_get_campaign_performance":
                    return await self.get_campaign_performance(arguments)
                elif name == "meta_ads_get_ad_sets":
                    return await self.get_ad_sets(arguments)
                elif name == "meta_ads_get_ads":
                    return await self.get_ads(arguments)
                elif name == "meta_ads_get_insights":
                    return await self.get_insights(arguments)
                else:
                    return [TextContent(type="text", text=f"Unknown tool: {name}")]
                    
            except Exception as e:
                logger.error(f"Error in tool {name}: {e}")
                return [TextContent(type="text", text=f"Error: {str(e)}")]
    
    async def list_accounts(self) -> List[TextContent]:
        """List all accessible ad accounts"""
        if not self.api:
            return [TextContent(type="text", text="Meta Ads API not initialized")]
        
        try:
            response = self.api.call('GET', '/me/adaccounts')
            accounts = response.get('data', [])
            
            result = {
                "accounts": [],
                "total_count": len(accounts)
            }
            
            for account in accounts:
                account_info = {
                    "id": account.get('id'),
                    "name": account.get('name'),
                    "account_status": account.get('account_status'),
                    "currency": account.get('currency'),
                    "timezone": account.get('timezone_name')
                }
                result["accounts"].append(account_info)
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
        except FacebookRequestError as e:
            return [TextContent(type="text", text=f"Facebook API Error: {e}")]
    
    async def get_campaigns(self, args: Dict[str, Any]) -> List[TextContent]:
        """Get campaigns from an ad account"""
        if not self.api:
            return [TextContent(type="text", text="Meta Ads API not initialized")]
        
        try:
            account_id = args.get('account_id', '')
            limit = args.get('limit', 50)
            
            # Ensure account ID has 'act_' prefix
            if not account_id.startswith('act_'):
                account_id = f'act_{account_id}'
            
            account = AdAccount(account_id)
            campaigns = account.get_campaigns(fields=[
                'id', 'name', 'status', 'objective', 'created_time', 
                'updated_time', 'start_time', 'stop_time'
            ], limit=limit)
            
            result = {
                "account_id": account_id,
                "campaigns": [],
                "total_count": 0
            }
            
            for campaign in campaigns:
                campaign_info = {
                    "id": campaign.get('id'),
                    "name": campaign.get('name'),
                    "status": campaign.get('status'),
                    "objective": campaign.get('objective'),
                    "created_time": campaign.get('created_time'),
                    "updated_time": campaign.get('updated_time'),
                    "start_time": campaign.get('start_time'),
                    "stop_time": campaign.get('stop_time')
                }
                result["campaigns"].append(campaign_info)
                result["total_count"] += 1
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
        except FacebookRequestError as e:
            return [TextContent(type="text", text=f"Facebook API Error: {e}")]
    
    async def get_campaign_performance(self, args: Dict[str, Any]) -> List[TextContent]:
        """Get campaign performance metrics"""
        if not self.api:
            return [TextContent(type="text", text="Meta Ads API not initialized")]
        
        try:
            account_id = args.get('account_id', '')
            campaign_ids = args.get('campaign_ids', [])
            start_date = args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
            end_date = args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
            
            # Ensure account ID has 'act_' prefix
            if not account_id.startswith('act_'):
                account_id = f'act_{account_id}'
            
            account = AdAccount(account_id)
            
            # Get insights for campaigns
            params = {
                'time_range': {
                    'since': start_date,
                    'until': end_date
                },
                'level': 'campaign',
                'fields': [
                    'campaign_id', 'campaign_name', 'impressions', 'clicks', 
                    'spend', 'cpm', 'cpc', 'ctr', 'reach', 'frequency',
                    'actions', 'cost_per_action_type'
                ]
            }
            
            if campaign_ids:
                params['filtering'] = [{'field': 'campaign.id', 'operator': 'IN', 'value': campaign_ids}]
            
            insights = account.get_insights(params=params)
            
            result = {
                "account_id": account_id,
                "date_range": {"start": start_date, "end": end_date},
                "campaigns": [],
                "total_count": 0
            }
            
            for insight in insights:
                campaign_info = {
                    "campaign_id": insight.get('campaign_id'),
                    "campaign_name": insight.get('campaign_name'),
                    "impressions": insight.get('impressions'),
                    "clicks": insight.get('clicks'),
                    "spend": insight.get('spend'),
                    "cpm": insight.get('cpm'),
                    "cpc": insight.get('cpc'),
                    "ctr": insight.get('ctr'),
                    "reach": insight.get('reach'),
                    "frequency": insight.get('frequency'),
                    "actions": insight.get('actions', []),
                    "cost_per_action_type": insight.get('cost_per_action_type', [])
                }
                result["campaigns"].append(campaign_info)
                result["total_count"] += 1
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
        except FacebookRequestError as e:
            return [TextContent(type="text", text=f"Facebook API Error: {e}")]
    
    async def get_ad_sets(self, args: Dict[str, Any]) -> List[TextContent]:
        """Get ad sets for a campaign"""
        if not self.api:
            return [TextContent(type="text", text="Meta Ads API not initialized")]
        
        try:
            account_id = args.get('account_id', '')
            campaign_id = args.get('campaign_id', '')
            limit = args.get('limit', 50)
            
            # Ensure account ID has 'act_' prefix
            if not account_id.startswith('act_'):
                account_id = f'act_{account_id}'
            
            account = AdAccount(account_id)
            ad_sets = account.get_ad_sets(fields=[
                'id', 'name', 'status', 'campaign_id', 'created_time',
                'updated_time', 'start_time', 'end_time', 'daily_budget',
                'lifetime_budget', 'bid_strategy'
            ], limit=limit)
            
            result = {
                "account_id": account_id,
                "campaign_id": campaign_id,
                "ad_sets": [],
                "total_count": 0
            }
            
            for ad_set in ad_sets:
                ad_set_info = {
                    "id": ad_set.get('id'),
                    "name": ad_set.get('name'),
                    "status": ad_set.get('status'),
                    "campaign_id": ad_set.get('campaign_id'),
                    "created_time": ad_set.get('created_time'),
                    "updated_time": ad_set.get('updated_time'),
                    "start_time": ad_set.get('start_time'),
                    "end_time": ad_set.get('end_time'),
                    "daily_budget": ad_set.get('daily_budget'),
                    "lifetime_budget": ad_set.get('lifetime_budget'),
                    "bid_strategy": ad_set.get('bid_strategy')
                }
                result["ad_sets"].append(ad_set_info)
                result["total_count"] += 1
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
        except FacebookRequestError as e:
            return [TextContent(type="text", text=f"Facebook API Error: {e}")]
    
    async def get_ads(self, args: Dict[str, Any]) -> List[TextContent]:
        """Get ads for an ad set"""
        if not self.api:
            return [TextContent(type="text", text="Meta Ads API not initialized")]
        
        try:
            account_id = args.get('account_id', '')
            ad_set_id = args.get('ad_set_id', '')
            limit = args.get('limit', 50)
            
            # Ensure account ID has 'act_' prefix
            if not account_id.startswith('act_'):
                account_id = f'act_{account_id}'
            
            account = AdAccount(account_id)
            ads = account.get_ads(fields=[
                'id', 'name', 'status', 'adset_id', 'created_time',
                'updated_time', 'creative'
            ], limit=limit)
            
            result = {
                "account_id": account_id,
                "ad_set_id": ad_set_id,
                "ads": [],
                "total_count": 0
            }
            
            for ad in ads:
                ad_info = {
                    "id": ad.get('id'),
                    "name": ad.get('name'),
                    "status": ad.get('status'),
                    "adset_id": ad.get('adset_id'),
                    "created_time": ad.get('created_time'),
                    "updated_time": ad.get('updated_time'),
                    "creative": ad.get('creative')
                }
                result["ads"].append(ad_info)
                result["total_count"] += 1
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
        except FacebookRequestError as e:
            return [TextContent(type="text", text=f"Facebook API Error: {e}")]
    
    async def get_insights(self, args: Dict[str, Any]) -> List[TextContent]:
        """Get detailed insights for campaigns, ad sets, or ads"""
        if not self.api:
            return [TextContent(type="text", text="Meta Ads API not initialized")]
        
        try:
            account_id = args.get('account_id', '')
            object_type = args.get('object_type', 'campaign')
            object_id = args.get('object_id', '')
            start_date = args.get('start_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
            end_date = args.get('end_date', datetime.now().strftime('%Y-%m-%d'))
            breakdowns = args.get('breakdowns', [])
            
            # Ensure account ID has 'act_' prefix
            if not account_id.startswith('act_'):
                account_id = f'act_{account_id}'
            
            account = AdAccount(account_id)
            
            params = {
                'time_range': {
                    'since': start_date,
                    'until': end_date
                },
                'level': object_type,
                'fields': [
                    f'{object_type}_id', f'{object_type}_name', 'impressions', 'clicks',
                    'spend', 'cpm', 'cpc', 'ctr', 'reach', 'frequency',
                    'actions', 'cost_per_action_type'
                ]
            }
            
            if breakdowns:
                params['breakdowns'] = breakdowns
            
            if object_id:
                params['filtering'] = [{'field': f'{object_type}.id', 'operator': 'IN', 'value': [object_id]}]
            
            insights = account.get_insights(params=params)
            
            result = {
                "account_id": account_id,
                "object_type": object_type,
                "object_id": object_id,
                "date_range": {"start": start_date, "end": end_date},
                "breakdowns": breakdowns,
                "insights": [],
                "total_count": 0
            }
            
            for insight in insights:
                insight_info = {
                    f"{object_type}_id": insight.get(f'{object_type}_id'),
                    f"{object_type}_name": insight.get(f'{object_type}_name'),
                    "impressions": insight.get('impressions'),
                    "clicks": insight.get('clicks'),
                    "spend": insight.get('spend'),
                    "cpm": insight.get('cpm'),
                    "cpc": insight.get('cpc'),
                    "ctr": insight.get('ctr'),
                    "reach": insight.get('reach'),
                    "frequency": insight.get('frequency'),
                    "actions": insight.get('actions', []),
                    "cost_per_action_type": insight.get('cost_per_action_type', [])
                }
                
                # Add breakdown data if present
                for breakdown in breakdowns:
                    insight_info[breakdown] = insight.get(breakdown)
                
                result["insights"].append(insight_info)
                result["total_count"] += 1
            
            return [TextContent(type="text", text=json.dumps(result, indent=2))]
            
        except FacebookRequestError as e:
            return [TextContent(type="text", text=f"Facebook API Error: {e}")]

async def main():
    """Main function to run the MCP server"""
    server_instance = MetaAdsMCPServer()
    
    async with stdio_server() as (read_stream, write_stream):
        await server_instance.server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="meta-ads",
                server_version="1.0.0",
                capabilities=server_instance.server.get_capabilities(
                    notification_options=None,
                    experimental_capabilities=None
                )
            )
        )

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
