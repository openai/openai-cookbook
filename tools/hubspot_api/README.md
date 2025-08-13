# HubSpot API Package

Reusable RESTful API client for HubSpot CRM integration with database-like query interface.

## Quick Setup

### 1. Environment Configuration

Create or update `tools/.env` with your HubSpot API key:

```env
# HubSpot API Configuration
HUBSPOT_API_KEY=your_hubspot_api_key_here

# Optional HubSpot Settings
HUBSPOT_TIMEOUT=30
HUBSPOT_MAX_RETRIES=3
HUBSPOT_RATE_LIMIT_DELAY=0.1
HUBSPOT_DEFAULT_LIMIT=100
ENVIRONMENT=development
```

### 2. Install Dependencies

```bash
pip install requests python-dotenv
```

### 3. Test Connection

```python
from hubspot_api import get_client
from hubspot_api.models import test_hubspot_connection

# Test connection
if test_hubspot_connection():
    print("✅ HubSpot API connected!")

# Get client stats
client = get_client()
print(f"Client stats: {client.get_stats()}")
```

## Architecture Overview

The HubSpot API package follows the same structure as the database package:

```
tools/hubspot_api/
├── __init__.py          # Package exports
├── config.py           # API key and environment configuration  
├── client.py           # HTTP client with retry and rate limiting
├── models.py           # Object models (Deal, Company, Contact)
├── query_builder.py    # Fluent query interface
└── README.md          # This file
```

## Usage Examples

### Direct Client Usage

```python
from hubspot_api import get_client

client = get_client()

# Search deals
deals = client.search_objects(
    object_type="deals",
    filter_groups=[{
        "filters": [
            {"propertyName": "dealstage", "operator": "EQ", "value": "closedwon"},
            {"propertyName": "createdate", "operator": "GTE", "value": "2025-07-01T00:00:00.000Z"}
        ]
    }],
    properties=["dealname", "amount", "id_empresa"],
    limit=50
)

print(f"Found {len(deals['results'])} deals")
```

### Using Object Models

```python
from hubspot_api.models import Deal, Company, Contact

# Find closed won deals in July 2025
july_deals = Deal.find_closed_won(
    start_date="2025-07-01T00:00:00.000Z",
    end_date="2025-07-31T23:59:59.999Z",
    date_property="createdate"
)

# Find companies with CUIT
companies_with_cuit = Company.find_with_cuit()

# Find specific company by CUIT
company = Company.find_by_cuit("30716311186")

# Find deals by empresa ID
deals = Deal.find_by_empresa_id("94334")

# Count total deals
total_deals = Deal.count()
```

### Using Query Builder

```python
from hubspot_api.query_builder import deals_query, companies_query

# Complex deal query
high_value_deals = (deals_query()
    .select("dealname", "amount", "dealstage", "closedate", "id_empresa")
    .where_equal("dealstage", "closedwon")
    .where_greater_than("amount", "100000")
    .where_date_range("closedate", "2025-07-01", "2025-07-31")
    .order_by_desc("amount")
    .limit(50)
    .execute())

# Company query with multiple filters
companies = (companies_query()
    .select("name", "cuit", "city", "createdate")
    .where_has_property("cuit")
    .where_equal("country", "Argentina")
    .or_where()  # Start OR condition
    .where_equal("city", "Buenos Aires")
    .order_by_asc("name")
    .get_all())

# Get all results with pagination
all_companies = (companies_query()
    .where_has_property("cuit")
    .get_all(max_results=1000))
```

### Pre-built Common Queries

```python
from hubspot_api.query_builder import (
    closed_won_deals_in_july_2025,
    companies_with_cuit,
    companies_missing_cuit
)

# Use pre-built queries
july_deals = closed_won_deals_in_july_2025().get_all()
companies_with_cuit = companies_with_cuit().get_all()
companies_missing_cuit = companies_missing_cuit().get_all()
```

## Integration with Colppy Database

```python
from hubspot_api.models import Deal, Company
from database.models import BaseModel

class Empresa(BaseModel):
    table_name = 'empresa'
    primary_key = 'IdEmpresa'

def sync_colppy_to_hubspot():
    """Example: Sync companies from Colppy to HubSpot"""
    
    # Get July 2025 closed won deals from HubSpot
    hubspot_deals = Deal.find_closed_won(
        start_date="2025-07-01T00:00:00.000Z",
        end_date="2025-07-31T23:59:59.999Z",
        date_property="createdate"
    )
    
    # Extract empresa IDs
    empresa_ids = []
    for deal in hubspot_deals:
        props = deal.get("properties", {})
        empresa_id = props.get("id_empresa")
        if empresa_id:
            empresa_ids.append(empresa_id)
    
    print(f"Found {len(empresa_ids)} unique empresa IDs in HubSpot")
    
    # Query Colppy database for these companies
    companies_with_cuits = []
    for empresa_id in empresa_ids:
        company = Empresa.find_by_id(empresa_id)
        if company:
            data = company.to_dict()
            cuit = data.get('CUIT', '').strip()
            if cuit:
                companies_with_cuits.append({
                    'id_empresa': empresa_id,
                    'cuit': cuit,
                    'nombre': data.get('Nombre', '')
                })
    
    print(f"Found {len(companies_with_cuits)} companies with CUITs in Colppy")
    
    # Check which CUITs are missing in HubSpot
    hubspot_cuits = set()
    hubspot_companies = Company.find_with_cuit(properties=["cuit"])
    
    for company in hubspot_companies:
        props = company.get("properties", {})
        cuit = props.get("cuit", "")
        if cuit:
            clean_cuit = "".join(filter(str.isdigit, cuit))
            hubspot_cuits.add(clean_cuit)
    
    # Find missing CUITs
    missing_cuits = []
    for company in companies_with_cuits:
        clean_cuit = "".join(filter(str.isdigit, company['cuit']))
        if clean_cuit not in hubspot_cuits:
            missing_cuits.append(company)
    
    print(f"Found {len(missing_cuits)} companies needing CUIT migration to HubSpot")
    
    return missing_cuits

# Run the sync
missing_companies = sync_colppy_to_hubspot()
```

## Key Features

- **RESTful API Client**: Full HTTP client with retry logic and rate limiting
- **Object Models**: Database-like models for Deals, Companies, Contacts
- **Query Builder**: Fluent interface for complex queries
- **Automatic Pagination**: Get all results with automatic page handling
- **Error Handling**: Comprehensive error handling and logging
- **Rate Limiting**: Built-in rate limit management
- **Environment Configuration**: Environment-based API key management
- **Integration Ready**: Designed to work with Colppy database package

## Advanced Usage

### Custom Object Types

```python
from hubspot_api.models import HubSpotObject

class CustomObject(HubSpotObject):
    object_type = "custom_object_type"
    default_properties = ["name", "custom_property", "createdate"]
    
    @classmethod
    def find_by_custom_property(cls, value):
        return cls.find_by_property("custom_property", value)

# Use custom object
custom_objects = CustomObject.find_all()
```

### Batch Operations

```python
from hubspot_api import get_client

client = get_client()

# Get all deals in batches
all_deals = client.get_all_objects(
    object_type="deals",
    filter_groups=[{
        "filters": [{"propertyName": "dealstage", "operator": "EQ", "value": "closedwon"}]
    }],
    max_results=5000  # Will handle pagination automatically
)

print(f"Retrieved {len(all_deals)} deals total")
```

### Error Handling

```python
from hubspot_api.client import HubSpotAPIError, HubSpotRateLimitError
from hubspot_api.models import Deal

try:
    deals = Deal.find_all()
except HubSpotRateLimitError:
    print("Rate limited - retry after delay")
except HubSpotAPIError as e:
    print(f"HubSpot API error: {e}")
except Exception as e:
    print(f"Unexpected error: {e}")
```

## Configuration Options

All configuration can be set via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `HUBSPOT_API_KEY` | Required | HubSpot API access token |
| `HUBSPOT_TIMEOUT` | 30 | Request timeout in seconds |
| `HUBSPOT_MAX_RETRIES` | 3 | Maximum retry attempts |
| `HUBSPOT_RATE_LIMIT_DELAY` | 0.1 | Delay between requests (seconds) |
| `HUBSPOT_DEFAULT_LIMIT` | 100 | Default page size for queries |
| `ENVIRONMENT` | development | Environment name |

## Filter Operators

The query builder supports all HubSpot filter operators:

- `EQ` - Equal to
- `NEQ` - Not equal to
- `LT` - Less than
- `LTE` - Less than or equal to
- `GT` - Greater than
- `GTE` - Greater than or equal to
- `BETWEEN` - Between two values
- `IN` - In list of values
- `NOT_IN` - Not in list of values
- `HAS_PROPERTY` - Property has any value
- `NOT_HAS_PROPERTY` - Property is empty
- `CONTAINS_TOKEN` - Contains text token

## Performance Tips

1. **Use specific properties**: Only request properties you need
2. **Add filters**: Use filters to reduce result sets
3. **Use pagination**: Use `limit()` for large datasets
4. **Batch operations**: Use `get_all()` for complete datasets
5. **Monitor rate limits**: Check client stats regularly

## Troubleshooting

### Connection Issues
- Verify API key in `.env` file
- Check API key permissions in HubSpot
- Ensure network connectivity

### Rate Limiting
- Increase `HUBSPOT_RATE_LIMIT_DELAY`
- Reduce concurrent requests
- Use batch operations instead of individual requests

### Query Issues
- Check property names against HubSpot schema
- Verify filter operator compatibility
- Use smaller result limits for testing

## Integration Examples

### Export HubSpot Data to CSV

```python
import csv
from hubspot_api.query_builder import closed_won_deals_in_july_2025

# Get July 2025 deals
deals = closed_won_deals_in_july_2025().get_all()

# Export to CSV
with open('july_2025_deals.csv', 'w', newline='') as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=['id', 'dealname', 'amount', 'id_empresa'])
    writer.writeheader()
    
    for deal in deals:
        props = deal.get('properties', {})
        writer.writerow({
            'id': deal.get('id'),
            'dealname': props.get('dealname'),
            'amount': props.get('amount'),
            'id_empresa': props.get('id_empresa')
        })
```

### Real-time Data Sync

```python
from hubspot_api.models import Company
from database.models import BaseModel

def sync_company_data():
    """Sync company data between Colppy and HubSpot"""
    
    # Get companies from both systems
    hubspot_companies = Company.find_all(properties=["name", "cuit", "colppy_id"])
    colppy_companies = Empresa.find_all()
    
    # Compare and identify missing/outdated records
    # Implementation depends on sync strategy
    
    return sync_results
```

## Need Help?

- Check the examples in each module
- Review HubSpot API documentation for object schemas
- Contact your development team for Colppy-specific integration questions