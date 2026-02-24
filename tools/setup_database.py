#!/usr/bin/env python3
"""
Database setup and testing script for AWS MySQL connectivity.
Run this after configuring your .env file.
"""

import os
import sys
import subprocess
from pathlib import Path

def install_dependencies():
    """Install required Python packages."""
    print("📦 Installing database dependencies...")
    
    try:
        # Install packages
        subprocess.check_call([
            sys.executable, "-m", "pip", "install", 
            "sqlalchemy>=2.0.0", 
            "pymysql>=1.0.0", 
            "cryptography>=41.0.0"
        ])
        print("✅ Dependencies installed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Failed to install dependencies: {e}")
        return False

def check_env_file():
    """Check if .env file exists and has required variables."""
    env_path = Path(__file__).parent / ".env"
    
    if not env_path.exists():
        print("❌ .env file not found!")
        print("\nCreate tools/.env with your AWS MySQL credentials:")
        print("""
DB_HOST=your-aws-mysql-endpoint.rds.amazonaws.com
DB_PORT=3306
DB_NAME=your_database_name
DB_USER=your_username
DB_PASSWORD=your_password
DB_CHARSET=utf8mb4
DB_SSL_MODE=REQUIRED
ENVIRONMENT=development
        """)
        return False
    
    # Check required variables
    required_vars = ["DB_HOST", "DB_NAME", "DB_USER", "DB_PASSWORD"]
    
    with open(env_path) as f:
        env_content = f.read()
    
    missing_vars = []
    for var in required_vars:
        if f"{var}=" not in env_content or f"{var}=your_" in env_content:
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing or incomplete environment variables: {', '.join(missing_vars)}")
        print("Please update your .env file with actual database credentials.")
        return False
    
    print("✅ .env file looks good!")
    return True

def test_database_connection():
    """Test database connectivity."""
    print("🔌 Testing database connection...")
    
    try:
        # Add tools directory to Python path
        tools_path = Path(__file__).parent
        sys.path.insert(0, str(tools_path))
        
        # Import and test database
        from database.connection import get_db
        db = get_db()
        
        if db.test_connection():
            print("✅ Database connection successful!")
            
            # Get basic info
            tables = db.list_tables()
            print(f"📊 Found {len(tables)} tables in database")
            
            if tables:
                print("📋 Available tables:")
                for table in tables[:10]:  # Show first 10 tables
                    print(f"   - {table}")
                
                if len(tables) > 10:
                    print(f"   ... and {len(tables) - 10} more tables")
            
            return True
        else:
            print("❌ Database connection failed!")
            return False
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you've installed the dependencies.")
        return False
    except Exception as e:
        print(f"❌ Database connection error: {e}")
        print("\nPossible issues:")
        print("- Check your database credentials in .env")
        print("- Verify AWS RDS security groups allow your IP")
        print("- Ensure database server is running")
        return False

def run_example():
    """Run a simple database example."""
    print("🚀 Running database example...")
    
    try:
        # Add tools directory to Python path
        tools_path = Path(__file__).parent
        sys.path.insert(0, str(tools_path))
        
        from database.connection import get_db
        from database import QueryBuilder
        db = get_db()
        
        # Get first table and show sample data
        tables = db.list_tables()
        if tables:
            table_name = tables[0]
            print(f"📋 Sample data from '{table_name}' table:")
            
            # Get table info
            info = db.get_table_info(table_name)
            print(f"   Columns: {len(info['columns'])}")
            print(f"   Total rows: {info['row_count']:,}")
            
            # Show first few rows
            sample_data = db.fetch_table_data(table_name, limit=3)
            if sample_data:
                print("   Sample records:")
                for i, row in enumerate(sample_data, 1):
                    print(f"     {i}. {dict(list(row.items())[:3])}...")  # Show first 3 columns
            
            print("✅ Database example completed successfully!")
            return True
        else:
            print("⚠️  No tables found in database")
            return True
            
    except Exception as e:
        print(f"❌ Example failed: {e}")
        return False

def main():
    """Main setup function."""
    print("🛠️  AWS MySQL Database Setup for Colppy")
    print("=" * 50)
    
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    
    success = True
    
    # Step 1: Install dependencies
    if not install_dependencies():
        success = False
    
    print()
    
    # Step 2: Check environment file
    if not check_env_file():
        success = False
        print("\n⚠️  Setup incomplete. Please configure .env file first.")
        return
    
    print()
    
    # Step 3: Test database connection
    if not test_database_connection():
        success = False
    
    print()
    
    # Step 4: Run example
    if success:
        if not run_example():
            success = False
    
    print("\n" + "=" * 50)
    
    if success:
        print("🎉 Database setup completed successfully!")
        print("\nNext steps:")
        print("1. Check out database/example_usage.py for more examples")
        print("2. Customize models in database/models.py for your tables")
        print("3. Start building your HubSpot migration scripts")
        print("\n📖 Read database/README.md for detailed documentation")
    else:
        print("❌ Setup encountered issues. Please fix them and try again.")
    
    print()

if __name__ == "__main__":
    main()