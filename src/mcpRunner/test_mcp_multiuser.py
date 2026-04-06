import asyncio
import os
import sys

# Ensure the script's directory is in the path for local imports
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from mcp_google_client import MCPGoogleClient

# Search for .env in the script's directory OR one level up (root)
script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.dirname(os.path.dirname(script_dir))

# Try loading from script dir first, then root as fallback
load_dotenv(os.path.join(script_dir, ".env"))
if not os.getenv("GOOGLE_ACCESS_TOKEN"):
    load_dotenv(os.path.join(root_dir, ".env"))

# --- Configuration ---
# Update this with your hosted Cloud Run URL
MCP_URL = "https://workspace-mcp-181562945855.asia-southeast2.run.app/"

# IMPORTANT: You need a valid Google Access Token with the following scopes:
# - https://www.googleapis.com/auth/gmail.modify
# - https://www.googleapis.com/auth/calendar
# - https://www.googleapis.com/auth/contacts
# You can obtain one via OAuth Playground or your app's frontend.
GOOGLE_ACCESS_TOKEN = os.getenv("GOOGLE_ACCESS_TOKEN", "REPLACE_WITH_YOUR_TOKEN")

async def test_mcp_flow():
    if GOOGLE_ACCESS_TOKEN == "REPLACE_WITH_YOUR_TOKEN" or not GOOGLE_ACCESS_TOKEN:
        print("Error: GOOGLE_ACCESS_TOKEN is not set.")
        print("Please check your .env file in this directory.")
        return

    print(f"\n--- Initializing MCP Client (Token: {GOOGLE_ACCESS_TOKEN[:10]}...) ---")
    client = MCPGoogleClient(MCP_URL, GOOGLE_ACCESS_TOKEN)
    
    try:
        # 1. List available tools to verify authentication
        print("\nStep 1: Listing Tools (Verifying Auth)...")
        tools = await client.list_tools()
        tool_names = [t['name'] for t in tools]
        print(f"Success! Found {len(tools)} tools.\n")
        
        # 2. Test Gmail (Search unread messages)
        if "search_gmail_messages" in tool_names:
            print("\nStep 2: Testing Gmail (Searching unread)...")
            gmail_results = await client.call_tool("search_gmail_messages", {
                "query": "is:unread"
            })
            # Limit the output string length to keep console clean
            out_str = str(gmail_results)
            print(f"Gmail Results (truncated): {out_str[:300]}...\n")
        else:
            print("\nStep 2: Gmail tool not found in current tier.")

        # 3. Test Contacts (Search for a contact)
        if "search_contacts" in tool_names:
            print("\nStep 3: Testing Contacts (Searching for 'test')...")
            contact_results = await client.call_tool("search_contacts", {
                "query": "test"
            })
            out_str = str(contact_results)
            print(f"Contacts Results: {out_str[:300]}...\n")
        else:
            print("\nStep 3: Contacts tool not found.")

        # 4. Test Calendar (List upcoming events)
        if "get_events" in tool_names:
            print("\nStep 4: Testing Calendar (Getting events)...")
            calendar_results = await client.call_tool("get_events", {
                "calendar_id": "primary"
            })
            out_str = str(calendar_results)
            print(f"Calendar Results: {out_str[:300]}...\n")
        else:
            print("\nStep 4: Calendar tool get_events not found.")

        # 5. Test Calendar (Create event) 
        if "manage_event" in tool_names:
            from datetime import datetime, timedelta, timezone
            now = datetime.now(timezone.utc)
            start_time = (now + timedelta(minutes=5)).isoformat()
            end_time = (now + timedelta(minutes=35)).isoformat()
            
            print("\nStep 5: Testing Calendar (Creating test event)...")
            create_results = await client.call_tool("manage_event", {
                "action": "create",
                "summary": "MCP Test Event",
                "description": "This is a test event created by MCP",
                "start": start_time,
                "end": end_time
            })
            out_str = str(create_results)
            print(f"Calendar Create Results: {out_str[:300]}...\n")
        else:
            print("\nStep 5: Calendar tool create_event not found.")

    except Exception as e:
        print(f"\nError occurred: {e}")
    finally:
        print("\n--- Closing Client ---")
        await client.close()

if __name__ == "__main__":
    # Ensure src directory is in path if needed
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    asyncio.run(test_mcp_flow())