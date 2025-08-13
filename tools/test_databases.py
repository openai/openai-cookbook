#!/usr/bin/env python3
"""
Test to connect and find available databases.
"""

import sys
import os
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

def test_databases():
    """Connect and list available databases."""
    try:
        print("🔌 Testing database connection...")
        
        # Import database modules
        from database.connection import DatabaseConnection
        
        # Create connection
        db = DatabaseConnection()
        
        print("✅ Database connected successfully!")
        
        # List available databases
        print("\n📋 Getting available databases...")
        databases_query = "SHOW DATABASES"
        databases = db.execute_query(databases_query)
        
        print("Available databases:")
        for db_info in databases:
            db_name = list(db_info.values())[0]
            print(f"   - {db_name}")
        
        # Try to find tables in each database
        print("\n🔍 Looking for tables in each database...")
        
        for db_info in databases:
            db_name = list(db_info.values())[0]
            
            # Skip system databases
            if db_name.lower() in ['information_schema', 'performance_schema', 'mysql', 'sys']:
                continue
                
            print(f"\n📊 Checking database: {db_name}")
            
            try:
                # Get tables in this database
                tables_query = f"SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = '{db_name}'"
                tables = db.execute_query(tables_query)
                
                if tables:
                    table_names = [list(t.values())[0] for t in tables]
                    print(f"   Found {len(table_names)} tables")
                    
                    # Look for Empresa table
                    empresa_tables = [t for t in table_names if 'empresa' in t.lower()]
                    if empresa_tables:
                        print(f"   🎯 FOUND EMPRESA TABLES: {empresa_tables}")
                    
                    # Show first few tables
                    print(f"   First 10 tables: {table_names[:10]}")
                    
                else:
                    print(f"   No tables found")
                    
            except Exception as e:
                print(f"   ❌ Error accessing {db_name}: {e}")
        
        # Close connection
        db.close()
        print(f"\n🎉 Database exploration completed!")
        
    except Exception as e:
        print(f"\n❌ Error: {e}")
        print(f"Error type: {type(e).__name__}")
        return False
    
    return True

if __name__ == "__main__":
    print("🚀 Colppy Database Exploration")
    print("=" * 50)
    
    success = test_databases()
    
    if success:
        print("\n✅ Exploration completed!")
    else:
        print("\n❌ Exploration failed!")
        exit(1)