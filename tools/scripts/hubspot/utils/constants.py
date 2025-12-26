"""
HubSpot field names and constants
Centralized constants for all HubSpot analysis scripts
"""

# Lifecycle Stage Date Fields
HS_DATE_ENTERED_LEAD = 'hs_v2_date_entered_lead'
HS_DATE_ENTERED_OPPORTUNITY = 'hs_v2_date_entered_opportunity'
HS_DATE_ENTERED_CUSTOMER = 'hs_v2_date_entered_customer'

# PQL (Product Qualified Lead) Fields
ACTIVO = 'activo'  # Boolean flag: 'true' if activated
FECHA_ACTIVO = 'fecha_activo'  # Timestamp when activation occurred

# Scoring Fields
FIT_SCORE_CONTADOR = 'fit_score_contador'

# Basic Contact Fields
EMAIL = 'email'
FIRSTNAME = 'firstname'
LASTNAME = 'lastname'
CREATEDATE = 'createdate'
LIFECYCLESTAGE = 'lifecyclestage'
HUBSPOT_OWNER_ID = 'hubspot_owner_id'

# Contact Engagement Fields
HS_FIRST_OUTREACH_DATE = 'hs_first_outreach_date'
HS_SA_FIRST_ENGAGEMENT_DATE = 'hs_sa_first_engagement_date'
HS_LEAD_STATUS = 'hs_lead_status'
LAST_LEAD_STATUS_DATE = 'last_lead_status_date'
HS_LIFECYCLESTAGE_CUSTOMER_DATE = 'hs_lifecyclestage_customer_date'

# Deal Fields
DEALNAME = 'dealname'
DEALSTAGE = 'dealstage'
CLOSEDATE = 'closedate'
AMOUNT = 'amount'
NUM_ASSOCIATED_DEALS = 'num_associated_deals'

# Common Property Lists
CONTACT_BASIC_PROPERTIES = [
    EMAIL,
    FIRSTNAME,
    LASTNAME,
    CREATEDATE,
    LIFECYCLESTAGE,
    HUBSPOT_OWNER_ID,
]

CONTACT_PQL_PROPERTIES = CONTACT_BASIC_PROPERTIES + [
    ACTIVO,
    FECHA_ACTIVO,
    HS_LIFECYCLESTAGE_CUSTOMER_DATE,
]

CONTACT_SQL_PROPERTIES = CONTACT_BASIC_PROPERTIES + [
    HS_DATE_ENTERED_LEAD,
    HS_DATE_ENTERED_OPPORTUNITY,
    HS_DATE_ENTERED_CUSTOMER,
    NUM_ASSOCIATED_DEALS,
]

CONTACT_CYCLE_TIME_PROPERTIES = CONTACT_BASIC_PROPERTIES + [
    HS_DATE_ENTERED_LEAD,
    HS_FIRST_OUTREACH_DATE,
    HS_SA_FIRST_ENGAGEMENT_DATE,
    HS_LEAD_STATUS,
    LAST_LEAD_STATUS_DATE,
]

# HubSpot Configuration
HUBSPOT_PORTAL_ID = '19877595'
HUBSPOT_UI_DOMAIN = 'app.hubspot.com'
HUBSPOT_BASE_URL = 'https://api.hubapi.com'

# Score Ranges for Categorization
SCORE_RANGES = {
    '40+': (40, float('inf')),
    '30-39': (30, 39.99),
    '20-29': (20, 29.99),
    '10-19': (10, 19.99),
    '0-9': (0, 9.99),
}

