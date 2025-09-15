#!/usr/bin/env python3
"""
HubSpot Workflow Validator
Validates HubSpot Custom Code workflow results using Python equivalent
"""

import sys
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

# Add tools directory to path
sys.path.append('/Users/virulana/openai-cookbook/tools')

try:
    from hubspot_api.client import HubSpotClient
except ImportError:
    print("❌ HubSpot API client not found. Using MCP tools instead.")
    HubSpotClient = None

def validate_workflow_with_python_client(company_id: str) -> Dict[str, Any]:
    """
    Validate workflow using Python HubSpot client
    
    Args:
        company_id: HubSpot company ID to validate
        
    Returns:
        Dictionary with validation results
    """
    if not HubSpotClient:
        return {"error": "HubSpot client not available"}
    
    try:
        # Initialize client
        client = HubSpotClient()
        
        print(f"=== VALIDATING WORKFLOW FOR COMPANY {company_id} ===")
        
        # Get company data
        company_data = client.get_object_by_id('companies', company_id, ['name', 'first_deal_closed_won_date'])
        if not company_data:
            return {"error": f"Company {company_id} not found"}
        
        company_name = company_data.get('properties', {}).get('name', 'Unknown')
        actual_date = company_data.get('properties', {}).get('first_deal_closed_won_date')
        
        print(f"Company: {company_name}")
        print(f"Actual field value: {actual_date}")
        
        # Get associations (simplified - no pagination)
        associations = client.get_associations(company_id, 'companies', 'deals')
        deal_ids = [str(assoc['toObjectId']) for assoc in associations.get('results', [])]
        
        print(f"Total deal associations: {len(deal_ids)}")
        
        # Get deal details for all deals
        won_dates = []
        for deal_id in deal_ids:
            deal_data = client.get_object_by_id('deals', deal_id, ['dealstage', 'closedate'])
            if deal_data:
                deal_stage = deal_data.get('properties', {}).get('dealstage')
                close_date = deal_data.get('properties', {}).get('closedate')
                
                if deal_stage == 'closedwon' and close_date:
                    won_dates.append(close_date)
                    print(f"✓ Won deal {deal_id}: {close_date}")
                else:
                    print(f"- Deal {deal_id}: {deal_stage}")
        
        # Calculate first won date
        if won_dates:
            first_won_date = min(won_dates)
            formatted_date = first_won_date.split('T')[0] if 'T' in first_won_date else first_won_date
        else:
            first_won_date = None
            formatted_date = None
        
        print(f"Calculated first won date: {formatted_date}")
        
        # Compare with actual field
        match_status = (formatted_date == actual_date.split('T')[0]) if actual_date else (formatted_date is None)
        
        return {
            "company_id": company_id,
            "company_name": company_name,
            "calculated_date": formatted_date,
            "actual_date": actual_date,
            "match_status": match_status,
            "total_deals": len(deal_ids),
            "won_deals": len(won_dates),
            "won_dates": won_dates
        }
        
    except Exception as e:
        return {"error": f"Validation failed: {str(e)}"}

def validate_workflow_with_mcp_tools(company_id: str) -> Dict[str, Any]:
    """
    Validate workflow using MCP HubSpot tools (fallback)
    
    Args:
        company_id: HubSpot company ID to validate
        
    Returns:
        Dictionary with validation results
    """
    print(f"=== VALIDATING WITH MCP TOOLS FOR COMPANY {company_id} ===")
    print("Note: This requires MCP tools to be available in the environment")
    
    try:
        # Import MCP tools if available
        import subprocess
        import json
        
        # Use MCP tools via subprocess (since we can't import them directly)
        print("Using MCP HubSpot tools for validation...")
        
        # Get company data
        company_cmd = f"""
        import sys
        sys.path.append('/Users/virulana/openai-cookbook')
        from mcp_hubspot_hubspot_batch_read_objects import mcp_hubspot_hubspot_batch_read_objects
        result = mcp_hubspot_hubspot_batch_read_objects(
            inputs=[{{'id': '{company_id}'}}],
            objectType='companies',
            properties=['name', 'first_deal_closed_won_date']
        )
        print(json.dumps(result))
        """
        
        # This is a simplified approach - in practice, you'd use the MCP tools directly
        return {
            "company_id": company_id,
            "method": "mcp_tools",
            "status": "requires_mcp_environment",
            "note": "MCP tools validation requires MCP environment setup"
        }
        
    except Exception as e:
        return {"error": f"MCP validation failed: {str(e)}"}

def main():
    """Main validation function"""
    if len(sys.argv) < 2:
        print("Usage: python3 hubspot_workflow_validator.py <company_id>")
        print("Example: python3 hubspot_workflow_validator.py 9019080056")
        return
    
    company_id = sys.argv[1]
    
    print("🧪 HubSpot Workflow Validator")
    print("=" * 50)
    
    # Try Python client first
    if HubSpotClient:
        print("📋 Using Python HubSpot Client")
        result = validate_workflow_with_python_client(company_id)
    else:
        print("📋 Using MCP Tools (fallback)")
        result = validate_workflow_with_mcp_tools(company_id)
    
    # Display results
    print("\n" + "=" * 50)
    print("📊 VALIDATION RESULTS")
    print("=" * 50)
    
    if "error" in result:
        print(f"❌ Error: {result['error']}")
    else:
        print(f"Company: {result['company_name']} (ID: {result['company_id']})")
        print(f"Calculated Date: {result['calculated_date']}")
        print(f"Actual Date: {result['actual_date']}")
        print(f"Match Status: {'✅ PASS' if result['match_status'] else '❌ FAIL'}")
        print(f"Total Deals: {result['total_deals']}")
        print(f"Won Deals: {result['won_deals']}")
        
        if result['match_status']:
            print("\n🎯 VALIDATION SUCCESSFUL!")
        else:
            print("\n🚨 VALIDATION FAILED - Dates don't match!")

if __name__ == "__main__":
    main()
