"""
Example usage of the database package for AWS MySQL.
Shows how to use it for data migration to HubSpot.
"""

from database import DatabaseConnection, BaseModel, QueryBuilder
from database.models import Company, User, Account
from database.query_builder import build_migration_query, find_records_for_migration

def example_basic_usage():
    """Basic database operations example."""
    
    # Get database connection (automatically initialized)
    from database.connection import db
    
    # Test connection
    print("Testing database connection...")
    if db.test_connection():
        print("✅ Database connected successfully!")
    
    # List all tables
    print("\nAvailable tables:")
    tables = db.list_tables()
    for table in tables:
        print(f"  - {table}")
    
    # Get table information
    if tables:
        table_name = tables[0]
        info = db.get_table_info(table_name)
        print(f"\nTable '{table_name}' info:")
        print(f"  Rows: {info['row_count']}")
        print(f"  Columns: {len(info['columns'])}")

def example_simple_queries():
    """Simple query examples."""
    
    from database.connection import db
    
    # Execute direct SQL query
    print("\nExecuting simple query...")
    results = db.execute_query("SELECT COUNT(*) as total FROM companies")
    print(f"Total companies: {results[0]['total']}")
    
    # Fetch table data with filtering
    print("\nFetching filtered data...")
    active_companies = db.fetch_table_data(
        "companies", 
        "status = :status", 
        {"status": "active"},
        limit=10
    )
    print(f"Found {len(active_companies)} active companies")

def example_model_usage():
    """Model-based operations example."""
    
    # Find all active companies
    print("\nUsing models...")
    companies = Company.find_active_companies()
    print(f"Active companies: {len(companies)}")
    
    # Find company by ID
    if companies:
        company = Company.find_by_id(companies[0].get_id())
        print(f"Company: {company}")
        print(f"Company data: {company.to_dict()}")
    
    # Find user by email
    user = User.find_by_email("admin@colppy.com")
    if user:
        print(f"Found user: {user}")
    
    # Count records
    total_users = User.count()
    active_users = User.count("status = :status", {"status": "active"})
    print(f"Total users: {total_users}, Active: {active_users}")

def example_query_builder():
    """Query builder examples."""
    
    print("\nUsing Query Builder...")
    
    # Simple query
    builder = QueryBuilder()
    results = (builder
               .select("id", "name", "email", "created_at")
               .from_table("companies")
               .where("status = :status AND type = :type", status="active", type="SMB")
               .order_by("created_at", "DESC")
               .limit(10)
               .execute())
    
    print(f"Query builder results: {len(results)} records")
    
    # Complex query with joins
    complex_results = (QueryBuilder()
                      .select("c.name as company_name", "u.email", "COUNT(a.id) as account_count")
                      .from_table("companies c")
                      .join("users u", "c.id = u.company_id")
                      .join("accounts a", "c.id = a.company_id")
                      .where("c.status = :status", status="active")
                      .group_by("c.id", "c.name", "u.email")
                      .having("COUNT(a.id) > :min_accounts", min_accounts=0)
                      .order_by("account_count", "DESC")
                      .limit(20)
                      .execute())
    
    print(f"Complex query results: {len(complex_results)} records")

def example_hubspot_migration():
    """Example of preparing data for HubSpot migration."""
    
    print("\nPreparing data for HubSpot migration...")
    
    # Map database columns to HubSpot properties
    company_mapping = {
        "id": "external_id",
        "name": "name",
        "email": "domain",
        "type": "industry",
        "created_at": "createdate",
        "phone": "phone",
        "website": "website"
    }
    
    # Build migration query
    migration_query = build_migration_query(
        "companies", 
        company_mapping,
        "status = :status AND created_at > :date",
        status="active",
        date="2024-01-01"
    )
    
    # Get data for migration
    companies_for_hubspot = migration_query.execute()
    print(f"Companies ready for HubSpot: {len(companies_for_hubspot)}")
    
    # Find new records since last sync
    new_records = find_records_for_migration(
        "companies",
        last_sync_date="2025-01-15",
        batch_size=500
    )
    print(f"New records since last sync: {len(new_records)}")
    
    # Show first record structure
    if companies_for_hubspot:
        print("\nSample record for HubSpot:")
        print(companies_for_hubspot[0])

def example_data_analysis():
    """Example of data analysis for company insights."""
    
    print("\nData analysis examples...")
    
    # Company type distribution
    company_types = (QueryBuilder()
                    .select("type", "COUNT(*) as count")
                    .from_table("companies")
                    .where("status = :status", status="active")
                    .group_by("type")
                    .order_by("count", "DESC")
                    .execute())
    
    print("Company type distribution:")
    for row in company_types:
        print(f"  {row['type']}: {row['count']}")
    
    # Monthly growth analysis
    monthly_growth = (QueryBuilder()
                     .select("DATE_FORMAT(created_at, '%Y-%m') as month", "COUNT(*) as new_companies")
                     .from_table("companies")
                     .where("created_at >= :start_date", start_date="2024-01-01")
                     .group_by("month")
                     .order_by("month", "ASC")
                     .execute())
    
    print("\nMonthly company growth:")
    for row in monthly_growth:
        print(f"  {row['month']}: {row['new_companies']} new companies")

if __name__ == "__main__":
    """
    Run examples. Make sure to:
    1. Create .env file with your database credentials
    2. Install dependencies: pip install -r requirements.txt
    3. Update model classes to match your actual database schema
    """
    
    try:
        # Run examples
        example_basic_usage()
        example_simple_queries()
        example_model_usage()
        example_query_builder()
        example_hubspot_migration()
        example_data_analysis()
        
        print("\n🚀 All examples completed successfully!")
        
    except Exception as e:
        print(f"❌ Error running examples: {e}")
        print("Make sure your .env file is configured with correct database credentials.")