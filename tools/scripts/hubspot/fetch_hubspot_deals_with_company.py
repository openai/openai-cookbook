import os
import sys
import time
import requests
import csv
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv
import argparse

load_dotenv()

API_KEY = os.getenv("HUBSPOT_API_KEY")
if not API_KEY:
    print("Error: HUBSPOT_API_KEY not found in environment variables")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Accountant channel company types (from documentation)
ACCOUNTANT_COMPANY_TYPES = [
    'Cuenta Contador',
    'Cuenta Contador y Reseller',
    'Contador Robado'
]

OUTPUT_DIR = os.path.join("tools", "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Helper to fetch all deals in the given date range

def fetch_deals(start_date, end_date, deal_stage, filter_type="closedate", filter_both_dates=False):
    """
    Fetch deals from HubSpot API
    
    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format
        deal_stage: Deal stage filter (e.g., 'closedwon', 'all')
        filter_type: Primary date filter type ('closedate' or 'createdate')
        filter_both_dates: If True, filter by BOTH createdate AND closedate (for monthly analysis)
    """
    url = "https://api.hubapi.com/crm/v3/objects/deals/search"
    all_deals = []
    after = None
    page = 0
    while True:
        page += 1
        print(f"Fetching deals page {page}...")
        
        # Build filters based on filter_type and deal_stage
        if filter_both_dates:
            # Filter by BOTH createdate AND closedate (for monthly analysis - matches HubSpot report filter)
            filters = [
                {"propertyName": "createdate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
                {"propertyName": "createdate", "operator": "LT", "value": f"{end_date}T00:00:00Z"},
                {"propertyName": "closedate", "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
                {"propertyName": "closedate", "operator": "LT", "value": f"{end_date}T00:00:00Z"}
            ]
        else:
            # Filter by single date type (default behavior)
            filters = [
                {"propertyName": filter_type, "operator": "GTE", "value": f"{start_date}T00:00:00Z"},
                {"propertyName": filter_type, "operator": "LT", "value": f"{end_date}T00:00:00Z"}
            ]
        
        # Only add dealstage filter if it's not "all"
        if deal_stage.lower() != "all":
            filters.append({"propertyName": "dealstage", "operator": "EQ", "value": deal_stage})
        
        payload = {
            "filterGroups": [
                {
                    "filters": filters
                }
            ],
            "properties": [
                "dealname", "dealstage", "closedate", "createdate", "amount", "hubspot_owner_id",
                "nombre_del_plan_del_negocio",  # Subscription plan name for ICP Operador analysis
                # UTM and campaign properties
                "hs_analytics_source", "hs_analytics_source_data_1", "hs_analytics_source_data_2",
                "utm_campaign", "utm_source", "utm_medium", "utm_content", "utm_term",
                "lead_source", "hs_analytics_first_touch_converting_campaign",
                "hs_analytics_last_touch_converting_campaign"
            ],
            "associations": ["companies"],
            "limit": 100
        }
        if after:
            payload["after"] = after
        resp = requests.post(url, headers=HEADERS, json=payload)
        if resp.status_code != 200:
            print(f"Error: {resp.status_code} {resp.text}")
            break
        data = resp.json()
        results = data.get("results", [])
        all_deals.extend(results)
        print(f"  Retrieved {len(results)} deals (total: {len(all_deals)})")
        after = data.get("paging", {}).get("next", {}).get("after")
        if not after:
            break
        time.sleep(0.2)
    return all_deals

# Helper to get company ID from associations (gets first company, not necessarily PRIMARY)

def extract_company_id(deal):
    assoc = deal.get("associations", {})
    companies = assoc.get("companies", {}).get("results", [])
    if companies:
        return companies[0].get("id", "")
    return ""

def get_deal_company_associations(deal_id):
    """Get all company associations for a deal using v4 API"""
    url = f"https://api.hubapi.com/crm/v4/objects/deals/{deal_id}/associations/companies"
    try:
        response = requests.get(url, headers=HEADERS, timeout=30)
        if response.status_code == 200:
            return response.json().get('results', [])
        return []
    except Exception as e:
        print(f"    ⚠️  Warning: Error getting associations for deal {deal_id}: {e}")
        return []

def get_primary_company_id(deal_id):
    """Find the primary company ID from deal-company associations (Type ID 5)"""
    associations = get_deal_company_associations(deal_id)
    for assoc in associations:
        association_types = assoc.get('associationTypes', [])
        for assoc_type in association_types:
            if assoc_type.get('typeId') == 5:  # PRIMARY association
                return assoc.get('toObjectId')
    return None

def get_company_details(company_id):
    """Get company details including name and type"""
    url = f"https://api.hubapi.com/crm/v3/objects/companies/{company_id}"
    params = {'properties': 'name,type'}
    try:
        response = requests.get(url, headers=HEADERS, params=params, timeout=30)
        if response.status_code == 200:
            return response.json().get('properties', {})
        return {}
    except Exception as e:
        print(f"    ⚠️  Warning: Error getting company {company_id}: {e}")
        return {}

def is_accountant_plan(plan_name):
    """Check if plan name contains 'ICP' AND 'Contador'"""
    if not plan_name:
        return False
    plan_upper = plan_name.upper()
    return 'ICP' in plan_upper and 'CONTADOR' in plan_upper

def analyze_icp_operador_billing(deal):
    """
    Analyze if deal is billed to accountant (ICP Operador).
    Returns dict with analysis results.
    """
    deal_id = deal.get('id')
    props = deal.get('properties', {})
    plan_name = props.get('nombre_del_plan_del_negocio', '')
    
    result = {
        'is_icp_operador': False,
        'method_used': 'NEITHER',
        'primary_company_id': None,
        'primary_company_name': None,
        'primary_company_type': None,
        'is_accountant_by_company_type': False,
        'is_accountant_by_plan_name': False
    }
    
    # METHOD 1: Check PRIMARY company type
    primary_company_id = get_primary_company_id(deal_id)
    if primary_company_id:
        result['primary_company_id'] = primary_company_id
        company_details = get_company_details(primary_company_id)
        result['primary_company_name'] = company_details.get('name', 'Unknown')
        result['primary_company_type'] = company_details.get('type', 'Unknown')
        
        if result['primary_company_type'] in ACCOUNTANT_COMPANY_TYPES:
            result['is_accountant_by_company_type'] = True
            result['is_icp_operador'] = True
            result['method_used'] = 'PRIMARY_COMPANY_TYPE'
    
    # METHOD 2: Check plan name
    if is_accountant_plan(plan_name):
        result['is_accountant_by_plan_name'] = True
        if not result['is_icp_operador']:
            result['is_icp_operador'] = True
            result['method_used'] = 'PLAN_NAME'
        elif result['method_used'] == 'PRIMARY_COMPANY_TYPE':
            result['method_used'] = 'BOTH'
    
    time.sleep(0.1)  # Rate limiting
    return result

# Optionally, map owner IDs to names (reuse mapping from leads script)
OWNER_MAP = {
    "8854527": "David Chacon",
    "43771160": "Victoria Gutiérrez",
    "72282443": "Eduardo Illiano",
    "75890889": "Mariela Sandroni",
    "76272874": "Damaris Justina Rojo",
    "76909178": "Soporte Colppy",
    "76931304": "Julieta Aguilar",
    "78535701": "Estefania Sol Arregui",
    "79369461": "Mariano Alvarez Bor",
    "80100566": "No Name",
    "103103434": "Axel Concha",
    "103406387": "Karina Lorena Russo",
    "151388545": "Pamela Viarengo",
    "156735647": "Equipo Andimol",
    "156735648": "Macarena Cuadro",
    "156735649": "Luisa Ines Facchini",
    "166611629": "No Name",
    "166611630": "Agustina Guevara",
    "166611631": "Carla Alonso",
    "166613311": "Ángela Camelo",
    "185247245": "Juan Diego Chiapparo",
    "185249056": "Martin de los santos",
    "185249653": "Julieta Ayerbe",
    "185249654": "Fernando Funes",
    "185249655": "Agustina Menditto",
    "195420559": "Tupac Bruch",
    "196609872": "Juliana Palacios",
    "200354433": "Sabrina Boggero",
    "200354449": "Maximiliano Cabañes",
    "206527914": "Melina Costa",
    "206527915": "Hernán Córdoba",
    "206528273": "Pedro Gomez Goldin",
    "206640141": "Maria Sol Contarino",
    "206640142": "Mayra Schneider",
    "210711167": "Cecilia Bonomo",
    "210711168": "Josefina Zabala",
    "210711169": "No Name",
    "210711170": "Jose Marino",
    "213453847": "Agustina Lopez",
    "213456768": "Facundo Benítez",
    "213456769": "Maria Pia Airaldi",
    "213456770": "Yamila Sosa",
    "213457436": "Antonella Pachas",
    "213457437": "Juan Calvente",
    "213458481": "Angie Páez",
    "213458482": "yesica nickel",
    "213458511": "Exiree Atencio",
    "213458512": "Mariana Leal",
    "216511812": "Juan Ignacio Onetto",
    "233436011": "Comunicacion Colppy",
    "236591532": "Alejandro Naranjo",
    "263663363": "Camilo Gonzalez",
    "263667385": "Javier Navarro",
    "335850520": "No Name",
    "354576217": "Franco Silva",
    "378736477": "Gaston Espoile",
    "416739362": "Claudia Cristi",
    "456300151": "Fernando Contador",
    "488534830": "Barbara Lamas",
    "509260862": "No Name",
    "509292821": "Agustina Grosso",
    "512834146": "Victoria Dacampo",
    "524074776": "Alexander Rondon",
    "612003866": "Romina Herrera",
    "619916557": "Adriana Zelonka",
    "672724138": "Pablo Ezcurra",
    "685347337": "Engelberth Sojo",
    "685409115": "Leslye Monzon",
    "688875036": "Pablo Pereira Colman",
    "688905556": "No Name",
    "689030010": "Dolores Herrero",
    "713598836": "Santiago Martinez",
    "863904255": "Tobías Carvajal Chen",
    "881283463": "No Name",
    "1280444080": "Franco Alvarez",
}

def main():
    parser = argparse.ArgumentParser(description='Fetch HubSpot deals with company associations and optional ICP Operador analysis')
    parser.add_argument('--start-date', type=str, help='Start date in format YYYY-MM-DD')
    parser.add_argument('--end-date', type=str, help='End date in format YYYY-MM-DD')
    parser.add_argument('--deal-stage', type=str, default='closedwon', help='Deal stage (default: closedwon)')
    parser.add_argument('--filter-type', type=str, default='closedate', choices=['closedate', 'createdate'], help='Date filter type (default: closedate). Ignored if --filter-both-dates is used.')
    parser.add_argument('--filter-both-dates', action='store_true', help='Filter by BOTH createdate AND closedate (matches HubSpot report filter for monthly analysis)')
    parser.add_argument('--analyze-icp-operador', action='store_true', help='Analyze ICP Operador billing (who we bill)')
    parser.add_argument('--month', type=str, help='Month in format YYYY-MM (alternative to start-date/end-date)')
    
    args = parser.parse_args()
    
    # Handle month argument
    if args.month:
        year, month = args.month.split('-')
        start_date = f"{year}-{month}-01"
        if month == '12':
            end_date = f"{int(year)+1}-01-01"
        else:
            end_date = f"{year}-{int(month)+1:02d}-01"
    elif args.start_date and args.end_date:
        start_date = args.start_date
        end_date = args.end_date
    else:
        parser.error("Either --month or both --start-date and --end-date must be provided")
    
    deal_stage = args.deal_stage
    filter_type = args.filter_type
    filter_both_dates = args.filter_both_dates
    
    # For ICP Operador analysis, always use both dates filter (matches HubSpot report standard)
    if args.analyze_icp_operador:
        filter_both_dates = True
        print("Note: Using both createdate AND closedate filter for ICP Operador analysis (matches HubSpot report standard)")
    
    # Fetch deals
    deals = fetch_deals(start_date, end_date, deal_stage, filter_type, filter_both_dates)
    print(f"\n✅ Fetched {len(deals)} deals.")
    
    if not deals:
        print("No deals found in the specified period.")
        return
    
    # Analyze ICP Operador billing if requested
    if args.analyze_icp_operador:
        print(f"\n🔍 ANALYZING ICP OPERADOR BILLING")
        print("=" * 80)
        
        analysis_results = []
        for i, deal in enumerate(deals, 1):
            print(f"[{i}/{len(deals)}] Analyzing deal {deal.get('id')}...", end="\r")
            result = analyze_icp_operador_billing(deal)
            analysis_results.append(result)
        
        # Create DataFrame and add analysis results
        df_data = []
        for deal, analysis in zip(deals, analysis_results):
            props = deal.get("properties", {})
            deal_id = deal.get("id", "")
            
            df_data.append({
                'deal_id': deal_id,
                'deal_name': props.get("dealname", ""),
                'deal_stage': props.get("dealstage", ""),
                'closedate': props.get("closedate", ""),
                'createdate': props.get("createdate", ""),
                'amount': props.get("amount", ""),
                'plan_name': props.get("nombre_del_plan_del_negocio", ""),
                'owner_id': props.get("hubspot_owner_id", ""),
                'owner_name': OWNER_MAP.get(props.get("hubspot_owner_id", ""), ""),
                'primary_company_id': analysis['primary_company_id'],
                'primary_company_name': analysis['primary_company_name'],
                'primary_company_type': analysis['primary_company_type'],
                'is_icp_operador': analysis['is_icp_operador'],
                'method_used': analysis['method_used'],
                'is_accountant_by_company_type': analysis['is_accountant_by_company_type'],
                'is_accountant_by_plan_name': analysis['is_accountant_by_plan_name']
            })
        
        df = pd.DataFrame(df_data)
        
        # Summary statistics
        print("\n" + "=" * 80)
        print("📊 ICP OPERADOR BILLING SUMMARY")
        print("=" * 80)
        
        total_deals = len(df)
        icp_operador_deals = df['is_icp_operador'].sum()
        by_company_type = df['is_accountant_by_company_type'].sum()
        by_plan_name = df['is_accountant_by_plan_name'].sum()
        non_icp_deals = total_deals - icp_operador_deals
        
        print(f"\nTotal Deals: {total_deals}")
        print(f"ICP Operador (Billed to Accountant): {icp_operador_deals} ({icp_operador_deals/total_deals*100:.1f}%)")
        print(f"  - Identified by PRIMARY company type: {by_company_type}")
        print(f"  - Identified by plan name (ICP + Contador): {by_plan_name}")
        print(f"Non-ICP Operador (Billed to SMB): {non_icp_deals} ({non_icp_deals/total_deals*100:.1f}%)")
        
        # Save detailed results
        output_csv = os.path.join(OUTPUT_DIR, f"hubspot_deals_{start_date}_to_{end_date}_stage_{deal_stage}_icp_operador_analysis.csv")
        df.to_csv(output_csv, index=False)
        print(f"\n💾 Detailed results saved to: {output_csv}")
        
    else:
        # Original functionality: export basic deal data
        output_csv = os.path.join(OUTPUT_DIR, f"hubspot_deals_{start_date}_to_{end_date}_stage_{deal_stage}_{filter_type}_with_company.csv")
        with open(output_csv, "w", newline="") as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(["Deal ID", "Deal Name", "Stage", "Close Date", "Create Date", "Amount", "Owner ID", "Owner Name", "Company ID (ID Empresa)", "Plan Name", "UTM Campaign", "UTM Source", "UTM Medium", "Lead Source", "Analytics Source", "First Touch Campaign", "Last Touch Campaign"])
            for deal in deals:
                deal_id = deal.get("id", "")
                props = deal.get("properties", {})
                deal_name = props.get("dealname", "")
                stage = props.get("dealstage", "")
                close_date = props.get("closedate", "")
                create_date = props.get("createdate", "")
                amount = props.get("amount", "")
                owner_id = props.get("hubspot_owner_id", "")
                owner_name = OWNER_MAP.get(owner_id, "")
                company_id = extract_company_id(deal)
                plan_name = props.get("nombre_del_plan_del_negocio", "")
                
                # UTM and campaign data
                utm_campaign = props.get("utm_campaign", "")
                utm_source = props.get("utm_source", "")
                utm_medium = props.get("utm_medium", "")
                lead_source = props.get("lead_source", "")
                analytics_source = props.get("hs_analytics_source", "")
                first_touch_campaign = props.get("hs_analytics_first_touch_converting_campaign", "")
                last_touch_campaign = props.get("hs_analytics_last_touch_converting_campaign", "")
                
                writer.writerow([deal_id, deal_name, stage, close_date, create_date, amount, owner_id, owner_name, company_id, plan_name, utm_campaign, utm_source, utm_medium, lead_source, analytics_source, first_touch_campaign, last_touch_campaign])
        print(f"💾 Exported to {output_csv}")

if __name__ == "__main__":
    main() 