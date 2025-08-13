#!/usr/bin/env python3
"""
Setup script for AFIP CUIT Lookup Service credentials
Helps configure TusFacturas.app API credentials safely
"""

import os
import getpass
from pathlib import Path


def create_env_file():
    """Create a .env file with AFIP API credentials"""
    
    print("AFIP CUIT Lookup Service - Credential Setup")
    print("==========================================")
    print()
    print("This script will help you configure your TusFacturas.app API credentials.")
    print("You can obtain these credentials from: https://www.tusfacturas.app/")
    print()
    print("IMPORTANT: You need a production account with ARCA linkage.")
    print("This service is NOT available in DEV plans.")
    print()
    
    # Get credentials from user
    print("Please enter your TusFacturas.app credentials:")
    print()
    
    apikey = getpass.getpass("API Key: ").strip()
    if not apikey:
        print("Error: API Key is required")
        return False
    
    usertoken = getpass.getpass("User Token: ").strip()
    if not usertoken:
        print("Error: User Token is required")
        return False
    
    apitoken = getpass.getpass("API Token: ").strip()
    if not apitoken:
        print("Error: API Token is required")
        return False
    
    # Optional HubSpot credentials
    print()
    print("Optional: HubSpot API credentials (press Enter to skip)")
    hubspot_key = getpass.getpass("HubSpot API Key (optional): ").strip()
    
    # Determine where to save the .env file
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    env_file_path = project_root / '.env'
    
    print()
    print(f"Saving credentials to: {env_file_path}")
    
    # Check if .env file already exists
    if env_file_path.exists():
        overwrite = input("A .env file already exists. Overwrite? (y/N): ").strip().lower()
        if overwrite != 'y':
            print("Setup cancelled.")
            return False
    
    # Create .env file content
    env_content = f"""# TusFacturas.app API Credentials
# Obtain these from: https://www.tusfacturas.app/
TUSFACTURAS_API_KEY="{apikey}"
TUSFACTURAS_USER_TOKEN="{usertoken}"
TUSFACTURAS_API_TOKEN="{apitoken}"

"""
    
    if hubspot_key:
        env_content += f"""# HubSpot API Credentials (optional)
HUBSPOT_API_KEY="{hubspot_key}"

"""
    
    env_content += """# Other environment variables can be added here
# Example:
# DATABASE_URL="your_database_url"
"""
    
    try:
        # Write the .env file
        with open(env_file_path, 'w') as f:
            f.write(env_content)
        
        # Set restrictive permissions
        os.chmod(env_file_path, 0o600)
        
        print()
        print("✅ Credentials saved successfully!")
        print(f"📁 File location: {env_file_path}")
        print()
        print("Next steps:")
        print("1. Test the setup by running: python afip_cuit_lookup.py")
        print("2. Make sure .env is in your .gitignore file")
        print("3. Never commit credentials to version control")
        print()
        
        return True
        
    except Exception as e:
        print(f"Error saving credentials: {e}")
        return False


def test_credentials():
    """Test the configured credentials"""
    
    print("Testing AFIP API credentials...")
    print()
    
    try:
        # Import and test the service
        from afip_cuit_lookup import AFIPCUITLookupService
        
        service = AFIPCUITLookupService()
        print("✅ Credentials loaded successfully")
        
        # Test with a known CUIT (this is a public test CUIT)
        test_cuit = "30712293841"  # Example public CUIT
        print(f"🔍 Testing lookup with CUIT: {test_cuit}")
        
        result = service.lookup_cuit(test_cuit)
        
        if result and not result.error:
            print("✅ API test successful!")
            print(f"   Company: {result.razon_social}")
            print(f"   Status: {result.estado}")
            print(f"   Tax Condition: {result.condicion_impositiva}")
        elif result and result.error:
            print("⚠️  API responded but with errors:")
            for error in result.errores:
                print(f"   - {error}")
        else:
            print("❌ API test failed - no response received")
            
    except ImportError as e:
        print(f"❌ Import error: {e}")
        print("Make sure you're running this from the correct directory")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        print()
        print("Common issues:")
        print("- Invalid credentials")
        print("- Account not linked with ARCA") 
        print("- Using DEV plan (production account required)")
        print("- Network connectivity issues")


def check_gitignore():
    """Check if .env is properly ignored by git"""
    
    script_dir = Path(__file__).parent
    project_root = script_dir.parent.parent
    gitignore_path = project_root / '.gitignore'
    
    if not gitignore_path.exists():
        print("⚠️  Warning: No .gitignore file found")
        print("   Consider creating one to protect your credentials")
        return False
    
    try:
        with open(gitignore_path, 'r') as f:
            gitignore_content = f.read()
        
        if '.env' in gitignore_content:
            print("✅ .env file is properly ignored by git")
            return True
        else:
            print("⚠️  Warning: .env is not in .gitignore")
            print("   Add '.env' to your .gitignore file to protect credentials")
            return False
            
    except Exception as e:
        print(f"Could not check .gitignore: {e}")
        return False


def main():
    """Main setup function"""
    
    try:
        while True:
            print()
            print("AFIP CUIT Lookup Service Setup")
            print("==============================")
            print()
            print("1. Configure API credentials")
            print("2. Test current credentials") 
            print("3. Check .gitignore configuration")
            print("4. Exit")
            print()
            
            choice = input("Select an option (1-4): ").strip()
            
            if choice == '1':
                create_env_file()
            elif choice == '2':
                test_credentials()
            elif choice == '3':
                check_gitignore()
            elif choice == '4':
                print("Setup complete. ¡Buena suerte!")
                break
            else:
                print("Invalid option. Please select 1-4.")
                
    except KeyboardInterrupt:
        print("\nSetup cancelled by user.")
    except Exception as e:
        print(f"Setup error: {e}")


if __name__ == "__main__":
    main()