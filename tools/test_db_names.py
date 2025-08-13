#!/usr/bin/env python3
"""
Test different database names to find the correct one.
"""

import sys
import os
from pathlib import Path

# Add current directory to Python path
sys.path.insert(0, str(Path(__file__).parent))

def test_database_names():
    """Try different database names."""
    
    # Common database names to try
    db_names = [
        'colppy',
        'colppydb',
        'staging', 
        'production',
        'main',
        'database',
        'colppy_prod',
        'colppy_staging',
        'app',
        'mysql',
        ''  # Try without database name
    ]
    
    for db_name in db_names:
        try:
            print(f"\n🔌 Trying database: '{db_name}'")
            
            # Update environment for this test
            os.environ['DB_NAME'] = db_name
            
            # Reload config
            import importlib
            from database import config as config_module
            importlib.reload(config_module)
            
            # Try connection
            from database.connection import DatabaseConnection
            
            # Create new connection for this test
            test_db = DatabaseConnection()
            
            if test_db.test_connection():
                print(f"✅ Successfully connected to database: '{db_name}'!")
                
                # Try to list tables
                try:
                    tables = test_db.execute_query("SHOW TABLES")
                    table_names = [list(t.values())[0] for t in tables] if tables else []
                    
                    print(f"📋 Found {len(table_names)} tables")
                    
                    # Look for Empresa table
                    empresa_tables = [t for t in table_names if 'empresa' in t.lower()]
                    if empresa_tables:
                        print(f"🎯 FOUND EMPRESA TABLES: {empresa_tables}")
                        
                        # Show sample data from first Empresa table
                        empresa_table = empresa_tables[0]
                        print(f"\n📊 Sample data from '{empresa_table}':")
                        sample = test_db.execute_query(f"SELECT * FROM {empresa_table} LIMIT 3")
                        
                        if sample:
                            for i, row in enumerate(sample, 1):
                                print(f"   Row {i}: {dict(list(row.items())[:5])}...")
                        
                        return db_name, empresa_tables
                    else:
                        print(f"📋 Available tables: {table_names[:10]}...")
                        
                except Exception as e:
                    print(f"⚠️  Could list connection but error getting tables: {e}")
                
                test_db.close()
                
            else:
                print(f"❌ Connection test failed for '{db_name}'")
                
        except Exception as e:
            error_msg = str(e)
            if "Access denied" in error_msg:
                print(f"❌ Access denied for database '{db_name}'")
            elif "Unknown database" in error_msg:
                print(f"❌ Database '{db_name}' does not exist")
            else:
                print(f"❌ Error with '{db_name}': {error_msg}")
    
    print(f"\n❌ Could not connect to any database with the given credentials")
    return None, []

if __name__ == "__main__":
    print("🚀 Testing Different Database Names")
    print("=" * 50)
    
    db_name, empresa_tables = test_database_names()
    
    if db_name is not None:
        print(f"\n🎉 SUCCESS!")
        print(f"   Database name: '{db_name}'")
        print(f"   Empresa tables: {empresa_tables}")
        print(f"\n📝 Update your .env file with: DB_NAME={db_name}")
    else:
        print(f"\n❌ No database connection successful")
        print(f"Please verify:")
        print(f"   - VPN is connected")
        print(f"   - Database credentials are correct")
        print(f"   - Database server is accessible")