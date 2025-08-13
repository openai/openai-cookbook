#!/usr/bin/env python3
"""
Quick test to connect to the database and list the Empresa table.
"""

import sys
import os
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

def test_database_connection():
    """Test database connection and look for Empresa table."""
    try:
        print("🔌 Testing database connection...")
        
        # Import database modules
        from database.connection import DatabaseConnection
        
        # Create connection
        db = DatabaseConnection()
        
        print("✅ Database connected successfully!")
        
        # List all tables
        print("\n📋 Getting list of tables...")
        tables = db.list_tables()
        print(f"Found {len(tables)} tables total")
        
        # Look for Empresa table (case insensitive)
        empresa_tables = [t for t in tables if 'empresa' in t.lower()]
        
        if empresa_tables:
            print(f"\n🎯 Found Empresa-related tables: {empresa_tables}")
            
            # Get details of the first Empresa table
            empresa_table = empresa_tables[0]
            print(f"\n📊 Getting details for '{empresa_table}' table...")
            
            info = db.get_table_info(empresa_table)
            print(f"   - Table: {info['table_name']}")
            print(f"   - Total rows: {info['row_count']:,}")
            print(f"   - Columns: {len(info['columns'])}")
            
            print(f"\n📝 Column structure:")
            for col in info['columns'][:10]:  # Show first 10 columns
                print(f"   - {col['COLUMN_NAME']}: {col['DATA_TYPE']}")
            
            if len(info['columns']) > 10:
                print(f"   ... and {len(info['columns']) - 10} more columns")
            
            # Show sample data
            print(f"\n📄 Sample data (first 3 rows):")
            sample_data = db.fetch_table_data(empresa_table, limit=3)
            
            if sample_data:
                for i, row in enumerate(sample_data, 1):
                    print(f"   Row {i}: {dict(list(row.items())[:5])}...")  # Show first 5 columns
            else:
                print("   No data found in table")
                
        else:
            print(f"\n⚠️  No 'Empresa' table found.")
            print(f"📋 Available tables (first 20):")
            for table in tables[:20]:
                print(f"   - {table}")
            
            if len(tables) > 20:
                print(f"   ... and {len(tables) - 20} more tables")
        
        # Close connection
        db.close()
        print(f"\n🎉 Test completed successfully!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print(f"Error type: {type(e).__name__}")
        return False
    
    return True

if __name__ == "__main__":
    print("🚀 Colppy Database Connection Test")
    print("=" * 50)
    
    # Check environment file
    env_file = Path(".env")
    if not env_file.exists():
        print("❌ .env file not found!")
        exit(1)
    
    # Run test
    success = test_database_connection()
    
    if success:
        print("\n✅ All tests passed!")
    else:
        print("\n❌ Test failed!")
        exit(1)