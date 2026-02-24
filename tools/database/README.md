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
from database import get_db

db = get_db()

# Execute direct SQL
empresas = db.execute_query(
    "SELECT IdEmpresa, Nombre, CUIT FROM empresa WHERE activa != 0 LIMIT 10"
)

# Fetch table data with filtering
active_empresas = db.fetch_table_data(
    "empresa",
    "activa != 0",
    limit=100
)
```

### Using Colppy Models

```python
from database import Empresa, Facturacion, Usuario, Plan

# Find empresa by ID (IdEmpresa = id_empresa in HubSpot)
empresa = Empresa.find_by_id(12345)

# Find by CUIT
empresa = Empresa.find_by_cuit("20123456789")

# Active empresas
empresas = Empresa.find_activas(limit=100)

# Facturacion by id_empresa
rows = Facturacion.find_by_id_empresa("12345")

# Count
total = Empresa.count()
activas = Empresa.count("activa != 0")
```

### Query Builder (Complex Queries)

```python
from database import QueryBuilder
from database.query_builder import JoinType

# Empresa + Plan join
results = (QueryBuilder()
    .select("e.IdEmpresa", "e.Nombre", "e.CUIT", "p.nombre as plan_nombre")
    .from_table("empresa e")
    .join("plan p", "e.idPlan = p.idPlan", join_type=JoinType.LEFT)
    .where("e.activa != 0")
    .limit(50)
    .execute())
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

## Colppy Schema

Models are pre-configured for Colppy MySQL: `Empresa`, `Facturacion`, `Usuario`, `UsuarioEmpresa`, `EmpresasHubspot`, `CrmMatch`, `Plan`.

Full schema: `tools/docs/COLPPY_MYSQL_SCHEMA.md`

## Common Operations

### Find Empresas for HubSpot Sync

```python
# Active empresas (id_empresa = IdEmpresa for HubSpot deals)
empresas = Empresa.find_activas(limit=500)

# By CUIT (matches customer_cuit in facturacion)
empresa = Empresa.find_by_cuit("20123456789")
```

### Analyze Data

```python
# Count by activa
total = Empresa.count()
activas = Empresa.count("activa != 0")

# Facturacion by id_empresa
rows = Facturacion.find_by_id_empresa("12345")
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