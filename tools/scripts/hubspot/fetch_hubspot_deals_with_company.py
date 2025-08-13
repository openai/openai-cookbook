import os
import sys
import time
import requests
import csv
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("HUBSPOT_API_KEY")
if not API_KEY:
    print("Error: HUBSPOT_API_KEY not found in environment variables")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json"
}

# Accept start and end date as arguments, dealstage, and filter type
if len(sys.argv) > 4:
    START_DATE = sys.argv[1]
    END_DATE = sys.argv[2]
    DEAL_STAGE = sys.argv[3]
    FILTER_TYPE = sys.argv[4]  # "closedate" or "createdate"
elif len(sys.argv) > 3:
    START_DATE = sys.argv[1]
    END_DATE = sys.argv[2]
    DEAL_STAGE = sys.argv[3]
    FILTER_TYPE = "closedate"
else:
    START_DATE = "2025-05-01"
    END_DATE = "2025-06-01"
    DEAL_STAGE = "closedwon"
    FILTER_TYPE = "closedate"

OUTPUT_DIR = os.path.join("hubspot_reports", "deals")
os.makedirs(OUTPUT_DIR, exist_ok=True)
OUTPUT_CSV = os.path.join(
    OUTPUT_DIR,
    f"hubspot_deals_{START_DATE}_to_{END_DATE}_stage_{DEAL_STAGE}_{FILTER_TYPE}_with_company.csv"
)

# Helper to fetch all deals in the given date range

def fetch_deals(start_date, end_date, deal_stage, filter_type="closedate"):
    url = "https://api.hubapi.com/crm/v3/objects/deals/search"
    all_deals = []
    after = None
    page = 0
    while True:
        page += 1
        print(f"Fetching deals page {page}...")
        
        # Build filters based on filter_type and deal_stage
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

# Helper to get company ID from associations

def extract_company_id(deal):
    assoc = deal.get("associations", {})
    companies = assoc.get("companies", {}).get("results", [])
    if companies:
        return companies[0].get("id", "")
    return ""

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
    deals = fetch_deals(START_DATE, END_DATE, DEAL_STAGE, FILTER_TYPE)
    print(f"Fetched {len(deals)} deals.")
    with open(OUTPUT_CSV, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["Deal ID", "Deal Name", "Stage", "Close Date", "Create Date", "Amount", "Owner ID", "Owner Name", "Company ID (ID Empresa)", "UTM Campaign", "UTM Source", "UTM Medium", "Lead Source", "Analytics Source", "First Touch Campaign", "Last Touch Campaign"])
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
            
            # UTM and campaign data
            utm_campaign = props.get("utm_campaign", "")
            utm_source = props.get("utm_source", "")
            utm_medium = props.get("utm_medium", "")
            lead_source = props.get("lead_source", "")
            analytics_source = props.get("hs_analytics_source", "")
            first_touch_campaign = props.get("hs_analytics_first_touch_converting_campaign", "")
            last_touch_campaign = props.get("hs_analytics_last_touch_converting_campaign", "")
            
            writer.writerow([deal_id, deal_name, stage, close_date, create_date, amount, owner_id, owner_name, company_id, utm_campaign, utm_source, utm_medium, lead_source, analytics_source, first_touch_campaign, last_touch_campaign])
    print(f"Exported to {OUTPUT_CSV}")

if __name__ == "__main__":
    main() 