#!/usr/bin/env python3
"""
Raw MySQL connection test to diagnose the exact issue.
"""

import pymysql
import sys

def test_raw_connection():
    """Test raw PyMySQL connection with detailed error reporting."""
    
    connection_configs = [
        {
            'host': 'colppydb-staging.colppy.com',
            'port': 3306,
            'user': 'juan_onetto',
            'password': 'GYxesM5B9Litn0',
            'charset': 'utf8mb4',
            'database': None  # Try without database first
        },
        {
            'host': 'colppydb-staging.colppy.com',
            'port': 3306,
            'user': 'juan_onetto',
            'password': 'GYxesM5B9Litn0',
            'charset': 'utf8mb4',
            'database': 'colppy'
        },
        {
            'host': 'colppydb-staging.colppy.com',
            'port': 3306,
            'user': 'juan_onetto',
            'password': 'GYxesM5B9Litn0',
            'charset': 'utf8mb4',
            'database': 'staging'
        }
    ]
    
    for i, config in enumerate(connection_configs, 1):
        print(f"\n🔌 Test {i}: Trying raw connection...")
        print(f"   Host: {config['host']}")
        print(f"   Port: {config['port']}")
        print(f"   User: {config['user']}")
        print(f"   Database: {config.get('database', 'None')}")
        
        try:
            # Try to connect
            connection = pymysql.connect(
                host=config['host'],
                port=config['port'],
                user=config['user'],
                password=config['password'],
                database=config.get('database'),
                charset=config['charset'],
                connect_timeout=30,
                read_timeout=30,
                write_timeout=30
            )
            
            print(f"   ✅ Connection successful!")
            
            # Try to execute a simple query
            with connection.cursor() as cursor:
                cursor.execute("SELECT VERSION()")
                version = cursor.fetchone()
                print(f"   📊 MySQL Version: {version[0]}")
                
                # Try to show databases
                cursor.execute("SHOW DATABASES")
                databases = cursor.fetchall()
                print(f"   📋 Found {len(databases)} databases:")
                for db in databases:
                    print(f"      - {db[0]}")
                
                # Look for databases with 'colppy' in the name
                colppy_dbs = [db[0] for db in databases if 'colppy' in db[0].lower()]
                if colppy_dbs:
                    print(f"   🎯 Colppy databases: {colppy_dbs}")
                    
                    # Try to connect to the first colppy database
                    target_db = colppy_dbs[0]
                    cursor.execute(f"USE {target_db}")
                    print(f"   ✅ Successfully switched to database: {target_db}")
                    
                    # Show tables
                    cursor.execute("SHOW TABLES")
                    tables = cursor.fetchall()
                    table_names = [t[0] for t in tables]
                    print(f"   📋 Found {len(table_names)} tables in {target_db}")
                    
                    # Look for Empresa table
                    empresa_tables = [t for t in table_names if 'empresa' in t.lower()]
                    if empresa_tables:
                        print(f"   🎉 FOUND EMPRESA TABLES: {empresa_tables}")
                        
                        # Show sample data from first Empresa table
                        empresa_table = empresa_tables[0]
                        cursor.execute(f"SELECT * FROM {empresa_table} LIMIT 3")
                        rows = cursor.fetchall()
                        
                        if rows:
                            print(f"   📄 Sample data from {empresa_table}:")
                            cursor.execute(f"DESCRIBE {empresa_table}")
                            columns = cursor.fetchall()
                            column_names = [col[0] for col in columns]
                            
                            for i, row in enumerate(rows, 1):
                                row_dict = dict(zip(column_names[:5], row[:5]))  # First 5 columns
                                print(f"      Row {i}: {row_dict}")
                    else:
                        print(f"   📋 Available tables: {table_names[:10]}...")
            
            connection.close()
            return True, target_db if 'colppy_dbs' in locals() and colppy_dbs else None
            
        except pymysql.Error as e:
            print(f"   ❌ MySQL Error: {e}")
            error_code = e.args[0] if e.args else 'Unknown'
            error_msg = e.args[1] if len(e.args) > 1 else str(e)
            
            if error_code == 1045:
                print(f"   🔑 Authentication failed - check username/password")
            elif error_code == 2003:
                print(f"   🌐 Cannot connect to host - check VPN/network")
            elif error_code == 1049:
                print(f"   📋 Database doesn't exist")
            else:
                print(f"   📋 Error code: {error_code}")
                print(f"   📋 Error message: {error_msg}")
                
        except Exception as e:
            print(f"   ❌ General Error: {e}")
    
    return False, None

if __name__ == "__main__":
    print("🚀 Raw MySQL Connection Test")
    print("=" * 50)
    
    success, db_name = test_raw_connection()
    
    if success:
        print(f"\n🎉 CONNECTION SUCCESSFUL!")
        if db_name:
            print(f"📝 Use this database name in your .env: DB_NAME={db_name}")
    else:
        print(f"\n❌ All connection attempts failed")
        print(f"\n🔧 Troubleshooting suggestions:")
        print(f"   1. Verify VPN is connected and working")
        print(f"   2. Check if database server allows connections from your IP")
        print(f"   3. Verify username and password are correct")
        print(f"   4. Ask your team for the correct database name and credentials")