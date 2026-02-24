---
name: hubspot-api-patterns
description: Colppy's HubSpot API client patterns, query builder usage, pagination standards, and common operations. Apply when writing or running HubSpot API queries, fetching deals/companies/contacts, or building analysis scripts.
---

# HubSpot API Patterns — Colppy

Patterns for working with Colppy's custom HubSpot API package and MCP tools.

---

## Custom API Package (tools/hubspot_api/)

### Architecture
```
tools/hubspot_api/
├── config.py           # API key and environment configuration
├── client.py           # HTTP client with retry and rate limiting
├── models.py           # Object models (Deal, Company, Contact)
└── query_builder.py    # Fluent query interface
```

### Using Object Models
```python
from hubspot_api.models import Deal, Company, Contact

# Find closed won deals
deals = Deal.find_closed_won(
    start_date="2025-07-01T00:00:00.000Z",
    end_date="2025-07-31T23:59:59.999Z"
)

# Find companies with CUIT
companies = Company.find_with_cuit()

# Find by CUIT
company = Company.find_by_cuit("30716311186")

# Find deals by empresa ID
deals = Deal.find_by_empresa_id("94334")
```

### Using Query Builder
```python
from hubspot_api.query_builder import deals_query, companies_query

# Complex query
results = (deals_query()
    .select("dealname", "amount", "dealstage", "closedate")
    .where_equal("dealstage", "closedwon")
    .where_greater_than("amount", "100000")
    .where_date_range("closedate", "2025-07-01", "2025-07-31")
    .order_by_desc("amount")
    .limit(50)
    .execute())

# Get all with pagination
all_companies = (companies_query()
    .where_has_property("cuit")
    .get_all(max_results=1000))
```

---

## MCP Tool Patterns (Cowork)

### Searching Objects
Use `hubspot-search-objects` with filter groups:
- Filters in same group = AND logic
- Separate filter groups = OR logic
- Max 5 filter groups, 6 filters each, 18 total

### Fetching Associations
Use `hubspot-list-associations`:
- `objectType`: source object type (e.g., "deals")
- `objectId`: the record ID
- `toObjectType`: target (e.g., "companies")

### Reading Objects by ID
Use `hubspot-batch-read-objects`:
- Include `propertiesWithHistory` for property change history
- Useful for checking Lead creation source (`hs_created_by_user_id`)

---

## Pagination Standards

- Default page size: 100
- Max per page: varies by endpoint
- Use `after` cursor for pagination
- Rate limit: use `HUBSPOT_RATE_LIMIT_DELAY` (default 0.5s)
- First 5 requests use `HUBSPOT_INITIAL_DELAY` (1.0s) to avoid burst 429s

---

## Common Operations

### Check if Contact is a Lead
```
1. hubspot-list-associations (contact → leads)
2. If results exist → Contact IS a Lead
3. If empty → NOT a Lead
```

### Determine ICP for a Deal
```
1. Check deal property `primary_company_type`
2. If populated and in ACCOUNTANT_COMPANY_TYPES → ICP Operador
3. If not, get associations (deal → companies, typeId 5)
4. Read primary company `type` field
5. Classify based on type value
```

### Get Owner Team
```
1. Use Owners API: /crm/v3/owners/{ownerId}
2. Check teams array for team.name
3. Never use Users API for team info
```

---

## Error Handling

- `HubSpotRateLimitError` → Retry after delay
- `HubSpotAPIError` → Check property names, filter operators
- 429 responses → Increase `HUBSPOT_RATE_LIMIT_DELAY` in .env

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `HUBSPOT_API_KEY` | Required | API access token |
| `HUBSPOT_TIMEOUT` | 30 | Request timeout (seconds) |
| `HUBSPOT_MAX_RETRIES` | 3 | Max retry attempts |
| `HUBSPOT_RATE_LIMIT_DELAY` | 0.5 | Delay between requests (seconds) |
| `HUBSPOT_DEFAULT_LIMIT` | 100 | Default page size |
