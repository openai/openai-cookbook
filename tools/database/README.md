# AWS MySQL Database Package

Fast, simple database connectivity for Colppy's company-centric transition and HubSpot data migration.

## Quick Setup

### 1. Create Environment File

Create `tools/.env` with your AWS MySQL credentials:

```env
# AWS MySQL Database Configuration
DB_HOST=your-aws-mysql-endpoint.rds.amazonaws.com
DB_PORT=3306
DB_NAME=your_database_name
DB_USER=your_username
DB_PASSWORD=your_password

# Database Settings
DB_CHARSET=utf8mb4
DB_SSL_MODE=REQUIRED

# Environment
ENVIRONMENT=development
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Test Connection

```python
from database.connection import db

# Test database connectivity
if db.test_connection():
    print("✅ Database connected!")
    
# List all tables
tables = db.list_tables()
print(f"Available tables: {tables}")
```

## Usage Examples

### Simple Queries

```python
from database.connection import db

# Execute direct SQL
companies = db.execute_query(
    "SELECT * FROM companies WHERE status = :status",
    {"status": "active"}
)

# Fetch table data with filtering
active_companies = db.fetch_table_data(
    "companies",
    "status = :status AND type = :type",
    {"status": "active", "type": "SMB"},
    limit=100
)
```

### Using Models

```python
from database.models import Company, User

# Find all active companies
companies = Company.find_active_companies()

# Find company by ID
company = Company.find_by_id(123)

# Find user by email
user = User.find_by_email("admin@colppy.com")

# Count records
total_companies = Company.count()
smb_companies = Company.count("type = :type", {"type": "SMB"})
```

### Query Builder (Complex Queries)

```python
from database import QueryBuilder

# Build complex query
results = (QueryBuilder()
    .select("c.name", "u.email", "COUNT(a.id) as accounts")
    .from_table("companies c")
    .join("users u", "c.id = u.company_id")
    .join("accounts a", "c.id = a.company_id")
    .where("c.status = :status", status="active")
    .group_by("c.id", "c.name", "u.email")
    .order_by("accounts", "DESC")
    .limit(50)
    .execute())
```

### HubSpot Migration

```python
from database.query_builder import build_migration_query

# Map database columns to HubSpot properties
mapping = {
    "id": "external_id",
    "company_name": "name", 
    "email": "domain",
    "type": "industry",
    "created_at": "createdate"
}

# Get data ready for HubSpot
migration_query = build_migration_query(
    "companies", 
    mapping,
    "status = :status AND created_at > :date",
    status="active",
    date="2024-01-01"
)

hubspot_data = migration_query.execute()
```

## File Structure

```
tools/database/
├── __init__.py           # Package exports
├── config.py            # Environment configuration
├── connection.py        # Database connection management
├── models.py           # Base model classes
├── query_builder.py    # Query builder for complex queries
├── example_usage.py    # Usage examples
└── README.md          # This file
```

## Key Features

- **Read-only operations** (safe for production data)
- **Connection pooling** for performance
- **Environment-based configuration**
- **Automatic retry logic**
- **Generic model classes** for any table
- **Query builder** for complex operations
- **HubSpot migration helpers**
- **Error handling and logging**

## Customizing Models

Update the model classes in `models.py` to match your database schema:

```python
class Company(BaseModel):
    table_name = "your_companies_table"
    primary_key = "company_id"  # or whatever your PK is
    
    @classmethod
    def find_by_cuit(cls, cuit: str):
        return cls.find_one("cuit = :cuit", {"cuit": cuit})
```

## Common Operations for Data Migration

### Find Companies for HubSpot Sync

```python
# Get companies created/updated since last sync
new_companies = (QueryBuilder()
    .from_table("companies")
    .where("updated_at > :last_sync OR created_at > :last_sync", 
           last_sync="2025-01-15")
    .execute())
```

### Analyze Data Before Migration

```python
# Check data quality
missing_emails = Company.count("email IS NULL OR email = ''")
print(f"Companies missing email: {missing_emails}")

# Get company type distribution
types = (QueryBuilder()
    .select("type", "COUNT(*) as count")
    .from_table("companies") 
    .group_by("type")
    .execute())
```

### Batch Processing for Large Tables

```python
# Process in batches of 1000
offset = 0
batch_size = 1000

while True:
    batch = (QueryBuilder()
        .from_table("companies")
        .where("status = :status", status="active")
        .order_by("id")
        .limit(batch_size)
        .execute())
    
    if not batch:
        break
        
    # Process batch for HubSpot
    process_hubspot_batch(batch)
    offset += batch_size
```

## Error Handling

The package includes built-in error handling:

```python
try:
    companies = Company.find_all()
except Exception as e:
    print(f"Database error: {e}")
    # Handle error appropriately
```

## Performance Tips

1. **Use LIMIT** for large tables
2. **Add WHERE clauses** to filter data
3. **Use batch processing** for large migrations
4. **Check connection pooling** settings in `config.py`

## Troubleshooting

### Connection Issues
- Verify AWS RDS security groups allow your IP
- Check database credentials in `.env`
- Ensure SSL/TLS settings match your RDS configuration

### Query Issues
- Use `echo=True` in engine configuration for SQL debugging
- Check table and column names with `db.get_table_info()`
- Verify parameter names match query placeholders

## Next Steps

1. Fill in your database credentials in `.env`
2. Run `example_usage.py` to test everything
3. Customize model classes for your tables
4. Start building your HubSpot migration scripts

Need help? Check the examples in `example_usage.py` or contact your development team.