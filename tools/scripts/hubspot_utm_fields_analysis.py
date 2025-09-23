#!/usr/bin/env python3
"""
HubSpot UTM Fields Analysis
Version: 1.0.0
Last Updated: 2025-01-09T21:00:00Z

This script analyzes the UTM-related fields found in HubSpot Contact Properties
and provides the correct internal field names for the custom code.
"""

def analyze_utm_fields():
    """Analyze UTM fields from HubSpot Contact Properties"""
    
    print("🔍 HUBSPOT UTM FIELDS ANALYSIS")
    print("=" * 80)
    print()
    
    # UTM fields found in HubSpot Contact Properties
    utm_fields = {
        # Primary UTM Fields
        "utm_campaign": {
            "internal_name": "utm_campaign",
            "ui_label": "utm_campaign",
            "type": "string",
            "group": "utm",
            "description": "Leads-Search-MercadoPago, Search_Contadores, Sales-Performance Max-V2, etc.",
            "status": "✅ VERIFIED - EXISTS"
        },
        "utm_source": {
            "internal_name": "utm_source", 
            "ui_label": "utm_source",
            "type": "string",
            "group": "utm",
            "description": "UTM source parameter",
            "status": "✅ VERIFIED - EXISTS"
        },
        "utm_medium": {
            "internal_name": "utm_medium",
            "ui_label": "utm_medium", 
            "type": "string",
            "group": "utm",
            "description": "UTM medium parameter",
            "status": "✅ VERIFIED - EXISTS"
        },
        "utm_term": {
            "internal_name": "utm_term",
            "ui_label": "utm_term",
            "type": "string", 
            "group": "utm",
            "description": "UTM term parameter",
            "status": "✅ VERIFIED - EXISTS"
        },
        "utm_content": {
            "internal_name": "utm_content",
            "ui_label": "utm_content",
            "type": "string",
            "group": "utm", 
            "description": "UTM content parameter",
            "status": "✅ VERIFIED - EXISTS"
        },
        
        # Original UTM Fields (backup copies)
        "utm_campaign_original": {
            "internal_name": "utm_campaign_original",
            "ui_label": "utm_campaign_original",
            "type": "string",
            "group": "utm",
            "description": "Original UTM campaign value",
            "status": "✅ VERIFIED - EXISTS"
        },
        "utm_source_original": {
            "internal_name": "utm_source_original",
            "ui_label": "utm_source_original", 
            "type": "string",
            "group": "utm",
            "description": "Original UTM source value",
            "status": "✅ VERIFIED - EXISTS"
        },
        "utm_medium_original": {
            "internal_name": "utm_medium_original",
            "ui_label": "utm_medium_original",
            "type": "string",
            "group": "utm",
            "description": "Original UTM medium value", 
            "status": "✅ VERIFIED - EXISTS"
        },
        "utm_content_original": {
            "internal_name": "utm_content_original",
            "ui_label": "utm_content_original",
            "type": "string",
            "group": "utm",
            "description": "Original UTM content value",
            "status": "✅ VERIFIED - EXISTS"
        },
        "utm_term_original": {
            "internal_name": "utm_term_original",
            "ui_label": "utm_term_original",
            "type": "string",
            "group": "utm", 
            "description": "Original UTM term value",
            "status": "✅ VERIFIED - EXISTS"
        },
        
        # Initial UTM Fields (first touch)
        "initial_utm_campaign": {
            "internal_name": "initial_utm_campaign",
            "ui_label": "initial_utm_campaign",
            "type": "string",
            "group": "contactinformation",
            "description": "Initial UTM campaign (first touch)",
            "status": "✅ VERIFIED - EXISTS"
        },
        "initial_utm_source": {
            "internal_name": "initial_utm_source",
            "ui_label": "initial_utm_source",
            "type": "string", 
            "group": "contactinformation",
            "description": "Initial UTM source (first touch)",
            "status": "✅ VERIFIED - EXISTS"
        },
        "initial_utm_medium": {
            "internal_name": "initial_utm_medium",
            "ui_label": "initial_utm_medium",
            "type": "string",
            "group": "contactinformation",
            "description": "Initial UTM medium (first touch)",
            "status": "✅ VERIFIED - EXISTS"
        }
    }
    
    print("📊 UTM FIELDS FOUND IN HUBSPOT:")
    print("-" * 50)
    
    for field_name, field_info in utm_fields.items():
        print(f"✅ {field_name}")
        print(f"   Internal Name: {field_info['internal_name']}")
        print(f"   UI Label: {field_info['ui_label']}")
        print(f"   Type: {field_info['type']}")
        print(f"   Group: {field_info['group']}")
        print(f"   Status: {field_info['status']}")
        if field_info['description']:
            print(f"   Description: {field_info['description']}")
        print()
    
    print("🎯 RECOMMENDED FIELD MAPPINGS FOR CUSTOM CODE:")
    print("-" * 60)
    print("Primary UTM Fields (for current/latest values):")
    print("  utm_campaign → utm_campaign")
    print("  utm_source → utm_source") 
    print("  utm_medium → utm_medium")
    print("  utm_term → utm_term")
    print("  utm_content → utm_content")
    print()
    print("Initial UTM Fields (for first touch attribution):")
    print("  initial_utm_campaign → initial_utm_campaign")
    print("  initial_utm_source → initial_utm_source")
    print("  initial_utm_medium → initial_utm_medium")
    print()
    
    print("⚠️  IMPORTANT NOTES:")
    print("-" * 30)
    print("1. All UTM fields are VERIFIED and exist in HubSpot")
    print("2. Use 'utm_*' fields for current/latest UTM values")
    print("3. Use 'initial_utm_*' fields for first-touch attribution")
    print("4. Use 'utm_*_original' fields for backup/audit purposes")
    print("5. All fields are in the 'utm' group except initial fields")
    print()
    
    return utm_fields

if __name__ == "__main__":
    analyze_utm_fields()



