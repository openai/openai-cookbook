# 🚀 Colppy Database Quick Start Guide

## ✅ SETUP COMPLETE!

Your AWS MySQL database connection is fully operational with 50,292+ companies ready for analysis and HubSpot migration.

## 🔗 Connection Details
- **Host**: colppydb-staging.colppy.com  
- **Database**: colppy
- **Table**: empresa (50,292 rows, 91 columns)
- **Migration Ready**: 26,291 companies with complete data

## 🏃‍♂️ Quick Examples

### 1. Simple Data Access
```python
from database.connection import DatabaseConnection
db = DatabaseConnection()

# Get companies
companies = db.fetch_table_data("empresa", "CUIT IS NOT NULL", limit=10)
```

### 2. Model-Based Access
```python
from database.models import BaseModel

class Empresa(BaseModel):
    table_name = 'empresa'
    primary_key = 'IdEmpresa'

# Get companies
companies = Empresa.find_all("localidad = 'CABA'", limit=100)
total = Empresa.count()
```

### 3. Complex Queries
```python
from database import QueryBuilder

results = (QueryBuilder()
    .select("Nombre", "CUIT", "localidad")
    .from_table("empresa")
    .where("CUIT IS NOT NULL AND localidad = :city", city="CABA")
    .order_by("Nombre")
    .limit(50)
    .execute())
```

### 4. HubSpot Migration Prep
```python
from database.query_builder import build_migration_query

# Map to HubSpot properties
mapping = {
    "IdEmpresa": "external_id",
    "Nombre": "name", 
    "CUIT": "cuit_number",
    "razonSocial": "legal_name",
    "domicilio": "address",
    "localidad": "city"
}

query = build_migration_query("empresa", mapping, 
    "CUIT IS NOT NULL AND Nombre IS NOT NULL")
hubspot_ready = query.execute()
```

## 🛠️ Direct MySQL Access
```bash
mysql -h colppydb-staging.colppy.com -u juan_onetto -p colppy
```

## 📊 Key Tables Discovered
- `empresa` - Main companies table (50,292 rows)
- `empresasHubspot` - HubSpot integration table  
- `empresasAmigrar` - Migration table
- `empresa_currency` - Currency settings
- `usuario_empresa` - User-company relationships

## 🎯 Ready for Company-Centric Transition!

You now have:
✅ **Database connectivity** - Fast, reliable connection  
✅ **Generic ODM** - Works with any table structure  
✅ **Query builder** - Complex operations made simple  
✅ **HubSpot helpers** - Migration-ready functions  
✅ **26,291 companies** - Ready for immediate migration  

## 🚀 Next Steps
1. **Explore data**: Use the examples above
2. **Build migration scripts**: Map Empresa → HubSpot Companies
3. **Analyze patterns**: Geographic, tax, industry insights
4. **Start transition**: Company-centric CRM migration

**Everything is ready for your company-centric transformation!** 🎉