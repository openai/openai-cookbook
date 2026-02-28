#!/usr/bin/env python3
"""
Generate OAuth refresh token for Google Ads API using the secure loopback
redirect (InstalledAppFlow). This avoids the deprecated OOB flow.
"""
import os
import sys
from google_auth_oauthlib.flow import InstalledAppFlow

def main():
    print("Google Ads OAuth Refresh Token Generator")
    print("=" * 50)
    
    # Ask for the path to your downloaded OAuth client secret JSON file
    # (Desktop app credentials). Example:
    # /Users/youruser/Downloads/client_secret_XXXX.apps.googleusercontent.com.json
    client_secrets_path = input(
        "Enter the full path to your OAuth client secret JSON file: "
    ).strip()

    if not client_secrets_path or not os.path.exists(client_secrets_path):
        print("Error: Valid client secret JSON file path is required!")
        sys.exit(1)

    try:
        # Create the installed-app flow and launch a local server to capture the code
        flow = InstalledAppFlow.from_client_secrets_file(
            client_secrets_path,
            scopes=["https://www.googleapis.com/auth/adwords"],
        )

        # Opens browser; uses http://localhost:<port> loopback redirect (secure, supported)
        creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")

        print("\nSuccess! Your refresh token is:")
        print(creds.refresh_token)
        print("\nAdd this to your .env file as GOOGLE_ADS_REFRESH_TOKEN")
        
        # Optionally save to .env file
        save_to_env = input("\nWould you like to save this to .env file? (y/n): ").lower()
        if save_to_env == 'y':
            env_path = os.path.join(os.path.dirname(__file__), '.env')
            
            # Check if .env exists
            env_content = ""
            if os.path.exists(env_path):
                with open(env_path, 'r') as f:
                    env_content = f.read()
            
            # Update or append refresh token
            if 'GOOGLE_ADS_REFRESH_TOKEN=' in env_content:
                lines = env_content.split('\n')
                for i, line in enumerate(lines):
                    if line.startswith('GOOGLE_ADS_REFRESH_TOKEN='):
                        lines[i] = f'GOOGLE_ADS_REFRESH_TOKEN={creds.refresh_token}'
                        break
                env_content = '\n'.join(lines)
            else:
                if env_content and not env_content.endswith('\n'):
                    env_content += '\n'
                env_content += f'GOOGLE_ADS_REFRESH_TOKEN={creds.refresh_token}\n'
            
            with open(env_path, 'w') as f:
                f.write(env_content)
            
            print(f"Refresh token saved to {env_path}")
            
    except Exception as e:
        print(f"\nError: Failed to get refresh token - {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

