#!/usr/bin/env python3
"""
HubSpot Workflow Validator - Dual Mode
Validates HubSpot Custom Code workflow results using either:
1. Python HubSpot client (when API key is available)
2. MCP tools (when running in MCP environment)

Usage:
    python3 hubspot_workflow_validator.py <company_id> [--method python|mcp]
"""

import sys
import os
import json
from datetime import datetime
from typing import Optional, List, Dict, Any

def validate_with_python_client(company_id: str) -> Dict[str, Any]:
    """
    Validate workflow using Python HubSpot client
    
    Requirements:
    - HUBSPOT_ACCESS_TOKEN environment variable must be set
    - hubspot_api.client module must be available
    
    Args:
        company_id: HubSpot company ID to validate
        
    Returns:
        Dictionary with validation results
    """
    try:
        # Add tools directory to path
        sys.path.append('/Users/virulana/openai-cookbook/tools')
        from hubspot_api.client import HubSpotClient
        
        # Initialize client
        client = HubSpotClient()
        
        print(f"=== VALIDATING WITH PYTHON CLIENT FOR COMPANY {company_id} ===")
        
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
            "won_dates": won_dates,
            "method": "python_client"
        }
        
    except ImportError as e:
        return {"error": f"Python client not available: {str(e)}"}
    except Exception as e:
        return {"error": f"Python validation failed: {str(e)}"}

def validate_with_mcp_tools(company_id: str) -> Dict[str, Any]:
    """
    Validate workflow using MCP HubSpot tools
    
    Requirements:
    - Must be running in MCP environment
    - MCP HubSpot tools must be available
    
    Args:
        company_id: HubSpot company ID to validate
        
    Returns:
        Dictionary with validation results
    """
    print(f"=== VALIDATING WITH MCP TOOLS FOR COMPANY {company_id} ===")
    print("Note: This method requires MCP environment and tools")
    
    return {
        "company_id": company_id,
        "method": "mcp_tools",
        "status": "requires_mcp_environment",
        "note": "MCP tools validation requires MCP environment setup",
        "instructions": [
            "1. Run this script in MCP environment",
            "2. Use MCP HubSpot tools directly",
            "3. Call mcp_hubspot_hubspot_batch_read_objects for company data",
            "4. Call mcp_hubspot_hubspot_list_associations for deal associations",
            "5. Call mcp_hubspot_hubspot_batch_read_objects for deal details"
        ]
    }

def print_validation_results(result: Dict[str, Any]):
    """Print validation results in a formatted way"""
    print("\n" + "=" * 60)
    print("📊 VALIDATION RESULTS")
    print("=" * 60)
    
    if "error" in result:
        print(f"❌ Error: {result['error']}")
        return
    
    if result.get("method") == "mcp_tools" and result.get("status") == "requires_mcp_environment":
        print(f"📋 Method: {result['method']}")
        print(f"📝 Note: {result['note']}")
        print("\n📋 Instructions:")
        for instruction in result.get("instructions", []):
            print(f"   {instruction}")
        return
    
    # Print successful validation results
    print(f"Company: {result['company_name']} (ID: {result['company_id']})")
    print(f"Method: {result['method']}")
    print(f"Calculated Date: {result['calculated_date']}")
    print(f"Actual Date: {result['actual_date']}")
    print(f"Match Status: {'✅ PASS' if result['match_status'] else '❌ FAIL'}")
    print(f"Total Deals: {result['total_deals']}")
    print(f"Won Deals: {result['won_deals']}")
    
    if result['match_status']:
        print("\n🎯 VALIDATION SUCCESSFUL!")
        print("The workflow calculation matches the actual field value.")
    else:
        print("\n🚨 VALIDATION FAILED - Dates don't match!")
        print("The workflow calculation does not match the actual field value.")

def main():
    """Main validation function"""
    if len(sys.argv) < 2:
        print("🧪 HubSpot Workflow Validator - Dual Mode")
        print("=" * 50)
        print("Usage: python3 hubspot_workflow_validator.py <company_id> [--method python|mcp]")
        print("")
        print("Examples:")
        print("  python3 hubspot_workflow_validator.py 9019080056")
        print("  python3 hubspot_workflow_validator.py 9019080056 --method python")
        print("  python3 hubspot_workflow_validator.py 9019080056 --method mcp")
        print("")
        print("Methods:")
        print("  python - Use Python HubSpot client (requires HUBSPOT_ACCESS_TOKEN)")
        print("  mcp    - Use MCP tools (requires MCP environment)")
        print("  auto   - Try Python first, fallback to MCP (default)")
        return
    
    company_id = sys.argv[1]
    method = "auto"
    
    if len(sys.argv) > 2 and sys.argv[2] == "--method":
        if len(sys.argv) > 3:
            method = sys.argv[3]
        else:
            print("❌ Error: --method requires a value (python|mcp)")
            return
    
    print("🧪 HubSpot Workflow Validator - Dual Mode")
    print("=" * 50)
    
    # Determine validation method
    if method == "python":
        result = validate_with_python_client(company_id)
    elif method == "mcp":
        result = validate_with_mcp_tools(company_id)
    else:  # auto
        print("🔄 Auto-detecting best validation method...")
        
        # Check if API key is available
        if os.getenv('HUBSPOT_ACCESS_TOKEN') or os.getenv('HUBSPOT_API_KEY'):
            print("📋 API key found, trying Python client...")
            result = validate_with_python_client(company_id)
            
            # If Python client fails, try MCP tools
            if "error" in result:
                print("⚠️ Python client failed, trying MCP tools...")
                result = validate_with_mcp_tools(company_id)
        else:
            print("📋 No API key found, using MCP tools...")
            result = validate_with_mcp_tools(company_id)
    
    print_validation_results(result)

if __name__ == "__main__":
    main()
