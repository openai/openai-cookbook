#!/usr/bin/env python3
"""
Debug Conversation Structure
Examine how labels/tags are stored in Intercom conversations
"""

import os
import json
import asyncio
import aiohttp
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables from root
load_dotenv(dotenv_path='/Users/virulana/openai-cookbook/.env')

INTERCOM_ACCESS_TOKEN = os.getenv('INTERCOM_ACCESS_TOKEN')
if not INTERCOM_ACCESS_TOKEN:
    raise ValueError("INTERCOM_ACCESS_TOKEN not found in environment variables.")

async def debug_conversation_structure():
    """Debug the structure of conversations to understand labels"""
    headers = {
        'Authorization': f'Bearer {INTERCOM_ACCESS_TOKEN}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'Intercom-Version': '2.13'
    }
    
    # Get a few conversations from Friday
    from_timestamp = int(datetime.fromisoformat("2025-08-29").timestamp())
    to_timestamp = int(datetime.fromisoformat("2025-08-29T23:59:59").timestamp())
    
    search_query = {
        "query": {
            "operator": "AND",
            "value": [
                {
                    "field": "created_at",
                    "operator": ">=",
                    "value": from_timestamp
                },
                {
                    "field": "created_at",
                    "operator": "<=",
                    "value": to_timestamp
                }
            ]
        },
        "pagination": {
            "per_page": 5  # Just get 5 for debugging
        }
    }
    
    async with aiohttp.ClientSession() as session:
        try:
            # Get conversation list
            response = await session.post(
                f"https://api.intercom.io/conversations/search",
                headers=headers,
                json=search_query,
                timeout=30
            )
            
            if response.status == 200:
                data = await response.json()
                conversations = data.get('conversations', [])
                
                print(f"🔍 Found {len(conversations)} conversations for debugging")
                
                # Examine first conversation in detail
                if conversations:
                    conv_id = conversations[0]['id']
                    print(f"\n📋 Examining conversation {conv_id}...")
                    
                    # Get detailed conversation
                    detail_response = await session.get(
                        f"https://api.intercom.io/conversations/{conv_id}",
                        headers=headers,
                        timeout=30
                    )
                    
                    if detail_response.status == 200:
                        conv_detail = await detail_response.json()
                        
                        print(f"\n📊 CONVERSATION STRUCTURE:")
                        print("=" * 50)
                        
                        # Print all top-level keys
                        print(f"Top-level keys: {list(conv_detail.keys())}")
                        
                        # Check for tags
                        if 'tags' in conv_detail:
                            print(f"\n🏷️ Tags structure:")
                            print(json.dumps(conv_detail['tags'], indent=2))
                        
                        # Check for conversation_parts
                        if 'conversation_parts' in conv_detail:
                            print(f"\n💬 Conversation parts structure:")
                            parts = conv_detail['conversation_parts']
                            if 'conversation_parts' in parts and parts['conversation_parts']:
                                first_part = parts['conversation_parts'][0]
                                print(f"First part keys: {list(first_part.keys())}")
                                if 'tags' in first_part:
                                    print(f"Part tags: {json.dumps(first_part['tags'], indent=2)}")
                        
                        # Check for admin assignee
                        if 'admin_assignee_id' in conv_detail:
                            print(f"\n👤 Admin assignee ID: {conv_detail['admin_assignee_id']}")
                        
                        # Check for source
                        if 'source' in conv_detail:
                            print(f"\n📝 Source structure:")
                            source = conv_detail['source']
                            print(f"Source keys: {list(source.keys())}")
                            if 'author' in source:
                                print(f"Author: {json.dumps(source['author'], indent=2)}")
                        
                        # Save full structure to file for examination
                        with open('/tmp/conversation_structure.json', 'w') as f:
                            json.dump(conv_detail, f, indent=2)
                        print(f"\n💾 Full structure saved to /tmp/conversation_structure.json")
                        
                    else:
                        print(f"❌ Error getting conversation details: {detail_response.status}")
                        
            else:
                print(f"❌ Error searching conversations: {response.status}")
                
        except Exception as e:
            print(f"❌ Error: {e}")

if __name__ == "__main__":
    asyncio.run(debug_conversation_structure())
